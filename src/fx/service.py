"""ScanService —— Discord bot 与 Web 看板共享的业务大脑。

聚合：触发扫盘、查询结果/单币、订阅管理、规则查改、订阅告警计算。
适配器（Discord / FastAPI）只负责接线与展示，不放业务逻辑。
"""

from __future__ import annotations

from typing import Dict, List, Optional

from .config import Settings
from .data.base import DataProvider
from .data.cache import KlineCache
from .output.serialize import result_summary, symbol_summary
from .output.store import Store
from .rules.store import RulesStore
from .scanner import batch

# 固定清单名（与 rules.json + 观察区一致）
LIST_NAMES = ["top", "bottom", "squeeze", "watch"]


def compute_alerts(prev_lists: Optional[Dict[str, List[str]]],
                   new_lists: Dict[str, List[str]],
                   subscriptions: List[tuple]) -> Dict[str, List[str]]:
    """计算「新进清单」相对上一轮的增量，匹配订阅，返回 user_id -> 告警文案。

    订阅 target 可为清单名（关注整张清单的新进）或具体币种（该币新进任意清单）。
    """
    prev_lists = prev_lists or {}
    newly: Dict[str, List[str]] = {}
    for name, syms in new_lists.items():
        before = set(prev_lists.get(name, []))
        newly[name] = [s for s in syms if s not in before]

    alerts: Dict[str, List[str]] = {}
    for user_id, target in subscriptions:
        msgs = []
        if target in newly:                      # 订阅了某清单
            for s in newly[target]:
                msgs.append(f"🆕 {s} 新进【{target}】清单")
        else:                                    # 订阅了某币种
            for name, syms in newly.items():
                if target in syms:
                    msgs.append(f"🆕 {target} 新进【{name}】清单")
        if msgs:
            alerts.setdefault(user_id, []).extend(msgs)
    return alerts


class ScanService:
    def __init__(self, settings: Settings, store: Store,
                 rules_store: Optional[RulesStore] = None,
                 provider: Optional[DataProvider] = None):
        self.settings = settings
        self.store = store
        self.rules_store = rules_store or RulesStore()
        self.provider = provider
        self._cache = KlineCache()

    # ---- 扫盘 ----
    async def rescan(self, symbols: Optional[List[str]] = None) -> dict:
        """触发一轮扫描，落库，返回结果摘要 + 本轮订阅告警。"""
        if self.provider is None:
            raise RuntimeError("未配置数据源 provider，无法扫盘")
        rules = self.rules_store.get()
        prev = self.store.load_result()
        result = await batch.run_scan(self.provider, self.settings, rules,
                                      cache=self._cache, symbols=symbols)
        summary = result_summary(result)
        alerts = compute_alerts(prev.get("lists") if prev else None,
                                summary["lists"], self.store.all_subscriptions())
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
