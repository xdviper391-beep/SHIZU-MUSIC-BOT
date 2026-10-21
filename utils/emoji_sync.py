"""Make every emoji in utils/emojis.py render, even when the bot is not in the emoji's server.

Discord only shows a custom emoji in message text when the bot can use it: the bot is in the
emoji's server, or the emoji belongs to the bot's own application. So at startup, each emoji in
utils/emojis.py that is not already one of this application's emoji is copied from Discord's CDN
into the bot's application emoji (Developer Portal > your app > Emojis) and the constant in
utils/emojis.py is swapped for the copy. Copies are named after the original plus the last digits
of its ID, so a restart reuses them instead of uploading again.

Needs discord.py 2.5+. It never blocks startup: if anything fails, the original emoji is kept.
Emoji that no longer exist on Discord (deleted) can't be copied and stay as they are.
"""
from __future__ import annotations

import asyncio
import logging
import re
from typing import Dict, Optional

import discord

from utils import emojis

log = logging.getLogger("shizumusic.emojis")

EMOJI_RE = re.compile(r"^<(a?):([A-Za-z0-9_]{2,32}):(\d{15,25})>$")
CDN_URL = "https://cdn.discordapp.com/emojis/{id}.{ext}?size={size}&quality=lossless"
MAX_BYTES = 256 * 1024  # Discord's limit for an emoji image


def clone_name(name: str, emoji_id: int) -> str:
    """Name of the application-emoji copy: unique per source emoji, max 32 chars."""
    return f"{name[:25]}_{str(emoji_id)[-6:]}"


async def download_emoji(session, emoji_id: int, animated: bool) -> Optional[bytes]:
    """Fetch the emoji image from Discord's CDN (works for any emoji that still exists)."""
    ext = "gif" if animated else "png"
    for size in (128, 64):
        try:
            async with session.get(CDN_URL.format(id=emoji_id, ext=ext, size=size)) as resp:
                if resp.status != 200:
                    return None
                data = await resp.read()
        except Exception:
            log.debug("CDN download failed for %s", emoji_id, exc_info=True)
            return None
        if len(data) <= MAX_BYTES:
            return data
    return None


async def sync_application_emojis(bot, session) -> None:
    """Copy the emoji in utils/emojis.py into the bot's application emoji. Never raises."""
    try:
        await _sync(bot, session)
    except Exception:
        log.warning("Emoji sync failed, keeping the original emoji", exc_info=True)


async def _sync(bot, session) -> None:
    if not hasattr(bot, "fetch_application_emojis"):
        log.warning("Emoji sync needs discord.py 2.5 or newer, skipping")
        return
    if bot.application_id is None:
        log.warning("Emoji sync skipped: application id not known yet")
        return

    wanted: Dict[str, "re.Match[str]"] = {}
    for const in dir(emojis):
        value = getattr(emojis, const)
        if const.isupper() and isinstance(value, str):
            match = EMOJI_RE.match(value)
            if match:
                wanted[const] = match
    if not wanted:
        return

    existing = await bot.fetch_application_emojis()
    owned_ids = {e.id for e in existing}
    by_name = {e.name: e for e in existing}

    copied = failed = already = 0
    for const, match in wanted.items():
        animated, name, emoji_id = bool(match.group(1)), match.group(2), int(match.group(3))
        if emoji_id in owned_ids:
            already += 1
            continue

        copy = by_name.get(clone_name(name, emoji_id))
        if copy is None:
            image = await download_emoji(session, emoji_id, animated)
            if image is None:
                log.warning("Could not copy emoji %s (%s): not found on Discord's CDN", const, emoji_id)
                failed += 1
                continue
            try:
                copy = await bot.create_application_emoji(name=clone_name(name, emoji_id), image=image)
            except discord.HTTPException:
                log.warning("Could not create application emoji for %s", const, exc_info=True)
                failed += 1
                continue
            by_name[copy.name] = copy
            copied += 1
            await asyncio.sleep(0.5)  # be gentle with the rate limit

        setattr(emojis, const, str(copy))

    log.info("Emoji sync: %d copied, %d already yours, %d failed", copied, already, failed)


async def ensure_app_emoji(bot, session, text: str) -> "tuple[str, bool]":
    """Make one emoji (`<:name:id>` / `<a:name:id>`) show in every server, for `.editemojis`.

    Same idea as the startup sync above: an emoji that is not one of this application's own is copied into the
    bot's application emoji and the copy is returned. Plain unicode emoji and emoji the bot already owns come back
    unchanged. Returns (emoji_to_save, ok). ok is False when the copy could not be made; the original is returned
    then and may only show where the bot can see it. Never raises.
    """
    match = EMOJI_RE.match(text or "")
    if match is None:
        return text, True
    if not hasattr(bot, "fetch_application_emojis") or bot.application_id is None:
        return text, False
    animated, name, emoji_id = bool(match.group(1)), match.group(2), int(match.group(3))
    try:
        existing = await bot.fetch_application_emojis()
        if any(e.id == emoji_id for e in existing):
            return text, True
        copy = next((e for e in existing if e.name == clone_name(name, emoji_id)), None)
        if copy is None:
            image = await download_emoji(session, emoji_id, animated)
            if image is None:
                return text, False
            copy = await bot.create_application_emoji(name=clone_name(name, emoji_id), image=image)
        return str(copy), True
    except Exception:
        log.warning("Could not copy emoji %s into the application emoji", emoji_id, exc_info=True)
        return text, False
