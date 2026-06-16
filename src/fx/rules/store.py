"""规则读写：加载 rules.json、按点路径改阈值并校验后回写。

供 Discord ``/rules`` ``/setrule`` 与 Web 可视化编辑共用同一存储与 schema。
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from ..config import DEFAULT_RULES, Rules


class RulesStore:
    def __init__(self, path: Path = None):
        self.path = Path(path or DEFAULT_RULES)

    def _raw(self) -> dict:
        return json.loads(self.path.read_text(encoding="utf-8"))

    def get(self) -> Rules:
        return Rules.load(self.path)

    def describe(self) -> dict:
        """返回当前可编辑阈值（用于展示）。"""
        r = self.get()
        out = {
            "classification.high_vol_min": r.classification.high_vol_min,
            "classification.low_vol_max": r.classification.low_vol_max,
        }
        for name, lst in r.lists.items():
            for i, c in enumerate(lst.conditions):
                thr = c.value if c.value is not None else f"{c.value_mult}×{c.value_metric}"
                out[f"lists.{name}.conditions.{i}.value"] = f"{c.metric} {c.op} {thr}"
        return out

    def set_value(self, path: str, value: Any) -> Rules:
        """按点路径设置一个值，校验通过后回写。返回新的 Rules。

        path 例：``classification.high_vol_min``、``lists.top.conditions.0.value``。
        列表索引用整数段表示。
        """
        data = self._raw()
        data.pop("_comment", None)
        node = data
        parts = path.split(".")
        for p in parts[:-1]:
            node = node[int(p)] if isinstance(node, list) else node[p]
        last = parts[-1]
        # 尽量转成 float（阈值多为数值）
        try:
            value = float(value)
        except (TypeError, ValueError):
            pass
        if isinstance(node, list):
            node[int(last)] = value
        else:
            node[last] = value

        rules = Rules(**data)            # 校验
        self.path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
        return rules
