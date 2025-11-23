"""
FastAPI Application - 单职责：API层
提供交易接口和数据Mock接口（统一接口，对Strategy Agent透明）
统一使用UTC时区
"""
import logging
from typing import Dict, Any, Optional
from datetime import datetime, timezone
from app.utils.time_utils import utc_timestamp, parse_utc_datetime, ensure_utc

from fastapi import FastAPI, HTTPException

from app.models import (
    PlaceOrderRequest,
    ModifyOrderRequest,
    CancelOrderRequest,
    VirtualOrder,
)
from app.backtest_runner import BacktestRunner
from app.config import settings

logger = logging.getLogger(__name__)
app = FastAPI(title="Virtual Exchange API (Backtest System)")

# 全局回测运行器（单例模式）
backtest_runner: Optional[BacktestRunner] = None


def get_runner() -> BacktestRunner:
    """获取或创建回测运行器"""
    global backtest_runner
    if backtest_runner is None:
        backtest_runner = BacktestRunner()
    return backtest_runner


# ========== 交易接口（与HyperliquidExchange保持一致） ==========

@app.post("/exchange/order")
async def place_order(order: PlaceOrderRequest) -> Dict[str, Any]:
    """
    Place order - 下单接口
    返回格式与HyperliquidExchange保持一致
    """
    try:
        runner = get_runner()
        engine = runner.get_engine()
        wallet = runner.get_wallet()
        
        # 构建pair（coin -> pair）
        pair = f"{order.coin}USDT"
        
        # 生成订单ID
        txid = f"order_{int(utc_timestamp() * 1000)}"
        
        # 确定订单类型
        ordertype = "market" if order.limit_px == 0 else "limit"
        
        # 创建虚拟订单
        virtual_order = VirtualOrder(
            txid=txid,
            pair=pair,
            type="buy" if order.is_buy else "sell",
            ordertype=ordertype,
            volume=order.sz,
            status="open",
            userref=int(utc_timestamp() * 1000) % 1000000,  # 简化：使用时间戳作为userref
            price=order.limit_px if order.limit_px > 0 else None,
            created_at=utc_timestamp(),
            stop_loss=order.stop_loss,
            take_profit=order.take_profit
        )
        
        # 检查余额
        current_price = runner.get_current_price(pair) or 0.0
        if not wallet.can_place_order(virtual_order, current_price):
            return {
                "status": "err",
                "response": "Insufficient balance"
            }
        
        # 添加到撮合引擎
        engine.add_order(virtual_order)
        
        # 扣款
        wallet.place_order(virtual_order, current_price)
        
        # 返回格式与Hyperliquid保持一致
        return {
            "status": "ok",
            "response": {
                "data": {
                    "statuses": [{
                        "resting": {
                            "oid": hash(txid) % 1000000000  # 简化：生成一个数字oid
                        }
                    }]
                }
            }
        }
        
    except Exception as e:
        logger.error(f"Order placement failed: {e}")
        return {"status": "err", "response": str(e)}


@app.post("/exchange/cancel")
async def cancel_order(req: CancelOrderRequest) -> Dict[str, Any]:
    """
    Cancel order - 取消订单接口
    返回格式与HyperliquidExchange保持一致
    """
    try:
        runner = get_runner()
        engine = runner.get_engine()
        wallet = runner.get_wallet()
        
        # 通过oid查找订单（简化：需要维护oid->txid映射，这里先简化）
        # 实际应该维护一个映射表
        order = None
        for txid, o in engine.orders.items():
            if hash(txid) % 1000000000 == req.oid:
                order = o
                break
        
        if not order:
            return {
                "status": "err",
                "response": "Order not found"
            }
        
        # 取消订单
        order.status = "canceled"
        order.canceled_at = utc_timestamp()
        order.canceled_reason = "User canceled"
        
        # 退款
        current_price = runner.get_current_price(order.pair) or 0.0
        wallet.cancel_order(order, current_price)
        
        # 从引擎移除
        engine.remove_order(order.txid)

        return {
            "status": "ok",
            "response": {"data": "Order canceled"}
        }
        
    except Exception as e:
        logger.error(f"Order cancellation failed: {e}")
        return {"status": "err", "response": str(e)}


@app.post("/exchange/modify")
async def modify_order(req: ModifyOrderRequest) -> Dict[str, Any]:
    """
    Modify order - 修改订单接口
    返回格式与HyperliquidExchange保持一致
    """
    try:
        runner = get_runner()
        engine = runner.get_engine()
        
        # 通过oid查找订单
        order = None
        for txid, o in engine.orders.items():
            if hash(txid) % 1000000000 == req.oid:
                order = o
                break
        
        if not order:
            return {
                "status": "err",
                "response": "Order not found"
            }
        
        # 修改订单
        order.volume = req.sz
        order.price = req.limit_px
        order.type = "buy" if req.is_buy else "sell"
        
        return {
            "status": "ok",
            "response": {"data": "Order modified"}
        }
        
    except Exception as e:
        logger.error(f"Order modification failed: {e}")
        return {"status": "err", "response": str(e)}


@app.post("/info")
async def get_info(req: Dict[str, Any]) -> Dict[str, Any]:
    """
    Info endpoint - 账户信息接口
    返回格式与HyperliquidExchange保持一致
    """
    req_type = req.get("type")
    
    if req_type == "metaAndAssetCtxs":
        # 返回universe信息（简化）
        return {
            "universe": [
                {"name": "BTC", "szDecimals": 5, "maxLeverage": 50},
                {"name": "ETH", "szDecimals": 4, "maxLeverage": 50},
                {"name": "XBT", "szDecimals": 5, "maxLeverage": 50},
            ]
        }
        
    if req_type == "clearinghouseState":
        # 返回账户状态
        runner = get_runner()
        wallet = runner.get_wallet()
        engine = runner.get_engine()
        
        # 计算账户价值
        current_prices = {}
        for order in engine.get_open_orders():
            if order.pair not in current_prices:
                current_prices[order.pair] = runner.get_current_price(order.pair) or 0.0
        
        account_value = wallet.get_account_value(current_prices)
        
        # 构建openOrders
        open_orders = []
        for order in engine.get_open_orders():
                open_orders.append({
                "oid": hash(order.txid) % 1000000000,
                "coin": order.pair.replace("USDT", ""),
                "side": "B" if order.type == "buy" else "A",
                "limitPx": str(order.price or "0"),
                "sz": str(order.volume),
                "timestamp": int(order.created_at * 1000)
                })

        return {
            "marginSummary": {
                "accountValue": str(account_value),
                "totalMarginUsed": "0.0"
            },
            "crossMarginSummary": {
                "accountValue": str(account_value)
            },
            "assetPositions": [],
            "openOrders": open_orders
        }
        
    return {"status": "err", "response": "Unknown info type"}


# ========== 数据Mock接口（Mock DataCollector） ==========

@app.get("/gpt-latest/{symbol}")
async def get_gpt_data(symbol: str) -> Dict[str, Any]:
    """
    Mock DataCollector的/gpt-latest/{symbol}接口
    根据当前回测时间点返回历史数据
    """
    runner = get_runner()
    current_price = runner.get_current_price(symbol) or 0.0
    
    # 简化：返回基本结构（实际应该从K线数据计算指标）
    return {
        "symbol": symbol,
        "common_info": {
            "ticker": {
                "last_price": current_price,
                "best_ask_price": current_price * 1.0001,  # 简化
                "best_bid_price": current_price * 0.9999,  # 简化
                "volume_24h": 0.0,
                "high_24h": current_price * 1.01,  # 简化
                "low_24h": current_price * 0.99  # 简化
            },
            "order_book": {
                "top_ask_price": current_price * 1.0001,
                "top_ask_volume": 0.0,
                "top_bid_price": current_price * 0.9999,
                "top_bid_volume": 0.0,
                "total_bid_volume": 0.0,
                "total_ask_volume": 0.0,
                "bid_ask_volume_ratio": 1.0,
                "spread": current_price * 0.0002
            },
            "recent_trades": {
                "recent_buy_count": 0,
                "recent_sell_count": 0,
                "total_buy_volume_trades": 0.0,
                "total_sell_volume_trades": 0.0,
                "buy_sell_volume_ratio": 1.0
            }
        },
        "intervals_data": {
            "1": {  # 1分钟数据
                "ohlc": {
                    "open": current_price,
                    "high": current_price * 1.01,
                    "low": current_price * 0.99,
                    "close": current_price,
                    "volume": 0.0
                },
                "indicators": {
                    "ema_9": current_price,
                    "sma_14": current_price,
                    "rsi": 50.0,
                    "macd_line": 0.0,
                    "macd_signal": 0.0,
                    "macd_hist": 0.0,
                    "bollinger_upper": current_price * 1.02,
                    "bollinger_middle": current_price,
                    "bollinger_lower": current_price * 0.98,
                    "atr": current_price * 0.01
                }
            }
        }
    }


# ========== 回测接口（可选，用于手动触发） ==========

@app.post("/backtest/run")
async def run_backtest(req: Dict[str, Any]) -> Dict[str, Any]:
    """
    手动触发回测（可选功能）
    
    Payload:
    {
        "symbol": "BTCUSDT",
        "timeframe": "1m",
        "start_time": "2024-01-01T00:00:00Z",
        "end_time": "2024-01-07T23:59:59Z",
        "orders": [...]  # 可选：初始订单列表
    }
    """
    try:
        symbol = req.get("symbol", "BTCUSDT")
        timeframe = req.get("timeframe", "1m")
        # 解析时间并确保为UTC
        start_time_str = req.get("start_time", "2024-01-01T00:00:00Z")
        end_time_str = req.get("end_time", "2024-01-07T23:59:59Z")
        start_time = parse_utc_datetime(start_time_str) or ensure_utc(datetime.fromisoformat(start_time_str.replace("Z", "+00:00")))
        end_time = parse_utc_datetime(end_time_str) or ensure_utc(datetime.fromisoformat(end_time_str.replace("Z", "+00:00")))
        
        # 创建新的回测运行器
        runner = BacktestRunner()
        
        # 如果有初始订单，转换为VirtualOrder
        orders = []
        if "orders" in req:
            for o in req["orders"]:
                orders.append(VirtualOrder(**o))
        
        # 执行回测
        report = runner.run(orders, symbol, timeframe, start_time, end_time)
        
        return {
            "status": "ok",
            "response": report.model_dump()
        }
        
    except Exception as e:
        logger.error(f"Backtest failed: {e}")
        return {"status": "err", "response": str(e)}
