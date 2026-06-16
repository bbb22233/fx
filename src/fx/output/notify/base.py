"""Notifier 抽象与告警分发。"""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Dict, List


class Notifier(ABC):
    @abstractmethod
    async def send(self, text: str) -> None:
        """推送一条消息。"""


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
