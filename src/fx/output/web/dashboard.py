"""扫盘看板页面 —— TUI 黑客风（绿底黑、等宽字体），移动端优先 + 自动刷新 + 扫描。

由 ``app.py`` 的 ``GET /`` 返回 ``DASHBOARD_HTML``（静态 shell，不碰 store）。
数据走既有 API：``GET /api/scan/latest``、``POST /api/rescan``。同币跨所去重在前端做
（与 serialize.collapse_by_symbol 同口径）。点击币种展开各交易所 16 指标快照（直接用
latest 里已带的 metrics，无需再请求）。
"""

from __future__ import annotations

DASHBOARD_HTML = r"""<!DOCTYPE html>
<html lang="zh">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1, maximum-scale=1">
<title>fx// scanner</title>
<style>
  :root { --g: #33ff66; --dim: #1f8a45; --bg: #050805; --panel: #0a120c; --warn: #ffcc00; --err: #ff4455; }
  * { box-sizing: border-box; }
  html, body { margin: 0; background: var(--bg); }
  body {
    color: var(--g); font-family: ui-monospace, "SF Mono", Menlo, Consolas, "Courier New", monospace;
    font-size: 14px; line-height: 1.45; padding: 10px; max-width: 1100px; margin: 0 auto;
    text-shadow: 0 0 4px rgba(51,255,102,.35);
  }
  /* 扫描线叠层 */
  body::before {
    content: ""; position: fixed; inset: 0; pointer-events: none; z-index: 9;
    background: repeating-linear-gradient(0deg, rgba(0,0,0,0) 0, rgba(0,0,0,0) 2px, rgba(0,0,0,.18) 3px);
  }
  a { color: var(--g); text-decoration: none; border-bottom: 1px dotted var(--dim); }
  h1 { font-size: 16px; margin: 0 0 8px; letter-spacing: 1px; }
  .blink { animation: blink 1s steps(2,start) infinite; }
  @keyframes blink { to { visibility: hidden; } }
  .bar { display: flex; flex-wrap: wrap; gap: 8px; align-items: center;
         border: 1px solid var(--dim); padding: 8px; margin-bottom: 10px; }
  .bar .sep { color: var(--dim); }
  button, .toggle {
    font-family: inherit; font-size: 13px; color: var(--g); background: transparent;
    border: 1px solid var(--g); padding: 5px 12px; cursor: pointer; text-transform: uppercase;
    letter-spacing: 1px;
  }
  button:hover { background: var(--g); color: #000; text-shadow: none; }
  button:disabled { opacity: .4; cursor: wait; }
  .toggle.on { background: var(--g); color: #000; text-shadow: none; }
  #status { color: var(--dim); }
  #status.warn { color: var(--warn); } #status.err { color: var(--err); }
  .grid { display: grid; gap: 10px; grid-template-columns: repeat(auto-fit, minmax(260px, 1fr)); }
  .panel { border: 1px solid var(--dim); background: var(--panel); padding: 0; }
  .panel > .head { padding: 6px 10px; border-bottom: 1px solid var(--dim);
                   display: flex; justify-content: space-between; background: rgba(51,255,102,.06); }
  .panel.top .head { color: var(--err); border-color: var(--err); }
  .panel.bottom .head { color: var(--warn); }
  .rows { padding: 4px 0; max-height: 46vh; overflow-y: auto; }
  .row { padding: 3px 10px; cursor: pointer; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }
  .row:hover { background: rgba(51,255,102,.12); }
  .row::before { content: "› "; color: var(--dim); }
  .row.open::before { content: "▼ "; }
  .detail { padding: 4px 10px 8px 22px; color: var(--dim); font-size: 12px; white-space: pre-wrap; }
  .empty { padding: 8px 10px; color: var(--dim); }
  .count { color: var(--dim); }
  @media (max-width: 600px) { body { font-size: 13px; padding: 6px; } .rows { max-height: none; } }
</style>
</head>
<body>
<h1>fx// CRYPTO MARKET SCANNER<span class="blink">_</span></h1>
<div class="bar">
  <button id="scan" onclick="doScan()">▶ scan</button>
  <button id="autoscan" class="toggle" onclick="toggleAutoScan()">auto-scan: off</button>
  <span class="sep">|</span>
  <span id="status">booting…</span>
  <span class="sep">|</span>
  <span id="clock"></span>
  <a href="/rules" style="margin-left:auto">⚙ rules</a>
</div>
<div id="grid" class="grid"></div>

<script>
const LABELS = { top: "顶部 / TOP", bottom: "底部 / BOTTOM", squeeze: "收口 / SQUEEZE", watch: "观察 / WATCH" };
const ORDER = ["top", "bottom", "squeeze", "watch"];
const REFRESH_MS = 5000;    // 结果自动刷新
const SCAN_MS = 60000;      // 自动扫描间隔
let latest = null, scanning = false, autoScan = false, scanTimer = null;

function esc(s) { return String(s).replace(/[&<>]/g, c => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;" }[c])); }
function status(t, cls) { const s = document.getElementById("status"); s.textContent = t; s.className = cls || ""; }
function fmt(x, n) { return (x === null || x === undefined) ? "—" : (+x).toFixed(n); }

// 同币跨所去重（口径同后端 serialize.collapse_by_symbol）
function collapse(keys, metrics) {
  const out = {};
  for (const k of keys || []) {
    const m = metrics[k] || {};
    const sym = m.symbol || k, ex = m.exchange || null;
    (out[sym] = out[sym] || { symbol: sym, items: [] }).items.push({ exchange: ex, key: k });
  }
  return Object.values(out);
}
function entryLabel(e) {
  const exs = e.items.map(i => i.exchange).filter(Boolean);
  return e.symbol + (exs.length ? ` [${exs.join(", ")}]` : "");
}
function detailText(e, metrics) {
  return e.items.map(it => {
    const m = metrics[it.key] || {}, p = (m.periods || {})["1d"] || {};
    const tag = it.exchange ? it.exchange + "  " : "";
    return `${tag}1D %B=${fmt(p.pctB, 2)} bw%rk=${fmt(p.bandwidth_pct_rank, 0)} `
         + `rem=${fmt(p.remaining_energy_pct, 2)} atr%=${fmt(p.atr_pct, 2)}\n`
         + `    mad21rk=${fmt(m.mad21_pct_rank, 0)} fund=${fmt(m.funding_rate, 5)} (rk ${fmt(m.funding_rate_pct_rank, 0)})`;
  }).join("\n");
}

function render() {
  const grid = document.getElementById("grid");
  if (!latest || !latest.lists) { grid.innerHTML = '<div class="empty">// no scan yet — press [scan]</div>'; return; }
  const metrics = latest.metrics || {};
  grid.innerHTML = "";
  for (const name of ORDER) {
    const entries = collapse((latest.lists || {})[name], metrics);
    const panel = document.createElement("div");
    panel.className = "panel " + name;
    panel.innerHTML = `<div class="head"><span>${LABELS[name]}</span><span class="count">[${entries.length}]</span></div>`;
    const rows = document.createElement("div"); rows.className = "rows";
    if (!entries.length) rows.innerHTML = '<div class="empty">—</div>';
    for (const e of entries) {
      const row = document.createElement("div"); row.className = "row"; row.textContent = entryLabel(e);
      const det = document.createElement("div"); det.className = "detail"; det.style.display = "none";
      row.onclick = () => {
        const open = det.style.display === "none";
        det.style.display = open ? "block" : "none";
        row.classList.toggle("open", open);
        if (open && !det.dataset.filled) { det.textContent = detailText(e, metrics); det.dataset.filled = "1"; }
      };
      rows.append(row, det);
    }
    panel.append(rows);
    grid.append(panel);
  }
}

async function loadLatest() {
  try {
    const r = await fetch("/api/scan/latest");
    latest = await r.json();
    render();
    const t = latest && latest.as_of ? latest.as_of.replace("T", " ").slice(0, 19) + "Z" : "n/a";
    if (!scanning) status("last scan: " + t);
  } catch (e) { status("link down: " + e, "err"); }
}

async function doScan() {
  if (scanning) return;
  scanning = true;
  document.getElementById("scan").disabled = true;
  status("scanning… ▓▓▓", "warn");
  try {
    const r = await fetch("/api/rescan", { method: "POST" });
    if (!r.ok) throw new Error("HTTP " + r.status);
    await loadLatest();
    status("scan complete ✓");
  } catch (e) {
    status("scan failed: " + e + " — auto-scan off", "err");
    autoScan = false; syncAutoScan();
  } finally {
    scanning = false;
    document.getElementById("scan").disabled = false;
  }
}

function syncAutoScan() {
  const b = document.getElementById("autoscan");
  b.textContent = "auto-scan: " + (autoScan ? "on" : "off");
  b.classList.toggle("on", autoScan);
  localStorage.setItem("fx_autoscan", autoScan ? "1" : "0");
  if (scanTimer) { clearInterval(scanTimer); scanTimer = null; }
  if (autoScan) scanTimer = setInterval(doScan, SCAN_MS);
}
function toggleAutoScan() { autoScan = !autoScan; syncAutoScan(); if (autoScan) doScan(); }

function tick() { document.getElementById("clock").textContent = new Date().toISOString().slice(11, 19) + "Z"; }

autoScan = localStorage.getItem("fx_autoscan") === "1";
syncAutoScan();
tick(); setInterval(tick, 1000);
loadLatest(); setInterval(loadLatest, REFRESH_MS);   // 结果自动刷新
</script>
</body>
</html>
"""
