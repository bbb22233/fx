"""把订阅告警直接发到 bot 所在频道（而非 webhook）。

不 import discord —— 只调用传入 client 的方法，因此可离线单测（喂个假 client 即可）。
``dispatch_alerts`` 产出的文案已带 ``<@用户ID>``，频道消息会自动渲染为 @ 提醒。
"""

from __future__ import annotations

from ..notify.base import Notifier


class DiscordBotNotifier(Notifier):
    def __init__(self, client, channel_id):
        self.client = client
        self.channel_id = int(channel_id)

    async def send(self, text: str) -> None:
        channel = self.client.get_channel(self.channel_id)
        if channel is None:                              # 缓存未就绪时回退到 fetch
            channel = await self.client.fetch_channel(self.channel_id)
        await channel.send(text)
