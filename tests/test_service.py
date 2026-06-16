"""ScanService / Store / RulesStore 测试 —— 全离线。"""

import asyncio
import shutil
from datetime import datetime, timedelta, timezone

import numpy as np
import pandas as pd

from fx.config import DEFAULT_RULES, Settings
from fx.data.base import DataProvider
from fx.indicators.timeframe import timeframe_seconds
from fx.output.store import Store
from fx.rules.store import RulesStore
from fx.service import ScanService, compute_alerts


# ----------------------------- Store -----------------------------
def test_store_subscriptions(tmp_path):
    s = Store(str(tmp_path / "t.db"))
    assert s.add_subscription("u1", "top") is True
    assert s.add_subscription("u1", "top") is False        # 重复
    assert s.list_subscriptions("u1") == ["top"]
    assert ("u1", "top") in s.all_subscriptions()
    assert s.remove_subscription("u1", "top") is True
    assert s.list_subscriptions("u1") == []
    s.close()


def test_store_result_roundtrip(tmp_path):
    s = Store(str(tmp_path / "t.db"))
    assert s.load_result() is None
    payload = {"as_of": "2026-01-01T00:00:00+00:00", "lists": {"top": ["BTCUSDT"]}}
    s.save_result(payload)
    assert s.load_result()["lists"]["top"] == ["BTCUSDT"]
    # 覆盖更新
    s.save_result({"as_of": "later", "lists": {"top": []}})
    assert s.load_result()["lists"]["top"] == []
    s.close()


# ----------------------------- RulesStore -----------------------------
def test_rules_store_set_value(tmp_path):
    p = tmp_path / "rules.json"
    shutil.copy(DEFAULT_RULES, p)
    rs = RulesStore(path=p)
    assert rs.get().classification.high_vol_min == 60.0
    rs.set_value("classification.high_vol_min", 70)
    assert rs.get().classification.high_vol_min == 70.0
    # 改清单条件阈值
    rs.set_value("lists.top.conditions.0.value", 0.95)
    assert rs.get().lists["top"].conditions[0].value == 0.95
    assert "lists.top.conditions.0.value" in rs.describe()


# ----------------------------- alerts -----------------------------
def test_compute_alerts_new_entries():
    prev = {"top": ["AAA"], "bottom": [], "squeeze": [], "watch": []}
    new = {"top": ["AAA", "BBB"], "bottom": [], "squeeze": ["CCC"], "watch": []}
    subs = [("u_top", "top"), ("u_sym", "CCC"), ("u_none", "bottom")]
    alerts = compute_alerts(prev, new, subs)
    assert alerts["u_top"] == ["🆕 BBB 新进【top】清单"]   # AAA 不是新进
    assert alerts["u_sym"] == ["🆕 CCC 新进【squeeze】清单"]
    assert "u_none" not in alerts


def test_compute_alerts_dedup_across_exchanges():
    """同币同轮在多所新进 → 合并为一条（带交易所标签）。"""
    metrics = {
        "binance:BTC/USDT:USDT": {"symbol": "BTC/USDT:USDT", "exchange": "binance"},
        "okx:BTC/USDT:USDT": {"symbol": "BTC/USDT:USDT", "exchange": "okx"},
    }
    new = {"top": ["binance:BTC/USDT:USDT", "okx:BTC/USDT:USDT"],
           "bottom": [], "squeeze": [], "watch": []}
    subs = [("u_top", "top"), ("u_sym", "BTC/USDT:USDT")]
    alerts = compute_alerts(None, new, subs, metrics=metrics)
    assert alerts["u_top"] == ["🆕 BTC/USDT:USDT [binance, okx] 新进【top】清单"]
    assert alerts["u_sym"] == ["🆕 BTC/USDT:USDT [binance, okx] 新进【top】清单"]


def test_compute_alerts_coin_level_no_repeat_when_another_exchange_joins():
    """币已在 binance 顶部，本轮 okx 才进 → 币级判定不再重复告警。"""
    prev_metrics = {"binance:BTC/USDT:USDT": {"symbol": "BTC/USDT:USDT", "exchange": "binance"}}
    metrics = {
        "binance:BTC/USDT:USDT": {"symbol": "BTC/USDT:USDT", "exchange": "binance"},
        "okx:BTC/USDT:USDT": {"symbol": "BTC/USDT:USDT", "exchange": "okx"},
    }
    prev = {"top": ["binance:BTC/USDT:USDT"], "bottom": [], "squeeze": [], "watch": []}
    new = {"top": ["binance:BTC/USDT:USDT", "okx:BTC/USDT:USDT"],
           "bottom": [], "squeeze": [], "watch": []}
    alerts = compute_alerts(prev, new, [("u_top", "top")],
                            metrics=metrics, prev_metrics=prev_metrics)
    assert "u_top" not in alerts        # 币种本就在清单里，不再报


# ----------------------------- ScanService -----------------------------
def _make_df(n, tf, now):
    step = timeframe_seconds(tf)
    idx = pd.to_datetime([now - timedelta(seconds=step * (n - 1 - i)) for i in range(n)], utc=True)
    close = 100 + np.arange(n) * 0.1 + np.sin(np.arange(n)) * 0.5
    return pd.DataFrame({"open": close, "high": close + 1, "low": close - 1,
                         "close": close, "volume": np.ones(n)}, index=idx)


class _Fake(DataProvider):
    async def fetch_top_volume(self, n):
        return ["AAAUSDT", "BBBUSDT"]

    async def fetch_ohlcv(self, symbol, timeframe, limit):
        return _make_df(limit, timeframe, datetime.now(timezone.utc) - timedelta(minutes=1))

    async def fetch_funding_history(self, symbol, limit):
        return list(np.linspace(-0.0002, 0.0003, limit))

    async def fetch_last_price(self, symbol):
        return 105.0


def _service(tmp_path):
    shutil.copy(DEFAULT_RULES, tmp_path / "rules.json")
    return ScanService(Settings(), Store(str(tmp_path / "t.db")),
                       RulesStore(path=tmp_path / "rules.json"), _Fake())


def test_service_rescan_and_query(tmp_path):
    svc = _service(tmp_path)
    summary = asyncio.run(svc.rescan(symbols=["AAAUSDT", "BBBUSDT"]))
    assert "lists" in summary and "alerts" in summary
    # 落库后可查询最新
    assert svc.get_latest()["as_of"] == summary["as_of"]
    snap = svc.get_symbol("AAAUSDT")
    assert snap and "periods" in snap and "1d" in snap["periods"]


def test_service_rescan_requires_provider(tmp_path):
    shutil.copy(DEFAULT_RULES, tmp_path / "rules.json")
    svc = ScanService(Settings(), Store(str(tmp_path / "t.db")),
                      RulesStore(path=tmp_path / "rules.json"), provider=None)
    try:
        asyncio.run(svc.rescan())
        assert False, "应抛出未配置 provider 错误"
    except RuntimeError:
        pass


def test_service_subscriptions_and_rules(tmp_path):
    svc = _service(tmp_path)
    assert svc.subscribe("u1", "top") is True
    assert svc.list_subscriptions("u1") == ["top"]
    desc = svc.set_rule("classification.high_vol_min", 65)
    assert "classification.high_vol_min" in desc
    assert svc.rules_store.get().classification.high_vol_min == 65.0
