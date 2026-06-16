"""规则可视化编辑后端：整文档替换（RulesStore.replace）+ Web API。

替换是 Web 编辑器「增删改」的核心能力（细粒度 set_value 无法增删清单/条件）。
分两层：离线的 RulesStore/classifier 端到端（必跑）；fastapi 端点（无 fastapi 则跳过）。
"""

import json
import shutil

import pytest

from fx.config import DEFAULT_RULES, Settings
from fx.models import PeriodMetrics, SymbolMetrics
from fx.output.store import Store
from fx.rules import classifier
from fx.rules.store import RulesStore
from fx.service import ScanService


def _store(tmp_path):
    p = tmp_path / "rules.json"
    shutil.copy(DEFAULT_RULES, p)
    return RulesStore(path=p), p


def _metrics(symbol, *, score, mad21_rank):
    """构造命中「自定义顶部」所需的指标。"""
    base = dict(open=0, high=0, low=0, close=0, amplitude_pct=0, atr_pct=0,
                remaining_energy_pct=0, pctB=0.5, bandwidth_pct=0)
    m = SymbolMetrics(symbol=symbol)
    m.periods["4h"] = PeriodMetrics(timeframe="4h", amp_pct_rank=score,
                                    atr_pct_rank=score, **base)
    m.periods["1d"] = PeriodMetrics(timeframe="1d", amp_pct_rank=0,
                                    atr_pct_rank=0, **base)
    m.mad21_pct_rank = mad21_rank
    return m


# ----------------------------- 改 + 保留注释 -----------------------------
def test_replace_roundtrip_and_keeps_comment(tmp_path):
    rs, p = _store(tmp_path)
    doc = rs.raw_rules()
    doc["classification"]["high_vol_min"] = 75.0
    doc["lists"]["top"]["conditions"][0]["value"] = 0.95
    rs.replace(doc)

    assert rs.get().classification.high_vol_min == 75.0
    assert rs.get().lists["top"].conditions[0].value == 0.95
    assert "_comment" in json.loads(p.read_text(encoding="utf-8"))  # 注释保留


# ----------------------------- 增（端到端命中新清单） -----------------------------
def test_add_list_takes_effect_in_classifier(tmp_path):
    rs, _ = _store(tmp_path)
    doc = rs.raw_rules()
    doc["lists"]["custom"] = {
        "label": "自定义顶部",
        "state": "A",
        "logic": "AND",
        "conditions": [{"metric": "mad21_pct_rank", "op": ">", "value": 80.0,
                        "value_metric": None, "value_mult": 1.0}],
    }
    rules = rs.replace(doc)
    assert "custom" in rules.lists

    hit = _metrics("HIT", score=70, mad21_rank=90)    # A 状态 + mad21>80
    miss = _metrics("MISS", score=70, mad21_rank=50)
    res = classifier.run([hit, miss], rules)
    assert res.lists["custom"] == ["HIT"]


# ----------------------------- 删 -----------------------------
def test_delete_list_and_condition(tmp_path):
    rs, _ = _store(tmp_path)
    doc = rs.raw_rules()
    del doc["lists"]["squeeze"]
    doc["lists"]["top"]["conditions"].pop()           # 删掉 mad21 条件
    rules = rs.replace(doc)
    assert "squeeze" not in rules.lists
    assert len(rules.lists["top"].conditions) == 1


# ----------------------------- 校验失败 -----------------------------
def test_replace_rejects_invalid(tmp_path):
    from pydantic import ValidationError
    rs, p = _store(tmp_path)
    before = p.read_text(encoding="utf-8")
    doc = rs.raw_rules()
    doc["lists"]["top"]["conditions"] = [{"op": ">", "value": 1}]  # 缺 metric
    with pytest.raises(ValidationError):
        rs.replace(doc)
    assert p.read_text(encoding="utf-8") == before                # 未写坏文件


# ----------------------------- Web 端点（需 fastapi） -----------------------------
def _client(tmp_path):
    pytest.importorskip("fastapi")
    from fastapi.testclient import TestClient
    from fx.output.web.app import create_app
    shutil.copy(DEFAULT_RULES, tmp_path / "rules.json")
    svc = ScanService(Settings(), Store(str(tmp_path / "t.db")),
                      RulesStore(path=tmp_path / "rules.json"), provider=None)
    return TestClient(create_app(svc))


def test_web_dashboard_is_static_shell(tmp_path):
    """看板 / 返回静态 HTML（不读 store，故 provider=None 也 200）。"""
    c = _client(tmp_path)
    r = c.get("/")
    assert r.status_code == 200
    assert "CRYPTO MARKET SCANNER" in r.text      # TUI 黑客风标题
    assert "loadLatest" in r.text                 # 自动刷新脚本


def test_web_rules_doc_and_meta(tmp_path):
    c = _client(tmp_path)
    doc = c.get("/api/rules/doc").json()
    assert "classification" in doc and "top" in doc["lists"]
    meta = c.get("/api/rules/meta").json()
    assert "1d" in meta["timeframes"]
    assert "pctB" in meta["period_metrics"] and "mad21_pct_rank" in meta["single_metrics"]
    assert ">" in meta["ops"]


def test_web_put_rules_valid_and_invalid(tmp_path):
    c = _client(tmp_path)
    doc = c.get("/api/rules/doc").json()
    doc["classification"]["low_vol_max"] = 25.0
    assert c.put("/api/rules", json=doc).status_code == 200
    assert c.get("/api/rules/doc").json()["classification"]["low_vol_max"] == 25.0

    bad = c.get("/api/rules/doc").json()
    bad["lists"]["top"]["conditions"] = [{"op": ">"}]   # 缺 metric
    assert c.put("/api/rules", json=bad).status_code == 400
