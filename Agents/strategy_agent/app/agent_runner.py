# agent_runner.py

"""
实现串行化的多代理“会议”流程。
"""
import asyncio
import uuid
from datetime import datetime, timezone # 导入datetime模块
from concurrent.futures import ThreadPoolExecutor
from typing import Dict, Any, List
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


async def run_agents_in_sequence_async() -> Dict[str, Any]:
    """
    按顺序运行所有启用的代理，模拟一个会议讨论流程。
    每个代理的输出都会成为下一个代理的输入上下文。
    """
    print("--- Starting Trading Strategy Meeting ---")

    # 1. 获取当前UTC时间并格式化
    current_utc_time = datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M:%S %Z')
    agent_configs = [c for c in get_agent_configs() if c.get("enabled")]

    print(f"Meeting Start Time: {current_utc_time}\n")

    # 2. 将时间戳作为会议的初始上下文
    meeting_context = f"# Meeting started at: {current_utc_time}\n"
    final_reports: Dict[str, Any] = {}
    meeting_session_id: str | None = None

    for idx, agent_config in enumerate(agent_configs):
        agent_name = agent_config["name"]
        print(f"--- It's {agent_name}'s turn ---")

        scheduler = _build_scheduler(agent_config["tools"])
        user_message = f"""
# Previous Discussion Context:
{meeting_context}

# Your Task:
Based on your role and the context above, please provide your analysis now.
"""

        # 对于首个 Agent，不传 session_id，由 GPTProxy 返回；其后使用该 session_id
        req_kwargs: dict[str, Any] = {
            'message': user_message,
            'system_message': agent_config['prompt'],
            'deployment_name': agent_config['deployment_name'],
        }
        if meeting_session_id:
            req_kwargs['session_id'] = meeting_session_id

        msg_req = MessageRequest(**req_kwargs)

        loop = asyncio.get_running_loop()
        result = await loop.run_in_executor(EXECUTOR, scheduler.analyze, msg_req)

        # 捕获并存储首次返回的 session_id
        if idx == 0:
            meeting_session_id = result.get('session_id')
            print(f"Using session_id from GPTProxy: {meeting_session_id}")

        agent_response_content = result.get('content', f"Agent {agent_name} did not return content.")
        print(f"Agent '{agent_name}' responded:\n{agent_response_content}\n")

        meeting_context += f"\n\n## Report from {agent_name}:\n{agent_response_content}"
        final_reports[agent_name] = result

    print("--- Trading Strategy Meeting Ended ---")
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