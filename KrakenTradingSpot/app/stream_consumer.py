import time
import json
import redis
import asyncio
import logging
import os

from app.config import settings
from app.ledger import ledger_instance as ledger
from app.models import StreamMessage, StreamAction, TradeLedgerEntry, TradeStatus, AddOrderRequest, AmendOrderRequest, CancelOrderRequest
from app.tasks import run_trade, cancel_trade, amend_order_task, wait_for_order_canceled_or_closed
from app.services import cancel_order_service
from app.utils.redis_utils import new_redis, ensure_group, xreadgroup, xack, xautoclaim_stale
from app.utils.async_utils import ensure_background_event_loop, submit_coro
from app.utils.tp_utils import normalize_take_profits_with_min_notional

logger = logging.getLogger(__name__)


def main() -> None:
    # Ensure background asyncio loop is running for task execution
    ensure_background_event_loop()
    client = new_redis()
    stream = settings.REDIS_STREAM_KEY
    group = settings.REDIS_STREAM_GROUP
    # 动态消费者命名：与 news_labeler 保持一致风格，便于多副本与 PEL 接管
    consumer = f"{settings.REDIS_STREAM_CONSUMER}-{os.getpid()}"

    # news_labeler 风格：确保组存在（从最新 $ 开始），并认领陈旧 pending
    ensure_group(client)
    try:
        reclaimed = 0
        for message_id, fields in xautoclaim_stale(
            client, group=group, consumer=consumer, min_idle_ms=settings.STREAM_PENDING_MIN_IDLE_MS, batch=settings.STREAM_PENDING_CLAIM_BATCH
        ):
            try:
                data = _parse_stream_fields(fields)
                req_id = data.get("request_id")
                logger.info(f"[STREAM] Reclaimed pending id={message_id} req={req_id}")
                sm = StreamMessage.model_validate(_coerce_stream_message(data))
                _process(sm, req_id)
                xack(client, group, message_id)
                reclaimed += 1
            except Exception as e:
                logger.info(f"[STREAM] Error processing reclaimed {message_id}: {e} payload={fields}")
        if reclaimed:
            logger.info(f"[STREAM] Reclaimed pending count={reclaimed}")
    except Exception as _reclaim_err:
        logger.info(f"[STREAM] Pending reclaim error: {_reclaim_err}")

    while True:
        try:
            resp = xreadgroup(client, group, consumer, count=settings.STREAM_READ_COUNT, block_ms=settings.STREAM_READ_BLOCK_MS)
            if not resp:
                continue
            _, messages = resp[0]
            for message_id, fields in messages:
                try:
                    data = _parse_stream_fields(fields)
                    req_id = data.get("request_id")
                    logger.info(f"[STREAM] Received message id={message_id} req={req_id} fields_keys={list((fields or {}).keys())}")
                    sm = StreamMessage.model_validate(_coerce_stream_message(data))
                    _process(sm, req_id)
                    xack(client, group, message_id)
                    logger.info(f"[STREAM] ACKed message id={message_id} req={req_id}")
                except Exception as e:
                    logger.info(f"[STREAM] Error processing {message_id}: {e} payload={fields}")
        except Exception as loop_err:
            logger.info(f"[STREAM] Loop error: {loop_err}")
            time.sleep(1)


def _lock_key(userref: int | None) -> str:
    prefix = settings.LOCK_KEY_PREFIX
    return f"{prefix}{userref}" if userref is not None else f"{prefix}default"


def _with_userref_lock(client: redis.Redis, userref: int | None, fn) -> None:
    key = _lock_key(userref)
    # 简易分布式锁：SET NX，带过期
    token = str(time.time())
    acquired = client.set(key, token, nx=True, ex=settings.LOCK_TTL_SEC)
    if not acquired:
        # 自旋等待片刻再试，避免同一组并发乱序（避免递归导致潜在栈溢出）
        time.sleep(settings.LOCK_RETRY_SLEEP_SEC)
        return _with_userref_lock(client, userref, fn)
    try:
        logger.info(f"[STREAM] Acquired lock key={key}")
        fn()
    finally:
        # 释放锁（简化实现；生产可使用 Lua 保证释放安全）
        try:
            if client.get(key) == token:
                client.delete(key)
                logger.info(f"[STREAM] Released lock key={key}")
        except Exception:
            pass


def _process(sm: StreamMessage, request_id: str | None) -> None:
    client = new_redis()
    loop = ensure_background_event_loop()
    def _exec():
        logger.info(f"[STREAM] Processing action={sm.action} symbol={sm.symbol} order_id={sm.order_id} trade_id={sm.trade_id} userref={sm.userref} req={request_id}")
        if sm.action == StreamAction.add:
            if not sm.plan:
                raise ValueError("add requires plan")
            trade_id = str(int(time.time() * 1000))
            payload = sm.plan.model_dump() if hasattr(sm.plan, "model_dump") else sm.plan
            payload["trade_id"] = trade_id
            payload.setdefault("userref", sm.userref or int(time.time()))
            logger.info(f"[STREAM] ADD plan received req={request_id} trade_id={trade_id} symbol={payload.get('symbol')} side={payload.get('side')} size={payload.get('position_size')} sl={payload.get('stop_loss_price')}")
            _ = AddOrderRequest.model_validate({
                "pair": payload["symbol"],
                "type": payload["side"],
                "ordertype": "market",
                "volume": str(payload["position_size"]),
                "userref": payload["userref"],
            })
            # submit to background event loop (non-blocking)
            submit_coro(loop, run_trade(payload))
            logger.info(f"[STREAM] Scheduled run_trade req={request_id} trade_id={trade_id}")
            return

        if sm.action == StreamAction.cancel:
            # 优先使用 Kraken order_id (txid) 直接撤单；否则退回内部 trade_id 逻辑
            if sm.order_id:
                # 直接按 txid 撤单，并在确认后按规则清理台账
                async def _cancel_and_maybe_cleanup(order_id: str) -> None:
                    try:
                        await cancel_order_service(CancelOrderRequest(txid=order_id))
                        _ = await wait_for_order_canceled_or_closed(order_id)
                    except Exception:
                        pass
                    # 关联台账
                    trade = None
                    canceled_role = None
                    for t in ledger.get_all_trades():
                        if getattr(t, "entry_txid", None) == order_id:
                            trade = t
                            canceled_role = "entry"
                            break
                        if getattr(t, "stop_loss_txid", None) == order_id:
                            trade = t
                            canceled_role = "stop_loss"
                            break
                    if not trade:
                        return
                    # 更新绑定 txid
                    if canceled_role == "entry":
                        def _upd_entry(tr: TradeLedgerEntry):
                            tr.entry_txid = None
                            return tr
                        ledger.update_trade_by_id_atomically(trade.trade_id, _upd_entry)
                    elif canceled_role == "stop_loss":
                        def _upd_sl(tr: TradeLedgerEntry):
                            tr.stop_loss_txid = None
                            return tr
                        ledger.update_trade_by_id_atomically(trade.trade_id, _upd_sl)

                    # 清理规则：
                    # - 若取消的是止损且 remaining_size == 0 → 直接 CLOSED 并删除
                    # - 或两类 txid 均为空（没有任何 open 订单）且状态为 PENDING/ACTIVE/TP1_HIT → 关闭并删除
                    t2 = ledger.get_trade_by_id(trade.trade_id)
                    if not t2:
                        return
                    should_close = False
                    if canceled_role == "stop_loss" and (getattr(t2, "remaining_size", 0.0) or 0.0) <= 1e-12:
                        should_close = True
                    if (getattr(t2, "entry_txid", None) in (None, "")) and (getattr(t2, "stop_loss_txid", None) in (None, "")):
                        should_close = True
                    if should_close:
                        def _mark_closed(tr: TradeLedgerEntry):
                            tr.status = TradeStatus.CLOSED
                            return tr
                        ledger.update_trade_by_id_atomically(trade.trade_id, _mark_closed)
                        ledger.delete_trade_by_id(trade.trade_id)

                submit_coro(loop, _cancel_and_maybe_cleanup(sm.order_id))
                logger.info(f"[STREAM] Scheduled direct cancel by order_id with cleanup req={request_id} order_id={sm.order_id}")
                return
            if sm.trade_id:
                trade = ledger.get_trade_by_id(sm.trade_id)
                stop_loss_txid = trade.stop_loss_txid if trade else None
                submit_coro(loop, cancel_trade(sm.trade_id, stop_loss_txid))
                logger.info(f"[STREAM] Scheduled cancel_trade req={request_id} trade_id={sm.trade_id} sl_txid={stop_loss_txid}")
                return
            raise ValueError("cancel requires order_id or trade_id")

        if sm.action == StreamAction.amend:
            # 1) 直接改交易所订单 + 同步更新台账（四项可一次性修改）
            if sm.order_id:
                # 先尝试找关联台账（entry 或 SL），便于同时更新 SL/TP 到台账
                linked_trade = None
                for t in ledger.get_all_trades():
                    if t.entry_txid == sm.order_id or t.stop_loss_txid == sm.order_id:
                        linked_trade = t
                        break

                # 入场价（仅限未成交限价单）
                if sm.new_entry_price is not None:
                    submit_coro(
                        loop,
                        amend_order_task(
                            AmendOrderRequest(
                                txid=sm.order_id,
                                limit_price=str(sm.new_entry_price)
                            ).model_dump()
                        )
                    )
                    logger.info(f"[STREAM] Direct amend entry price req={request_id} order_id={sm.order_id} new_entry={sm.new_entry_price}")

                # 止损触发价：若 order_id 正是 SL 单 → 直改交易所；否则仅更新台账（入场未成阶段）
                if sm.new_stop_loss_price is not None:
                    if linked_trade and linked_trade.stop_loss_txid == sm.order_id:
                        submit_coro(
                            loop,
                            amend_order_task(
                                AmendOrderRequest(
                                    txid=sm.order_id,
                                    trigger_price=str(sm.new_stop_loss_price)
                                ).model_dump()
                            )
                        )
                        logger.info(f"[STREAM] Direct amend stop-loss req={request_id} order_id={sm.order_id} new_sl={sm.new_stop_loss_price}")
                    # 同步更新台账（无论是否直改了交易所），确保后续重挂或展示一致
                    if linked_trade:
                        def _upd_sl(tr: TradeLedgerEntry):
                            tr.stop_loss_price = float(sm.new_stop_loss_price)
                            return tr
                        ledger.update_trade_by_id_atomically(linked_trade.trade_id, _upd_sl)

                # TP1/TP2：仅更新台账价格
                if linked_trade and any(v is not None for v in [sm.new_tp1_price, sm.new_tp2_price]):
                    def _upd_tp(tr: TradeLedgerEntry):
                        # 舍弃 TP2：若只提供 new_tp2_price 且当前只有一个 TP，则忽略新增第二档
                        if sm.new_tp1_price is not None and len(tr.take_profits) >= 1:
                            tr.take_profits[0].price = float(sm.new_tp1_price)
                        if sm.new_tp2_price is not None and len(tr.take_profits) >= 2:
                            tr.take_profits[1].price = float(sm.new_tp2_price)
                        return tr
                    ledger.update_trade_by_id_atomically(linked_trade.trade_id, _upd_tp)
                    logger.info(f"[STREAM] Updated ledger TP via order_id req={request_id} trade_id={linked_trade.trade_id} tp1={sm.new_tp1_price} tp2={sm.new_tp2_price}")

                # 若本次请求同时带了 trade_id，则无论是否找到 linked_trade，仍对指定 trade_id 做一次台账更新（保证一键改四项）
                if sm.trade_id:
                    def _upd_all(tr: TradeLedgerEntry):
                        # entry 价仅在 PENDING 时更新
                        if sm.new_entry_price is not None and tr.status == TradeStatus.PENDING:
                            tr.entry_price = float(sm.new_entry_price)
                        if sm.new_stop_loss_price is not None:
                            tr.stop_loss_price = float(sm.new_stop_loss_price)
                        if sm.new_tp1_price is not None and len(tr.take_profits) >= 1:
                            tr.take_profits[0].price = float(sm.new_tp1_price)
                        if sm.new_tp2_price is not None:
                            if len(tr.take_profits) >= 2:
                                tr.take_profits[1].price = float(sm.new_tp2_price)
                            # 舍弃新增第二档：不自动创建 TP2
                        return tr
                    ledger.update_trade_by_id_atomically(sm.trade_id, _upd_all)
                    logger.info(f"[STREAM] Also updated ledger by trade_id req={request_id} trade_id={sm.trade_id} entry={sm.new_entry_price} sl={sm.new_stop_loss_price} tp1={sm.new_tp1_price} tp2={sm.new_tp2_price}")
                return
            if not sm.trade_id:
                raise ValueError("amend requires order_id or trade_id")
            trade = ledger.get_trade_by_id(sm.trade_id)
            if not trade:
                logger.info(f"[STREAM] amend ignored: trade_id {sm.trade_id} not found")
                return
            if trade.status == TradeStatus.PENDING:
                def _upd(t: TradeLedgerEntry):
                    if sm.new_entry_price is not None:
                        t.entry_price = float(sm.new_entry_price)
                    if sm.new_stop_loss_price is not None:
                        t.stop_loss_price = sm.new_stop_loss_price
                    # TP 可单独改价或整体替换
                    if sm.new_tp1_price is not None and len(t.take_profits) >= 1:
                        t.take_profits[0].price = float(sm.new_tp1_price)
                    if sm.new_tp2_price is not None and len(t.take_profits) >= 2:
                        t.take_profits[1].price = float(sm.new_tp2_price)
                    if sm.new_take_profits is not None:
                        t.take_profits = normalize_take_profits_with_min_notional(
                            original=sm.new_take_profits,
                            position_size=t.position_size,
                            min_notional_usd=settings.TP_MIN_NOTIONAL_USD,
                        )
                    return t
                ledger.update_trade_by_id_atomically(sm.trade_id, _upd)
                logger.info(f"[STREAM] Updated pending plan req={request_id} trade_id={sm.trade_id} new_sl={sm.new_stop_loss_price} new_tps={bool(sm.new_take_profits)}")
                return

            def _upd2(t: TradeLedgerEntry):
                if sm.new_stop_loss_price is not None:
                    t.stop_loss_price = sm.new_stop_loss_price
                if sm.new_take_profits is not None:
                    t.take_profits = normalize_take_profits_with_min_notional(
                        original=sm.new_take_profits,
                        position_size=t.position_size,
                        min_notional_usd=settings.TP_MIN_NOTIONAL_USD,
                    )
                return t
            ledger.update_trade_by_id_atomically(sm.trade_id, _upd2)
            if sm.new_stop_loss_price is not None and trade.stop_loss_txid:
                submit_coro(
                    loop,
                    amend_order_task(
                        AmendOrderRequest(
                            txid=trade.stop_loss_txid,
                            trigger_price=str(sm.new_stop_loss_price)
                        ).model_dump()
                    )
                )
                logger.info(f"[STREAM] Scheduled amend SL on exchange req={request_id} trade_id={sm.trade_id} sl_txid={trade.stop_loss_txid} new_sl={sm.new_stop_loss_price}")

    _with_userref_lock(client, sm.userref, _exec)


def _parse_stream_fields(fields: dict) -> dict:
    """将多字段消息解析为统一 dict。对嵌套 JSON 字段做反序列化。"""
    data: dict[str, any] = {}
    for k, v in (fields or {}).items():
        if k in {"plan", "new_take_profits"} and isinstance(v, str):
            try:
                data[k] = json.loads(v)
                continue
            except Exception:
                pass
        data[k] = v
    return data


def _coerce_stream_message(data: dict) -> dict:
    """将解析后的字段转化为 `StreamMessage` 所需的 shape（如将列表转为对象列表等）。"""
    # 对齐 models.StreamMessage：plan -> TradePlan, new_take_profits -> List[TakeProfitTarget]
    # 这里保持原样由 pydantic 做最终校验；只保证空值与类型基本合理
    if data.get("plan") is None and data.get("symbol") and data.get("action") == "add":
        # 兼容：某些生产方可能只传平铺字段
        data["plan"] = {
            "symbol": data.get("symbol"),
            "side": data.get("side"),
            "entry_price": data.get("entry_price"),
            "position_size": data.get("position_size"),
            "stop_loss_price": data.get("stop_loss_price"),
            "take_profits": data.get("take_profits"),
            "userref": data.get("userref"),
        }
    return data



if __name__ == "__main__":
    main()


