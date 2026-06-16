"""历史 K 线窗口的增量缓存。

首轮全量拉满所需窗口；之后每轮只补最新几根并合并去重、裁剪到所需长度，
大幅降低稳态请求量。
"""

from __future__ import annotations

from typing import Dict, Tuple

import pandas as pd

from .base import DataProvider


class KlineCache:
    def __init__(self, refresh_bars: int = 3):
        # 每轮增量补拉的根数（覆盖未收线 + 最近新收线）
        self._refresh_bars = refresh_bars
        self._store: Dict[Tuple[str, str], pd.DataFrame] = {}

    async def get_window(self, provider: DataProvider, symbol: str, timeframe: str,
                         required: int) -> pd.DataFrame:
        key = (symbol, timeframe)
        cached = self._store.get(key)

        if cached is None or len(cached) < required:
            df = await provider.fetch_ohlcv(symbol, timeframe, required)
        else:
            recent = await provider.fetch_ohlcv(symbol, timeframe, self._refresh_bars)
            df = pd.concat([cached, recent])
            df = df[~df.index.duplicated(keep="last")].sort_index()

        df = df.tail(required)
        self._store[key] = df
        return df
