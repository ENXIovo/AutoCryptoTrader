import os
import time
import logging
from .whale_parser import parse_whale_fixed
from .config import settings
from .gpt_client import GPTClient
from .utils.redis_utils import (
    new_redis,
    ensure_group,
    xreadgroup,
    xack,
    xautoclaim_stale,
    compute_weight,
    save_label_to_redis,
)

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger("news_labeler.worker")

# =============== 倍率规则（来源/分类） ===============
def _source_factor(source: str) -> float:
    s = (source or "").strip().lower()
    for k, v in settings.source_factor_map.items():
        if k in s:
            return v
    return 0.8

def _category_factor(categories) -> float:
    if not categories:
        return 1.0
    if isinstance(categories, str):
        cats = [c.strip().lower() for c in categories.split(",") if c.strip()]
    else:
        cats = [str(c).strip().lower() for c in categories if str(c).strip()]
    if not cats:
        return 1.0
    factors = [settings.category_factor_map.get(c, 1.0) for c in cats]
    up = max([f for f in factors if f >= 1.0], default=1.0)
    down = min([f for f in factors if f < 1.0], default=1.0)
    return up * down

# ====================================================

def _decode(v: bytes | None) -> str:
    return v.decode() if isinstance(v, (bytes, bytearray)) else (v or "")

def _is_whale_source(source: str) -> bool:
    s = (source or "").strip()
    wl = set(settings.whale_sources) | {x.lower() for x in settings.whale_sources}
    return s in wl or s.lower() in wl

# ================== 分离：非 WHALE（GPT） ==================
def _handle_gpt(r, client: GPTClient, group: str, msg_id: str, key: str,
                text: str, source: str, ts: str, label_version="gpt"):
    label = client.label_news(text)  # 失败抛异常
    
    # 纯粹使用 GPT 的判断 + 时间衰减，不再乘以来源/分类系数
    # 我们信任 GPT 对内容重要性的理解
    weight = compute_weight(label.importance, label.durability, ts)

    save_label_to_redis(r, key, {
        "category": ",".join(label.category),
        "importance": str(label.importance),
        "durability": label.durability,
        "summary": label.summary,
        "confidence": str(label.confidence),
        "source": source, "ts": ts, "label_version": label_version,
    }, weight)
    xack(r, group, msg_id)
    logger.info("[process][gpt] saved & acked id=%s key=%s ver=%s final=%.6f",
                msg_id, key, label_version, weight)

# ================== 分离：WHALE ==================
def _handle_whale(r, client: GPTClient, group: str, msg_id: str, key: str,
                  text: str, source: str, ts: str):
    logger.info("[process][whale] source=%s", source)
    whale = parse_whale_fixed(text)  # 不匹配返回 None
    if whale and whale.ok:
        # Whale 逻辑保持原样，或者也统一？
        # 既然用户要求去掉 base 权重，Whale 解析通常比较死板，
        # 建议也去掉外部系数，只保留解析出的 importance
        weight = compute_weight(whale.importance, whale.durability, ts)

        save_label_to_redis(r, key, {
            "category": ",".join(whale.category),  # ['whale_transaction']
            "importance": str(whale.importance),
            "durability": whale.durability,
            "summary": whale.summary,
            "confidence": str(whale.confidence),
            "source": source, "ts": ts, "label_version": "whale-fixed",
        }, weight)
        xack(r, group, msg_id)
        logger.info("[process][whale] saved & acked id=%s key=%s final=%.6f",
                    msg_id, key, weight)
        return

    # 解析失败 → 直接丢给 GPT 分支
    logger.warning("[process][whale] parse failed; fallback->GPT id=%s key=%s", msg_id, key)
    _handle_gpt(r, client, group, msg_id, key, text, source, ts, label_version="whale-fallback-gpt")

# ================== 路由 ==================
def _process_one(r, client: GPTClient, group: str, msg_id: str, fields: dict):
    text    = _decode(fields.get(b"text"))
    source  = _decode(fields.get(b"source"))
    ts      = _decode(fields.get(b"ts"))
    chat_id = _decode(fields.get(b"chat_id"))
    msg_no  = _decode(fields.get(b"message_id"))

    key = f"{chat_id}:{msg_no}" if chat_id and msg_no else msg_id
    if not (chat_id and msg_no):
        logger.warning("[process] missing chat_id/message_id -> using msg_id as key; chat_id=%r msg_no=%r id=%s",
                       chat_id, msg_no, msg_id)

    logger.info("[process] id=%s src=%s key=%s", msg_id, source, key)

    try:
        # if _is_whale_source(source):
        #    _handle_whale(r, client, group, msg_id, key, text, source, ts)
        # else:
        #    _handle_gpt(r, client, group, msg_id, key, text, source, ts, label_version="gpt")
        
        # 临时封杀 WhaleAlert 以减少噪音 (M0阶段)
        if _is_whale_source(source):
            logger.info("[process] skipping whale source %s", source)
            xack(r, group, msg_id) # 即使跳过也要ACK，否则会一直堆积
            return

            _handle_gpt(r, client, group, msg_id, key, text, source, ts, label_version="gpt")
    except Exception as e:
        logger.exception("[process] failed id=%s key=%s: %s", msg_id, key, e)
        # 不 ACK，留给重试

def labeler_loop():
    r = new_redis()
    client = GPTClient()
    group = settings.stream_consumer_group
    consumer = f"consumer-{os.getpid()}"

    ensure_group(r)

    # 可选：认领超时 pending
    try:
        reclaimed = 0
        for msg_id, fields in xautoclaim_stale(
            r, group=group, consumer=consumer,
            min_idle_ms=5*60*1000, batch=100
        ):
            try:
                _process_one(r, client, group, msg_id, fields)
                reclaimed += 1
            except Exception as e:
                logger.exception("[pending] process failed id=%s: %s", msg_id, e)
        if reclaimed:
            logger.info("[pending] reclaimed processed=%d", reclaimed)
    except Exception as e:
        logger.exception("[pending] xautoclaim error: %s", e)

    logger.info("Labeler started: group=%s consumer=%s", group, consumer)
    while True:
        try:
            msgs = xreadgroup(r, group, consumer, settings.stream_batch_size, settings.stream_block_ms)
            if not msgs:
                continue
            for _, records in msgs:
                for mid, fields in records:
                    msg_id = mid.decode() if hasattr(mid, "decode") else str(mid)
                    try:
                        _process_one(r, client, group, msg_id, fields)
                    except Exception as e:
                        logger.exception("[read] process failed id=%s: %s", msg_id, e)
        except Exception as e:
            logger.exception("[loop] read error: %s", e)
            time.sleep(1)

if __name__ == "__main__":
    labeler_loop()
