from __future__ import annotations

from typing import List

from app.models import TakeProfitTarget


def _ensure_two_tps(original: List[TakeProfitTarget]) -> List[TakeProfitTarget]:
    """Normalize to exactly two TP targets whose percentages sum to 100.

    - If one is provided, synthesize the second as (100 - p1) at the same price.
    - If more than two are provided, keep the first two and scale to sum 100.
    - If the sum is not 100, scale proportionally.
    """
    tps: List[TakeProfitTarget] = list(original or [])
    if not tps:
        # Fallback: create two equal splits with zero price
        return [
            TakeProfitTarget(price=0.0, percentage_to_sell=50.0, is_hit=False),
            TakeProfitTarget(price=0.0, percentage_to_sell=50.0, is_hit=False),
        ]
    if len(tps) == 1:
        p1 = tps[0].percentage_to_sell
        p2 = max(0.0, 100.0 - p1)
        tps.append(
            TakeProfitTarget(price=tps[0].price, percentage_to_sell=p2, is_hit=False)
        )
    if len(tps) > 2:
        tps = tps[:2]
    total = (tps[0].percentage_to_sell or 0.0) + (tps[1].percentage_to_sell or 0.0)
    if abs(total - 100.0) > 1e-9 and total > 0:
        scale = 100.0 / total
        tps[0].percentage_to_sell *= scale
        tps[1].percentage_to_sell *= scale
    return tps


def normalize_take_profits_with_min_notional(
    original: List[TakeProfitTarget],
    position_size: float,
    min_notional_usd: float,
) -> List[TakeProfitTarget]:
    """Apply standard two-TP normalization with an extra rule:

    If both TP1 and TP2 individual notionals (qty_for_tp * tp_price) are below
    `min_notional_usd`, then collapse into a single TP1 selling 100% at TP1 price.
    """
    # First, coerce to two TPs and percentages that sum to 100
    tps = _ensure_two_tps(original)

    # Compute individual notionals in USD
    qty_tp1 = position_size * (tps[0].percentage_to_sell / 100.0)
    qty_tp2 = position_size * (tps[1].percentage_to_sell / 100.0)
    notional_tp1 = qty_tp1 * float(tps[0].price or 0.0)
    notional_tp2 = qty_tp2 * float(tps[1].price or 0.0)

    if notional_tp1 < min_notional_usd and notional_tp2 < min_notional_usd:
        # Collapse to single TP1 at 100%
        return [
            TakeProfitTarget(
                price=float(tps[0].price or 0.0),
                percentage_to_sell=100.0,
                is_hit=False,
            )
        ]

    return tps


