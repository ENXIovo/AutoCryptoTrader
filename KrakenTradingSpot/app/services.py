import time

from app.kraken_client import KrakenClient
from app.models import AddOrderRequest, AmendOrderRequest, CancelOrderRequest

# 实例化客户端，在服务层级共享，避免重复创建
client = KrakenClient()


# ----------------  下   单  ----------------
def add_order_service(payload: AddOrderRequest) -> str:
    """
    提交一个新订单，并返回主交易ID (txid)。
    """
    # .model_dump() 是 Pydantic v2 的标准用法，可以正确处理别名和排除None值
    payload_dict = payload.model_dump(by_alias=True, exclude_none=True)
    
    # 如果调用时未提供userref，可以在这里设置一个默认值
    payload_dict.setdefault("userref", int(time.time()))
    
    print(f"提交新订单: {payload_dict}")
    resp = client.add_order(payload_dict)

    if resp.get("error"):
        raise RuntimeError(f"Kraken 'AddOrder' 失败: {resp['error']}")

    # 直接从返回的字典中提取核心信息
    txid = resp.get("result", {}).get("txid", [None])[0]
    if not txid:
        raise ValueError("未能从Kraken响应中获取交易ID (txid)。")
        
    return txid


# ----------------  改   单  ----------------
def amend_order_service(payload: AmendOrderRequest) -> str:
    """
    修改一个现有订单，并返回修改ID (amend_id)。
    """
    payload_dict = payload.model_dump(exclude_none=True)
    
    print(f"提交改单: {payload_dict}")
    resp = client.amend_order(payload_dict)

    if resp.get("error"):
        raise RuntimeError(f"Kraken 'AmendOrder' 失败: {resp['error']}")
        
    amend_id = resp.get("result", {}).get("amend_id")
    if not amend_id:
        raise ValueError("未能从Kraken响应中获取修改ID (amend_id)。")
        
    return amend_id


# ----------------  撤   单  ----------------
def cancel_order_service(payload: CancelOrderRequest) -> int:
    """
    取消一个现有订单，并返回成功取消的订单数量。
    """
    payload_dict = payload.model_dump(exclude_none=True)

    print(f"提交撤单: {payload_dict}")
    resp = client.cancel_order(payload_dict)

    if resp.get("error"):
        raise RuntimeError(f"Kraken 'CancelOrder' 失败: {resp['error']}")
        
    count = resp.get("result", {}).get("count")
    if count is None:
        raise ValueError("未能从Kraken响应中获取取消数量。")

    return count