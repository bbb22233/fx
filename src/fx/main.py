"""CLI 入口。

- ``fx demo``   : 用合成数据跑通「指标 → 分类 → 清单」离线闭环（无需联网）。
- ``fx run-scan``: 连真实交易所跑一轮（需安装 live 依赖，P4 接入）。
- ``fx serve``  : 启动看板（P5）。
"""

from __future__ import annotations

import argparse
import sys
from datetime import datetime, timedelta, timezone

import numpy as np
import pandas as pd

from .config import Rules, Settings
from .indicators import engine
from .rules import classifier
from .indicators.timeframe import timeframe_seconds


def _synth_frame(tf: str, n: int, *, seed: int, vol: float, drift: float) -> pd.DataFrame:
    """生成一段合成 OHLC（随机游走），用于离线 demo。"""
    rng = np.random.default_rng(seed)
    step = timeframe_seconds(tf)
    end = datetime.now(timezone.utc).replace(microsecond=0)
    idx = pd.to_datetime([end - timedelta(seconds=step * (n - 1 - i)) for i in range(n)], utc=True)
    rets = rng.normal(drift, vol, n)
    close = 100 * np.exp(np.cumsum(rets))
    spread = np.abs(rng.normal(0, vol, n)) * close
    high = close + spread
    low = close - spread
    open_ = np.concatenate([[close[0]], close[:-1]])
    return pd.DataFrame({"open": open_, "high": high, "low": low,
                         "close": close, "volume": rng.random(n) * 1000}, index=idx)


def _demo(settings: Settings, rules: Rules) -> int:
    profiles = {
        "CALMUSDT": dict(vol=0.005, drift=0.0),     # 低波动 → 可能进收口
        "WILDUSDT": dict(vol=0.05, drift=0.01),     # 高波动 → 可能进顶/底
        "MIDUSDT": dict(vol=0.02, drift=0.0),       # 过渡区
    }
    metrics_list = []
    for i, (sym, p) in enumerate(profiles.items()):
        frames = {}
        for tf in settings.timeframes:
            n = max(settings.percentile_window.get(tf, 200),
                    settings.derived_percentile_window + settings.mad.ma_long) + 5
            frames[tf] = _synth_frame(tf, n, seed=i * 10 + hash(tf) % 7,
                                      vol=p["vol"], drift=p["drift"])
        funding = list(np.random.default_rng(i).normal(0.0001, 0.0002, 99))
        metrics_list.append(engine.compute(sym, frames, settings, funding))

    result = classifier.run(metrics_list, rules)

    print(f"\n扫描时间: {result.as_of.isoformat()}\n")
    for sym, m in result.metrics.items():
        p1d = m.periods.get("1d")
        print(f"  {sym:10s} 状态={result.states.get(sym, '?'):5s} "
              f"波动分={classifier.volatility_score(m, rules):.1f} "
              f"%B(1d)={p1d.pctB:.2f} 带宽rank={p1d.bandwidth_pct_rank:.0f} "
              f"MAD21rank={m.mad21_pct_rank:.0f} 剩余动能={p1d.remaining_energy_pct:+.2f}")
    print("\n清单:")
    for name, syms in result.lists.items():
        print(f"  {name:10s}: {', '.join(syms) if syms else '—'}")
    return 0


def _build_providers(settings: Settings, use_pro: bool = False):
    """按 settings.active_exchanges 构造多个 provider（id -> provider）。"""
    from .data.binance import create_provider
    return {eid: create_provider(eid, settings, use_pro=use_pro)
            for eid in settings.active_exchanges}


def _build_service(settings: Settings, providers=None):
    """组装 ScanService（接真实交易所，可同时扫多家）。需 live 依赖与网络。"""
    from .output.store import Store
    from .rules.store import RulesStore
    from .service import ScanService
    providers = providers if providers is not None else _build_providers(settings)
    return ScanService(settings, Store("fx.db"), RulesStore(), providers)


def _run_scan(settings: Settings) -> int:
    import asyncio
    svc = _build_service(settings)
    summary = asyncio.run(svc.rescan())
    from .output.discord_bot.commands import format_scan
    print(format_scan(summary))
    return 0


def _serve(settings: Settings) -> int:
    import uvicorn
    from .output.web.app import create_app
    app = create_app(_build_service(settings))
    uvicorn.run(app, host="0.0.0.0", port=8000)
    return 0


def _bot(settings: Settings) -> int:
    from .output.discord_bot.bot import run_bot
    from .output.discord_bot.commands import CommandRouter
    run_bot(CommandRouter(_build_service(settings)))
    return 0


def _watch(settings: Settings) -> int:
    """扫一轮播种参考 → WS 实时异动告警（多所，需 ccxt.pro + 网络）。"""
    import asyncio
    import os

    from .output.discord_bot.commands import format_realtime_alert
    from .output.store import Store
    from .rules.store import RulesStore
    from .scanner import realtime
    from .service import ScanService

    providers = _build_providers(settings, use_pro=True)
    svc = ScanService(settings, Store("fx.db"), RulesStore(), providers)
    monitor = realtime.RealtimeMonitor(timeframe=settings.realtime.timeframe,
                                       energy_mult=settings.realtime.energy_mult)

    webhook = os.getenv("DISCORD_WEBHOOK_URL")
    notifier = None
    if webhook:
        from .output.notify.webhook import DiscordWebhookNotifier
        notifier = DiscordWebhookNotifier(webhook)

    async def on_alert(alert):
        text = format_realtime_alert(alert)
        print(text)
        if notifier:
            await notifier.send(text)

    async def _main():
        summary = await svc.rescan()
        monitor.seed_from_summary(summary)
        # 各所并发订阅 WS：监控键 = 'exchange:symbol'，与扫描结果键一致
        tasks = []
        for eid, provider in providers.items():
            prefix = f"{eid}:"
            symbols = [k[len(prefix):] for k in summary.get("metrics", {}) if k.startswith(prefix)]
            if symbols:
                tasks.append(realtime.watch(provider, symbols, monitor,
                                            on_alert=on_alert, exchange_id=eid))
        await asyncio.gather(*tasks)

    asyncio.run(_main())
    return 0


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(prog="fx", description="加密市场状态识别器 / 扫盘器")
    sub = parser.add_subparsers(dest="cmd", required=True)
    sub.add_parser("demo", help="离线合成数据跑通闭环")
    sub.add_parser("run-scan", help="连交易所跑一轮（需 live 依赖 + 网络）")
    sub.add_parser("serve", help="启动 Web 看板（需 live 依赖 + 网络）")
    sub.add_parser("bot", help="启动 Discord 交互机器人（需 live 依赖 + 网络）")
    sub.add_parser("watch", help="WS 实时异动监控告警（需 ccxt.pro + 网络）")

    args = parser.parse_args(argv)
    settings = Settings.load()
    rules = Rules.load()

    if args.cmd == "demo":
        return _demo(settings, rules)
    if args.cmd == "run-scan":
        return _run_scan(settings)
    if args.cmd == "serve":
        return _serve(settings)
    if args.cmd == "bot":
        return _bot(settings)
    if args.cmd == "watch":
        return _watch(settings)
    print(f"未知命令 {args.cmd!r}。", file=sys.stderr)
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
