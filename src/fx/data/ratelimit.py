"""并发/限频控制。

用信号量限制同时在飞的请求数；配合 tenacity（若已安装）对 429/418/瞬时错误
做指数退避。tenacity 缺失时退化为无重试，便于离线/最小依赖运行。
"""

from __future__ import annotations

import asyncio
from typing import Awaitable, Callable, TypeVar

T = TypeVar("T")

try:  # 可选依赖
    from tenacity import (retry, retry_if_exception_type, stop_after_attempt,
                          wait_exponential)
    _HAS_TENACITY = True
except Exception:  # pragma: no cover
    _HAS_TENACITY = False


class RateLimiter:
    """限制并发的轻量包装。"""

    def __init__(self, max_concurrency: int = 10):
        self._sem = asyncio.Semaphore(max_concurrency)

    async def run(self, coro_fn: Callable[[], Awaitable[T]]) -> T:
        async with self._sem:
            if _HAS_TENACITY:
                return await self._with_retry(coro_fn)
            return await coro_fn()

    @staticmethod
    async def _with_retry(coro_fn: Callable[[], Awaitable[T]]) -> T:  # pragma: no cover
        @retry(stop=stop_after_attempt(4),
               wait=wait_exponential(multiplier=1, min=2, max=16),
               retry=retry_if_exception_type(Exception),
               reraise=True)
        async def _call():
            return await coro_fn()
        return await _call()
