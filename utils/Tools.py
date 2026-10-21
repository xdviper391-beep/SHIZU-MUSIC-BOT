from __future__ import annotations

import os
import sys
from datetime import datetime, timezone
from typing import List, Optional, Tuple

import aiosqlite
import discord
from discord.ext import commands

from utils import emojis as E
from utils.config import DB_DIR, DEFAULT_PREFIX

__all__ = [
    "setup_db",
    "getConfig",
    "updateConfig",
    "restart_program",
    "blacklist_check",
    "ignore_check",
    "top_check",
    "get_ignore_data",
    "is_topcheck_enabled",
    "db_path",
    "np_set",
    "np_remove",
    "np_list",
]


def db_path(name: str) -> str:
    """Absolute path of a database file inside ./db (independent of the working directory)."""
    return str(DB_DIR / name)


async def setup_db() -> None:
    """Create the db folder and every table the bot reads. Safe to call on every start."""
    DB_DIR.mkdir(parents=True, exist_ok=True)

    async with aiosqlite.connect(db_path("prefix.db")) as db:
        await db.execute(
            """CREATE TABLE IF NOT EXISTS prefixes (
                guild_id INTEGER PRIMARY KEY,
                prefix TEXT NOT NULL
            )"""
        )
        await db.commit()

    async with aiosqlite.connect(db_path("block.db")) as db:
        await db.execute(
            """CREATE TABLE IF NOT EXISTS user_blacklist (
                user_id INTEGER PRIMARY KEY,
                timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )"""
        )
        await db.execute(
            """CREATE TABLE IF NOT EXISTS guild_blacklist (
                guild_id INTEGER PRIMARY KEY,
                timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )"""
        )
        await db.commit()

    async with aiosqlite.connect(db_path("ignore.db")) as db:
        await db.execute("CREATE TABLE IF NOT EXISTS ignored_commands (guild_id INTEGER, command_name TEXT)")
        await db.execute("CREATE TABLE IF NOT EXISTS ignored_channels (guild_id INTEGER, channel_id INTEGER)")
        await db.execute("CREATE TABLE IF NOT EXISTS ignored_users (guild_id INTEGER, user_id INTEGER)")
        await db.execute("CREATE TABLE IF NOT EXISTS bypassed_users (guild_id INTEGER, user_id INTEGER)")
        await db.commit()

    async with aiosqlite.connect(db_path("np.db")) as db:
        await db.execute("CREATE TABLE IF NOT EXISTS np (id INTEGER PRIMARY KEY, expiry_time TEXT NULL)")
        await db.execute("CREATE TABLE IF NOT EXISTS staff (id INTEGER PRIMARY KEY)")
        await db.execute("CREATE TABLE IF NOT EXISTS autonp (guild_id INTEGER PRIMARY KEY)")
        await db.commit()

    async with aiosqlite.connect(db_path("topcheck.db")) as db:
        await db.execute(
            "CREATE TABLE IF NOT EXISTS topcheck (guild_id INTEGER PRIMARY KEY, enabled INTEGER DEFAULT 0)"
        )
        await db.commit()


async def is_topcheck_enabled(guild_id: int) -> bool:
    async with aiosqlite.connect(db_path("topcheck.db")) as db:
        async with db.execute("SELECT enabled FROM topcheck WHERE guild_id = ?", (guild_id,)) as cursor:
            row = await cursor.fetchone()
            return row is not None and row[0] == 1


async def getConfig(guildID: int) -> dict:
    """Per-guild config. Guilds without a stored prefix use the PREFIX from .env."""
    async with aiosqlite.connect(db_path("prefix.db")) as db:
        async with db.execute("SELECT prefix FROM prefixes WHERE guild_id = ?", (guildID,)) as cursor:
            row = await cursor.fetchone()
    return {"prefix": row[0] if row else DEFAULT_PREFIX}


async def updateConfig(guildID: int, data: dict) -> None:
    async with aiosqlite.connect(db_path("prefix.db")) as db:
        await db.execute(
            "INSERT OR REPLACE INTO prefixes (guild_id, prefix) VALUES (?, ?)",
            (guildID, data["prefix"]),
        )
        await db.commit()


def restart_program() -> None:
    python = sys.executable
    os.execl(python, python, *sys.argv)


def blacklist_check():
    async def predicate(ctx: commands.Context) -> bool:
        if ctx.guild is None:
            raise commands.NoPrivateMessage()
        async with aiosqlite.connect(db_path("block.db")) as db:
            cursor = await db.execute("SELECT 1 FROM user_blacklist WHERE user_id = ?", (ctx.author.id,))
            if await cursor.fetchone():
                return False
            cursor = await db.execute("SELECT 1 FROM guild_blacklist WHERE guild_id = ?", (ctx.guild.id,))
            if await cursor.fetchone():
                return False
        return True

    return commands.check(predicate)


async def get_ignore_data(guild_id: int) -> dict:
    data = {"channel": set(), "user": set(), "command": set(), "bypassuser": set()}
    async with aiosqlite.connect(db_path("ignore.db")) as db:
        async with db.execute("SELECT channel_id FROM ignored_channels WHERE guild_id = ?", (guild_id,)) as cur:
            data["channel"] = {str(row[0]) for row in await cur.fetchall()}
        async with db.execute("SELECT user_id FROM ignored_users WHERE guild_id = ?", (guild_id,)) as cur:
            data["user"] = {str(row[0]) for row in await cur.fetchall()}
        async with db.execute("SELECT command_name FROM ignored_commands WHERE guild_id = ?", (guild_id,)) as cur:
            data["command"] = {str(row[0]).strip().lower() for row in await cur.fetchall()}
        async with db.execute("SELECT user_id FROM bypassed_users WHERE guild_id = ?", (guild_id,)) as cur:
            data["bypassuser"] = {str(row[0]) for row in await cur.fetchall()}
    return data


def ignore_check():
    async def predicate(ctx: commands.Context) -> bool:
        if ctx.guild is None:
            raise commands.NoPrivateMessage()
        data = await get_ignore_data(ctx.guild.id)

        if str(ctx.author.id) in data["bypassuser"]:
            return True
        if str(ctx.channel.id) in data["channel"] or str(ctx.author.id) in data["user"]:
            return False

        names = {ctx.command.name.strip().lower()}
        names.update(alias.strip().lower() for alias in ctx.command.aliases)
        if names & data["command"]:
            return False
        return True

    return commands.check(predicate)


def top_check():
    async def predicate(ctx: commands.Context) -> bool:
        if not ctx.guild:
            return True
        if getattr(ctx, "invoked_with", None) in ("help", "h"):
            return True
        if not await is_topcheck_enabled(ctx.guild.id):
            return True

        if ctx.author != ctx.guild.owner and ctx.author.top_role.position <= ctx.guild.me.top_role.position:
            embed = discord.Embed(
                title=f"{E.DENIED} Access Denied",
                description="Your top role must be at a **higher** position than my top role.",
                color=0x000000,
            )
            embed.set_footer(
                text=f"“{ctx.command.qualified_name}” command executed by {ctx.author}",
                icon_url=ctx.author.display_avatar.url,
            )
            await ctx.send(embed=embed)
            return False
        return True

    return commands.check(predicate)


# ───────────────────── no-prefix (np) storage ─────────────────────
def _parse_expiry(value: Optional[str]) -> Optional[datetime]:
    """Stored expiry -> aware UTC datetime. None (or unreadable) means 'never expires'."""
    if not value:
        return None
    try:
        parsed = datetime.fromisoformat(str(value))
    except ValueError:
        return None
    return parsed if parsed.tzinfo else parsed.replace(tzinfo=timezone.utc)


async def np_set(user_id: int, expires_at: Optional[datetime]) -> None:
    """Add a user to the no-prefix list (or update their expiry). expires_at=None means permanent."""
    stored = expires_at.astimezone(timezone.utc).isoformat() if expires_at else None
    async with aiosqlite.connect(db_path("np.db")) as db:
        await db.execute("INSERT OR REPLACE INTO np (id, expiry_time) VALUES (?, ?)", (user_id, stored))
        await db.commit()


async def np_remove(user_id: int) -> bool:
    """Remove a user. Returns False if they weren't on the list."""
    async with aiosqlite.connect(db_path("np.db")) as db:
        async with db.execute("SELECT 1 FROM np WHERE id = ?", (user_id,)) as cursor:
            if await cursor.fetchone() is None:
                return False
        await db.execute("DELETE FROM np WHERE id = ?", (user_id,))
        await db.commit()
    return True


async def np_list() -> List[Tuple[int, Optional[datetime]]]:
    """All active no-prefix users. Expired entries are deleted on the way."""
    now = datetime.now(timezone.utc)
    active: List[Tuple[int, Optional[datetime]]] = []
    expired: List[int] = []
    async with aiosqlite.connect(db_path("np.db")) as db:
        async with db.execute("SELECT id, expiry_time FROM np") as cursor:
            rows = await cursor.fetchall()
        for user_id, raw in rows:
            expiry = _parse_expiry(raw)
            if expiry is not None and expiry <= now:
                expired.append(user_id)
            else:
                active.append((int(user_id), expiry))
        for user_id in expired:
            await db.execute("DELETE FROM np WHERE id = ?", (user_id,))
        if expired:
            await db.commit()
    return active
