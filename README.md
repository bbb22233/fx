# fx — 加密货币市场状态识别器 / 扫盘器

周期性 / 实时扫描全市场加密币种，计算一组技术与市场指标，按过滤规则把币种
分类筛选（顶部 / 底部 / 收口待变盘 / 观察区），并通过 Web 看板与消息推送
（Telegram / 钉钉 / Discord）呈现。

## 当前进度

已完成（全部含离线单元测试，35 个全通过）：

- **P0–P3 离线核心**：16 指标（纯函数）、配置驱动规则引擎、分类器。
- **P4 数据层**：ccxt 版 BinanceProvider（可注入 mock）、Top N 选币、限频、
  增量缓存、批量扫描编排。
- **P5 存储/看板**：sqlite 持久化、FastAPI JSON API + 极简看板页。
- **P6 推送**：Telegram / 钉钉 / Discord webhook 通知 + 订阅告警分发。
- **P6.5 Discord 交互机器人**：slash 命令 `/scan /rescan /symbol /sub /unsub
  /subs /rules /setrule`，业务委托给共享 `ScanService`。
- **P7 实时监控**：WS 现价缓存 + tick 级**异动告警**（复用「剩余动能」语义：
  当未收线 K 已走幅度远超当前时间进度该有的量即告警），收线 cron 定时调度。

待办：OKX/Bybit 数据源；Web 规则可视化编辑。

> 联网功能（`run-scan` / `serve` / `bot`）需在可访问交易所/Discord 的环境运行，
> 并 `pip install -e ".[live]"`。核心逻辑均已用 mock 离线覆盖。

## 架构要点

Discord 机器人与 Web 看板都是薄适配器，共享同一业务大脑 **`ScanService`**
（触发扫盘 / 查询 / 订阅 / 规则查改）。命令格式化与规则求值是纯函数，便于测试。

## 指标（16）

按 4 周期（1H/4H/8H/1D）各算：OHLC、振幅%、ATR%、剩余动能%（时间归一化）、
振幅/ATR 百分位、布林 %B、带宽%。
单值：MAD21%/MAD72%（vs 日线 MA）、资金费率、资金费率百分位。
1D 衍生百分位：MAD21 百分位、带宽百分位。

## 过滤规则

1. **波动分类（4H）**：波动分 =（ATR百分位 + 振幅百分位)/2
   - ≥60 → 状态 A（中/高波动）；≤30 → 状态 B（低波动）；其间 → 观察区
2. **状态 A**（看 1D）：顶部 = %B>0.9 且 MAD21百分位>90；底部 = %B<0.1 且 MAD21百分位<10
3. **状态 B**（看 1D）：收口 = 带宽百分位<20 且 剩余动能% > 0.5×ATR%

阈值与条件见 `config/rules.json`（配置驱动，改阈值不动代码）；运行参数见
`config/settings.yaml`。

## 快速开始

```bash
pip install -e .            # 核心；联网功能用 pip install -e ".[live]"
pytest                      # 跑单元测试（35 个）
PYTHONPATH=src python -m fx.main demo   # 离线合成数据跑通闭环

# 联网（需可访问交易所 / Discord）
fx run-scan                 # 连 Binance 跑一轮并打印清单
fx serve                    # 启动看板 http://localhost:8000
fx bot                      # 启动 Discord 交互机器人（需 DISCORD_BOT_TOKEN）
fx watch                    # WS 实时异动监控（需 ccxt.pro；告警可推 DISCORD_WEBHOOK_URL）
```

## 目录

```
src/fx/
  config.py        配置 + 规则 schema（pydantic）
  models.py        SymbolMetrics / ScanResult（含 metric@timeframe 寻址）
  indicators/      16 指标，纯函数 + engine 编排
  rules/           evaluator（条件求值）+ classifier（分类与清单）
  data/base.py     DataProvider 抽象（可插拔数据层）
  main.py          CLI（demo / run-scan / serve）
```
