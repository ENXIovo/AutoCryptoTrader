# rrr.py
from __future__ import annotations
from typing import Any, Dict, List, Optional

def _f(x: Any) -> Optional[float]:
    try:
        return None if x is None else float(x)
    except Exception:
        return None

def calc_rrr_batch(cases: List[Dict[str, Any]]) -> Dict[str, Any]:
    """
    纯数学 RRR 批量计算器。
    输入每个 case 仅支持四个键：
      entry (必填), stop (必填), tp1 (必填), tp2 (可选)
    输出：risk、reward、rrr（tp1/tp2）、以及 50/50 blended。
    """
    out = {"results": []}
    for i, c in enumerate(cases):
        entry = _f(c.get("entry"))
        stop  = _f(c.get("stop"))
        tp1   = _f(c.get("tp1"))
        tp2   = _f(c.get("tp2"))

        item = {"i": i, "input": {"entry": entry, "stop": stop, "tp1": tp1, "tp2": tp2}}
        errs = []
        if entry is None: errs.append("entry required")
        if stop  is None: errs.append("stop required")
        if tp1   is None: errs.append("tp1 required")

        if not errs:
            risk = abs(entry - stop)
            if risk <= 0:
                errs.append("risk must be > 0 (entry != stop)")
            else:
                reward1 = abs(tp1 - entry)
                rrr1 = reward1 / risk
                item.update({
                    "risk_abs": risk,
                    "reward_tp1_abs": reward1,
                    "rrr_tp1": rrr1
                })
                if tp2 is not None:
                    reward2 = abs(tp2 - entry)
                    rrr2 = reward2 / risk
                    blended = (reward1 + reward2) / (2 * risk)
                    item.update({
                        "reward_tp2_abs": reward2,
                        "rrr_tp2": rrr2,
                        "rrr_blended_50_50": blended
                    })
        if errs: item["errors"] = errs
        out["results"].append(item)
    return out
