"""Top N 成交额选币（纯函数，便于离线测试）。"""

from __future__ import annotations

import re
from typing import Dict, List

from ..config import UniverseCfg

# 杠杆代币基币名特征
_LEVERAGED = re.compile(r"(UP|DOWN|BULL|BEAR)$")


def _base_of(symbol: str) -> str:
    """从 ccxt symbol 取基币：'BTC/USDT:USDT' -> 'BTC'。"""
    return symbol.split("/", 1)[0]


def _matches_market(symbol: str, quote: str, market_type: str) -> bool:
    if market_type == "swap":
        # 线性永续：BASE/QUOTE:QUOTE
        return symbol.endswith(f"/{quote}:{quote}")
    # 现货：BASE/QUOTE（无结算后缀）
    return symbol.endswith(f"/{quote}") and ":" not in symbol


def select_top_volume(tickers: Dict[str, dict], cfg: UniverseCfg) -> List[str]:
    """从 ccxt ``fetch_tickers`` 结果挑出 24h 成交额 Top N。

    ``tickers`` 形如 ``{symbol: {"quoteVolume": float, ...}}``。
    """
    candidates = []
    for symbol, t in tickers.items():
        if not _matches_market(symbol, cfg.quote, cfg.market_type):
            continue
        if cfg.exclude_leveraged and _LEVERAGED.search(_base_of(symbol)):
            continue
        qv = t.get("quoteVolume")
        if qv is None:
            continue
        candidates.append((symbol, float(qv)))

    candidates.sort(key=lambda x: x[1], reverse=True)
    return [s for s, _ in candidates[: cfg.top_n]]
