"""基于 webhook 的推送实现（Telegram / 钉钉 / Discord）。

httpx 懒加载：未安装/未配置时构造即报错，但不影响其它模块导入。
"""

from __future__ import annotations

from .base import Notifier


class _WebhookNotifier(Notifier):
    def __init__(self, url: str):
        if not url:
            raise ValueError("webhook URL 不能为空")
        self.url = url

    async def _post(self, payload: dict):
        import httpx  # 懒加载
        async with httpx.AsyncClient(timeout=10) as client:
            r = await client.post(self.url, json=payload)
            r.raise_for_status()


class DiscordWebhookNotifier(_WebhookNotifier):
    async def send(self, text: str) -> None:
        await self._post({"content": text})


class DingTalkNotifier(_WebhookNotifier):
    async def send(self, text: str) -> None:
        await self._post({"msgtype": "text", "text": {"content": text}})


class TelegramNotifier(Notifier):
    def __init__(self, bot_token: str, chat_id: str):
        self.url = f"https://api.telegram.org/bot{bot_token}/sendMessage"
        self.chat_id = chat_id

    async def send(self, text: str) -> None:
        import httpx
        async with httpx.AsyncClient(timeout=10) as client:
            r = await client.post(self.url, json={"chat_id": self.chat_id, "text": text})
            r.raise_for_status()
