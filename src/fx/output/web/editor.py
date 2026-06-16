"""规则可视化编辑器页面（纯 vanilla JS，无构建步骤）。

由 ``app.py`` 的 ``GET /rules`` 直接返回 ``EDITOR_HTML``。页面通过
``/api/rules/doc`` + ``/api/rules/meta`` 初始化，保存时 ``PUT /api/rules``。
"""

from __future__ import annotations

EDITOR_HTML = r"""<!DOCTYPE html>
<html lang="zh">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>fx 规则编辑</title>
<style>
  :root { --g: #33ff66; --dim: #1f8a45; --bg: #050805; --panel: #0a120c; --err: #ff4455; }
  * { box-sizing: border-box; }
  html, body { background: var(--bg); }
  body {
    font-family: ui-monospace, "SF Mono", Menlo, Consolas, "Courier New", monospace;
    margin: 0 auto; padding: 12px; color: var(--g); max-width: 960px; font-size: 14px;
    text-shadow: 0 0 4px rgba(51,255,102,.35);
  }
  body::before { content: ""; position: fixed; inset: 0; pointer-events: none; z-index: 9;
    background: repeating-linear-gradient(0deg, rgba(0,0,0,0) 0, rgba(0,0,0,0) 2px, rgba(0,0,0,.18) 3px); }
  h1 { font-size: 16px; letter-spacing: 1px; } h2 { font-size: 14px; margin: 18px 0 8px; color: var(--dim); }
  a { color: var(--g); border-bottom: 1px dotted var(--dim); text-decoration: none; }
  .card { border: 1px solid var(--dim); padding: 12px 14px; margin: 10px 0; background: var(--panel); }
  .cond { display: flex; flex-wrap: wrap; gap: 6px; align-items: center; padding: 6px 0; border-top: 1px dashed var(--dim); }
  .row { display: flex; flex-wrap: wrap; gap: 10px; align-items: center; margin: 6px 0; }
  label.fld { font-size: 12px; color: var(--dim); display: inline-flex; gap: 4px; align-items: center; }
  select, input { padding: 4px 6px; font-size: 13px; font-family: inherit; color: var(--g);
    background: #000; border: 1px solid var(--dim); }
  input[type=number] { width: 92px; } input.key { width: 110px; } input.label { width: 130px; }
  button { padding: 5px 10px; font-size: 13px; font-family: inherit; border: 1px solid var(--g);
    background: transparent; color: var(--g); cursor: pointer; text-transform: uppercase; letter-spacing: 1px; }
  button:hover { background: var(--g); color: #000; text-shadow: none; }
  button.primary { background: var(--g); color: #000; text-shadow: none; }
  button.del { color: var(--err); border-color: var(--err); }
  button.del:hover { background: var(--err); color: #000; }
  .toolbar { position: sticky; top: 0; background: var(--bg); padding: 8px 0; border-bottom: 1px solid var(--dim); z-index: 10; }
  #msg { margin-left: 12px; font-size: 13px; color: var(--dim); }
  .ok { color: var(--g) !important; } .err { color: var(--err) !important; white-space: pre-wrap; }
</style>
</head>
<body>
<h1>⚙️ 过滤规则编辑 <a href="/" style="font-size:13px">← 返回看板</a></h1>
<div class="toolbar">
  <button class="primary" onclick="save()">保存到 rules.json</button>
  <button onclick="load()">放弃修改 / 重载</button>
  <span id="msg"></span>
</div>

<h2>分类阈值（波动分 → A/B/观察）</h2>
<div id="classification" class="card"></div>

<h2>清单（A=中/高波动 顶/底；B=低波动 收口）</h2>
<div id="lists"></div>
<button onclick="addList()">+ 新增清单</button>

<script>
let META = null;          // 下拉目录
let CL = null;            // classification 对象
let LISTS = [];           // [{key,label,state,logic,conditions:[...]}]

function msg(text, cls) { const m = document.getElementById('msg'); m.textContent = text; m.className = cls || ''; }

// 全部合法指标 ref：单值指标 + period@timeframe 笛卡尔积
function metricOptions() {
  const opts = [...META.single_metrics];
  for (const m of META.period_metrics) for (const tf of META.timeframes) opts.push(m + '@' + tf);
  return opts;
}
function sel(value, options, onchange, extra) {
  const s = document.createElement('select');
  for (const o of options) {
    const opt = document.createElement('option');
    opt.value = o.value !== undefined ? o.value : o;
    opt.textContent = o.label !== undefined ? o.label : o;
    if (opt.value === String(value)) opt.selected = true;
    s.appendChild(opt);
  }
  s.onchange = e => onchange(e.target.value);
  if (extra) Object.assign(s, extra);
  return s;
}
function num(value, step, onchange) {
  const i = document.createElement('input');
  i.type = 'number'; i.step = step || 'any'; i.value = value;
  i.onchange = e => onchange(e.target.value === '' ? null : parseFloat(e.target.value));
  return i;
}
function fld(text, el) { const l = document.createElement('label'); l.className = 'fld'; l.append(text, el); return l; }

async function load() {
  msg('加载中…');
  const [doc, meta] = await Promise.all([
    fetch('/api/rules/doc').then(r => r.json()),
    fetch('/api/rules/meta').then(r => r.json()),
  ]);
  META = meta;
  CL = doc.classification;
  LISTS = Object.entries(doc.lists).map(([key, v]) => ({ key, ...v }));
  render();
  msg('已加载', 'ok');
}

function render() { renderClassification(); renderLists(); }

function renderClassification() {
  const c = document.getElementById('classification');
  c.innerHTML = '';
  const row1 = document.createElement('div'); row1.className = 'row';
  row1.append(
    fld('高波动下限 ≥', num(CL.high_vol_min, 'any', v => CL.high_vol_min = v)),
    fld('低波动上限 ≤', num(CL.low_vol_max, 'any', v => CL.low_vol_max = v)),
    fld('聚合', sel(CL.score_agg, ['mean'], v => CL.score_agg = v)),
  );
  c.appendChild(row1);
  const opts = metricOptions();
  const smWrap = document.createElement('div');
  smWrap.append(document.createTextNode('波动分指标：'));
  CL.score_metrics.forEach((m, i) => {
    smWrap.append(sel(m, opts, v => CL.score_metrics[i] = v));
    const d = document.createElement('button'); d.className = 'del'; d.textContent = '×';
    d.onclick = () => { CL.score_metrics.splice(i, 1); renderClassification(); };
    smWrap.append(d, ' ');
  });
  const add = document.createElement('button'); add.textContent = '+ 指标';
  add.onclick = () => { CL.score_metrics.push(opts[0]); renderClassification(); };
  smWrap.append(add);
  c.appendChild(smWrap);
}

function renderLists() {
  const root = document.getElementById('lists');
  root.innerHTML = '';
  LISTS.forEach((lst, li) => root.appendChild(renderList(lst, li)));
}

function renderList(lst, li) {
  const card = document.createElement('div'); card.className = 'card';
  const head = document.createElement('div'); head.className = 'row';
  const keyIn = document.createElement('input'); keyIn.className = 'key'; keyIn.value = lst.key;
  keyIn.onchange = e => lst.key = e.target.value.trim();
  const labIn = document.createElement('input'); labIn.className = 'label'; labIn.value = lst.label;
  labIn.onchange = e => lst.label = e.target.value;
  head.append(
    fld('键', keyIn),
    fld('名称', labIn),
    fld('状态', sel(lst.state, META.states, v => lst.state = v)),
    fld('组合', sel(lst.logic, META.logics, v => lst.logic = v)),
  );
  const delList = document.createElement('button'); delList.className = 'del'; delList.textContent = '删除清单';
  delList.onclick = () => { LISTS.splice(li, 1); renderLists(); };
  head.append(delList);
  card.append(head);

  lst.conditions.forEach((cond, ci) => card.append(renderCond(lst, cond, ci)));
  const addC = document.createElement('button'); addC.textContent = '+ 新增条件';
  addC.onclick = () => {
    lst.conditions.push({ metric: metricOptions()[0], op: '>', value: 0, value_metric: null, value_mult: 1.0 });
    renderLists();
  };
  card.append(addC);
  return card;
}

function renderCond(lst, cond, ci) {
  const opts = metricOptions();
  const row = document.createElement('div'); row.className = 'cond';
  row.append(sel(cond.metric, opts, v => cond.metric = v));
  row.append(sel(cond.op, META.ops, v => cond.op = v));

  const byMetric = cond.value_metric !== null && cond.value_metric !== undefined;
  const mode = sel(byMetric ? 'metric' : 'const',
    [{ value: 'const', label: '常量值' }, { value: 'metric', label: '指标×倍数' }],
    v => {
      if (v === 'metric') { cond.value = null; cond.value_metric = opts[0]; cond.value_mult = cond.value_mult || 1.0; }
      else { cond.value_metric = null; cond.value = cond.value ?? 0; }
      renderLists();
    });
  row.append(mode);

  if (byMetric) {
    row.append(sel(cond.value_metric, opts, v => cond.value_metric = v));
    row.append(document.createTextNode('×'));
    row.append(num(cond.value_mult ?? 1.0, 'any', v => cond.value_mult = v ?? 1.0));
  } else {
    row.append(num(cond.value ?? 0, 'any', v => cond.value = v));
  }

  const del = document.createElement('button'); del.className = 'del'; del.textContent = '删除';
  del.onclick = () => { lst.conditions.splice(ci, 1); renderLists(); };
  row.append(del);
  return row;
}

function addList() {
  let k = 'list' + (LISTS.length + 1);
  LISTS.push({ key: k, label: '新清单', state: 'A', logic: 'AND',
    conditions: [{ metric: metricOptions()[0], op: '>', value: 0, value_metric: null, value_mult: 1.0 }] });
  renderLists();
}

async function save() {
  const lists = {};
  for (const l of LISTS) {
    if (!l.key) { msg('清单键不能为空', 'err'); return; }
    if (lists[l.key]) { msg('清单键重复：' + l.key, 'err'); return; }
    lists[l.key] = { label: l.label, state: l.state, logic: l.logic, conditions: l.conditions };
  }
  const payload = { classification: CL, lists };
  msg('保存中…');
  const r = await fetch('/api/rules', {
    method: 'PUT', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(payload),
  });
  if (r.ok) { const doc = await r.json(); CL = doc.classification;
    LISTS = Object.entries(doc.lists).map(([key, v]) => ({ key, ...v })); render(); msg('✅ 已保存', 'ok'); }
  else { const e = await r.json(); msg('校验失败：\n' + JSON.stringify(e.detail, null, 2), 'err'); }
}

load();
</script>
</body>
</html>
"""
