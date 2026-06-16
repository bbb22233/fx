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
        "exchange": m.exchange,
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


def collapse_by_symbol(keys, metrics: dict) -> list:
    """把清单里的 key（可能是 ``exchange:symbol``）按币种去重，合并各交易所。

    返回 ``[{"symbol", "exchanges"}]``，保持首见顺序。单所(exchange=None)时
    exchanges 为 ``[None]``，展示层退化为裸 symbol（最干净）。用 metrics 里携带的
    symbol/exchange 字段还原，避免对含 ``:`` 的 symbol 做歧义字符串切分。
    """
    out: dict = {}
    for k in keys:
        m = metrics.get(k) or {}
        sym = m.get("symbol", k)
        ex = m.get("exchange")
        exchanges = out.setdefault(sym, [])
        if ex not in exchanges:
            exchanges.append(ex)
    return [{"symbol": sym, "exchanges": exs} for sym, exs in out.items()]


def format_symbol_entry(entry: dict) -> str:
    """去重条目 → 展示串：单所为 ``BTC/USDT:USDT``，多所为 ``BTC/USDT:USDT [binance, okx]``。"""
    exs = [e for e in entry["exchanges"] if e]
    return entry["symbol"] + (f" [{', '.join(exs)}]" if exs else "")


def result_summary(result: ScanResult) -> dict:
    """整轮扫描结果（清单 + 状态 + 各币快照）。"""
    return {
        "as_of": result.as_of.isoformat(),
        "lists": result.lists,
        "states": result.states,
        "metrics": {sym: symbol_summary(m) for sym, m in result.metrics.items()},
    }
