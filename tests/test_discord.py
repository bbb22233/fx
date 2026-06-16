"""Discord 命令路由/格式化 + 看板渲染测试 —— 全离线。"""

import asyncio
import shutil
from datetime import datetime, timedelta, timezone

import numpy as np
import pandas as pd

from fx.config import DEFAULT_RULES, Settings
from fx.data.base import DataProvider
from fx.indicators.timeframe import timeframe_seconds
from fx.output.discord_bot import commands
from fx.output.discord_bot.commands import CommandRouter
from fx.output.store import Store
from fx.output.web.app import _render
from fx.rules.store import RulesStore
from fx.service import ScanService


# ----------------------------- 纯函数格式化 -----------------------------
def test_format_scan_empty_and_filled():
    assert "暂无" in commands.format_scan(None)
    summary = {"as_of": "T", "lists": {"top": ["A", "B"], "bottom": [], "squeeze": [], "watch": []}}
    out = commands.format_scan(summary)
    assert "顶部" in out and "A, B" in out


def test_format_symbol_and_subs_and_rules():
    assert "未找到" in commands.format_symbol(None)
    snap = {"symbol": "X", "funding_rate": 0.0001, "funding_rate_pct_rank": 50,
            "mad21_pct": 1.0, "mad21_pct_rank": 60, "mad72_pct": 2.0,
            "periods": {"1d": {"pctB": 0.5, "bandwidth_pct": 3.0,
                               "bandwidth_pct_rank": 40, "remaining_energy_pct": 1.0,
                               "atr_pct": 2.0}}}
    assert "X" in commands.format_symbol(snap)
    assert "还没有订阅" in commands.format_subscriptions([])
    assert "top" in commands.format_subscriptions(["top"])
    assert "high_vol_min" in commands.format_rules({"classification.high_vol_min": 60})


def test_render_dashboard():
    assert "暂无" in _render(None)
    html = _render({"as_of": "T", "lists": {"top": ["A"], "bottom": [], "squeeze": [], "watch": []}})
    assert "顶部 (1)" in html and "<li>A</li>" in html


# ----------------------------- 路由（接 service） -----------------------------
def _make_df(n, tf, now):
    step = timeframe_seconds(tf)
    idx = pd.to_datetime([now - timedelta(seconds=step * (n - 1 - i)) for i in range(n)], utc=True)
    close = 100 + np.arange(n) * 0.1 + np.sin(np.arange(n)) * 0.5
    return pd.DataFrame({"open": close, "high": close + 1, "low": close - 1,
                         "close": close, "volume": np.ones(n)}, index=idx)


class _Fake(DataProvider):
    async def fetch_top_volume(self, n):
        return ["AAAUSDT"]

    async def fetch_ohlcv(self, symbol, timeframe, limit):
        return _make_df(limit, timeframe, datetime.now(timezone.utc) - timedelta(minutes=1))

    async def fetch_funding_history(self, symbol, limit):
        return list(np.linspace(-0.0002, 0.0003, limit))

    async def fetch_last_price(self, symbol):
        return 105.0


def _router(tmp_path):
    shutil.copy(DEFAULT_RULES, tmp_path / "rules.json")
    svc = ScanService(Settings(), Store(str(tmp_path / "t.db")),
                      RulesStore(path=tmp_path / "rules.json"), _Fake())
    return CommandRouter(svc)


def test_router_full_flow(tmp_path):
    r = _router(tmp_path)
    run = lambda c, u="u1", a=None: asyncio.run(r.handle(c, u, a))

    assert "暂无" in run("scan")                       # 还没扫
    assert "已重新扫描" in run("rescan")               # 触发扫盘
    assert "AAAUSDT" in run("symbol", a=["AAAUSDT"])   # 查单币
    assert "用法" in run("symbol")                     # 缺参数

    assert "已订阅" in run("sub", a=["top"])
    assert "已存在" in run("sub", a=["top"])
    assert "top" in run("subs")
    assert "已取消订阅" in run("unsub", a=["top"])

    assert "high_vol_min" in run("rules")
    assert "已更新规则" in run("setrule", a=["classification.high_vol_min", "65"])
    assert "失败" in run("setrule", a=["bad.path.xyz", "1"])   # 非法路径
    assert "未知命令" in run("nope")
