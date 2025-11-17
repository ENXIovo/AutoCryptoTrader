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
            # 仅通过 userref 撤销整组，并清理台账
            if sm.userref is not None:
                async def _cancel_by_userref(uref: int) -> None:
                    try:
                        from app.services import cancel_order_service
                        await cancel_order_service(CancelOrderRequest(userref=uref))
                    except Exception:
                        pass
                    # 全量清理该 userref 的台账
                    try:
                        to_delete = [t.trade_id for t in ledger.get_all_trades() if str(getattr(t, "userref", None)) == str(uref)]
                        for tid in to_delete:
                            trade = ledger.get_trade_by_id(tid)
                            if trade:
                                def _mark_closed(tr: TradeLedgerEntry):
                                    tr.status = TradeStatus.CLOSED
                                    return tr
                                ledger.update_trade_by_id_atomically(tid, _mark_closed)
                                ledger.delete_trade_by_id(tid)
                    except Exception:
                        pass
                submit_coro(loop, _cancel_by_userref(sm.userref))
                logger.info(f"[STREAM] Scheduled cancel by userref req={request_id} userref={sm.userref}")
                return
            raise ValueError("cancel requires userref")

        if sm.action == StreamAction.amend:
            # 仅通过 userref 修改（组内所有相关订单与台账）
            if sm.userref is not None:
                try:
                    uref = str(sm.userref)
                    linked = [t for t in ledger.get_all_trades() if str(getattr(t, "userref", None)) == uref]
                    if not linked:
                        logger.info(f"[STREAM] amend ignored: no trades for userref={uref}")
                        return
                    for t in linked:
                        # 台账更新
                        def _upd_all(tr: TradeLedgerEntry):
                            if sm.new_entry_price is not None and tr.status == TradeStatus.PENDING:
                                tr.entry_price = float(sm.new_entry_price)
                            if sm.new_stop_loss_price is not None:
                                tr.stop_loss_price = float(sm.new_stop_loss_price)
                            if sm.new_tp1_price is not None and len(tr.take_profits) >= 1:
                                tr.take_profits[0].price = float(sm.new_tp1_price)
                            if sm.new_tp2_price is not None and len(tr.take_profits) >= 2:
                                tr.take_profits[1].price = float(sm.new_tp2_price)
                            return tr
                        ledger.update_trade_by_id_atomically(t.trade_id, _upd_all)

                        # 交易所订单修改：入场限价（未成交）或已有止损
                        if sm.new_entry_price is not None and getattr(t, "entry_txid", None) and t.status == TradeStatus.PENDING:
                            submit_coro(
                                loop,
                                amend_order_task(
                                    AmendOrderRequest(
                                        txid=t.entry_txid,
                                        limit_price=str(sm.new_entry_price)
                                    ).model_dump()
                                )
                            )
                        if sm.new_stop_loss_price is not None and getattr(t, "stop_loss_txid", None):
                            submit_coro(
                                loop,
                                amend_order_task(
                                    AmendOrderRequest(
                                        txid=t.stop_loss_txid,
                                        trigger_price=str(sm.new_stop_loss_price)
                                    ).model_dump()
                                )
                            )
                    logger.info(f"[STREAM] Amended by userref req={request_id} userref={uref} entry={sm.new_entry_price} sl={sm.new_stop_loss_price} tp1={sm.new_tp1_price} tp2={sm.new_tp2_price}")
                    return
                except Exception:
                    return
            raise ValueError("amend requires userref")

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


