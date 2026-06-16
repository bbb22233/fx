"""指标 13/14：布林带 %B 与带宽%。参数 MA(21) ± 2σ。

标准差用「总体标准差」(ddof=0)，与多数图表软件默认一致。
"""

from __future__ import annotations

from typing import Tuple

import pandas as pd


def bollinger(close: pd.Series, period: int = 21, std_mult: float = 2.0
              ) -> Tuple[pd.Series, pd.Series, pd.Series]:
    """返回 (upper, middle, lower)。"""
    middle = close.rolling(period).mean()
    std = close.rolling(period).std(ddof=0)
    upper = middle + std_mult * std
    lower = middle - std_mult * std
    return upper, middle, lower


def pct_b(close: pd.Series, upper: pd.Series, lower: pd.Series) -> pd.Series:
    """指标 13：%B = (现价 − 下轨) / (上轨 − 下轨)。0=下轨、1=上轨。"""
    width = upper - lower
    return (close - lower) / width


def bandwidth_pct(upper: pd.Series, middle: pd.Series, lower: pd.Series) -> pd.Series:
    """指标 14：带宽% = (上轨 − 下轨) / 中轨 ×100。"""
    return (upper - lower) / middle * 100.0
