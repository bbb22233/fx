"""ccxt 通用数据源实现（Binance / OKX / Bybit ...）。

设计要点：
- ccxt 懒加载，模块本身可在未装 ccxt 时被导入（测试/离线友好）。
- ``exchange`` 客户端可注入，单测传入 fake 即可，无需联网。
- 通用 ``CcxtProvider`` + ``create_provider`` 工厂：换所只需换 exchange_id。
- 限频集中在此层（RateLimiter + ccxt 内置 enableRateLimit）。
- 未收线 K 的 close 用现价覆盖、high/low 取极值。
"""

from __future__ import annotations

from typing import AsyncIterator, List, Optional, Sequence

import pandas as pd

from ..config import Settings
from .base import DataProvider
from .ratelimit import RateLimiter
from .universe import select_top_volume

# 支持的交易所（ccxt 统一接口，symbol/资金费率字段跨所一致）
SUPPORTED_EXCHANGES = ("binance", "okx", "bybit")


def to_dataframe(ohlcv: Sequence[Sequence[float]]) -> pd.DataFrame:
    """ccxt OHLCV 列表 → DataFrame（UTC DatetimeIndex 升序）。"""
    df = pd.DataFrame(ohlcv, columns=["ts", "open", "high", "low", "close", "volume"])
    df.index = pd.to_datetime(df["ts"], unit="ms", utc=True)
    df.index.name = "open_time"
    return df.drop(columns=["ts"]).astype(float).sort_index()


def override_unclosed(df: pd.DataFrame, last_price: Optional[float]) -> pd.DataFrame:
    """用现价覆盖最后一根（未收线）K 的 close，并修正 high/low 极值。"""
    if last_price is None or df.empty:
        return df
    df = df.copy()
    i = df.index[-1]
    df.loc[i, "close"] = last_price
    df.loc[i, "high"] = max(df.loc[i, "high"], last_price)
    df.loc[i, "low"] = min(df.loc[i, "low"], last_price)
    return df


def required_bars(timeframe: str, settings: Settings) -> int:
    """该周期需拉取的 K 线根数（按指标依赖深度扩展，避免百分位失真）。"""
    pct = settings.percentile_window.get(timeframe, 200)
    base = pct + settings.atr_period
    if timeframe == "1d":
        # 衍生百分位需对过去每根算布林带宽/MAD → 额外回看
        base = max(
            base,
            settings.derived_percentile_window + settings.mad.ma_long,
            settings.derived_percentile_window + settings.bollinger.period,
        )
    return base + 5  # 小缓冲


class CcxtProvider(DataProvider):
    """基于 ccxt 统一接口的通用数据源。"""

    def __init__(self, exchange, settings: Settings, exchange_id: Optional[str] = None):
        self._ex = exchange
        self._settings = settings
        self.exchange_id = exchange_id or getattr(exchange, "id", None)
        self._limiter = RateLimiter(settings.ratelimit.max_concurrency)

    async def close(self):  # pragma: no cover
        await self._ex.close()

    async def fetch_top_volume(self, n: int) -> List[str]:
        tickers = await self._limiter.run(lambda: self._ex.fetch_tickers())
        cfg = self._settings.universe
        return select_top_volume(tickers, cfg.model_copy(update={"top_n": n}))

    async def fetch_ohlcv(self, symbol: str, timeframe: str, limit: int) -> pd.DataFrame:
        ohlcv = await self._limiter.run(
            lambda: self._ex.fetch_ohlcv(symbol, timeframe, limit=limit))
        return to_dataframe(ohlcv)

    async def fetch_funding_history(self, symbol: str, limit: int) -> Sequence[float]:
        rows = await self._limiter.run(
            lambda: self._ex.fetch_funding_rate_history(symbol, limit=limit))
        return [float(r["fundingRate"]) for r in rows]

    async def fetch_last_price(self, symbol: str) -> float:
        t = await self._limiter.run(lambda: self._ex.fetch_ticker(symbol))
        return float(t["last"])

    async def watch_tickers(self, symbols: Sequence[str]) -> AsyncIterator[dict]:  # pragma: no cover - 需 WS
        """ccxt.pro WS 行情流：逐个产出 {'symbol','last'}。需用 use_pro=True 构造。"""
        while True:
            tickers = await self._ex.watch_tickers(list(symbols))
            for sym, t in tickers.items():
                yield {"symbol": sym, "last": t.get("last")}


def create_provider(exchange_id: str, settings: Settings,
                    use_pro: bool = False) -> CcxtProvider:  # pragma: no cover - 需联网/ccxt
    """按交易所 id 构造 CcxtProvider。WS 用 ccxt.pro，仅 REST 用 ccxt.async_support。"""
    if exchange_id not in SUPPORTED_EXCHANGES:
        raise ValueError(f"暂不支持的交易所: {exchange_id!r}（支持 {SUPPORTED_EXCHANGES}）")
    if use_pro:
        import ccxt.pro as ccxt
    else:
        import ccxt.async_support as ccxt

    # 默认市场类型按所而异，可被 settings.exchange_options 覆盖
    options = {"defaultType": settings.universe.market_type}
    options.update(settings.exchange_options.get(exchange_id, {}))
    ex = getattr(ccxt, exchange_id)({
        "enableRateLimit": settings.ratelimit.enable_ccxt_ratelimit,
        "options": options,
    })
    return CcxtProvider(ex, settings, exchange_id=exchange_id)


# 向后兼容别名
BinanceProvider = CcxtProvider
