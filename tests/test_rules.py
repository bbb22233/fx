"""规则层用例：分类分流 + 各清单条件 + 配置驱动验证。"""

from fx.config import Condition, Rules
from fx.models import PeriodMetrics, SymbolMetrics
from fx.rules import classifier
from fx.rules.evaluator import evaluate_condition


def _period(tf, **kw):
    base = dict(timeframe=tf, open=0, high=0, low=0, close=0, amplitude_pct=0,
                atr_pct=0, remaining_energy_pct=0, amp_pct_rank=0, atr_pct_rank=0,
                pctB=0.5, bandwidth_pct=0)
    base.update(kw)
    return PeriodMetrics(**base)


def _make(symbol, *, score, pctb_1d=0.5, mad21_rank=50.0, bw_rank_1d=50.0,
          rem_1d=0.0, atr_1d=4.0):
    """构造一个币种指标：score 控制 4h 波动分（两项相等取该值）。"""
    m = SymbolMetrics(symbol=symbol)
    m.periods["4h"] = _period("4h", amp_pct_rank=score, atr_pct_rank=score)
    m.periods["1d"] = _period("1d", pctB=pctb_1d, bandwidth_pct_rank=bw_rank_1d,
                              remaining_energy_pct=rem_1d, atr_pct=atr_1d)
    m.mad21_pct_rank = mad21_rank
    return m


def test_classify_states():
    rules = Rules.load()
    assert classifier.classify_state(_make("A", score=70), rules) == "A"
    assert classifier.classify_state(_make("B", score=20), rules) == "B"
    assert classifier.classify_state(_make("W", score=45), rules) == "watch"


def test_top_and_bottom_lists():
    rules = Rules.load()
    top = _make("TOP", score=70, pctb_1d=0.95, mad21_rank=95)
    bottom = _make("BOT", score=70, pctb_1d=0.05, mad21_rank=5)
    neither = _make("MID", score=70, pctb_1d=0.5, mad21_rank=50)
    res = classifier.run([top, bottom, neither], rules)
    assert res.lists["top"] == ["TOP"]
    assert res.lists["bottom"] == ["BOT"]


def test_squeeze_list_metric_vs_metric():
    rules = Rules.load()
    # 带宽rank=10<20；剩余动能=3 > atr(4)*0.5=2 → 命中收口
    hit = _make("SQ", score=20, bw_rank_1d=10, rem_1d=3.0, atr_1d=4.0)
    # 剩余动能=1 < 2 → 不命中
    miss = _make("NO", score=20, bw_rank_1d=10, rem_1d=1.0, atr_1d=4.0)
    res = classifier.run([hit, miss], rules)
    assert res.lists["squeeze"] == ["SQ"]


def test_watch_list():
    rules = Rules.load()
    res = classifier.run([_make("W", score=45)], rules)
    assert res.lists["watch"] == ["W"]


def test_state_gating():
    """低波动币即使 %B 高也不会进顶部清单（顶部要求状态 A）。"""
    rules = Rules.load()
    low_but_high_pctb = _make("X", score=20, pctb_1d=0.99, mad21_rank=99)
    res = classifier.run([low_but_high_pctb], rules)
    assert "X" not in res.lists["top"]
    assert res.states["X"] == "B"


def test_evaluate_condition_value_metric():
    m = _make("E", score=20, rem_1d=3.0, atr_1d=4.0)
    cond = Condition(metric="remaining_energy_pct@1d", op=">",
                     value_metric="atr_pct@1d", value_mult=0.5)
    assert evaluate_condition(m, cond) is True
    cond_fail = Condition(metric="remaining_energy_pct@1d", op=">",
                          value_metric="atr_pct@1d", value_mult=1.0)
    assert evaluate_condition(m, cond_fail) is False  # 3 > 4 ? 否


def test_threshold_is_config_driven():
    """改 rules 配置阈值，行为随之变化（验证非硬编码）。"""
    rules = Rules.load()
    rules.lists["top"].conditions[0].value = 0.99  # 抬高 %B 门槛
    m = _make("T", score=70, pctb_1d=0.95, mad21_rank=95)  # 0.95 不再过 0.99
    res = classifier.run([m], rules)
    assert res.lists["top"] == []
