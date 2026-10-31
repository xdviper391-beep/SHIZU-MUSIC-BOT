"""Styling and text display helpers for Shizu Music.
Follows the clean aesthetic established in Shizu Notify and Shizu Logs.
"""
from __future__ import annotations

from typing import Optional, Union
import discord
from utils import config

_SMALL_CAPS = str.maketrans(
    "abcdefghijklmnopqrstuvwxyz",
    "ᴀʙᴄᴅᴇꜰɢʜɪᴊᴋʟᴍɴᴏᴘǫʀꜱᴛᴜᴠᴡxʏᴢ",
)

NO_MENTIONS = discord.AllowedMentions.none()


def fancy(text: str) -> str:
    """Transform title/header into clean small caps (e.g. 'Shizu Music' -> 'ꜱʜɪᴢᴜ ᴍᴜꜱɪᴄ').
    Never pass custom emoji markup or URLs through this.
    """
    return text.lower().translate(_SMALL_CAPS)


def get_embed_color() -> discord.Colour:
    """Return configured bot accent color as discord.Colour."""
    c = config.EMBED_COLOR
    if isinstance(c, discord.Colour):
        return c
    try:
        if isinstance(c, str):
            c = c.strip("#")
            return discord.Colour(int(c, 16))
        return discord.Colour(int(c))
    except Exception:
        return discord.Colour.from_rgb(138, 43, 226)  # Default Shizu Purple #8A2BE2


class NoticeView(discord.ui.LayoutView):
    """A clean, modern Components V2 container for single notices and ephemeral errors."""

    def __init__(self, message: str, icon: Optional[str] = None, *, color: Optional[discord.Colour] = None):
        super().__init__(timeout=60)
        from utils import emojis as E
        prefix_icon = icon or E.DOT
        self.add_item(
            discord.ui.Container(
                discord.ui.TextDisplay(f"{prefix_icon} {message}"),
                accent_colour=color or get_embed_color(),
            )
        )


class MentionView(discord.ui.LayoutView):
    """Modern interactive reply shown whenever the bot is directly mentioned."""

    def __init__(self, user: discord.abc.User, prefix: str, bot: discord.Client):
        super().__init__(timeout=300)
        from utils import emojis as E
        from utils import config

        self.user = user
        self.prefix = prefix
        self.bot = bot

        help_btn = discord.ui.Button(
            label="Open Help Menu",
            emoji=E.CONFIG,
            style=discord.ButtonStyle.primary,
        )
        help_btn.callback = self._on_help

        invite_url = discord.utils.oauth_url(
            bot.user.id if bot.user else (getattr(bot, "application_id", None) or 1563258310071812206),
            permissions=discord.Permissions(administrator=True),
            scopes=("bot", "applications.commands"),
        )
        invite_btn = discord.ui.Button(
            label="Invite Bot",
            emoji=E.HEART,
            style=discord.ButtonStyle.link,
            url=invite_url,
        )

        buttons = [help_btn, invite_btn]
        support_url = (config.SUPPORT_URL or "").strip()
        if support_url.startswith("http") and support_url.rstrip("/") not in ("https://discord.gg", "http://discord.gg"):
            buttons.append(
                discord.ui.Button(
                    label="Support Server",
                    emoji=E.BELL,
                    style=discord.ButtonStyle.link,
                    url=support_url,
                )
            )

        self.add_item(
            discord.ui.Container(
                discord.ui.TextDisplay(
                    f"## {E.DJ} {fancy(config.NAME)}\n"
                    f"{E.ARROW} Hey {user.mention}! Serving uninterrupted 24/7 beats with crystal-clear audio.\n"
                    f"{E.ARROW} Current Prefix: `{prefix}` · Play songs with `{prefix}play <song>` or `/play`.\n"
                    f"{E.ARROW} Tap **Open Help Menu** below or type `{prefix}help` to explore all commands."
                ),
                discord.ui.Separator(),
                discord.ui.ActionRow(*buttons),
                discord.ui.Separator(),
                discord.ui.TextDisplay(f"-# {E.DOT} Powered by Lavalink v4.2 & YouTube OAuth • Developers: {config.DEVELOPERS}"),
                accent_colour=get_embed_color(),
            )
        )

    async def _on_help(self, interaction: discord.Interaction):
        if interaction.user.id != self.user.id:
            from utils import emojis as E
            await interaction.response.send_message(
                f"{E.OFFLINE} Only {self.user.mention} can open the help menu from this mention. Please type `{self.prefix}help` yourself.",
                ephemeral=True,
            )
            return
        from utils.help import HelpView
        ctx = await self.bot.get_context(interaction.message)
        ctx.author = interaction.user
        help_view = HelpView(ctx, self.prefix)
        await interaction.response.send_message(view=help_view, ephemeral=True)

