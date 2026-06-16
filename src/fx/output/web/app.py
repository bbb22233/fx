"""FastAPI 看板 + 规则可视化编辑 + JSON API。

``create_app(service)`` 工厂注入 ScanService；fastapi 懒加载，未安装时本模块
仍可导入。看板页面极简：读最新结果渲染四张清单表。规则编辑页见 ``editor.py``。
"""

from __future__ import annotations

import dataclasses

from ...models import PeriodMetrics, SymbolMetrics
from ...service import LIST_NAMES
from ..discord_bot.commands import LIST_LABELS
from .editor import EDITOR_HTML

_OPS = [">", "<", ">=", "<=", "=="]
_LOGICS = ["AND", "OR"]
_STATES = ["A", "B"]
# 指标目录：从数据类字段派生（与 models 单一事实源保持一致）
_PERIOD_METRICS = [f.name for f in dataclasses.fields(PeriodMetrics) if f.name != "timeframe"]
_SINGLE_METRICS = [f.name for f in dataclasses.fields(SymbolMetrics)
                   if f.name not in ("symbol", "exchange", "periods", "as_of")]


def create_app(service):  # pragma: no cover - 需 fastapi
    from fastapi import FastAPI, HTTPException
    from fastapi.responses import HTMLResponse
    from pydantic import ValidationError

    app = FastAPI(title="fx 加密扫盘看板")

    @app.get("/api/scan/latest")
    def latest():
        return service.get_latest() or {}

    @app.post("/api/rescan")
    async def rescan():
        return await service.rescan()

    @app.get("/api/symbol/{symbol:path}")
    def symbol(symbol: str):
        snap = service.get_symbol(symbol)
        if snap is None:
            raise HTTPException(404, "未找到该币种")
        return snap

    @app.get("/api/rules")
    def rules():
        return service.describe_rules()

    @app.get("/api/rules/doc")
    def rules_doc():
        """完整结构化规则（供可视化编辑器渲染）。"""
        return service.get_rules_doc()

    @app.get("/api/rules/meta")
    def rules_meta():
        """编辑器下拉选项目录。"""
        return {
            "period_metrics": _PERIOD_METRICS,
            "single_metrics": _SINGLE_METRICS,
            "timeframes": list(service.settings.timeframes),
            "ops": _OPS,
            "logics": _LOGICS,
            "states": _STATES,
        }

    @app.put("/api/rules")
    def replace_rules(payload: dict):
        """整文档替换规则；校验失败返回 400。"""
        try:
            return service.replace_rules(payload)
        except ValidationError as exc:
            raise HTTPException(400, exc.errors())

    @app.get("/rules", response_class=HTMLResponse)
    def rules_editor():
        return EDITOR_HTML

    @app.get("/", response_class=HTMLResponse)
    def dashboard():
        return _render(service.get_latest())

    return app


def _render(summary) -> str:
    nav = "<p><a href='/rules'>⚙️ 编辑规则</a></p>"
    if not summary:
        return ("<html><meta charset='utf-8'><body>" + nav
                + "<h2>暂无扫描结果</h2><p>POST /api/rescan 触发一轮扫描。</p></body></html>")
    blocks = [nav, f"<h2>扫描时间：{summary.get('as_of')}</h2>"]
    for name in LIST_NAMES:
        syms = summary.get("lists", {}).get(name, [])
        label = LIST_LABELS.get(name, name)
        items = "".join(f"<li>{s}</li>" for s in syms) or "<li>—</li>"
        blocks.append(f"<h3>{label} ({len(syms)})</h3><ul>{items}</ul>")
    return "<html><meta charset='utf-8'><body>" + "".join(blocks) + "</body></html>"
