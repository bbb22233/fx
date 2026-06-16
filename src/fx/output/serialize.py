"""把 SymbolMetrics / ScanResult 转成可展示/可持久化的 dict（看板、推送、存储共用）。"""

from __future__ import annotations

from typing import Optional

from ..models import ScanResult, SymbolMetrics


def _round(x: Optional[float], n: int = 4) -> Optional[float]:
    return None if x is None else round(float(x), n)


def symbol_summary(m: SymbolMetrics) -> dict:
    """单币的关键指标快照（用于 /symbol 与看板表格）。"""
    p1d = m.periods.get("1d")
    out = {
        "symbol": m.symbol,
        "mad21_pct": _round(m.mad21_pct, 2),
        "mad72_pct": _round(m.mad72_pct, 2),
        "mad21_pct_rank": _round(m.mad21_pct_rank, 1),
        "funding_rate": _round(m.funding_rate, 6),
        "funding_rate_pct_rank": _round(m.funding_rate_pct_rank, 1),
        "periods": {},
    }
    for tf, p in m.periods.items():
        out["periods"][tf] = {
            "close": _round(p.close),
            "amplitude_pct": _round(p.amplitude_pct, 2),
            "atr_pct": _round(p.atr_pct, 2),
            "remaining_energy_pct": _round(p.remaining_energy_pct, 2),
            "amp_pct_rank": _round(p.amp_pct_rank, 1),
            "atr_pct_rank": _round(p.atr_pct_rank, 1),
            "pctB": _round(p.pctB, 3),
            "bandwidth_pct": _round(p.bandwidth_pct, 2),
            "bandwidth_pct_rank": _round(p.bandwidth_pct_rank, 1),
        }
    return out


def result_summary(result: ScanResult) -> dict:
    """整轮扫描结果（清单 + 状态 + 各币快照）。"""
    return {
        "as_of": result.as_of.isoformat(),
        "lists": result.lists,
        "states": result.states,
        "metrics": {sym: symbol_summary(m) for sym, m in result.metrics.items()},
    }
