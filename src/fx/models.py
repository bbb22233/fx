"""贯穿全程的数据结构。

指标层产出 ``SymbolMetrics``，规则层消费它。``SymbolMetrics.get`` 提供
统一的 ``metric@timeframe`` 命名空间寻址，让规则配置与指标实现解耦。
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Dict, List, Optional


@dataclass
class PeriodMetrics:
    """单个币种在单个周期上的指标快照。"""

    timeframe: str
    open: float
    high: float
    low: float
    close: float
    amplitude_pct: float            # (High-Low)/上一周期收盘 ×100
    atr_pct: float                  # ATR(14)/当前收盘 ×100
    remaining_energy_pct: float     # ATR%×已过时间比例 − 振幅%
    amp_pct_rank: float             # 振幅% 在过去 N 根的百分位
    atr_pct_rank: float             # ATR% 在过去 N 根的百分位
    pctB: float                     # 布林带 %B
    bandwidth_pct: float            # 布林带带宽%
    bandwidth_pct_rank: Optional[float] = None  # 带宽% 的百分位（仅 1D 计算）


@dataclass
class SymbolMetrics:
    """一个币种的全部 16 项指标（4 周期 + 单值）。"""

    symbol: str
    periods: Dict[str, PeriodMetrics] = field(default_factory=dict)
    # 单值指标（不分周期）
    mad21_pct: Optional[float] = None        # 现价 vs 日线 MA21
    mad72_pct: Optional[float] = None         # 现价 vs 日线 MA72
    mad21_pct_rank: Optional[float] = None    # MAD21% 在过去 180 根 1D 的百分位
    funding_rate: Optional[float] = None      # 最新一期资金费率（原始值，如 0.0001）
    funding_rate_pct_rank: Optional[float] = None  # 资金费率在过去 33 天的百分位
    as_of: datetime = field(default_factory=lambda: datetime.now(timezone.utc))

    # ---- 指标寻址 ----
    def get(self, ref: str) -> Optional[float]:
        """按 ``key`` 或 ``key@timeframe`` 取指标值，找不到返回 None。

        例：``pctB@1d``、``atr_pct_rank@4h``、``mad21_pct_rank``、``funding_rate``。
        """
        if "@" in ref:
            key, tf = ref.split("@", 1)
            period = self.periods.get(tf)
            if period is None:
                return None
            return getattr(period, key, None)
        return getattr(self, ref, None)


@dataclass
class ScanResult:
    """某一轮扫描的产物。"""

    as_of: datetime
    # symbol -> 状态: "A"(中/高波动) / "B"(低波动) / "watch"(过渡观察区)
    states: Dict[str, str] = field(default_factory=dict)
    # 清单名 -> 命中币种列表。固定清单: top / bottom / squeeze / watch
    lists: Dict[str, List[str]] = field(default_factory=dict)
    # symbol -> 指标快照（看板/推送展示用）
    metrics: Dict[str, SymbolMetrics] = field(default_factory=dict)
