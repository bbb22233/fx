"""定时调度：按各周期 K 线收线时刻触发扫描（UTC）。

``timeframe_cron`` 是纯函数（可测）；``start_scheduler`` 用 APScheduler 接线
（懒加载）。收线后稍延迟几秒再扫，确保交易所已生成新 K。
"""

from __future__ import annotations

from typing import Dict

# 收线后延迟秒数（等交易所出新 K）
_CLOSE_DELAY_SEC = 10


def timeframe_cron(timeframe: str) -> Dict:
    """返回 APScheduler CronTrigger 的 kwargs（UTC），对齐各周期收线时刻。"""
    tf = timeframe.lower()
    common = {"minute": 0, "second": _CLOSE_DELAY_SEC, "timezone": "UTC"}
    if tf == "1h":
        return {"hour": "*", **common}
    if tf == "4h":
        return {"hour": "0,4,8,12,16,20", **common}
    if tf == "8h":
        return {"hour": "0,8,16", **common}
    if tf == "1d":
        return {"hour": 0, **common}
    raise ValueError(f"未支持的调度周期: {timeframe!r}")


def start_scheduler(service, settings, on_result=None):  # pragma: no cover - 需 APScheduler
    """为每个周期注册收线扫描任务，并启动调度器。

    on_result(summary): 每轮扫描后的回调（推送/落库已在 service.rescan 内完成）。
    """
    from apscheduler.schedulers.asyncio import AsyncIOScheduler
    from apscheduler.triggers.cron import CronTrigger

    scheduler = AsyncIOScheduler(timezone="UTC")

    async def _job():
        summary = await service.rescan()
        if on_result:
            await on_result(summary)

    seen = set()
    for tf in settings.timeframes:
        cron = timeframe_cron(tf)
        # 避免不同周期在同一时刻重复触发：用 cron 表达式去重
        key = tuple(sorted(cron.items()))
        if key in seen:
            continue
        seen.add(key)
        scheduler.add_job(_job, CronTrigger(**cron), id=f"scan-{tf}",
                          misfire_grace_time=120, coalesce=True)

    scheduler.start()
    return scheduler
