import asyncio
from collections.abc import Coroutine

_loop: asyncio.AbstractEventLoop | None = None


def run_job_coroutine[T](coroutine: Coroutine[object, object, T]) -> T:
    global _loop
    if _loop is None or _loop.is_closed():
        _loop = asyncio.new_event_loop()
    return _loop.run_until_complete(coroutine)
