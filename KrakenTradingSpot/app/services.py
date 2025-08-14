# app/services.py
import time
import logging
from typing import Dict, Any

from app.kraken_client import KrakenClient
from app.models import AddOrderRequest, AmendOrderRequest, CancelOrderRequest

# 共享异步客户端实例
client = KrakenClient()


async def add_order_service(payload: AddOrderRequest) -> str:
    """
    提交一个新订单，并返回主交易ID (txid)。
    在这里统一将 pair 解析为 Kraken altname，避免上游关心命名差异。
    """
    # by_alias=True 以输出 close[...] 等别名字段；mode="json" 触发 field_serializer(JSON 场景)
    payload_dict: Dict[str, Any] = payload.model_dump(mode="json", by_alias=True, exclude_none=True)
    # 若未提供 userref，默认给一个时间戳作为分组标识
    if payload_dict.get("userref") is None:
        payload_dict["userref"] = int(time.time())

    # 统一解析 pair -> altname
    if "pair" in payload_dict and payload_dict["pair"]:
        alt = await client.resolve_altname(str(payload_dict["pair"]))
        if not alt:
            raise ValueError(f"未能解析交易对: {payload_dict['pair']}")
        payload_dict["pair"] = alt

    logging.getLogger(__name__).info(f"提交新订单: {payload_dict}")
    resp = await client.add_order(payload_dict)

    if resp.get("error"):
        raise RuntimeError(f"Kraken 'AddOrder' 失败: {resp['error']}")

    result = resp.get("result") or {}
    txids = result.get("txid") or []
    if isinstance(txids, list):
        txid = txids[0] if txids else None
    else:
        txid = txids

    if not txid:
        raise ValueError("未能从 Kraken 响应中获取交易ID (txid)。")

    return str(txid)


async def amend_order_service(payload: AmendOrderRequest) -> str:
    """
    修改一个现有订单，并返回修改ID (amend_id)。
    """
    payload_dict: Dict[str, Any] = payload.model_dump(exclude_none=True)

    logging.getLogger(__name__).info(f"提交改单: {payload_dict}")
    resp = await client.amend_order(payload_dict)

    if resp.get("error"):
        raise RuntimeError(f"Kraken 'AmendOrder' 失败: {resp['error']}")

    amend_id = (resp.get("result") or {}).get("amend_id")
    if not amend_id:
        raise ValueError("未能从 Kraken 响应中获取修改ID (amend_id)。")

    return str(amend_id)


async def cancel_order_service(payload: CancelOrderRequest) -> int:
    """
    取消一个现有订单，并返回成功取消的订单数量。
    """
    payload_dict: Dict[str, Any] = payload.model_dump(exclude_none=True)

    logging.getLogger(__name__).info(f"提交撤单: {payload_dict}")
    resp = await client.cancel_order(payload_dict)

    if resp.get("error"):
        raise RuntimeError(f"Kraken 'CancelOrder' 失败: {resp['error']}")

    count = (resp.get("result") or {}).get("count")
    if count is None:
        raise ValueError("未能从 Kraken 响应中获取取消数量。")

    return int(count)
