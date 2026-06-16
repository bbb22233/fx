"""通用百分位（指标 8/9/15/16 共用）。

定义：当前值在「过去窗口」里的百分位排名 = 窗口内严格小于当前值的占比。
- 窗口取末尾 ``window`` 个值（含当前值），当前值与其余 ``window-1`` 个比较。
- 唯一最大 → 100；唯一最小 → 0；空/不足返回 NaN/50。

这样 ``rank > 90`` 直观表示「当前值处于近 N 根的前 10% 高位」。
"""

from __future__ import annotations

from typing import Optional, Sequence

import numpy as np


def percentile_rank(values: Sequence[float], window: Optional[int] = None) -> float:
    """返回 ``values`` 最后一个有效值在其前 ``window`` 个值中的百分位（0–100）。"""
    arr = np.asarray(values, dtype="float64")
    arr = arr[~np.isnan(arr)]
    if arr.size == 0:
        return float("nan")
    if window is not None and window > 0:
        arr = arr[-window:]
    current = arr[-1]
    others = arr[:-1]
    if others.size == 0:
        return 50.0
    return float((others < current).sum() / others.size * 100.0)
