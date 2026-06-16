"""一轮批量扫描的主编排。

流程：选币 → 并发拉各周期 K 线（增量缓存）+ 资金费率 + 现价覆盖未收线 K
→ 算 16 指标 → 分类筛选 → ScanResult。单币失败跳过，不阻塞整轮。
"""

from __future__ import annotations

import asyncio
import logging
from datetime import datetime, timezone
from typing import List, Optional

from ..config import Rules, Settings
from ..data.base import DataProvider
from ..data.binance import override_unclosed, required_bars
from ..data.cache import KlineCache
from ..indicators import engine
from ..models import ScanResult, SymbolMetrics
from ..rules import classifier

log = logging.getLogger(__name__)


async def _build_metrics(provider: DataProvider, cache: KlineCache, symbol: str,
                         settings: Settings, now: datetime) -> Optional[SymbolMetrics]:
    try:
        last_price = await provider.fetch_last_price(symbol)
        frames = {}
        for tf in settings.timeframes:
            df = await cache.get_window(provider, symbol, tf, required_bars(tf, settings))
            frames[tf] = override_unclosed(df, last_price)
        funding = await provider.fetch_funding_history(
            symbol, settings.funding.lookback_periods)
        return engine.compute(symbol, frames, settings, funding, now=now)
    except Exception as exc:  # 单币失败不阻塞整轮
        log.warning("跳过 %s：%s", symbol, exc)
        return None


async def run_scan(provider: DataProvider, settings: Settings, rules: Rules,
                   cache: Optional[KlineCache] = None,
                   symbols: Optional[List[str]] = None,
                   now: Optional[datetime] = None) -> ScanResult:
    now = now or datetime.now(timezone.utc)
    cache = cache or KlineCache()
    if symbols is None:
        symbols = await provider.fetch_top_volume(settings.universe.top_n)

    sem = asyncio.Semaphore(settings.ratelimit.max_concurrency)

    async def _one(sym):
        async with sem:
            return await _build_metrics(provider, cache, sym, settings, now)

    results = await asyncio.gather(*[_one(s) for s in symbols])
    metrics_list = [m for m in results if m is not None]
    return classifier.run(metrics_list, rules, as_of=now)
