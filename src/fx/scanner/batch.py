"""一轮批量扫描的主编排。

流程：选币 → 并发拉各周期 K 线（增量缓存）+ 资金费率 + 现价覆盖未收线 K
→ 算 16 指标 → 分类筛选 → ScanResult。单币失败跳过，不阻塞整轮。
"""

from __future__ import annotations

import asyncio
import logging
from datetime import datetime, timezone
from typing import Dict, List, Optional

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
    exchange = getattr(provider, "exchange_id", None)
    try:
        last_price = await provider.fetch_last_price(symbol)
        frames = {}
        for tf in settings.timeframes:
            df = await cache.get_window(provider, symbol, tf, required_bars(tf, settings))
            frames[tf] = override_unclosed(df, last_price)
        funding = await provider.fetch_funding_history(
            symbol, settings.funding.lookback_periods)
        return engine.compute(symbol, frames, settings, funding, now=now, exchange=exchange)
    except Exception as exc:  # 单币失败不阻塞整轮
        log.warning("跳过 %s@%s：%s", symbol, exchange, exc)
        return None


async def _collect_metrics(provider: DataProvider, settings: Settings,
                           cache: KlineCache, symbols: Optional[List[str]],
                           now: datetime) -> List[SymbolMetrics]:
    """对一个交易所拉数据并算指标，返回 SymbolMetrics 列表。"""
    if symbols is None:
        symbols = await provider.fetch_top_volume(settings.universe.top_n)
    sem = asyncio.Semaphore(settings.ratelimit.max_concurrency)

    async def _one(sym):
        async with sem:
            return await _build_metrics(provider, cache, sym, settings, now)

    results = await asyncio.gather(*[_one(s) for s in symbols])
    return [m for m in results if m is not None]


async def run_scan(provider: DataProvider, settings: Settings, rules: Rules,
                   cache: Optional[KlineCache] = None,
                   symbols: Optional[List[str]] = None,
                   now: Optional[datetime] = None) -> ScanResult:
    now = now or datetime.now(timezone.utc)
    cache = cache or KlineCache()
    metrics_list = await _collect_metrics(provider, settings, cache, symbols, now)
    return classifier.run(metrics_list, rules, as_of=now)


async def run_multi_scan(providers: Dict[str, DataProvider], settings: Settings,
                         rules: Rules, caches: Optional[Dict[str, KlineCache]] = None,
                         now: Optional[datetime] = None) -> ScanResult:
    """同时扫多家交易所，合并成一个 ScanResult（键按 'exchange:symbol' 区分）。

    各所并发、各自独立缓存；单所失败不阻塞其它所。
    """
    now = now or datetime.now(timezone.utc)
    caches = caches or {}

    async def _per_exchange(ex_id: str, provider: DataProvider) -> List[SymbolMetrics]:
        cache = caches.setdefault(ex_id, KlineCache())
        try:
            return await _collect_metrics(provider, settings, cache, None, now)
        except Exception as exc:  # 单所失败不阻塞其它所
            log.warning("交易所 %s 扫描失败：%s", ex_id, exc)
            return []

    per = await asyncio.gather(*[_per_exchange(eid, p) for eid, p in providers.items()])
    metrics_list = [m for sub in per for m in sub]
    return classifier.run(metrics_list, rules, as_of=now)
