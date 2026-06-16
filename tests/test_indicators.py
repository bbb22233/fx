"""指标黄金测试 —— 数值均为手算期望值。"""

from datetime import datetime, timedelta, timezone

import numpy as np
import pandas as pd
import pytest

from fx.indicators import bollinger, funding, mad, ohlc
from fx.indicators.percentile import percentile_rank
from fx.indicators.timeframe import elapsed_fraction, timeframe_seconds


def test_percentile_rank_basic():
    assert percentile_rank([1, 2, 3, 4, 5]) == 100.0      # 末值最大
    assert percentile_rank([5, 4, 3, 2, 1]) == 0.0        # 末值最小
    assert percentile_rank([1, 2, 3, 4, 10], window=3) == 100.0
    assert percentile_rank([]) != percentile_rank([])     # NaN != NaN


def test_percentile_rank_window_and_nan():
    # 窗口只取末 3 个 [3,4,2]，当前=2，others=[3,4] 无小于 → 0
    assert percentile_rank([9, 9, 3, 4, 2], window=3) == 0.0
    # NaN 被忽略
    assert percentile_rank([1, 2, np.nan, 3]) == 100.0


def test_amplitude_pct():
    high = pd.Series([11, 12], dtype=float)
    low = pd.Series([9, 8], dtype=float)
    close = pd.Series([10, 11], dtype=float)
    amp = ohlc.amplitude_pct(high, low, close)
    assert np.isnan(amp.iloc[0])
    assert amp.iloc[1] == pytest.approx(40.0)  # (12-8)/10*100


def test_atr_pct_wilder():
    high = pd.Series([10, 12, 15, 14], dtype=float)
    low = pd.Series([5, 7, 9, 8], dtype=float)
    close = pd.Series([8, 11, 10, 13], dtype=float)
    # TR=[5,5,6,6]；RMA(3): seed=16/3，末值=(seed*2+6)/3≈5.5556
    atrp = ohlc.atr_pct(high, low, close, period=3)
    assert atrp.iloc[-1] == pytest.approx(5.55556 / 13 * 100, rel=1e-4)


def test_bollinger_pctb_bandwidth():
    close = pd.Series([10, 11, 12, 13, 14], dtype=float)
    upper, middle, lower = bollinger.bollinger(close, period=5, std_mult=2.0)
    pctb = bollinger.pct_b(close, upper, lower)
    bw = bollinger.bandwidth_pct(upper, middle, lower)
    assert middle.iloc[-1] == pytest.approx(12.0)
    assert pctb.iloc[-1] == pytest.approx(0.853553, rel=1e-5)
    assert bw.iloc[-1] == pytest.approx(47.14045, rel=1e-5)


def test_mad():
    assert mad.mad_pct(110, 100) == pytest.approx(10.0)
    assert mad.mad_pct(90, 100) == pytest.approx(-10.0)


def test_remaining_energy():
    # ATR%=10, 已过一半时间 → 该走 5，实际走 3 → 剩余 +2（蓄势）
    assert ohlc.remaining_energy_pct(10.0, 3.0, 0.5) == pytest.approx(2.0)
    # 实际走 8 > 该走 5 → 剩余 -3（异动）
    assert ohlc.remaining_energy_pct(10.0, 8.0, 0.5) == pytest.approx(-3.0)


def test_timeframe_seconds():
    assert timeframe_seconds("1h") == 3600
    assert timeframe_seconds("4h") == 14400
    assert timeframe_seconds("1d") == 86400


def test_elapsed_fraction():
    now = datetime(2026, 1, 1, 1, 0, tzinfo=timezone.utc)
    open_4h = now - timedelta(hours=1)
    assert elapsed_fraction(open_4h, "4h", now) == pytest.approx(0.25)
    # 超过周期 → clamp 1.0（已收线）
    open_old = now - timedelta(hours=5)
    assert elapsed_fraction(open_old, "4h", now) == 1.0


def test_funding_percentile():
    hist = [0.0001] * 98 + [0.0005]
    assert funding.latest_funding_rate(hist) == pytest.approx(0.0005)
    assert funding.funding_rate_percentile(hist, 99) == pytest.approx(100.0)
