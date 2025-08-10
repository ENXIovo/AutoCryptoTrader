# agent_runner.py

"""
实现串行化的多代理“会议”流程。
"""
import asyncio
import json
import os
import redis
from datetime import datetime, timezone # 导入datetime模块
from concurrent.futures import ThreadPoolExecutor
from typing import Dict, Any, List, Optional
from .config import get_agent_configs, settings
from .gpt_client import GPTClient
from .scheduler import Scheduler
from .tool_schemas import TOOL_SCHEMAS
from .tool_handlers import TOOL_HANDLERS
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
    - 使用 Hash 结构：field=UTC 时间戳，value=JSON 报告
    - 键名由 settings.analysis_results_key 指定
    """
    # 选用与你 Celery 一致的 Redis，优先 result_backend，没有就用 broker
    r = redis.Redis.from_url(settings.redis_url)

    ts = datetime.now(timezone.utc).isoformat()

    # 尽量用 JSON 序列化；若个别字段不可序列化，可按需做轻量转换
    try:
        payload = json.dumps(report_data, ensure_ascii=False)
    except TypeError:
        payload = json.dumps(
            {k: v if isinstance(v, (str, int, float, bool, list, dict, type(None))) else str(v)
             for k, v in report_data.items()},
            ensure_ascii=False
        )

    # Hash: HSET analysis_results <ts> <json>
    r.hset(settings.analysis_results_key, ts, payload)


def _get_trade_universe() -> List[str]:
    """
    从 env 中读取可选币种，形如：
    trade_universe_json='["BTC","ETH"]'
    如果未设置，则默认 ["BTC","ETH"]。
    （不修改 config.py，纯在本文件自给自足）
    """
    raw = settings.trade_universe_json
    if raw:
        try:
            arr = json.loads(raw)
            if isinstance(arr, list) and all(isinstance(x, str) for x in arr):
                return arr
        except Exception:
            pass
    return ["BTC"]

async def _analyze_agent(
    agent_cfg: Dict[str, Any],
    user_message: str,
    system_message_override: Optional[str] = None,
) -> Dict[str, Any]:
    scheduler = _build_scheduler(agent_cfg["tools"])
    msg_req = MessageRequest(
        message=user_message,
        system_message=system_message_override or agent_cfg["prompt"],
        deployment_name=agent_cfg["deployment_name"],
    )
    loop = asyncio.get_running_loop()
    return await loop.run_in_executor(EXECUTOR, scheduler.analyze, msg_req)

async def run_agents_in_sequence_async() -> Dict[str, Any]:
    """
    新版：并行 News/PM/多份 TA；随后串行 Risk -> CTO。
    """
    print("--- Starting Trading Strategy Meeting (parallel News/PM/TA) ---")

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

    # 1) 并行：News（一次）+ PM（一次）+ TA（多币种）
    tasks = []
    task_tags = []  # 用于标注结果属于谁/哪个 symbol

    if news_cfg:
        tasks.append(
            _analyze_agent(
                news_cfg,
                user_message=f"""{meeting_context_header}
# Your Task:
Provide today's market/crypto executive brief as per your role.
""",
            )
        )
        task_tags.append(("Market Analyst", None))

    if pm_cfg:
        tasks.append(
            _analyze_agent(
                pm_cfg,
                user_message=f"""{meeting_context_header}
# Your Task:
Review existing holdings and open orders first; free capital if applicable.
""",
            )
        )
        task_tags.append(("Position Manager", None))

    ta_symbols = _get_trade_universe()
    if ta_cfg:
        for sym in ta_symbols:
            # 如果提示词里支持 {symbol} 占位符，则替换；否则保持原样
            ta_prompt = ta_cfg["prompt"]
            if "{symbol}" in ta_prompt:
                ta_prompt = ta_prompt.format(symbol=sym)

            tasks.append(
                _analyze_agent(
                    ta_cfg,
                    user_message=f"""{meeting_context_header}
# Your Task:
Act as Lead Technical Analyst for symbol: {sym}.
Focus ONLY on {sym} (and optionally {sym}BTC for relative strength).
""",
                    system_message_override=ta_prompt,
                )
            )
            task_tags.append(("Lead Technical Analyst", sym))

    parallel_results = await asyncio.gather(*tasks)

    # 收集并打印
    ta_bucket: Dict[str, Dict[str, Any]] = {}
    for (role, sym), res in zip(task_tags, parallel_results):
        content = res.get("content", f"{role} returned no content.")
        if role == "Lead Technical Analyst":
            ta_bucket[sym] = res
            print(f"[TA:{sym}] responded:\n{content}\n")
        else:
            final_reports[role] = res
            print(f"[{role}] responded:\n{content}\n")

    # 2) 串行：拼接会议上下文 → Risk
    meeting_context = meeting_context_header

    if "Market Analyst" in final_reports:
        meeting_context += f"\n\n## Report from Market Analyst:\n{final_reports['Market Analyst'].get('content','')}"
    if "Position Manager" in final_reports:
        meeting_context += f"\n\n## Report from Position Manager:\n{final_reports['Position Manager'].get('content','')}"

    for sym in ta_symbols:
        if sym in ta_bucket:
            meeting_context += f"\n\n## Report from Lead Technical Analyst ({sym}):\n{ta_bucket[sym].get('content','')}"

    final_reports["Lead Technical Analyst"] = ta_bucket

    # 3) Risk（一次）
    if risk_cfg:
        risk_result = await _analyze_agent(
            risk_cfg,
            user_message=f"""{meeting_context}

# Your Task:
Using the above reports, screen all candidate symbols at once.
""",
        )
        final_reports["Risk Manager"] = risk_result
        print(f"[Risk Manager] responded:\n{risk_result.get('content','')}\n")

    # 4) CTO（一次）
    if cto_cfg:
        cto_result = await _analyze_agent(
            cto_cfg,
            user_message=f"""{meeting_context}

## Report from Risk Manager:
{final_reports.get('Risk Manager', {}).get('content','')}

# Your Task:
Make the final decision (approve at most ONE plan or NO TRADE) and provide an actionable plan if any.
""",
        )
        final_reports["Chief Trading Officer"] = cto_result
        print(f"[Chief Trading Officer] responded:\n{cto_result.get('content','')}\n")

    print("--- Trading Strategy Meeting Ended ---")

    # 入库
    try:
        _store_analysis_results(final_reports)
    except Exception as e:
        print(f"Failed to store analysis results: {e}")

    return final_reports

# --- 保留您原有的并行执行函数，以备不时之需 ---

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