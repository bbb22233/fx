"""指标 5/6/7：振幅% / ATR% / 剩余动能%（时间归一化）。

ATR 采用 Wilder RMA 平滑，与 TradingView 口径一致。
"""

from __future__ import annotations

import numpy as np
import pandas as pd


def true_range(high: pd.Series, low: pd.Series, close: pd.Series) -> pd.Series:
    """真实波幅 TR = max(H-L, |H-prevC|, |L-prevC|)。首根无 prevC 时取 H-L。"""
    prev_close = close.shift(1)
    hl = high - low
    hc = (high - prev_close).abs()
    lc = (low - prev_close).abs()
    tr = pd.concat([hl, hc, lc], axis=1).max(axis=1)
    tr.iloc[0] = (high.iloc[0] - low.iloc[0]) if len(high) else np.nan
    return tr


def _rma(series: pd.Series, period: int) -> pd.Series:
    """Wilder 平滑（RMA）：以首 period 个值的 SMA 作种子，其后递推。"""
    vals = series.to_numpy(dtype="float64")
    out = np.full(vals.shape, np.nan)
    if len(vals) < period:
        return pd.Series(out, index=series.index)
    out[period - 1] = np.nanmean(vals[:period])
    for i in range(period, len(vals)):
        out[i] = (out[i - 1] * (period - 1) + vals[i]) / period
    return pd.Series(out, index=series.index)


def atr(high: pd.Series, low: pd.Series, close: pd.Series, period: int = 14) -> pd.Series:
    """ATR(period) = RMA(TrueRange, period)。"""
    return _rma(true_range(high, low, close), period)


def atr_pct(high: pd.Series, low: pd.Series, close: pd.Series, period: int = 14) -> pd.Series:
    """指标 6：ATR% = ATR(period) / 当前收盘 ×100。"""
    return atr(high, low, close, period) / close * 100.0


def amplitude_pct(high: pd.Series, low: pd.Series, close: pd.Series) -> pd.Series:
    """指标 5：振幅% = (High − Low) / 上一周期收盘 ×100（含跳空）。"""
    return (high - low) / close.shift(1) * 100.0


def remaining_energy_pct(atr_pct_value: float, amplitude_pct_value: float,
                         elapsed_fraction: float) -> float:
    """指标 7：剩余动能% = ATR% × 已过时间比例 − 振幅%。

    正数 = 比当前时间进度该有的走得慢（蓄势）；负数 = 已超进度节奏（异动）。
    """
    return atr_pct_value * elapsed_fraction - amplitude_pct_value
