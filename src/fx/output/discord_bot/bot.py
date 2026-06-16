"""discord.py 接线层。

把 slash 命令交互转发给 ``CommandRouter``。discord.py 懒加载，未安装时
本模块仍可被导入（便于离线/最小依赖）；``run_bot`` 调用时才真正需要。
"""

from __future__ import annotations

import os

from .commands import CommandRouter


def build_client(router: CommandRouter, settings=None, channel_id=None):  # pragma: no cover - 需 discord.py/网络
    import discord
    from discord import app_commands

    intents = discord.Intents.default()
    client = discord.Client(intents=intents)
    tree = app_commands.CommandTree(client)
    _started = {"v": False}

    @client.event
    async def on_ready():
        await tree.sync()
        # 配了频道 → 用「频道内推送」notifier，并在本进程起定时扫描（告警直接发到频道）
        if _started["v"] or not channel_id:
            return
        _started["v"] = True
        from .notify import DiscordBotNotifier
        router.svc.notifier = DiscordBotNotifier(client, channel_id)
        if settings is not None:
            from ...scanner.scheduler import start_scheduler
            start_scheduler(router.svc, settings)

    @tree.command(name="scan", description="查看最新扫盘结果")
    async def scan(it: "discord.Interaction"):
        await it.response.send_message(await router.handle("scan", str(it.user.id)))

    @tree.command(name="rescan", description="立即重新扫描一轮")
    async def rescan(it: "discord.Interaction"):
        await it.response.defer(thinking=True)
        await it.followup.send(await router.handle("rescan", str(it.user.id)))

    @tree.command(name="symbol", description="查看单个币种指标快照")
    async def symbol(it: "discord.Interaction", name: str):
        await it.response.send_message(await router.handle("symbol", str(it.user.id), [name]))

    @tree.command(name="sub", description="订阅清单或币种")
    async def sub(it: "discord.Interaction", target: str):
        await it.response.send_message(await router.handle("sub", str(it.user.id), [target]))

    @tree.command(name="unsub", description="取消订阅")
    async def unsub(it: "discord.Interaction", target: str):
        await it.response.send_message(await router.handle("unsub", str(it.user.id), [target]))

    @tree.command(name="subs", description="查看我的订阅")
    async def subs(it: "discord.Interaction"):
        await it.response.send_message(await router.handle("subs", str(it.user.id)))

    @tree.command(name="rules", description="查看规则阈值")
    async def rules(it: "discord.Interaction"):
        await it.response.send_message(await router.handle("rules", str(it.user.id)))

    @tree.command(name="setrule", description="修改规则阈值")
    async def setrule(it: "discord.Interaction", path: str, value: str):
        await it.response.send_message(
            await router.handle("setrule", str(it.user.id), [path, value]))

    return client


def run_bot(router: CommandRouter, token: str = None, settings=None, channel_id=None):  # pragma: no cover
    token = token or os.getenv("DISCORD_BOT_TOKEN")
    channel_id = channel_id or os.getenv("DISCORD_CHANNEL_ID")
    if not token:
        raise RuntimeError("缺少 DISCORD_BOT_TOKEN")
    client = build_client(router, settings=settings, channel_id=channel_id)
    client.run(token)
