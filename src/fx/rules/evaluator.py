"""扁平条件组求值器。

一条 ``Condition`` 把某指标与「常量」或「另一指标×倍数」比较；一个 ``ListRule``
用 AND/OR 组合多条。不上递归 DSL —— 足以表达本期全部清单规则。
"""

from __future__ import annotations

import math
import operator
from typing import Optional

from ..config import Condition, ListRule
from ..models import SymbolMetrics

_OPS = {
    ">": operator.gt,
    "<": operator.lt,
    ">=": operator.ge,
    "<=": operator.le,
    "==": operator.eq,
}


def _is_valid(x: Optional[float]) -> bool:
    return x is not None and not (isinstance(x, float) and math.isnan(x))


def evaluate_condition(metrics: SymbolMetrics, cond: Condition) -> bool:
    lhs = metrics.get(cond.metric)
    if not _is_valid(lhs):
        return False

    if cond.value_metric is not None:
        rhs_base = metrics.get(cond.value_metric)
        if not _is_valid(rhs_base):
            return False
        rhs = rhs_base * cond.value_mult
    else:
        rhs = cond.value
    if not _is_valid(rhs):
        return False

    op = _OPS.get(cond.op)
    if op is None:
        raise ValueError(f"不支持的比较符: {cond.op!r}")
    return bool(op(lhs, rhs))


def evaluate_list(metrics: SymbolMetrics, rule: ListRule) -> bool:
    results = (evaluate_condition(metrics, c) for c in rule.conditions)
    if rule.logic.upper() == "OR":
        return any(results)
    return all(results)
