"""推送：MultiNotifier 扇出 + dispatch_alerts + ScanService 扫描后自动推送订阅告警。"""

import asyncio
import shutil
from datetime import datetime, timedelta, timezone

import numpy as np
import pandas as pd

from fx.config import DEFAULT_RULES, Settings
from fx.data.base import DataProvider
from fx.indicators.timeframe import timeframe_seconds
from fx.output.notify.base import MultiNotifier, Notifier, dispatch_alerts
from fx.output.store import Store
from fx.rules.store import RulesStore
from fx.service import ScanService


class _FakeNotifier(Notifier):
    def __init__(self):
        self.sent = []

    async def send(self, text):
        self.sent.append(text)


class _BoomNotifier(Notifier):
    async def send(self, text):
        raise RuntimeError("down")


# ----------------------------- dispatch / MultiNotifier -----------------------------
def test_dispatch_alerts_ats_user():
    n = _FakeNotifier()
    sent = asyncio.run(dispatch_alerts(n, {"u1": ["🆕 BTC 新进【top】清单"], "u2": ["a", "b"]}))
    assert sent == 3
    assert "<@u1> 🆕 BTC 新进【top】清单" in n.sent


def test_multi_notifier_fans_out_and_isolates_failure():
    a, b = _FakeNotifier(), _FakeNotifier()
    multi = MultiNotifier([a, _BoomNotifier(), b, None])   # 含失败的 + None
    asyncio.run(multi.send("hi"))
    assert a.sent == ["hi"] and b.sent == ["hi"]           # 一路失败不影响其它


# ----------------------------- ScanService 扫描后推送 -----------------------------
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


def test_rescan_dispatches_subscription_alerts(tmp_path):
    """订阅者在首轮(prev=None → 命中即新进)收到与 summary['alerts'] 一致条数的推送。"""
    shutil.copy(DEFAULT_RULES, tmp_path / "rules.json")
    notifier = _FakeNotifier()
    svc = ScanService(Settings(), Store(str(tmp_path / "t.db")),
                      RulesStore(path=tmp_path / "rules.json"), _Fake(), notifier=notifier)
    # 订阅全部清单，确保任何命中都会触发告警
    for name in ("top", "bottom", "squeeze", "watch"):
        svc.subscribe("u1", name)

    summary = asyncio.run(svc.rescan(symbols=["AAAUSDT", "BBBUSDT"]))
    total = sum(len(v) for v in summary["alerts"].values())
    assert len(notifier.sent) == total                       # 每条告警都推了
    if total:                                                # 至少一条时校验 @ 文案
        assert all(s.startswith("<@u1> 🆕") for s in notifier.sent)


# ----------------------------- 频道内推送（bot notifier） -----------------------------
class _FakeChannel:
    def __init__(self):
        self.sent = []

    async def send(self, text):
        self.sent.append(text)


class _FakeClient:
    def __init__(self, cached=True):
        self.channel = _FakeChannel()
        self._cached = cached

    def get_channel(self, cid):
        return self.channel if self._cached else None

    async def fetch_channel(self, cid):
        return self.channel


def test_discord_bot_notifier_posts_to_channel():
    from fx.output.discord_bot.notify import DiscordBotNotifier
    c = _FakeClient(cached=True)
    asyncio.run(DiscordBotNotifier(c, "123").send("<@u1> hi"))
    assert c.channel.sent == ["<@u1> hi"]


def test_discord_bot_notifier_fetches_when_not_cached():
    from fx.output.discord_bot.notify import DiscordBotNotifier
    c = _FakeClient(cached=False)                    # get_channel→None → fetch 回退
    asyncio.run(DiscordBotNotifier(c, 123).send("yo"))
    assert c.channel.sent == ["yo"]


def test_rescan_without_notifier_is_noop(tmp_path):
    shutil.copy(DEFAULT_RULES, tmp_path / "rules.json")
    svc = ScanService(Settings(), Store(str(tmp_path / "t.db")),
                      RulesStore(path=tmp_path / "rules.json"), _Fake())   # 无 notifier
    summary = asyncio.run(svc.rescan(symbols=["AAAUSDT", "BBBUSDT"]))      # 不应抛错
    assert "alerts" in summary
