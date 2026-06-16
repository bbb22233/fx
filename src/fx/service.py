"""ScanService —— Discord bot 与 Web 看板共享的业务大脑。

聚合：触发扫盘、查询结果/单币、订阅管理、规则查改、订阅告警计算。
适配器（Discord / FastAPI）只负责接线与展示，不放业务逻辑。
"""

from __future__ import annotations

from typing import Dict, List, Optional, Union

from .config import Settings
from .data.base import DataProvider
from .data.cache import KlineCache
from .output.serialize import (collapse_by_symbol, format_symbol_entry,
                               result_summary, symbol_summary)
from .output.store import Store
from .rules.store import RulesStore
from .scanner import batch

# 固定清单名（与 rules.json + 观察区一致）
LIST_NAMES = ["top", "bottom", "squeeze", "watch"]


def compute_alerts(prev_lists: Optional[Dict[str, List[str]]],
                   new_lists: Dict[str, List[str]],
                   subscriptions: List[tuple],
                   metrics: Optional[dict] = None,
                   prev_metrics: Optional[dict] = None) -> Dict[str, List[str]]:
    """计算「新进清单」相对上一轮的增量，匹配订阅，返回 user_id -> 告警文案。

    判定与文案都在**币级**：同一币种在多个交易所命中只算一次、只发一条（合并交易所标签）。
    metrics/prev_metrics 缺省时退化为裸 symbol（单所行为不变）。
    订阅 target 可为清单名（关注整张清单的新进）或具体币种（该币新进任意清单）。
    """
    prev_lists = prev_lists or {}
    # 上一轮各清单已在的币种集合（币级）
    prev_coin = {name: {e["symbol"] for e in collapse_by_symbol(keys, prev_metrics)}
                 for name, keys in prev_lists.items()}
    # 本轮各清单新进的币种条目（symbol 不在上一轮该清单 → 首次进入）
    newly: Dict[str, list] = {}
    for name, keys in new_lists.items():
        before = prev_coin.get(name, set())
        newly[name] = [e for e in collapse_by_symbol(keys, metrics)
                       if e["symbol"] not in before]

    alerts: Dict[str, List[str]] = {}
    for user_id, target in subscriptions:
        msgs = []
        if target in newly:                      # 订阅了某清单
            for e in newly[target]:
                msgs.append(f"🆕 {format_symbol_entry(e)} 新进【{target}】清单")
        else:                                    # 订阅了某币种
            for name, entries in newly.items():
                for e in entries:
                    if e["symbol"] == target:
                        msgs.append(f"🆕 {format_symbol_entry(e)} 新进【{name}】清单")
        if msgs:
            alerts.setdefault(user_id, []).extend(msgs)
    return alerts


class ScanService:
    def __init__(self, settings: Settings, store: Store,
                 rules_store: Optional[RulesStore] = None,
                 provider: Union[DataProvider, Dict[str, DataProvider], None] = None):
        self.settings = settings
        self.store = store
        self.rules_store = rules_store or RulesStore()
        # 统一存成 dict: exchange_id -> provider（单个也包成 dict）
        if provider is None:
            self.providers: Dict[str, DataProvider] = {}
        elif isinstance(provider, dict):
            self.providers = provider
        else:
            eid = getattr(provider, "exchange_id", None) or "default"
            self.providers = {eid: provider}
        self._caches: Dict[str, KlineCache] = {}

    # ---- 扫盘 ----
    async def rescan(self, symbols: Optional[List[str]] = None) -> dict:
        """触发一轮扫描（多交易所同时），落库，返回结果摘要 + 本轮订阅告警。"""
        if not self.providers:
            raise RuntimeError("未配置数据源 provider，无法扫盘")
        rules = self.rules_store.get()
        prev = self.store.load_result()
        if len(self.providers) == 1 and symbols is not None:
            # 指定 symbols 的单所路径（保留给测试/精确扫描）
            (eid, prov), = self.providers.items()
            cache = self._caches.setdefault(eid, KlineCache())
            result = await batch.run_scan(prov, self.settings, rules,
                                          cache=cache, symbols=symbols)
        else:
            result = await batch.run_multi_scan(self.providers, self.settings, rules,
                                                caches=self._caches)
        summary = result_summary(result)
        alerts = compute_alerts(prev.get("lists") if prev else None,
                                summary["lists"], self.store.all_subscriptions(),
                                metrics=summary["metrics"],
                                prev_metrics=prev.get("metrics") if prev else None)
        self.store.save_result(summary)
        summary["alerts"] = alerts
        return summary

    # ---- 查询 ----
    def get_latest(self) -> Optional[dict]:
        return self.store.load_result()

    def get_list(self, name: str) -> List[str]:
        latest = self.get_latest()
        return (latest or {}).get("lists", {}).get(name, [])

    def get_symbol(self, symbol: str) -> Optional[dict]:
        latest = self.get_latest()
        if not latest:
            return None
        return latest.get("metrics", {}).get(symbol)

    # ---- 订阅 ----
    def subscribe(self, user_id: str, target: str) -> bool:
        return self.store.add_subscription(user_id, target)

    def unsubscribe(self, user_id: str, target: str) -> bool:
        return self.store.remove_subscription(user_id, target)

    def list_subscriptions(self, user_id: str) -> List[str]:
        return self.store.list_subscriptions(user_id)

    # ---- 规则 ----
    def describe_rules(self) -> dict:
        return self.rules_store.describe()

    def set_rule(self, path: str, value) -> dict:
        self.rules_store.set_value(path, value)
        return self.describe_rules()

    def get_rules_doc(self) -> dict:
        """完整结构化规则文档（Web 可视化编辑器初始化用）。"""
        return self.rules_store.raw_rules()

    def replace_rules(self, data: dict) -> dict:
        """整文档替换规则（Web 编辑器保存）。校验失败抛 ValidationError。"""
        self.rules_store.replace(data)
        return self.get_rules_doc()
