"""数据层与扫描编排测试 —— 全部 mock，无需 ccxt/联网。"""

import asyncio
from datetime import datetime, timedelta, timezone

import numpy as np
import pandas as pd

from fx.config import Rules, Settings, UniverseCfg
from fx.data.base import DataProvider
from fx.data.binance import override_unclosed, required_bars, to_dataframe
from fx.data.cache import KlineCache
from fx.data.universe import select_top_volume
from fx.indicators.timeframe import timeframe_seconds
from fx.scanner import batch


# ----------------------------- universe -----------------------------
def test_select_top_volume_filters_and_sorts():
    cfg = UniverseCfg(top_n=2, quote="USDT", market_type="swap", exclude_leveraged=True)
    tickers = {
        "BTC/USDT:USDT": {"quoteVolume": 100},
        "ETH/USDT:USDT": {"quoteVolume": 300},
        "SOL/USDT:USDT": {"quoteVolume": 200},
        "BTCUP/USDT:USDT": {"quoteVolume": 999},   # 杠杆代币，剔除
        "DOGE/USDT": {"quoteVolume": 999},          # 现货，非 swap，剔除
        "XRP/BTC:BTC": {"quoteVolume": 999},        # quote 非 USDT，剔除
    }
    assert select_top_volume(tickers, cfg) == ["ETH/USDT:USDT", "SOL/USDT:USDT"]


# ----------------------------- binance utils -----------------------------
def test_to_dataframe():
    ohlcv = [[1700000000000, 1, 2, 0.5, 1.5, 10],
             [1700003600000, 1.5, 3, 1, 2.5, 20]]
    df = to_dataframe(ohlcv)
    assert list(df.columns) == ["open", "high", "low", "close", "volume"]
    assert df.index.tz is not None
    assert df["close"].iloc[-1] == 2.5


def test_override_unclosed():
    df = pd.DataFrame({"open": [1, 2], "high": [2, 3], "low": [0.5, 1], "close": [1.5, 2.5]},
                      index=pd.to_datetime([1700000000000, 1700003600000], unit="ms", utc=True))
    out = override_unclosed(df, last_price=5.0)
    assert out["close"].iloc[-1] == 5.0
    assert out["high"].iloc[-1] == 5.0   # 现价高于原 high → 修正
    assert out["low"].iloc[-1] == 1.0
    # 原 df 不被改动
    assert df["close"].iloc[-1] == 2.5


def test_required_bars_depth():
    s = Settings()
    assert required_bars("4h", s) == 233 + 14 + 5
    # 1d 需衍生窗口 + MA72 深度
    assert required_bars("1d", s) == max(180 + 14, 180 + 72, 180 + 21) + 5


# ----------------------------- fake provider -----------------------------
def _make_df(n, tf, now):
    step = timeframe_seconds(tf)
    idx = pd.to_datetime([now - timedelta(seconds=step * (n - 1 - i)) for i in range(n)], utc=True)
    close = 100 + np.arange(n) * 0.1 + np.sin(np.arange(n)) * 0.5
    return pd.DataFrame({"open": close, "high": close + 1, "low": close - 1,
                         "close": close, "volume": np.ones(n)}, index=idx)


class FakeProvider(DataProvider):
    def __init__(self, now, fail=None):
        self.now = now
        self.fail = fail or set()
        self.ohlcv_calls = 0

    async def fetch_top_volume(self, n):
        return ["AAAUSDT", "BBBUSDT", "FAILUSDT"][:n] if n >= 3 else ["AAAUSDT", "BBBUSDT"]

    async def fetch_ohlcv(self, symbol, timeframe, limit):
        self.ohlcv_calls += 1
        if symbol in self.fail:
            raise RuntimeError("boom")
        return _make_df(limit, timeframe, self.now - timedelta(minutes=1))

    async def fetch_funding_history(self, symbol, limit):
        return list(np.linspace(-0.0002, 0.0003, limit))

    async def fetch_last_price(self, symbol):
        if symbol in self.fail:
            raise RuntimeError("boom")
        return 105.0


def test_run_scan_orchestration():
    now = datetime(2026, 6, 16, 0, 0, tzinfo=timezone.utc)
    provider = FakeProvider(now)
    settings = Settings()
    rules = Rules.load()
    result = asyncio.run(batch.run_scan(provider, settings, rules,
                                        symbols=["AAAUSDT", "BBBUSDT"], now=now))
    assert set(result.metrics.keys()) == {"AAAUSDT", "BBBUSDT"}
    for sym in ("AAAUSDT", "BBBUSDT"):
        assert sym in result.states               # 都被分类
        assert "1d" in result.metrics[sym].periods


def test_run_scan_skips_failures():
    now = datetime(2026, 6, 16, 0, 0, tzinfo=timezone.utc)
    provider = FakeProvider(now, fail={"FAILUSDT"})
    result = asyncio.run(batch.run_scan(provider, Settings(), Rules.load(),
                                        symbols=["AAAUSDT", "FAILUSDT"], now=now))
    assert "AAAUSDT" in result.metrics
    assert "FAILUSDT" not in result.metrics       # 失败被跳过


def test_cache_incremental():
    now = datetime(2026, 6, 16, 0, 0, tzinfo=timezone.utc)
    provider = FakeProvider(now)
    cache = KlineCache(refresh_bars=3)
    # 首轮全量
    df1 = asyncio.run(cache.get_window(provider, "AAAUSDT", "4h", 50))
    assert len(df1) == 50
    calls_after_first = provider.ohlcv_calls
    # 次轮增量（只补 3 根），长度仍为 50
    df2 = asyncio.run(cache.get_window(provider, "AAAUSDT", "4h", 50))
    assert len(df2) == 50
    assert provider.ohlcv_calls == calls_after_first + 1
