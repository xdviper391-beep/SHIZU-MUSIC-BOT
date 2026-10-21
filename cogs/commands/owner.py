from __future__ import annotations

import re
from datetime import datetime, timedelta, timezone
from typing import Optional, Tuple

import discord
from discord.ext import commands

from core import ShizuMusic
from utils import DescriptionEmbedPaginator, Paginator
from utils import emojis as E

_DURATION_RE = re.compile(r"^(\d{1,5})\s*([mhdw])$", re.IGNORECASE)
_UNITS = {"m": "minutes", "h": "hours", "d": "days", "w": "weeks"}
_PERMANENT = {"perm", "permanent", "lifetime", "forever", "never"}
_MAX_DURATION = timedelta(days=3650)


def parse_duration(text: str) -> Tuple[bool, Optional[timedelta]]:
    """'30m' / '12h' / '7d' / '2w' -> (True, timedelta); 'permanent' -> (True, None); bad -> (False, None)."""
    text = text.strip().lower()
    if text in _PERMANENT:
        return True, None
    match = _DURATION_RE.match(text)
    if not match:
        return False, None
    amount, unit = int(match.group(1)), match.group(2).lower()
    delta = timedelta(**{_UNITS[unit]: amount})
    if amount <= 0 or delta > _MAX_DURATION:
        return False, None
    return True, delta


def _embed(text: str, color: int = 0x000000) -> discord.Embed:
    return discord.Embed(description=text, color=color)


def _access(expires_at: Optional[datetime]) -> str:
    if expires_at is None:
        return "Permanent"
    stamp = int(expires_at.timestamp())
    return f"until <t:{stamp}:F> (<t:{stamp}:R>)"


class Owner(commands.Cog):
    """Bot-owner only commands. Hidden from help, silent for everyone else."""

    def __init__(self, bot: ShizuMusic):
        self.bot = bot

    async def cog_check(self, ctx: commands.Context) -> bool:
        if not await self.bot.is_owner(ctx.author):
            raise commands.NotOwner()  # Errors cog stays silent for this
        return True

    @commands.group(name="np", invoke_without_command=True, hidden=True, usage="np <add|remove|list>")
    async def np(self, ctx: commands.Context):
        await ctx.send(
            embed=_embed(
                "**No-prefix (np) users**\n"
                "`np add <user> [duration]` - let a user run commands without a prefix\n"
                "`np remove <user>` - take it away\n"
                "`np list` - show everyone on the list\n\n"
                "Duration: `30m`, `12h`, `7d`, `2w` or `permanent` (default)."
            )
        )

    @np.command(name="add", hidden=True, usage="np add <user> [duration]")
    async def np_add(self, ctx: commands.Context, user: discord.User, duration: str = "permanent"):
        if user.bot:
            await ctx.send(embed=_embed(f"{E.WARNING} Bots can't be added to the no-prefix list.", 0xFF0000))
            return

        valid, delta = parse_duration(duration)
        if not valid:
            await ctx.send(
                embed=_embed(f"{E.WARNING} Invalid duration. Use `30m`, `12h`, `7d`, `2w` or `permanent`.", 0xFF0000)
            )
            return

        expires_at = datetime.now(timezone.utc) + delta if delta else None
        already = user.id in self.bot.np_users
        await self.bot.add_np_user(user.id, expires_at)

        verb = "Updated" if already else "Added"
        await ctx.send(
            embed=_embed(
                f"{E.TICK} {verb} **{user}** (`{user.id}`) on the no-prefix list.\nAccess: **{_access(expires_at)}**"
            )
        )

    @np.command(name="remove", aliases=["rm", "delete"], hidden=True, usage="np remove <user>")
    async def np_remove(self, ctx: commands.Context, user: discord.User):
        if await self.bot.remove_np_user(user.id):
            await ctx.send(embed=_embed(f"{E.TICK} Removed **{user}** (`{user.id}`) from the no-prefix list."))
        else:
            await ctx.send(embed=_embed(f"{E.WARNING} **{user}** isn't on the no-prefix list.", 0xFF0000))

    @np.command(name="list", aliases=["all"], hidden=True, usage="np list")
    async def np_list(self, ctx: commands.Context):
        now = datetime.now(timezone.utc)
        active = {uid: exp for uid, exp in self.bot.np_users.items() if exp is None or exp > now}
        if not active:
            await ctx.send(embed=_embed(f"{E.WARNING} The no-prefix list is empty."))
            return

        entries = [
            f"{index}. <@{user_id}> (`{user_id}`) - {_access(expiry)}"
            for index, (user_id, expiry) in enumerate(sorted(active.items()), start=1)
        ]
        embeds = DescriptionEmbedPaginator(
            entries=entries,
            title="No-prefix users",
            description="Users who can run commands without a prefix.",
            per_page=10,
            color=0x000000,
        ).get_pages()
        await Paginator(ctx, embeds).paginate()

    # ── emergency tools ─────────────────────────────────
    async def reset_guild_playback(self, guild: discord.Guild) -> str:
        """Wipe everything about the guild's music playback. Returns a short report."""
        from cogs.commands import music as music_module  # local import: the music cog imports core, not owner

        cog = self.bot.get_cog("Music")
        notes = []
        vc = guild.voice_client
        channel = getattr(vc, "channel", None)
        if channel is not None:
            await music_module.set_vc_status(channel, None)
        if cog is not None:
            cog.forget_guild(guild.id)
            cog.recent.pop(guild.id, None)
        if isinstance(vc, music_module.MusicPlayer):
            try:
                await vc.shutdown()
                notes.append("player stopped, queue cleared")
            except Exception:
                notes.append("player was stuck, forced it off")
        if guild.voice_client is not None:  # stale / half-dead voice connection
            try:
                await guild.voice_client.disconnect(force=True)
                notes.append("voice connection reset")
            except Exception:
                try:
                    guild.voice_client.cleanup()
                except Exception:
                    pass
        music_module._client_start = 0  # try YouTube's default clients first again
        notes.append("YouTube client fallback reset")
        return ", ".join(notes)

    @commands.command(name="forcefix", aliases=["ff"], hidden=True, usage="forcefix [guild_id]")
    async def forcefix(self, ctx: commands.Context, guild_id: Optional[str] = None):
        """Fix a music playback error: stop, clear the queue and reset this (or the given) guild's player."""
        guild = ctx.guild
        if guild_id:
            digits = re.sub(r"\D", "", guild_id)
            guild = self.bot.get_guild(int(digits)) if digits else None
        if guild is None:
            await ctx.send(embed=_embed(f"{E.WARNING} I can't find that server.", 0xFF0000))
            return
        report = await self.reset_guild_playback(guild)
        await ctx.send(
            embed=_embed(f"{E.TICK} Music playback reset for **{guild.name}** (`{guild.id}`): {report}.\nStart again with the play command.")
        )

    @commands.command(name="forcequit", aliases=["fq"], hidden=True, usage="forcequit <guild_id>")
    async def forcequit(self, ctx: commands.Context, guild_id: str):
        """Make the bot leave the server with the given ID."""
        digits = re.sub(r"\D", "", guild_id)
        guild = self.bot.get_guild(int(digits)) if digits else None
        if guild is None:
            await ctx.send(embed=_embed(f"{E.WARNING} I'm not in a server with that ID.", 0xFF0000))
            return
        name, gid = guild.name, guild.id
        try:
            await self.reset_guild_playback(guild)
        except Exception:
            pass
        try:
            await guild.leave()
        except discord.HTTPException as exc:
            await ctx.send(embed=_embed(f"{E.WARNING} I couldn't leave **{name}**: {exc}", 0xFF0000))
            return
        try:
            await ctx.send(embed=_embed(f"{E.TICK} Left **{name}** (`{gid}`)."))
        except discord.HTTPException:
            pass  # the command was run inside the guild we just left
