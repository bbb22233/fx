"""Discord 命令的格式化与路由。

格式化是纯函数（可离线单测）；CommandRouter 把命令委托给 ScanService。
discord.py 的 bot.py 只需把交互事件转成 ``router.handle(...)``。
"""

from __future__ import annotations

from typing import List, Optional

from ...output.serialize import collapse_by_symbol, format_symbol_entry
from ...service import LIST_NAMES, ScanService

LIST_LABELS = {"top": "顶部", "bottom": "底部", "squeeze": "收口待变盘", "watch": "观察区"}


# ----------------------------- 格式化（纯函数） -----------------------------
def format_scan(summary: Optional[dict]) -> str:
    if not summary:
        return "暂无扫描结果，先用 `/rescan` 跑一轮。"
    metrics = summary.get("metrics", {})
    lines = [f"📊 扫描时间：{summary.get('as_of', '?')}"]
    for name in LIST_NAMES:
        keys = summary.get("lists", {}).get(name, [])
        entries = collapse_by_symbol(keys, metrics)        # 同币跨所去重
        label = LIST_LABELS.get(name, name)
        names = [format_symbol_entry(e) for e in entries]
        shown = ", ".join(names[:15]) + (f" …(+{len(names) - 15})" if len(names) > 15 else "")
        lines.append(f"【{label}】({len(entries)}): {shown or '—'}")
    return "\n".join(lines)


def format_symbol(snapshot: Optional[dict]) -> str:
    if not snapshot:
        return "未找到该币种（可能不在最近扫描范围内，或先 `/rescan`）。"
    p = snapshot.get("periods", {}).get("1d", {})
    return (
        f"🔎 {snapshot['symbol']}\n"
        f"  资金费率: {snapshot.get('funding_rate')} (百分位 {snapshot.get('funding_rate_pct_rank')})\n"
        f"  MAD21%: {snapshot.get('mad21_pct')} (百分位 {snapshot.get('mad21_pct_rank')}) | "
        f"MAD72%: {snapshot.get('mad72_pct')}\n"
        f"  1D: %B={p.get('pctB')} 带宽%={p.get('bandwidth_pct')} "
        f"(rank {p.get('bandwidth_pct_rank')}) 剩余动能={p.get('remaining_energy_pct')} "
        f"ATR%={p.get('atr_pct')}"
    )


def format_subscriptions(targets: List[str]) -> str:
    if not targets:
        return "你还没有订阅。用 `/sub <清单名或币种>` 添加，如 `/sub top` 或 `/sub BTC/USDT:USDT`。"
    return "你的订阅：\n" + "\n".join(f"• {t}" for t in targets)


def format_realtime_alert(alert) -> str:
    """实时异动告警文案。"""
    return (
        f"⚡ 异动 {alert.symbol} ({alert.timeframe})\n"
        f"  现价 {alert.price} | 已走幅度 {alert.amplitude_pct:.2f}% "
        f"(时间进度 {alert.elapsed_fraction*100:.0f}%) "
        f"剩余动能 {alert.remaining_energy_pct:+.2f} → 提前发力"
    )


def format_rules(desc: dict) -> str:
    lines = ["⚙️ 当前规则阈值（`/setrule <路径> <值>` 修改）："]
    for k, v in desc.items():
        lines.append(f"  {k} = {v}")
    return "\n".join(lines)


# ----------------------------- 路由 -----------------------------
class CommandRouter:
    """把命令名 + 参数委托给 ScanService，返回给用户展示的文本。"""

    def __init__(self, service: ScanService):
        self.svc = service

    async def handle(self, command: str, user_id: str, args: Optional[List[str]] = None) -> str:
        args = args or []
        if command == "scan":
            return format_scan(self.svc.get_latest())
        if command == "rescan":
            summary = await self.svc.rescan()
            return "✅ 已重新扫描。\n" + format_scan(summary)
        if command == "symbol":
            if not args:
                return "用法：`/symbol <币种>`"
            return format_symbol(self.svc.get_symbol(args[0]))
        if command == "sub":
            if not args:
                return "用法：`/sub <清单名或币种>`"
            ok = self.svc.subscribe(user_id, args[0])
            return f"{'✅ 已订阅' if ok else '已存在订阅'}：{args[0]}"
        if command == "unsub":
            if not args:
                return "用法：`/unsub <清单名或币种>`"
            ok = self.svc.unsubscribe(user_id, args[0])
            return f"{'✅ 已取消订阅' if ok else '未找到该订阅'}：{args[0]}"
        if command == "subs":
            return format_subscriptions(self.svc.list_subscriptions(user_id))
        if command == "rules":
            return format_rules(self.svc.describe_rules())
        if command == "setrule":
            if len(args) < 2:
                return "用法：`/setrule <路径> <值>`，如 `/setrule classification.high_vol_min 65`"
            try:
                desc = self.svc.set_rule(args[0], args[1])
            except Exception as exc:
                return f"❌ 修改失败：{exc}"
            return "✅ 已更新规则。\n" + format_rules(desc)
        return f"未知命令：{command}"
