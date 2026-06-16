"""实时异动监控测试（离线，纯逻辑）。"""

from datetime import datetime, timedelta, timezone

from fx.output.discord_bot.commands import format_realtime_alert
from fx.scanner.realtime import RealtimeMonitor, floor_to_timeframe


UTC = timezone.utc


def test_floor_to_timeframe():
    ts = datetime(2026, 6, 16, 3, 37, 12, tzinfo=UTC)
    assert floor_to_timeframe(ts, "1h") == datetime(2026, 6, 16, 3, 0, tzinfo=UTC)
    assert floor_to_timeframe(ts, "4h") == datetime(2026, 6, 16, 0, 0, tzinfo=UTC)
    assert floor_to_timeframe(ts, "1d") == datetime(2026, 6, 16, 0, 0, tzinfo=UTC)


def test_no_reference_no_alert():
    m = RealtimeMonitor(timeframe="1h", energy_mult=0.5)
    assert m.on_tick("BTC", 100.0, datetime(2026, 6, 16, 3, 6, tzinfo=UTC)) is None


def test_anomaly_trigger_and_cooldown():
    m = RealtimeMonitor(timeframe="1h", energy_mult=0.5)
    m.set_reference("BTC", atr_pct=2.0, prev_close=100.0)
    now = datetime(2026, 6, 16, 3, 6, tzinfo=UTC)  # 1h 进度 10%

    # 平静 tick：振幅 0 → 剩余动能 +0.2 → 不告警
    assert m.on_tick("BTC", 100.0, now) is None
    # 急拉到 102：振幅 2% > 阈值 → 剩余动能 0.2-2= -1.8 < -1.0 → 告警
    alert = m.on_tick("BTC", 102.0, now)
    assert alert is not None
    assert alert.symbol == "BTC" and alert.remaining_energy_pct < 0
    # 同一根 K 再来一个更猛的 tick → 冷却，不重复告警
    assert m.on_tick("BTC", 103.0, now) is None


def test_new_bar_resets():
    m = RealtimeMonitor(timeframe="1h", energy_mult=0.5)
    m.set_reference("BTC", atr_pct=2.0, prev_close=100.0)
    m.on_tick("BTC", 102.0, datetime(2026, 6, 16, 3, 6, tzinfo=UTC))  # 触发并冷却
    # 下一根 K：振幅从新价重新累积，单 tick 振幅 0 → 不告警
    assert m.on_tick("BTC", 103.0, datetime(2026, 6, 16, 4, 6, tzinfo=UTC)) is None


def test_seed_from_summary():
    m = RealtimeMonitor(timeframe="1h")
    summary = {"metrics": {"ETH": {"periods": {"1h": {"atr_pct": 2.0, "close": 100.0}}}}}
    m.seed_from_summary(summary)
    alert = m.on_tick("ETH", 105.0, datetime(2026, 6, 16, 3, 6, tzinfo=UTC))
    assert alert is not None  # 振幅 5% 远超阈值


def test_format_realtime_alert():
    m = RealtimeMonitor(timeframe="1h")
    m.set_reference("BTC", 2.0, 100.0)
    alert = m.on_tick("BTC", 103.0, datetime(2026, 6, 16, 3, 6, tzinfo=UTC))
    text = format_realtime_alert(alert)
    assert "异动 BTC" in text and "提前发力" in text
