"""FastAPI 看板 + JSON API。

``create_app(service)`` 工厂注入 ScanService；fastapi 懒加载，未安装时本模块
仍可导入。看板页面极简：读最新结果渲染四张清单表。
"""

from __future__ import annotations

from ...service import LIST_NAMES
from ..discord_bot.commands import LIST_LABELS


def create_app(service):  # pragma: no cover - 需 fastapi
    from fastapi import FastAPI, HTTPException
    from fastapi.responses import HTMLResponse

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

    @app.get("/", response_class=HTMLResponse)
    def dashboard():
        return _render(service.get_latest())

    return app


def _render(summary) -> str:
    if not summary:
        return "<h2>暂无扫描结果</h2><p>POST /api/rescan 触发一轮扫描。</p>"
    blocks = [f"<h2>扫描时间：{summary.get('as_of')}</h2>"]
    for name in LIST_NAMES:
        syms = summary.get("lists", {}).get(name, [])
        label = LIST_LABELS.get(name, name)
        items = "".join(f"<li>{s}</li>" for s in syms) or "<li>—</li>"
        blocks.append(f"<h3>{label} ({len(syms)})</h3><ul>{items}</ul>")
    return "<html><meta charset='utf-8'><body>" + "".join(blocks) + "</body></html>"
