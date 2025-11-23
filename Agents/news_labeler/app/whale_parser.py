# app/whale_parser.py
import re
import logging
from dataclasses import dataclass
from typing import Optional

logger = logging.getLogger(__name__)

# 只识别这种核心结构：
#   100,000,000 #USDC (99,984,400 USD) minted at USDC Treasury
#   999 #BTC (116,882,002 USD) transferred from unknown wallet ...
#   500,000,000 #XRP (1,480,487,661 USD) locked in escrow at #Ripple
#
# 规则：数字 + 空格 + #SYMBOL + 空格 + "(" + 美元数 + " USD" + ")"
WHALE_CORE_RE = re.compile(
    r"""
    (?P<amount>[\d,]+(?:\.\d+)?)            # 任何数量（我们不使用，只为鲁棒）
    \s+\#(?P<symbol>[A-Za-z0-9]{2,12})      # #SYMBOL
    \s*\(
        \$?\s*(?P<usd>[\d,]+(?:\.\d+)?)     # 美元数
        \s*USD
    \)
    """,
    re.IGNORECASE | re.VERBOSE | re.DOTALL,
)

UNKNOWN_RE = re.compile(r"\bunknown\b", re.IGNORECASE)


# 轻清洗：去多空格/换行/首尾空白（不删除 emoji）
def _clean(s: str) -> str:
    s = s.replace("\n", " ").replace("\r", " ")
    s = re.sub(r"\s+", " ", s)
    return s.strip()

def _to_float(s: str) -> float:
    try:
        return float(s.replace(",", ""))
    except Exception:
        return 0.0

def _importance_by_usd(usd: float, is_routine: bool = False) -> float:
    # 策略：Stablecoin 铸造/销毁/国库流转 -> 大幅降权，除非金额巨大
    if is_routine:
        if usd >= 1_000_000_000: return 0.85  # 10亿才算大事
        if usd >= 500_000_000:   return 0.75  # 5亿
        return 0.40  # 其他一律低分

    # 正常交易 (转账/砸盘/买入)
    if usd >= 300_000_000:  # ≥$300m
        return 0.95
    if usd >= 100_000_000:
        return 0.90
    if usd >= 50_000_000:
        return 0.80
    if usd >= 20_000_000:
        return 0.70
    
    return 0.40 # 提高门槛，几百万的别推了

def _is_routine_operation(text: str) -> bool:
    """检测是否为 Mint/Burn/Treasury 等例行操作"""
    t = text.lower()
    keywords = ["minted", "burned", "treasury", "reserve"]
    return any(k in t for k in keywords)

def _unknown_factor(line: str) -> tuple[float, int]:
    """根据 'unknown' 出现次数返回惩罚系数与计数。"""
    n = len(UNKNOWN_RE.findall(line))
    if n == 0:
        return 1.0, 0
    if n == 1:
        return 0.8, 1
    return 0.6, n  # 2 个及以上

@dataclass
class WhaleResult:
    ok: bool
    category: list[str]      # 固定 ['whale_transaction']
    importance: float
    durability: str          # 固定 'hours'
    summary: str             # 原文（轻清洗）
    confidence: float        # 有美元估值就给高置信

def parse_whale_fixed(text: str) -> Optional[WhaleResult]:
    if not text:
        logger.debug("[whale.simple] empty text")
        return None

    line = _clean(text)
    if not line:
        logger.debug("[whale.simple] empty after clean")
        return None

    m = WHALE_CORE_RE.search(line)
    if not m:
        logger.debug("[whale.simple] core pattern not matched: '%s'", line[:200])
        return None

    symbol = m.group("symbol").upper()
    usd = _to_float(m.group("usd"))
    
    # 判定是否 routine
    is_routine = _is_routine_operation(line)
    
    importance = _importance_by_usd(usd, is_routine)
    confidence = 0.9 if usd > 0 else 0.7

    # ★ 新增：根据 unknown 次数下调重要度
    factor, unk_cnt = _unknown_factor(line)
    importance *= factor

    summary = line

    logger.info(
        "[whale.simple] ok symbol=%s usd=%.2f importance=%.2f (routine=%s unknown_cnt=%d factor=%.2f) confidence=%.2f",
        symbol, usd, importance, is_routine, unk_cnt, factor, confidence
    )

    return WhaleResult(
        ok=True,
        category=["whale_transaction"],
        importance=importance,
        durability="hours",
        summary=summary,
        confidence=confidence,
    )