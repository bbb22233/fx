"""分类器：波动分 → A/B/观察 → 顶/底/收口清单。

第一级（波动分分流）是结构性逻辑，硬编码；阈值与各清单条件来自 ``Rules`` 配置。
"""

from __future__ import annotations

import math
from datetime import datetime, timezone
from typing import Iterable, List, Optional

from ..config import Rules
from ..models import ScanResult, SymbolMetrics
from .evaluator import evaluate_list


def volatility_score(metrics: SymbolMetrics, rules: Rules) -> Optional[float]:
    """波动分 = score_metrics 的聚合（默认 mean）。任一缺失则返回 None。"""
    vals = [metrics.get(ref) for ref in rules.classification.score_metrics]
    if any(v is None or (isinstance(v, float) and math.isnan(v)) for v in vals):
        return None
    if rules.classification.score_agg == "mean":
        return sum(vals) / len(vals)
    raise ValueError(f"不支持的聚合: {rules.classification.score_agg!r}")


def classify_state(metrics: SymbolMetrics, rules: Rules) -> Optional[str]:
    """返回 'A'(中/高波动) / 'B'(低波动) / 'watch'(过渡观察区) / None(数据不足)。"""
    score = volatility_score(metrics, rules)
    if score is None:
        return None
    c = rules.classification
    if score >= c.high_vol_min:
        return "A"
    if score <= c.low_vol_max:
        return "B"
    return "watch"


def run(metrics_list: Iterable[SymbolMetrics], rules: Rules,
        as_of: Optional[datetime] = None) -> ScanResult:
    """对一批币种跑完整分类与清单筛选。"""
    result = ScanResult(as_of=as_of or datetime.now(timezone.utc))
    result.lists = {name: [] for name in rules.lists}
    result.lists["watch"] = []

    for m in metrics_list:
        result.metrics[m.symbol] = m
        state = classify_state(m, rules)
        if state is None:
            continue
        result.states[m.symbol] = state

        if state == "watch":
            result.lists["watch"].append(m.symbol)
            continue

        # A/B：套用该状态下的各清单条件
        for name, rule in rules.lists.items():
            if rule.state != state:
                continue
            if evaluate_list(m, rule):
                result.lists[name].append(m.symbol)

    return result
