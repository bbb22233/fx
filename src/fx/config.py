"""配置加载与校验。

``settings.yaml`` → 运行参数；``rules.json`` → 规则定义。都用 pydantic 校验，
避免魔法数散落与配置笔误。
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Dict, List, Optional

import yaml
from pydantic import BaseModel, Field

_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_SETTINGS = _ROOT / "config" / "settings.yaml"
DEFAULT_RULES = _ROOT / "config" / "rules.json"


# ----------------------------- settings -----------------------------
class UniverseCfg(BaseModel):
    top_n: int = 200
    quote: str = "USDT"
    market_type: str = "swap"
    exclude_leveraged: bool = True
    refresh_minutes: int = 60


class BollingerCfg(BaseModel):
    period: int = 21
    std_mult: float = 2.0


class MadCfg(BaseModel):
    ma_short: int = 21
    ma_long: int = 72


class FundingCfg(BaseModel):
    lookback_days: int = 33
    periods_per_day: int = 3

    @property
    def lookback_periods(self) -> int:
        return self.lookback_days * self.periods_per_day


class RateLimitCfg(BaseModel):
    max_concurrency: int = 10
    enable_ccxt_ratelimit: bool = True


class RealtimeCfg(BaseModel):
    timeframe: str = "1d"          # 实时异动监控周期（默认 1D）
    energy_mult: float = 0.5       # 异动阈值：剩余动能 < −energy_mult×ATR% 即告警


class Settings(BaseModel):
    timeframes: List[str] = ["1h", "4h", "8h", "1d"]
    universe: UniverseCfg = Field(default_factory=UniverseCfg)
    percentile_window: Dict[str, int] = {"1h": 200, "4h": 233, "8h": 168, "1d": 180}
    bollinger: BollingerCfg = Field(default_factory=BollingerCfg)
    atr_period: int = 14
    mad: MadCfg = Field(default_factory=MadCfg)
    funding: FundingCfg = Field(default_factory=FundingCfg)
    derived_percentile_window: int = 180
    ratelimit: RateLimitCfg = Field(default_factory=RateLimitCfg)
    realtime: RealtimeCfg = Field(default_factory=RealtimeCfg)
    exchange: str = "binance"                       # 单所回退（向后兼容）
    exchanges: List[str] = Field(default_factory=list)  # 同时扫多家；为空则用 [exchange]
    # 各所 ccxt 选项覆盖（如 defaultType，因各所默认市场类型不同）
    exchange_options: Dict[str, dict] = Field(default_factory=dict)
    output: dict = Field(default_factory=dict)

    @property
    def active_exchanges(self) -> List[str]:
        return self.exchanges or [self.exchange]

    @classmethod
    def load(cls, path: Optional[Path] = None) -> "Settings":
        path = path or DEFAULT_SETTINGS
        data = yaml.safe_load(Path(path).read_text(encoding="utf-8")) or {}
        return cls(**data)


# ------------------------------- rules ------------------------------
class Condition(BaseModel):
    metric: str                       # 例 "pctB@1d"
    op: str                           # > < >= <= ==
    value: Optional[float] = None     # 与常量比较
    value_metric: Optional[str] = None  # 与另一指标比较
    value_mult: float = 1.0           # 乘在 value_metric 上


class ListRule(BaseModel):
    label: str
    state: str                        # 该清单要求币种处于哪个状态: A / B
    logic: str = "AND"               # AND / OR
    conditions: List[Condition]


class ClassificationRule(BaseModel):
    score_metrics: List[str]
    score_agg: str = "mean"
    high_vol_min: float = 60.0
    low_vol_max: float = 30.0


class Rules(BaseModel):
    classification: ClassificationRule
    lists: Dict[str, ListRule]

    @classmethod
    def load(cls, path: Optional[Path] = None) -> "Rules":
        path = path or DEFAULT_RULES
        data = json.loads(Path(path).read_text(encoding="utf-8"))
        data.pop("_comment", None)
        return cls(**data)
