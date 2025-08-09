# tasks.py

"""
Celery 定时任务：周期性运行策略代理。
"""
import asyncio
from celery import Celery
from celery.schedules import crontab
from .config import settings
# 导入新的串行会议运行器
from .agent_runner import run_agents_in_sequence_async

celery_app = Celery(
    "strategy_tasks",
    broker=settings.celery_broker_url,
    backend=settings.celery_result_backend,
)


# 解析 CRON 表达式（形如 "0 */4 * * *"）
minute, hour, day, month, dow = settings.strategy_cron.split()
celery_app.conf.beat_schedule = {
    "run-strategy-agent": {
        "task": "app.tasks.run_strategy",
        "schedule": crontab(minute=minute, hour=hour,
                            day_of_month=day, month_of_year=month,
                            day_of_week=dow),
        "options": {"queue": "auto_trade_queue"},
    }
}
celery_app.conf.timezone = "UTC"


@celery_app.task(name="app.tasks.run_strategy")
def run_strategy():
    """
    Celery task to run the trading strategy session using the sequential meeting workflow.
    """
    print("Starting scheduled trading strategy session...")
    try:
        # 使用asyncio.run来执行异步的会议函数
        result = asyncio.run(run_agents_in_sequence_async())
        # 你可以在这里把结果写 DB / 发通知
        print("Strategy meeting finished. Final reports:", result)
    except Exception as e:
        print(f"An error occurred during the scheduled session: {e}")