from __future__ import annotations

import logging
import shutil
import typing
from datetime import datetime, timezone
from typing import Dict, List, Optional

import aiohttp
import discord
from colorama import Fore, Style, init
from discord.ext import commands

from utils import config
from utils.Tools import getConfig, np_list, np_remove, np_set, setup_db
from utils.emoji_sync import sync_application_emojis

from .Context import Context

init(autoreset=True)
log = logging.getLogger("testingmusic")

extensions: List[str] = ["cogs"]


class TestingMusic(commands.AutoShardedBot):
    session: aiohttp.ClientSession

    def __init__(self, *args, **kwargs):
        # Only the intents a prefix-command music bot needs. Message Content is the
        # one privileged intent (enable it in the Developer Portal).
        intents = discord.Intents.default()
        intents.message_content = True
        intents.voice_states = True

        super().__init__(
            command_prefix=self.get_prefix,
            case_insensitive=True,
            intents=intents,
            status=discord.Status.do_not_disturb,
            activity=discord.Activity(
                type=discord.ActivityType.playing,
                name=f"{config.DEFAULT_PREFIX}help | music",
            ),
            strip_after_prefix=True,
            owner_ids=set(config.OWNER_IDS),
            allowed_mentions=discord.AllowedMentions(everyone=False, replied_user=False, roles=False),
            shard_count=config.SHARD_COUNT,
        )
        # user_id -> expiry (None = permanent). Loaded from db/np.db, kept in memory for speed.
        self.np_users: Dict[int, Optional[datetime]] = {}
        self._ready_announced = False

    # ── lifecycle ───────────────────────────────────────
    async def setup_hook(self) -> None:
        self.session = aiohttp.ClientSession()
        await setup_db()
        self.np_users = dict(await np_list())
        # Must run before the cogs load: the player buttons read the emoji when they are defined.
        await sync_application_emojis(self, self.session)
        await self.load_extensions()

        if config.ENABLE_JISHAKU:
            try:
                await self.load_extension("jishaku")
                log.warning("Jishaku is enabled: owners can run code on this machine.")
            except Exception:
                log.exception("Could not load jishaku (pip install jishaku)")

        if config.SYNC_COMMANDS:
            try:
                synced = await self.tree.sync()
                log.info("Synced %d slash commands", len(synced))
            except Exception:
                log.exception("Slash command sync failed")

    async def load_extensions(self) -> None:
        for extension in extensions:
            try:
                await self.load_extension(extension)
                print(Fore.GREEN + Style.BRIGHT + f"Loaded extension: {extension}")
            except Exception:
                log.exception("Failed to load extension %s", extension)
        print(Fore.GREEN + Style.BRIGHT + "*" * 20)

    async def close(self) -> None:
        session = getattr(self, "session", None)
        if session is not None and not session.closed:
            await session.close()
        await super().close()

    async def on_ready(self) -> None:
        if self._ready_announced:
            return
        self._ready_announced = True
        print(Fore.MAGENTA + Style.BRIGHT + "=" * 44)
        print(Fore.MAGENTA + Style.BRIGHT + f"   {config.NAME}".center(44))
        print(Fore.MAGENTA + Style.BRIGHT + "=" * 44)
        print("Loaded & Online!")
        print(f"Logged in as: {self.user}")
        print(f"Connected to: {len(self.guilds)} guilds")
        print(f"Commands: {len(set(self.walk_commands()))} prefix | {len(self.tree.get_commands())} slash")
        if not shutil.which(config.FFMPEG_PATH or "ffmpeg"):
            print(Fore.YELLOW + "FFmpeg: NOT FOUND (install it or set FFMPEG_PATH in .env) - music playback will fail")
        else:
            print("FFmpeg: found")
        print()
        print(Fore.CYAN + Style.BRIGHT + "Invite link (open it in your browser to add the bot to a server):")
        print(Fore.CYAN + Style.BRIGHT + self.invite_url)
        print()

    # ── helpers ─────────────────────────────────────────
    @property
    def invite_url(self) -> str:
        """OAuth2 invite link (bot + slash commands) with the permissions a music bot needs."""
        return discord.utils.oauth_url(
            self.application_id or self.user.id,
            permissions=discord.Permissions(
                view_channel=True, send_messages=True, embed_links=True, attach_files=True,
                read_message_history=True, add_reactions=True, use_external_emojis=True,
                connect=True, speak=True, set_voice_channel_status=True, view_audit_log=True,
            ),
            scopes=("bot", "applications.commands"),
        )

    async def get_context(self, origin, *, cls=Context):
        return await super().get_context(origin, cls=cls)

    async def invoke_help_command(self, ctx: Context) -> None:
        """Invoke the help command or default help command if help extensions is not loaded."""
        return await ctx.send_help(ctx.command)

    async def send_raw(self, channel_id: int, content: str, **kwargs) -> typing.Optional[discord.Message]:
        await self.http.send_message(channel_id, content, **kwargs)

    async def fetch_message_by_channel(
        self, channel: discord.TextChannel, messageID: int
    ) -> typing.Optional[discord.Message]:
        async for msg in channel.history(
            limit=1,
            before=discord.Object(messageID + 1),
            after=discord.Object(messageID - 1),
        ):
            return msg

    # ── no-prefix (np) users ────────────────────────────
    async def add_np_user(self, user_id: int, expires_at: Optional[datetime]) -> None:
        await np_set(user_id, expires_at)
        self.np_users[user_id] = expires_at

    async def remove_np_user(self, user_id: int) -> bool:
        self.np_users.pop(user_id, None)
        return await np_remove(user_id)

    async def _is_no_prefix_user(self, user_id: int) -> bool:
        if user_id not in self.np_users:
            return False
        expiry = self.np_users[user_id]
        if expiry is not None and expiry <= datetime.now(timezone.utc):
            await self.remove_np_user(user_id)  # expired: clean up
            return False
        return True

    async def get_prefix(self, message: discord.Message):
        if message.guild:
            prefix = (await getConfig(message.guild.id))["prefix"]
        else:
            prefix = config.DEFAULT_PREFIX

        if await self._is_no_prefix_user(message.author.id):
            # "No prefix" users can run commands without typing a prefix.
            return commands.when_mentioned_or(prefix, "")(self, message)
        return commands.when_mentioned_or(prefix)(self, message)

    async def on_message_edit(self, before: discord.Message, after: discord.Message) -> None:
        if before.content == after.content:
            return
        if after.guild is None or after.author.bot:
            return
        ctx: Context = await self.get_context(after, cls=Context)
        if ctx.command is None:
            return
        await self.invoke(ctx)
