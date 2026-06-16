"""周期工具：周期字符串 ↔ 秒数，以及"已过时间比例"计算。"""

from __future__ import annotations

from datetime import datetime, timezone

_UNIT_SECONDS = {"m": 60, "h": 3600, "d": 86400, "w": 604800}


def timeframe_seconds(timeframe: str) -> int:
    """'1h' -> 3600, '4h' -> 14400, '1d' -> 86400。"""
    tf = timeframe.strip().lower()
    unit = tf[-1]
    if unit not in _UNIT_SECONDS:
        raise ValueError(f"无法识别的周期: {timeframe!r}")
    qty = int(tf[:-1])
    return qty * _UNIT_SECONDS[unit]


def elapsed_fraction(open_time: datetime, timeframe: str, now: datetime) -> float:
    """当前 K 线「已过时间比例」，clamp 到 (0, 1]。

    = (now − openTime) / 周期长度。已收线（now ≥ 收线时刻）记为 1.0。
    要求 open_time / now 都是带 tz 的 UTC（或可被视为 UTC）。
    """
    if open_time.tzinfo is None:
        open_time = open_time.replace(tzinfo=timezone.utc)
    if now.tzinfo is None:
        now = now.replace(tzinfo=timezone.utc)
    span = timeframe_seconds(timeframe)
    elapsed = (now - open_time).total_seconds()
    frac = elapsed / span
    if frac <= 0:
        # now 早于或等于开盘：视为刚开盘的一个极小正比例，避免除零/负数
        return 1.0 / span
    return min(frac, 1.0)
