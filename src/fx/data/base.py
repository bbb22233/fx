"""DataProvider 抽象基类 —— 可插拔数据层的契约。

换交易所只需实现本接口（Binance / OKX / Bybit ...）。指标层只依赖此契约，
不关心数据来源。
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import AsyncIterator, List, Sequence

import pandas as pd


class DataProvider(ABC):
    """统一数据访问接口。"""

    @abstractmethod
    async def fetch_top_volume(self, n: int) -> List[str]:
        """按 24h 成交额返回 Top N 的 symbol 列表。"""

    @abstractmethod
    async def fetch_ohlcv(self, symbol: str, timeframe: str, limit: int) -> pd.DataFrame:
        """返回含 open/high/low/close/volume 列、UTC DatetimeIndex（升序）的 K 线。

        最后一行可为未收线 K。
        """

    @abstractmethod
    async def fetch_funding_history(self, symbol: str, limit: int) -> Sequence[float]:
        """返回最近 limit 期资金费率（升序，原始值）。"""

    @abstractmethod
    async def fetch_last_price(self, symbol: str) -> float:
        """最新成交价（用于覆盖未收线 K 的 close）。"""

    async def watch_tickers(self, symbols: Sequence[str]) -> AsyncIterator[dict]:
        """（可选）WS 实时行情流。默认未实现。"""
        raise NotImplementedError
        yield  # pragma: no cover
