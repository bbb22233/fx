"""多交易所扫描 + 工厂 + 实时配置测试（全离线）。"""

import asyncio
from datetime import datetime, timedelta, timezone

import numpy as np
import pandas as pd
import pytest

from fx.config import Rules, Settings
from fx.data.base import DataProvider
from fx.data.binance import create_provider
from fx.indicators.timeframe import timeframe_seconds
from fx.scanner import batch
from fx.scanner.realtime import RealtimeMonitor


def _make_df(n, tf, now):
    step = timeframe_seconds(tf)
    idx = pd.to_datetime([now - timedelta(seconds=step * (n - 1 - i)) for i in range(n)], utc=True)
    close = 100 + np.arange(n) * 0.1 + np.sin(np.arange(n)) * 0.5
    return pd.DataFrame({"open": close, "high": close + 1, "low": close - 1,
                         "close": close, "volume": np.ones(n)}, index=idx)


class _Fake(DataProvider):
    def __init__(self, exchange_id):
        self.exchange_id = exchange_id

    async def fetch_top_volume(self, n):
        return ["BTCUSDT"]                 # 两所都有同一币种

    async def fetch_ohlcv(self, symbol, timeframe, limit):
        return _make_df(limit, timeframe, datetime.now(timezone.utc) - timedelta(minutes=1))

    async def fetch_funding_history(self, symbol, limit):
        return list(np.linspace(-0.0002, 0.0003, limit))

    async def fetch_last_price(self, symbol):
        return 105.0


def test_run_multi_scan_namespaces_keys():
    providers = {"binance": _Fake("binance"), "okx": _Fake("okx")}
    result = asyncio.run(batch.run_multi_scan(providers, Settings(), Rules.load()))
    # 同名币在两所不撞键
    assert set(result.metrics.keys()) == {"binance:BTCUSDT", "okx:BTCUSDT"}
    assert result.metrics["binance:BTCUSDT"].exchange == "binance"
    assert "binance:BTCUSDT" in result.states and "okx:BTCUSDT" in result.states


def test_run_multi_scan_one_exchange_failure_isolated():
    class _Boom(_Fake):
        async def fetch_top_volume(self, n):
            raise RuntimeError("down")

    providers = {"binance": _Fake("binance"), "bybit": _Boom("bybit")}
    result = asyncio.run(batch.run_multi_scan(providers, Settings(), Rules.load()))
    # bybit 整所失败不影响 binance
    assert "binance:BTCUSDT" in result.metrics
    assert not any(k.startswith("bybit:") for k in result.metrics)


def test_create_provider_rejects_unknown():
    with pytest.raises(ValueError):
        create_provider("kraken", Settings())


def test_single_provider_key_unchanged():
    """单所(无 exchange_id)行为不变：键仍是裸 symbol。"""
    result = asyncio.run(batch.run_scan(_Fake(None), Settings(), Rules.load(),
                                        symbols=["BTCUSDT"]))
    assert list(result.metrics.keys()) == ["BTCUSDT"]


def test_realtime_config_defaults():
    s = Settings()
    assert s.realtime.timeframe == "1d"
    assert s.realtime.energy_mult == 0.5
    assert RealtimeMonitor().timeframe == "1d"


def test_active_exchanges():
    assert Settings(exchange="binance").active_exchanges == ["binance"]
    assert Settings(exchanges=["okx", "bybit"]).active_exchanges == ["okx", "bybit"]
