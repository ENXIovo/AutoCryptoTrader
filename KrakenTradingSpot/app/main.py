# app/main.py
from fastapi import FastAPI, HTTPException
from app import tasks, ledger
from app.models import TradePlan, TradeStatus

app = FastAPI(title="Kraken Trading Service")

@app.post("/trades/execute", status_code=202)
def execute_trade_endpoint(plan: TradePlan):
    """
    接收一个完整的交易计划，并派发一个Celery任务来异步执行和监控。
    """
    # 检查是否已有同symbol的活跃交易
    existing_trade = ledger.get_trade(plan.symbol)
    if existing_trade and existing_trade.status not in [TradeStatus.CLOSED]:
        raise HTTPException(
            status_code=409, 
            detail=f"An active trade for {plan.symbol} already exists."
        )

    # 派发主任务
    tasks.execute_and_monitor_trade.delay(plan.model_dump())
    return {"message": "Trade execution and monitoring task has been dispatched.", "plan": plan}

@app.post("/trades/cancel", status_code=200)
def cancel_trade_endpoint(symbol: str):
    """
    手动终止对某个交易的监控并尝试取消其挂单。
    """
    trade = ledger.get_trade(symbol)
    if not trade or not trade.stop_loss_txid:
        raise HTTPException(status_code=404, detail=f"No active trade or stop-loss order found for {symbol}.")
    
    # 派发取消任务
    tasks.cancel_trade_task.delay(symbol, trade.stop_loss_txid)
    return {"message": f"Cancellation task for {symbol} has been dispatched."}

# 周期性任务的启动器 (如果你使用Celery Beat)
@app.on_event("startup")
async def startup_event():
    # 可以在这里触发一个周期性任务来检查所有监控是否正常
    print("Kraken Trading Service has started.")