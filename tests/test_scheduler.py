"""调度 cron 映射 + 实时现价缓存测试（离线）。"""

import pytest

from fx.scanner.realtime import PriceCache
from fx.scanner.scheduler import timeframe_cron


def test_timeframe_cron_hours():
    assert timeframe_cron("1h")["hour"] == "*"
    assert timeframe_cron("4h")["hour"] == "0,4,8,12,16,20"
    assert timeframe_cron("8h")["hour"] == "0,8,16"
    assert timeframe_cron("1d")["hour"] == 0
    # 都在整点 + 延迟、UTC
    for tf in ("1h", "4h", "8h", "1d"):
        c = timeframe_cron(tf)
        assert c["minute"] == 0 and c["timezone"] == "UTC"


def test_timeframe_cron_invalid():
    with pytest.raises(ValueError):
        timeframe_cron("2h")


def test_price_cache():
    pc = PriceCache()
    assert pc.get("BTCUSDT") is None
    pc.update("BTCUSDT", 100.0)
    assert pc.get("BTCUSDT") == 100.0
