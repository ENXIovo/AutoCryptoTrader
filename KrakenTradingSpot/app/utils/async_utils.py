import asyncio
import threading
import logging
from typing import Optional, Coroutine, Any


_ASYNC_LOOP: Optional[asyncio.AbstractEventLoop] = None
_ASYNC_THREAD: Optional[threading.Thread] = None


def ensure_background_event_loop() -> asyncio.AbstractEventLoop:
    global _ASYNC_LOOP, _ASYNC_THREAD
    if _ASYNC_LOOP and _ASYNC_LOOP.is_running():
        return _ASYNC_LOOP

    loop = asyncio.new_event_loop()

    def _runner() -> None:
        asyncio.set_event_loop(loop)
        loop.run_forever()

    thread = threading.Thread(target=_runner, name="stream-consumer-asyncio", daemon=True)
    thread.start()
    _ASYNC_LOOP = loop
    _ASYNC_THREAD = thread
    # 基础日志配置：INFO 级别，防止外部未配置时看不到日志
    logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(name)s: %(message)s")
    return loop


def submit_coro(loop: asyncio.AbstractEventLoop, coro: Coroutine[Any, Any, Any]) -> None:
    asyncio.run_coroutine_threadsafe(coro, loop)


