"""实时监控（P7）：WS 现价流 → 未收线 K 现价缓存 + tick 级异动告警。

异动判定复用「剩余动能」语义：从 tick 累积当前未收线 K 的 high/low，按当前
时间进度算时间归一化剩余动能；当「已走幅度远超进度该有的量」(剩余动能跌破
阈值) → 实时告警「提前发力/异动」。完整指标重算仍由收线 cron 驱动，这里只做
轻量的现价维护与异动捕捉，避免每个 tick 全量重算。

检测逻辑为纯函数（可离线测试）；WS 接线在 ``watch`` 里懒加载。
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Dict, Optional, Tuple

from ..indicators.ohlc import remaining_energy_pct
from ..indicators.timeframe import elapsed_fraction, timeframe_seconds


# ----------------------------- 现价缓存 -----------------------------
class PriceCache:
    """symbol -> 最新现价，供批量扫描覆盖未收线 K 使用。"""

    def __init__(self):
        self._prices: Dict[str, float] = {}

    def update(self, symbol: str, price: float) -> None:
        self._prices[symbol] = price

    def get(self, symbol: str) -> Optional[float]:
        return self._prices.get(symbol)


# ----------------------------- 实时 K 与告警 -----------------------------
def floor_to_timeframe(ts: datetime, timeframe: str) -> datetime:
    """把时间戳向下取整到所在周期的开盘时刻（UTC）。"""
    if ts.tzinfo is None:
        ts = ts.replace(tzinfo=timezone.utc)
    step = timeframe_seconds(timeframe)
    epoch = int(ts.timestamp())
    return datetime.fromtimestamp(epoch - epoch % step, tz=timezone.utc)


@dataclass
class LiveBar:
    open_time: datetime
    open: float
    high: float
    low: float
    close: float
    anchor: float  # 振幅基准（上一根收盘），用作分母与 high/low 起点


@dataclass
class RealtimeAlert:
    symbol: str
    timeframe: str
    price: float
    amplitude_pct: float
    remaining_energy_pct: float
    elapsed_fraction: float


class RealtimeMonitor:
    """tick 级异动监控。

    告警条件：剩余动能% < −energy_mult × ATR%
      （即当前 K 已走幅度 > ATR×(已过时间比例 + energy_mult)，明显提前发力）。
    每根 K 只告警一次（避免刷屏）。
    """

    def __init__(self, timeframe: str = "1d", energy_mult: float = 0.5):
        self.timeframe = timeframe
        self.energy_mult = energy_mult
        # 参考数据：symbol -> (ATR%, 上一周期收盘)
        self._ref: Dict[str, Tuple[float, float]] = {}
        self._bars: Dict[str, LiveBar] = {}
        self._alerted: Dict[str, datetime] = {}  # symbol -> 已告警的 K 开盘时刻

    def set_reference(self, symbol: str, atr_pct: float, prev_close: float) -> None:
        """由最近一轮扫描喂入参考 ATR% 与上一周期收盘价。"""
        self._ref[symbol] = (atr_pct, prev_close)

    def seed_from_summary(self, summary: dict) -> None:
        """从扫描结果摘要批量喂参考（用对应周期的 ATR% 与该周期 open≈上一收盘）。"""
        for sym, snap in summary.get("metrics", {}).items():
            p = snap.get("periods", {}).get(self.timeframe)
            if not p:
                continue
            atrp = p.get("atr_pct")
            # open 近似为上一周期收盘（忽略跳空），缺失则用 close
            prev_close = snap["periods"][self.timeframe].get("close")
            if atrp is not None and prev_close:
                self.set_reference(sym, atrp, prev_close)

    def on_tick(self, symbol: str, price: float,
                now: Optional[datetime] = None) -> Optional[RealtimeAlert]:
        """处理一个现价 tick，必要时返回异动告警。"""
        now = now or datetime.now(timezone.utc)
        ref = self._ref.get(symbol)
        if ref is None:
            return None  # 无参考（未扫描过该币）
        atr_pct, prev_close = ref
        if not prev_close:
            return None

        bar_open = floor_to_timeframe(now, self.timeframe)
        bar = self._bars.get(symbol)
        if bar is None or bar.open_time != bar_open:
            # 新 K：锚=上一根实时 K 的收盘（无则用扫描参考的上一周期收盘）
            anchor = bar.close if bar is not None else prev_close
            bar = LiveBar(bar_open, open=anchor, high=max(anchor, price),
                          low=min(anchor, price), close=price, anchor=anchor)
            self._bars[symbol] = bar
        else:
            bar.high = max(bar.high, price)
            bar.low = min(bar.low, price)
            bar.close = price

        amplitude_pct = (bar.high - bar.low) / bar.anchor * 100.0
        elapsed = elapsed_fraction(bar_open, self.timeframe, now)
        rem = remaining_energy_pct(atr_pct, amplitude_pct, elapsed)

        if rem < -self.energy_mult * atr_pct:
            if self._alerted.get(symbol) == bar_open:
                return None  # 本根 K 已告警
            self._alerted[symbol] = bar_open
            return RealtimeAlert(symbol, self.timeframe, price,
                                 amplitude_pct, rem, elapsed)
        return None


async def watch(provider, symbols, monitor: RealtimeMonitor,
                price_cache: Optional[PriceCache] = None,
                on_alert=None, exchange_id: Optional[str] = None):  # pragma: no cover - 需 WS/网络
    """订阅 WS 行情：更新现价缓存 + 跑异动检测，命中则回调 on_alert。

    多交易所时传 exchange_id，监控键统一为 'exchange:symbol'，与扫描结果键一致。
    """
    async for ticker in provider.watch_tickers(symbols):
        sym, last = ticker.get("symbol"), ticker.get("last")
        if not sym or last is None:
            continue
        last = float(last)
        key = f"{exchange_id}:{sym}" if exchange_id else sym
        if price_cache is not None:
            price_cache.update(key, last)
        alert = monitor.on_tick(key, last)
        if alert and on_alert:
            await on_alert(alert)
