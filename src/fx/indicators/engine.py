"""指标编排：对一个币种算齐 16 项指标 → SymbolMetrics。

输入约定：``frames`` 是 ``{timeframe: DataFrame}``，每个 DataFrame 含
``open/high/low/close`` 列与 UTC DatetimeIndex（升序）。最后一行可为未收线 K，
其 ``close`` 应已被现价覆盖（由数据层负责）。
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Dict, Optional, Sequence

import pandas as pd

from ..config import Settings
from ..models import PeriodMetrics, SymbolMetrics
from . import bollinger, mad, ohlc
from .funding import funding_rate_percentile, latest_funding_rate
from .percentile import percentile_rank
from .timeframe import elapsed_fraction


def _period_metrics(tf: str, df: pd.DataFrame, settings: Settings,
                    now: datetime) -> PeriodMetrics:
    high, low, close, open_ = df["high"], df["low"], df["close"], df["open"]
    n = settings.percentile_window.get(tf)

    amp = ohlc.amplitude_pct(high, low, close)
    atrp = ohlc.atr_pct(high, low, close, settings.atr_period)
    upper, middle, lower = bollinger.bollinger(
        close, settings.bollinger.period, settings.bollinger.std_mult)
    pctb = bollinger.pct_b(close, upper, lower)
    bw = bollinger.bandwidth_pct(upper, middle, lower)

    amp_last = float(amp.iloc[-1])
    atr_last = float(atrp.iloc[-1])
    elapsed = elapsed_fraction(df.index[-1].to_pydatetime(), tf, now)

    bw_rank = None
    if tf == "1d":
        bw_rank = percentile_rank(bw.to_numpy(), settings.derived_percentile_window)

    return PeriodMetrics(
        timeframe=tf,
        open=float(open_.iloc[-1]),
        high=float(high.iloc[-1]),
        low=float(low.iloc[-1]),
        close=float(close.iloc[-1]),
        amplitude_pct=amp_last,
        atr_pct=atr_last,
        remaining_energy_pct=ohlc.remaining_energy_pct(atr_last, amp_last, elapsed),
        amp_pct_rank=percentile_rank(amp.to_numpy(), n),
        atr_pct_rank=percentile_rank(atrp.to_numpy(), n),
        pctB=float(pctb.iloc[-1]),
        bandwidth_pct=float(bw.iloc[-1]),
        bandwidth_pct_rank=bw_rank,
    )


def compute(symbol: str, frames: Dict[str, pd.DataFrame], settings: Settings,
            funding_history: Optional[Sequence[float]] = None,
            now: Optional[datetime] = None) -> SymbolMetrics:
    """算齐一个币种的全部指标。"""
    now = now or datetime.now(timezone.utc)
    m = SymbolMetrics(symbol=symbol, as_of=now)

    for tf, df in frames.items():
        if df is None or len(df) == 0:
            continue
        m.periods[tf] = _period_metrics(tf, df, settings, now)

    # 单值指标：基于日线
    daily = frames.get("1d")
    if daily is not None and len(daily):
        price = float(daily["close"].iloc[-1])
        m.mad21_pct, m.mad72_pct = mad.daily_mad(
            daily["close"], price, settings.mad.ma_short, settings.mad.ma_long)
        mad21_series = mad.daily_mad_series(daily["close"], settings.mad.ma_short)
        m.mad21_pct_rank = percentile_rank(
            mad21_series.to_numpy(), settings.derived_percentile_window)

    if funding_history is not None and len(funding_history):
        m.funding_rate = latest_funding_rate(funding_history)
        m.funding_rate_pct_rank = funding_rate_percentile(
            funding_history, settings.funding.lookback_periods)

    return m
