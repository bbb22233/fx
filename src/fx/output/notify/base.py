"""Notifier 抽象与告警分发。"""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Dict, List


class Notifier(ABC):
    @abstractmethod
    async def send(self, text: str) -> None:
        """推送一条消息。"""


class MultiNotifier(Notifier):
    """扇出到多个 Notifier（如同时发 Discord + 钉钉 + Telegram）。单个失败不影响其余。"""

    def __init__(self, notifiers):
        self.notifiers = [n for n in notifiers if n is not None]

    async def send(self, text: str) -> None:
        for n in self.notifiers:
            try:
                await n.send(text)
            except Exception:  # noqa: BLE001 - 一路失败不阻断其它推送
                pass


async def dispatch_alerts(notifier: Notifier, alerts: Dict[str, List[str]]) -> int:
    """把订阅告警逐条推送，返回发送条数。

    alerts: user_id -> [文案...]（user_id 用于 @，由具体 Notifier 决定怎么用）。
    """
    sent = 0
    for user_id, msgs in alerts.items():
        for m in msgs:
            await notifier.send(f"<@{user_id}> {m}")
            sent += 1
    return sent
