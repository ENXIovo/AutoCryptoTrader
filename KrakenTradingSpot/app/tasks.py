# app/tasks.py
from celery import Celery
from celery.schedules import crontab
import time
from typing import Dict, Any

from app.config import settings
from app.kraken_client import KrakenClient
from app.ledger import ledger_instance as ledger
from app.models import (
    TradePlan, TradeLedgerEntry, TradeStatus,
    AddOrderRequest, AmendOrderRequest,
    OrderSide, OrderType
)

# --- 1. Celery实例配置 ---
# 完全按照你的风格，在tasks.py中直接配置
celery_app = Celery(
    "kraken_trading_tasks",
    broker=settings.CELERY_BROKER_URL,
    backend=settings.CELERY_RESULT_BACKEND,
)

# --- 2. Celery Beat 守护任务配置 ---
# 这是保证系统鲁棒性的核心
celery_app.conf.beat_schedule = {
    "check-and-restart-monitors-every-minute": {
        "task": "app.tasks.check_and_restart_monitors", # 指向我们新的守护任务
        "schedule": crontab(minute="*"),  # 每分钟检查一次
    },
}
celery_app.conf.timezone = "UTC"

# --- 3. 客户端单例 ---
# 确保在Celery Worker进程中只有一个KrakenClient实例
kraken = KrakenClient()


# --- 核心任务一：执行与启动监控 (已优化) ---
@celery_app.task(bind=True)
def execute_and_monitor_trade(self, plan_dict: Dict[str, Any]):
    """
    接收交易计划，负责下单、挂止损，并启动持续监控。
    """
    plan = TradePlan.model_validate(plan_dict)
    ledger_entry = TradeLedgerEntry(**plan.model_dump(), remaining_size=plan.position_size)
    ledger.write_trade(ledger_entry)

    try:
        # 伪代码: 假设你有一个查询订单状态的函数
        # 你需要在 kraken_client.py 中实现它
        # async def query_orders(self, txid: str) -> dict:
        #     return await self._post("/private/QueryOrders", {"txid": txid})

        # 1. 下主订单 (市价单)
        main_order_payload = AddOrderRequest(
            pair=plan.symbol, type=plan.side, ordertype=OrderType.market, volume=str(plan.position_size)
        )
        entry_txid = kraken.add_order(main_order_payload.model_dump(exclude_none=True))
        print(f"[{plan.symbol}] Main order placed. TXID: {entry_txid}")

        # [RELIABILITY] 轮询确认市价单成交，取代 time.sleep()
        if not wait_for_order_closed(entry_txid):
             raise Exception(f"Main order {entry_txid} did not close in time.")
        print(f"[{plan.symbol}] Main order confirmed closed.")

        # 2. 下止损单
        sl_order_payload = AddOrderRequest(
            pair=plan.symbol,
            type=OrderSide.sell if plan.side == OrderSide.buy else OrderSide.buy,
            ordertype=OrderType.stop_loss,
            price=str(plan.stop_loss_price),
            volume=str(plan.position_size)
        )
        sl_txid = kraken.add_order(sl_order_payload.model_dump(exclude_none=True))
        print(f"[{plan.symbol}] Stop-loss order placed. TXID: {sl_txid}")

        # 3. 原子性更新台账
        def update_after_fill(trade: TradeLedgerEntry):
            trade.status = TradeStatus.ACTIVE
            trade.entry_txid = entry_txid
            trade.stop_loss_txid = sl_txid
            return trade
        ledger.update_trade_atomically(plan.symbol, update_after_fill)

        # 4. 启动持续监控
        monitor_single_trade.delay(plan.symbol)

    except Exception as exc:
        print(f"CRITICAL ERROR during trade setup for {plan.symbol}: {exc}")
        # 在这里添加告警逻辑，例如发送邮件或Telegram消息
        ledger.update_trade_atomically(plan.symbol, lambda t: t.status == TradeStatus.CLOSED)


# --- 核心任务二：持续监控 (已优化) ---
@celery_app.task(bind=True, max_retries=None)
def monitor_single_trade(self, symbol: str):
    """一个独立的、只负责监控一个交易对的循环任务。"""
    print(f"MONITORING STARTED for {symbol}")

    while True:
        try:
            current_trade = ledger.get_trade(symbol)
            if not current_trade or current_trade.status not in [TradeStatus.ACTIVE, TradeStatus.TP1_HIT]:
                print(f"Stopping monitor for {symbol}: Trade closed or cancelled.")
                break

            live_price = float(kraken.get_ticker({"pair": symbol})[symbol]['c'][0])
            print(f"[{symbol}] Live: {live_price:.2f} | Status: {current_trade.status}")

            # 检查TP1
            if current_trade.status == TradeStatus.ACTIVE and live_price >= current_trade.take_profits[0].price:
                execute_tp1_logic(current_trade)
                continue

            # 检查TP2
            if len(current_trade.take_profits) > 1 and not current_trade.take_profits[1].is_hit and live_price >= current_trade.take_profits[1].price:
                execute_final_tp_logic(current_trade)
                break # 交易结束，退出循环

            time.sleep(1) # 正常监控循环间隔

        except Exception as exc:
            print(f"Error in monitor loop for {symbol}: {exc}. Retrying...")
            # 在这里添加告警逻辑
            time.sleep(10) # 发生错误时等待更长时间

# --- 逻辑拆分，使主任务更清晰 ---
def execute_tp1_logic(trade: TradeLedgerEntry):
    """封装并执行TP1的原子逻辑"""
    print(f"TP1 HIT for {trade.symbol}")
    
    def _do_tp1(t: TradeLedgerEntry):
        tp1_target = t.take_profits[0]
        size_to_sell = t.position_size * (tp1_target.percentage_to_sell / 100.0)
        remaining_qty = t.position_size - size_to_sell

        # a. 修改止损单
        amend_req = AmendOrderRequest(txid=t.stop_loss_txid, order_qty=str(remaining_qty))
        kraken.amend_order(amend_req.model_dump(exclude_none=True))
        
        # [RELIABILITY] 轮询确认修改成功
        if not wait_for_order_amended(t.stop_loss_txid, str(remaining_qty)):
            raise Exception(f"Amend SL order {t.stop_loss_txid} failed.")
        print(f"[{t.symbol}] SL order amended successfully.")

        # b. 市价卖出部分
        sell_req = AddOrderRequest(pair=t.symbol, type=OrderSide.sell, ordertype=OrderType.market, volume=str(size_to_sell))
        kraken.add_order(sell_req.model_dump(exclude_none=True))
        
        # c. 更新台账模型
        t.status = TradeStatus.TP1_HIT
        t.take_profits[0].is_hit = True
        t.remaining_size -= size_to_sell
        return t

    ledger.update_trade_atomically(trade.symbol, _do_tp1)


def execute_final_tp_logic(trade: TradeLedgerEntry):
    """执行最终平仓逻辑"""
    print(f"Final TP HIT for {trade.symbol}")
    kraken.cancel_order({"txid": trade.stop_loss_txid})
    
    sell_req = AddOrderRequest(
        pair=trade.symbol, type=OrderSide.sell, ordertype=OrderType.market, volume=str(trade.remaining_size)
    )
    kraken.add_order(sell_req.model_dump(exclude_none=True))
    
    ledger.delete_trade(trade.symbol)


# --- 新增的可靠性辅助函数 ---
def wait_for_order_closed(txid: str, timeout_seconds: int = 60) -> bool:
    """轮询直到订单状态为'closed'。"""
    start_time = time.time()
    while time.time() - start_time < timeout_seconds:
        # 你需要实现 kraken.query_orders 方法
        order_info = kraken.query_orders({"txid": txid})
        if order_info and order_info.get(txid, {}).get("status") == "closed":
            return True
        time.sleep(0.5)
    return False


def wait_for_order_amended(txid: str, expected_vol: str, timeout_seconds: int = 30) -> bool:
    """轮询直到订单数量被成功修改。"""
    start_time = time.time()
    while time.time() - start_time < timeout_seconds:
        order_info = kraken.query_orders({"txid": txid})
        if order_info and order_info.get(txid, {}).get("vol") == expected_vol:
            return True
        time.sleep(0.5)
    return False


# --- 新增的Celery Beat守护任务 ---
@celery_app.task
def check_and_restart_monitors():
    """一个周期性任务，用于发现并重启丢失的监控任务。"""
    print("BEAT: Checking for lost monitors...")
    active_symbols = ledger.get_all_active_symbols()
    inspector = celery_app.control.inspect()
    active_tasks = inspector.active()

    if not active_tasks: # 如果没有worker在运行
        return

    currently_monitored_symbols = {
        eval(task['args'])[0]
        for worker_tasks in active_tasks.values()
        for task in worker_tasks
        if task.get('name') == 'app.tasks.monitor_single_trade'
    }
    
    for symbol in active_symbols:
        if symbol not in currently_monitored_symbols:
            print(f"BEAT: Restarting lost monitor for {symbol}!")
            monitor_single_trade.delay(symbol)