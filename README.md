# fx — 加密货币市场状态识别器 / 扫盘器

周期性 / 实时扫描全市场加密币种，计算一组技术与市场指标，按过滤规则把币种
分类筛选（顶部 / 底部 / 收口待变盘 / 观察区），并通过 Web 看板与消息推送
（Telegram / 钉钉 / Discord）呈现。

## 当前进度

已完成 **离线核心闭环（P0–P3）**：指标层（16 指标，纯函数）、规则引擎
（配置驱动的阈值条件）、分类器（波动分 → A/B/观察 → 各清单）、单元测试。

数据接入（Binance）、调度、看板、推送、Discord 交互机器人为后续阶段
（P4–P7），详见 `config/` 与计划。

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
pip install -e .            # 或 pip install pandas numpy pydantic pydantic-settings pyyaml
pytest                      # 跑单元测试
PYTHONPATH=src python -m fx.main demo   # 离线合成数据跑通闭环
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
