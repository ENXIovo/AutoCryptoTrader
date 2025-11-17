# agent_runner.py

"""
实现串行化的多代理“会议”流程。
"""
import asyncio
import json
import os
import redis
import requests
from datetime import datetime, timezone, timedelta
from concurrent.futures import ThreadPoolExecutor
from typing import Dict, Any, List, Optional
# CHANGED: 导入 get_trade_universe
from .config import get_agent_configs, settings, get_trade_universe 
from .gpt_client import GPTClient
from .scheduler import Scheduler
from .tool_schemas import TOOL_SCHEMAS
from .tool_handlers import TOOL_HANDLERS
from .tool_router import DataClient
from .models import MessageRequest

EXECUTOR = ThreadPoolExecutor(max_workers=8)


def _build_scheduler(tools: list[str]) -> Scheduler:
    # 仅暴露该代理允许的工具 schema / handler
    schemas = {k: v for k, v in TOOL_SCHEMAS.items() if k in tools}
    handlers = {k: v for k, v in TOOL_HANDLERS.items() if k in tools}
    return Scheduler(
        gpt_client=GPTClient(settings.gpt_proxy_url),
        tool_handlers=handlers,
        tool_schemas=schemas,
    )

def _store_analysis_results(report_data: Dict[str, Any]) -> None:
    """
    将本次会议的聚合结果写入 Redis：
    - 使用 Redis Stream（XADD），天然按时间有序，便于按最新读取
    - 键名由 settings.analysis_results_stream_key 指定
    """
    # 选用与你 Celery 一致的 Redis，优先 result_backend，没有就用 broker
    r = redis.Redis.from_url(settings.redis_url)
    ts = datetime.now(timezone.utc).isoformat()
    try:
        payload = json.dumps(report_data, ensure_ascii=False)
    except TypeError:
        payload = json.dumps(
            {k: v if isinstance(v, (str, int, float, bool, list, dict, type(None))) else str(v)
             for k, v in report_data.items()},
            ensure_ascii=False
        )
    # 写入 Stream，自动按时间有序，支持 MAXLEN 修剪
    try:
        maxlen = int(getattr(settings, "analysis_results_stream_maxlen", 0))
    except Exception:
        maxlen = 0
    xadd_kwargs = {}
    if maxlen and maxlen > 0:
        xadd_kwargs["maxlen"] = maxlen
        xadd_kwargs["approximate"] = True  # 使用近似修剪以提高性能

    r.xadd(
        name=settings.analysis_results_stream_key,
        fields={
            "ts": ts,
            "payload": payload,
        },
        **xadd_kwargs,
    )
# --- Helper: attach a concise userref snapshot for CTO/Executor ---
def _build_userref_snapshot() -> str:
    try:
        resp = requests.get(f"{settings.trading_url}/kraken-filter", timeout=5)
        resp.raise_for_status()
        data = resp.json() or {}
        open_orders = data.get("open_orders") or {}
        # Collect distinct userrefs per symbol for quick referencing
        lines: list[str] = []
        for pair, orders in (open_orders or {}).items():
            userrefs = []
            try:
                userrefs = sorted({str(o.get("userref")) for o in (orders or []) if o.get("userref") is not None})
            except Exception:
                userrefs = []
            if not userrefs:
                continue
            lines.append(f"- {pair}: userref(s): {', '.join(userrefs)}")
        if not lines:
            return "No open orders snapshot available (no userrefs found)."
        header = (
            "Userref Snapshot (use these userref values for cancels/amends; do not use order_id/trade_id):\n"
        )
        return header + "\n".join(lines)
    except Exception as _:
        return "Userref Snapshot unavailable (kraken-filter fetch failed)."


# --- Helper: attach last_price snapshot from DataCollector for CTO ---
def _build_last_price_snapshot() -> str:
    try:
        dc = DataClient(settings.data_service_url)
        symbols = get_trade_universe()
        lines: list[str] = []
        
        def _candidate_data_symbols(sym: str) -> list[str]:
            s = str(sym).upper().strip()
            bases: list[str]
            if s in ("BTC", "XBT"):
                bases = ["XBT", "BTC"]
            else:
                bases = [s]
            candidates: list[str] = []
            for b in bases:
                candidates.append(f"{b}USD")
            # 去重，保持顺序
            seen: set[str] = set()
            uniq: list[str] = []
            for c in candidates:
                if c not in seen:
                    seen.add(c)
                    uniq.append(c)
            return uniq
        for sym in symbols:
            try:
                last = None
                for query_sym in _candidate_data_symbols(sym):
                    try:
                        data = dc.getKlineIndicators(query_sym)
                        last = (
                            ((data or {}).get("common_info") or {})
                            .get("ticker", {})
                            .get("last_price")
                        )
                        if last is not None:
                            break
                    except Exception:
                        continue
                if last is not None:
                    lines.append(f"- {sym}: last_price={last}")
            except Exception:
                continue
        if not lines:
            return "No last_price snapshot available."
        return "Live Ticker (last_price only):\n" + "\n".join(lines)
    except Exception:
        return "Live Ticker snapshot unavailable."



# REMOVED: 本地的 _get_trade_universe 函数已被删除，因为它现在从 config.py 导入


async def _analyze_agent(
    agent_cfg: Dict[str, Any],
    user_message: str,
    system_message_override: Optional[str] = None,
) -> Dict[str, Any]:
    scheduler = _build_scheduler(agent_cfg["tools"])
    loop = asyncio.get_running_loop()

    primary_deployment = agent_cfg.get("deployment_name")
    fallback_order = [
        "gpt-5-mini",
        "gpt-5-nano",
    ]

    async def _call(deployment_name: str) -> Dict[str, Any]:
        req = MessageRequest(
            message=user_message,
            system_message=system_message_override or agent_cfg["prompt"],
            deployment_name=deployment_name,
        )
        return await loop.run_in_executor(EXECUTOR, scheduler.analyze, req)

    last_err: Exception | None = None
    # Try primary once, with 30s timeout set in GPTClient
    try:
        return await _call(primary_deployment)
    except Exception as e:
        last_err = e

    # Sequential fallbacks: mini -> nano, each only once
    for fb in fallback_order:
        if fb == primary_deployment:
            continue
        try:
            return await _call(fb)
        except Exception as e2:
            last_err = e2

    # Final fallback: return an error-shaped response to avoid crashing the meeting
    return {
        "content": f"[ERROR] Agent '{agent_cfg.get('name')}' failed after retries and fallback. Last error: {last_err}",
        "error": str(last_err) if last_err else "unknown",
    }

async def run_agents_in_sequence_async() -> Dict[str, Any]:
    """
    新版：并行 News/多份 TA；随后串行 PM -> Risk -> CTO（CTO 直接执行工具）。
    """
    print("--- Starting Trading Strategy Meeting (New Workflow) ---")

    current_utc_time = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S %Z")
    agent_configs = [c for c in get_agent_configs() if c.get("enabled")]
    print(f"Meeting Start Time: {current_utc_time}\n")

    meeting_context_header = f"# Meeting started at: {current_utc_time}\n"
    final_reports: Dict[str, Any] = {"_meta": {"start_time_utc": current_utc_time}}

    # 识别各角色配置
    cfg_by_name = {c["name"]: c for c in agent_configs}
    news_cfg = cfg_by_name.get("Market Analyst")
    pm_cfg = cfg_by_name.get("Position Manager")
    ta_cfg = cfg_by_name.get("Lead Technical Analyst")
    risk_cfg = cfg_by_name.get("Risk Manager")
    cto_cfg = cfg_by_name.get("Chief Trading Officer")

    # ------------------ MODIFIED: STAGE 1 (Parallel Base Analysis) ------------------
    # 只运行不互相依赖的基础分析师
    tasks = []
    task_tags = []

    if news_cfg:
        tasks.append(_analyze_agent(news_cfg, user_message=f"{meeting_context_header}\n# Your Task:\nProvide today's market/crypto executive brief."))
        task_tags.append(("Market Analyst", None))

    ta_symbols = get_trade_universe()
    if ta_cfg:
        for sym in ta_symbols:
            ta_prompt = ta_cfg["prompt"].format(symbol=sym) if "{symbol}" in ta_cfg["prompt"] else ta_cfg["prompt"]
            tasks.append(_analyze_agent(ta_cfg, user_message=f"{meeting_context_header}\n# Your Task:\nAct as Lead Technical Analyst for symbol: {sym}.", system_message_override=ta_prompt))
            task_tags.append(("Lead Technical Analyst", sym))

    if tasks:
        parallel_results = await asyncio.gather(*tasks)
    else:
        parallel_results = []


    # 收集并构建基础会议上下文
    ta_bucket: Dict[str, Dict[str, Any]] = {}
    base_context = meeting_context_header

    for (role, sym), res in zip(task_tags, parallel_results):
        content = res.get("content", f"{role} returned no content.")
        if role == "Market Analyst":
            final_reports[role] = res
            base_context += f"\n\n## Report from Market Analyst:\n{content}"
            print(f"[{role}] responded:\n{content}\n")
        elif role == "Lead Technical Analyst":
            ta_bucket[sym] = res
            base_context += f"\n\n## Report from Lead Technical Analyst ({sym}):\n{content}"
            print(f"[TA:{sym}] responded:\n{content}\n")
    
    final_reports["Lead Technical Analyst"] = ta_bucket


    # ------------------ NEW: STAGE 2 (Sequential Position Manager) ------------------
    # PM 在 TA 和 News 之后运行，并接收他们的报告
    if pm_cfg:
        pm_result = await _analyze_agent(
            pm_cfg,
            user_message=f"""{base_context}

# Your Task:
Based on the market and technical reports above, review existing holdings and open orders.
Propose a clear action plan, including any dynamic adjustments based on the new TA.
""",
        )
        final_reports["Position Manager"] = pm_result
        print(f"[Position Manager] responded:\n{pm_result.get('content','')}\n")

    # ------------------ NEW: STAGE 3 & 4 (Sequential Risk -> CTO) ------------------
    # 构建包含 PM 智能建议的完整上下文
    full_context = base_context
    if "Position Manager" in final_reports:
        full_context += f"\n\n## Report from Position Manager:\n{final_reports['Position Manager'].get('content','')}"

    # Risk（一次）
    if risk_cfg:
        risk_result = await _analyze_agent(risk_cfg, user_message=f"{full_context}\n\n# Your Task:\nUsing all the above reports, screen candidate symbols.")
        final_reports["Risk Manager"] = risk_result
        print(f"[Risk Manager] responded:\n{risk_result.get('content','')}\n")

    # CTO（一次）
    if cto_cfg:
        final_context_for_cto = full_context
        if "Risk Manager" in final_reports:
            final_context_for_cto += f"\n\n## Report from Risk Manager:\n{final_reports.get('Risk Manager', {}).get('content','')}"

        # Compute and inject scheduling context for CTO
        now_dt = datetime.now(timezone.utc)
        # Find next default meeting time at :05 UTC where hour % 4 == 0
        candidate = now_dt.replace(minute=5, second=0, microsecond=0)
        if candidate <= now_dt:
            candidate = candidate + timedelta(hours=1)
        while candidate.hour % 4 != 0:
            candidate = candidate + timedelta(hours=1)
        now_iso = now_dt.strftime("%Y-%m-%dT%H:%M:%SZ")
        next_default_iso = candidate.strftime("%Y-%m-%dT%H:%M:%SZ")

        scheduling_note = (
            f"\n\n## Scheduling Context (for CTO)\n"
            f"Current time (UTC): {now_iso}\n"
            f"Default next meeting (UTC, every 4h at :05): {next_default_iso}\n\n"
            f"If needed, call `rescheduleMeeting(countdown_minutes, reason)` to adjust ONLY the next meeting. "
            f"Baseline cadence remains every 4h at :05 UTC. If you do not call it, the next meeting occurs at the default time above.\n"
        )

        # Attach userref snapshot for decision context
        final_context_for_cto += f"\n\n## Userref Snapshot\n{_build_userref_snapshot()}\n"
        # Attach last price snapshot for limit-order validation guidance
        final_context_for_cto += f"\n\n## Live Ticker\n{_build_last_price_snapshot()}\n"

        cto_result = await _analyze_agent(
            cto_cfg,
            user_message=f"{final_context_for_cto}{scheduling_note}\n\n# Your Task:\nMake the final decision and provide an actionable plan.",
        )
        final_reports["Chief Trading Officer"] = cto_result
        print(f"[Chief Trading Officer] responded:\n{cto_result.get('content','')}\n")

    # Stage 5 removed: CTO executes directly with tools


    print("--- Trading Strategy Meeting Ended ---")

    try:
        _store_analysis_results(final_reports)
    except Exception as e:
        print(f"Failed to store analysis results: {e}")

    return final_reports

# --- The rest of the file remains the same ---

async def _run_single_agent(cfg: Dict[str, Any]) -> Dict[str, Any]:
    scheduler = _build_scheduler(cfg["tools"])
    msg_req = MessageRequest(
        message=cfg["prompt"],
        system_message=cfg["prompt"],
    )
    loop = asyncio.get_running_loop()
    result = await loop.run_in_executor(EXECUTOR, scheduler.analyze, msg_req)
    return {"agent_name": cfg["name"], "result": result}


async def run_all_agents_async() -> Dict[str, Any]:
    cfgs = [c for c in get_agent_configs() if c.get("enabled")]
    tasks = [_run_single_agent(c) for c in cfgs]
    return {
        "agents": await asyncio.gather(*tasks)
    }


def run_all_agents() -> Dict[str, Any]:
    return asyncio.run(run_all_agents_async())