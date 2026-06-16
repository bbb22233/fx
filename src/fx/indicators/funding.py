"""指标 11/12：资金费率与资金费率百分位（单值，不分周期）。"""

from __future__ import annotations

from typing import Sequence

from .percentile import percentile_rank


def latest_funding_rate(funding_history: Sequence[float]) -> float:
    """最新一期资金费率（原始值，如 0.0001 = 0.01%）。"""
    return float(funding_history[-1]) if len(funding_history) else float("nan")


def funding_rate_percentile(funding_history: Sequence[float], lookback_periods: int = 99) -> float:
    """当前资金费率在过去 lookback_periods 期（≈33天）里的百分位（0–100）。"""
    return percentile_rank(funding_history, window=lookback_periods)
