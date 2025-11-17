import asyncio
import time
from typing import Dict, Any, Optional
import logging

from app.virtual_exchange import virtual_exch
from app.config import settings
from app.ledger import ledger_instance as ledger
from app.models import (
    TradePlan, TradeLedgerEntry, TradeStatus,
    AddOrderRequest, AmendOrderRequest, CancelOrderRequest,
    OrderSide, OrderType, TakeProfitTarget,
)
from app.services import (
    add_order_service,
    amend_order_service,
    cancel_order_service,
)
from app.utils.tp_utils import normalize_take_profits_with_min_notional

def _normalize_take_profits(original: list[TakeProfitTarget]) -> list[TakeProfitTarget]:
    """确保恰好两个 TP，百分比之和为 100。
    - 若只有一个：补齐第二个为 (100 - p1)
    - 若多于两个：仅取前两个，并按比例缩放到和为 100
    - 若两者和不为 100：按比例缩放
    """
    tps = list(original or [])
    if not tps:
        return [
            TakeProfitTarget(price=0.0, percentage_to_sell=50.0, is_hit=False),
            TakeProfitTarget(price=0.0, percentage_to_sell=50.0, is_hit=False),
        ]
    if len(tps) == 1:
        p1 = tps[0].percentage_to_sell
        p2 = max(0.0, 100.0 - p1)
        # 复制第一档价格作为兜底，实际业务应要求上游提供两个价格
        tps.append(TakeProfitTarget(price=tps[0].price, percentage_to_sell=p2, is_hit=False))
    if len(tps) > 2:
        tps = tps[:2]
    total = (tps[0].percentage_to_sell or 0.0) + (tps[1].percentage_to_sell or 0.0)
    if abs(total - 100.0) > 1e-9 and total > 0:
        scale = 100.0 / total
        tps[0].percentage_to_sell *= scale
        tps[1].percentage_to_sell *= scale
    return tps

# 虚拟交易所：提供 get_ticker 兼容接口
kraken = virtual_exch
logger = logging.getLogger(__name__)


async def run_trade(plan_dict: Dict[str, Any]) -> None:
    logger.info(f"[TASK] run_trade START symbol={plan_dict.get('symbol')} side={plan_dict.get('side')} size={plan_dict.get('position_size')} sl={plan_dict.get('stop_loss_price')} trade_id={plan_dict.get('trade_id')}")
    # 多仓：plan_dict 包含 trade_id
    plan = TradePlan.model_validate(plan_dict)
    # 规范化 TP：确保两档且合计 100，并应用“单个 TP 名义额 < 阈值则只挂 TP1”规则
    try:
        normalized_tps = normalize_take_profits_with_min_notional(
            original=plan.take_profits,
            position_size=plan.position_size,
            min_notional_usd=settings.TP_MIN_NOTIONAL_USD,
        )
    except Exception:
        # 兜底：使用原先的两档比例规范化
        normalized_tps = _normalize_take_profits(plan.take_profits)
    trade_id = str(plan_dict.get("trade_id"))
    # 确保统一的 userref（若上游未提供，则在此确定一个并贯穿所有订单）
    plan_userref = plan.userref if plan.userref is not None else int(time.time())
    # 用规范化后的 TP 写入台账
    ledger_entry = TradeLedgerEntry(
        **(plan.model_dump() | {
            "take_profits": [tp.model_dump() for tp in normalized_tps],
            "userref": plan_userref,
        }),
        trade_id=trade_id,
        remaining_size=plan.position_size
    )
    ledger.write_trade(ledger_entry)

    try:
        # 1) 主订单（按 TradePlan 入场细节）+ 条件平仓止损（随主单成交自动触发）
        main_order_payload = AddOrderRequest(
            pair=plan.symbol,
            type=plan.side,
            ordertype=plan.entry_ordertype,
            price=str(plan.entry_price) if plan.entry_ordertype != OrderType.market else None,
            price2=str(plan.entry_price2) if plan.entry_price2 is not None else None,
            volume=str(plan.position_size),
            oflags=plan.oflags,
            timeinforce=plan.timeinforce,
            trigger=plan.trigger,
            close_ordertype=OrderType.stop_loss,
            close_price=str(plan.stop_loss_price),
            userref=plan_userref,
        )
        logger.info(f"[TASK] Placing main {plan.entry_ordertype.value} order symbol={plan.symbol} vol={plan.position_size}")
        entry_txid = await add_order_service(main_order_payload)
        logger.info(f"[TASK] Main order placed symbol={plan.symbol} entry_txid={entry_txid}")

        # 立即写入 entry_txid，便于上游通过 open_orders 标记 'entry' 角色
        def _set_entry_txid(trade: TradeLedgerEntry):
            trade.entry_txid = entry_txid
            return trade
        ledger.update_trade_by_id_atomically(trade_id, _set_entry_txid)

        # 市价单：通常即时成交，可等待 closed 确认并转 ACTIVE；限价单：不等待，由 WS 事件推动
        if plan.entry_ordertype == OrderType.market:
            if not await wait_for_order_closed(entry_txid):
                raise Exception(f"Main order {entry_txid} did not close in time.")
            logger.info(f"[TASK] Main order confirmed closed symbol={plan.symbol} entry_txid={entry_txid}")

            def update_after_fill(trade: TradeLedgerEntry):
                trade.status = TradeStatus.ACTIVE
                return trade
            ledger.update_trade_atomically(plan.symbol, update_after_fill)

            # 市价单直接启动监控
            asyncio.create_task(monitor_trade(trade_id))

    except Exception as exc:
        logger.info(f"[TASK] CRITICAL ERROR during trade setup symbol={plan.symbol} err={exc}")
        def _fail_close(t: TradeLedgerEntry):
            t.status = TradeStatus.CLOSED
            return t
        ledger.update_trade_atomically(plan.symbol, _fail_close)


async def monitor_trade(trade_id: str) -> None:
    logger.info(f"[TASK] MONITOR START trade_id={trade_id}")

    while True:
        try:
            current_trade = ledger.get_trade_by_id(trade_id)
            if not current_trade or current_trade.status not in [TradeStatus.ACTIVE, TradeStatus.TP1_HIT]:
                logger.info(f"[TASK] MONITOR STOP trade_id={trade_id} reason=closed_or_cancelled")
                break

            # 公共 Ticker：使用新的统一返回结构
            ticker = await kraken.get_ticker({"pair": current_trade.symbol})
            if ticker.get("error"):
                raise Exception(f"Ticker error: {ticker['error']}")
            live_price = float(ticker["result"]["c"][0])  # 收盘价 'c'[0]
            # 也可使用 ticker["pair_key"]、ticker["altname"] 做日志/核对
            logger.info(f"[TASK] Live symbol={current_trade.symbol} trade_id={trade_id} price={live_price:.2f} status={current_trade.status}")

            # 检查 TP1
            if current_trade.status == TradeStatus.ACTIVE and live_price >= current_trade.take_profits[0].price:
                await execute_tp1_logic(current_trade)
                await asyncio.sleep(1.0)
                continue

            # 检查 TP2（最终平仓）
            if len(current_trade.take_profits) > 1 and not current_trade.take_profits[1].is_hit and live_price >= current_trade.take_profits[1].price:
                await execute_final_tp_logic(current_trade)
                break

            # 停止使用 REST 轮询止损状态，等待 WS 驱动的等待函数判定

            await asyncio.sleep(settings.MONITOR_TICKER_INTERVAL_SEC)

        except Exception as exc:
            logger.info(f"[TASK] MONITOR ERROR trade_id={trade_id} err={exc}. Retrying in {settings.MONITOR_ERROR_RETRY_SEC}s...")
            await asyncio.sleep(settings.MONITOR_ERROR_RETRY_SEC)


async def cancel_trade(trade_id: str, stop_loss_txid: Optional[str] = None) -> None:
    logger.info(f"[TASK] CANCEL REQUEST trade_id={trade_id} stop_loss_txid={stop_loss_txid}")

    def _mark_closing(t: TradeLedgerEntry):
        t.status = TradeStatus.CLOSING
        return t
    # 兼容：通过 symbol 原子更新第一笔；这里我们改为直接精确删除
    trade = ledger.get_trade_by_id(trade_id)
    if trade:
        def _mark_closing(t: TradeLedgerEntry):
            t.status = TradeStatus.CLOSING
            return t
        ledger.update_trade_atomically(trade.symbol, _mark_closing)

    try:
        if stop_loss_txid:
            await cancel_order_service(CancelOrderRequest(txid=stop_loss_txid))
            logger.info(f"[TASK] CancelOrder sent trade_id={trade_id} stop_loss_txid={stop_loss_txid}")
            canceled = await wait_for_order_canceled_or_closed(stop_loss_txid)
            logger.info(f"[TASK] stop_loss order canceled_or_closed trade_id={trade_id} confirmed={canceled}")

        def _mark_closed(t: TradeLedgerEntry):
            t.status = TradeStatus.CLOSED
            return t
        if trade:
            ledger.update_trade_atomically(trade.symbol, _mark_closed)
            ledger.delete_trade_by_id(trade_id)
            logger.info(f"[TASK] Ledger cleaned symbol={trade.symbol} trade_id={trade_id} CLOSED")

    except Exception as exc:
        logger.info(f"[TASK] ERROR during cancel_trade trade_id={trade_id} err={exc}")
        def _force_close(t: TradeLedgerEntry):
            t.status = TradeStatus.CLOSED
            return t
        if trade:
            ledger.update_trade_atomically(trade.symbol, _force_close)
            ledger.delete_trade_by_id(trade_id)


async def execute_tp1_logic(trade: TradeLedgerEntry):
    logger.info(f"[TASK] TP1 HIT symbol={trade.symbol} trade_id={trade.trade_id}")

    tp1_target = trade.take_profits[0]
    size_to_sell = trade.position_size * (tp1_target.percentage_to_sell / 100.0)
    remaining_qty = trade.position_size - size_to_sell

    amend_req = AmendOrderRequest(txid=trade.stop_loss_txid, order_qty=str(remaining_qty))
    await amend_order_service(amend_req)

    ok = await wait_for_order_amended(trade.stop_loss_txid, str(remaining_qty))
    if not ok:
        raise Exception(f"Amend SL order {trade.stop_loss_txid} failed.")
    logger.info(f"[{trade.symbol}] SL order amended successfully.")

    sell_req = AddOrderRequest(
        pair=trade.symbol,
        type=OrderSide.sell,
        ordertype=OrderType.market,
        volume=str(size_to_sell),
        userref=getattr(trade, "userref", None),
    )
    await add_order_service(sell_req)

    def _do_tp1_update(t: TradeLedgerEntry):
        t.status = TradeStatus.TP1_HIT
        t.take_profits[0].is_hit = True
        t.remaining_size -= size_to_sell
        return t

    ledger.update_trade_atomically(trade.symbol, _do_tp1_update)

    # 若仅有一个 TP 或者第一档已全仓卖出，则直接收尾：撤掉 SL 并清理台账
    if len(trade.take_profits) < 2 or remaining_qty <= 1e-12:
        try:
            if trade.stop_loss_txid:
                await cancel_order_service(CancelOrderRequest(txid=trade.stop_loss_txid))
        finally:
            ledger.delete_trade_by_id(trade.trade_id)
            logger.info(f"[TASK] Trade fully closed after TP1 symbol={trade.symbol} trade_id={trade.trade_id}")


async def execute_final_tp_logic(trade: TradeLedgerEntry):
    logger.info(f"[TASK] FINAL TP HIT symbol={trade.symbol} trade_id={trade.trade_id}")

    await cancel_order_service(CancelOrderRequest(txid=trade.stop_loss_txid))

    sell_req = AddOrderRequest(
        pair=trade.symbol,
        type=OrderSide.sell,
        ordertype=OrderType.market,
        volume=str(trade.remaining_size),
        userref=getattr(trade, "userref", None),
    )
    await add_order_service(sell_req)

    ledger.delete_trade_by_id(trade.trade_id)


async def amend_order_task(amend_dict: Dict[str, Any]) -> None:
    """异步改单任务：供执行器调用。"""
    req = AmendOrderRequest.model_validate(amend_dict)
    await amend_order_service(req)


async def wait_for_order_closed(txid: str, timeout_seconds: int | None = None) -> bool:
    """基于 Redis 事件流的等待：由 VirtualExchange 将每个订单状态广播到 kraken:orders:{txid} Stream。
    这里消费该 Stream，直到看到 closed/canceled 或超时。"""
    from app.utils.redis_utils import new_redis, xread_block
    r = new_redis()
    key = f"{settings.ORDER_EVENT_STREAM_PREFIX}{txid}"
    start_time = time.time()
    timeout_seconds = timeout_seconds or settings.ORDER_CLOSED_TIMEOUT_SEC
    last_id = "0-0"
    while time.time() - start_time < timeout_seconds:
        resp = xread_block(r, key, last_id, block_ms=settings.ORDER_WAIT_BLOCK_MS, count=1)
        if resp:
            _, entries = resp[0]
            for entry_id, fields in entries:
                last_id = entry_id
                status = (fields.get("status") or "").lower()
                if status in {"closed", "canceled"}:
                    return True
        await asyncio.sleep(settings.ORDER_WAIT_POLL_SLEEP_SEC)
    return False


async def wait_for_order_amended(txid: str, expected_vol: str, timeout_seconds: int | None = None) -> bool:
    from app.utils.redis_utils import new_redis, xread_block
    r = new_redis()
    key = f"{settings.ORDER_EVENT_STREAM_PREFIX}{txid}"
    start_time = time.time()
    timeout_seconds = timeout_seconds or settings.ORDER_AMEND_TIMEOUT_SEC
    last_id = "0-0"
    while time.time() - start_time < timeout_seconds:
        resp = xread_block(r, key, last_id, block_ms=settings.ORDER_WAIT_BLOCK_MS, count=1)
        if resp:
            _, entries = resp[0]
            for entry_id, fields in entries:
                last_id = entry_id
                vol = fields.get("vol")
                status = (fields.get("status") or "").lower()
                if vol == expected_vol or status in {"closed", "canceled"}:
                    return True
        await asyncio.sleep(settings.ORDER_WAIT_POLL_SLEEP_SEC)
    return False


async def wait_for_order_canceled_or_closed(txid: str, timeout_seconds: int | None = None) -> bool:
    from app.utils.redis_utils import new_redis, xread_block
    r = new_redis()
    key = f"{settings.ORDER_EVENT_STREAM_PREFIX}{txid}"
    start_time = time.time()
    timeout_seconds = timeout_seconds or settings.ORDER_CANCEL_TIMEOUT_SEC
    last_id = "0-0"
    while time.time() - start_time < timeout_seconds:
        resp = xread_block(r, key, last_id, block_ms=settings.ORDER_WAIT_BLOCK_MS, count=1)
        if resp:
            _, entries = resp[0]
            for entry_id, fields in entries:
                last_id = entry_id
                status = (fields.get("status") or "").lower()
                if status in {"closed", "canceled"}:
                    return True
        await asyncio.sleep(settings.ORDER_WAIT_POLL_SLEEP_SEC)
    return False


def check_and_restart_monitors():
    # 纯 asyncio 版本如需守护可由外部调度器调用；此处留空或日志提示
    logger.info("[TASK] check_and_restart_monitors noop in asyncio mode")
