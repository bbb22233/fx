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


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(prog="fx", description="加密市场状态识别器 / 扫盘器")
    sub = parser.add_subparsers(dest="cmd", required=True)
    sub.add_parser("demo", help="离线合成数据跑通闭环")
    sub.add_parser("run-scan", help="连交易所跑一轮（需 live 依赖）")
    sub.add_parser("serve", help="启动看板（需 live 依赖）")

    args = parser.parse_args(argv)
    settings = Settings.load()
    rules = Rules.load()

    if args.cmd == "demo":
        return _demo(settings, rules)
    print(f"命令 {args.cmd!r} 尚未接入（见计划 P4+）。", file=sys.stderr)
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
