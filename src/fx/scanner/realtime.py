"""实时监控（P7 骨架）：WS 现价流 → 更新未收线 K 的现价 + 实时异动告警。

完整指标重算仍由收线 cron 驱动；此处只维护现价缓存并对剧烈异动即时告警，
避免每个 tick 全量重算。具体阈值化告警逻辑可后续扩展。
"""

from __future__ import annotations

from typing import Dict


class PriceCache:
    """symbol -> 最新现价，供未收线 K 覆盖与实时告警使用。"""

    def __init__(self):
        self._prices: Dict[str, float] = {}

    def update(self, symbol: str, price: float) -> None:
        self._prices[symbol] = price

    def get(self, symbol: str) -> float | None:
        return self._prices.get(symbol)


async def watch(provider, symbols, price_cache: PriceCache):  # pragma: no cover - 需 WS/网络
    """订阅 WS 行情，持续更新现价缓存。"""
    async for ticker in provider.watch_tickers(symbols):
        sym = ticker.get("symbol")
        last = ticker.get("last")
        if sym and last is not None:
            price_cache.update(sym, float(last))
