"""指标 10：均线偏离度 MAD%（固定用日线 MA）。

MAD% = (现价 − 日线MA) / 日线MA ×100，对日线 MA21 与 MA72 各算一个。
是「单值」指标：与计算周期无关，每个币种只有一组值。
"""

from __future__ import annotations

import pandas as pd


def sma(series: pd.Series, period: int) -> pd.Series:
    return series.rolling(period).mean()


def mad_pct(price: float, ma_value: float) -> float:
    """(price − ma) / ma ×100。"""
    return (price - ma_value) / ma_value * 100.0


def daily_mad(daily_close: pd.Series, price: float, ma_short: int = 21,
              ma_long: int = 72) -> tuple[float, float]:
    """由日线收盘序列与当前价，算 (MAD21%, MAD72%)。"""
    ma_s = sma(daily_close, ma_short).iloc[-1]
    ma_l = sma(daily_close, ma_long).iloc[-1]
    return mad_pct(price, ma_s), mad_pct(price, ma_l)


def daily_mad_series(daily_close: pd.Series, ma_period: int) -> pd.Series:
    """历史每根 1D 的 MAD%（用于求 MAD21 百分位）。

    用每根 1D 的收盘价对其当根 MA 的偏离；当前根则在调用处用现价覆盖。
    """
    ma = sma(daily_close, ma_period)
    return (daily_close - ma) / ma * 100.0
