from __future__ import annotations

import logging
from typing import Any, Dict, Optional

import discord
from discord.ext import commands

from utils import config
from utils import emojis as E

log = logging.getLogger("shizumusic.help")


def _invite_url(bot: commands.Bot) -> str:
    return discord.utils.oauth_url(
        bot.user.id,
        permissions=discord.Permissions(
            view_channel=True,
            send_messages=True,
            embed_links=True,
            attach_files=True,
            read_message_history=True,
            add_reactions=True,
            use_external_emojis=True,
            connect=True,
            speak=True,
            set_voice_channel_status=True,
        ),
        scopes=("bot", "applications.commands"),
    )


class HelpCategorySelect(discord.ui.Select):
    def __init__(self, invoker_id: int):
        options = [
            discord.SelectOption(
                label="Home Overview",
                value="home",
                description="General info, bot statistics & quick start guide",
                emoji="🏠",
                default=True,
            ),
            discord.SelectOption(
                label="Music Commands",
                value="music",
                description="Play, queue, loop, autoplay, seek & volume controls",
                emoji="🎵",
            ),
            discord.SelectOption(
                label="Remix & Audio FX",
                value="remix",
                description="Interactive console, 8D, Bassboost, Lofi & audio filters",
                emoji="🎛️",
            ),
            discord.SelectOption(
                label="Server Configuration",
                value="settings",
                description="Custom server prefix, permissions & session controls",
                emoji="⚙️",
            ),
            discord.SelectOption(
                label="Bot Info & Connectivity",
                value="info",
                description="Latency, system statistics, music sources & links",
                emoji="ℹ️",
            ),
        ]
        super().__init__(
            placeholder="Select what you need help with...",
            min_values=1,
            max_values=1,
            options=options,
            row=0,
        )
        self.invoker_id = invoker_id

    async def callback(self, interaction: discord.Interaction):
        if interaction.user.id != self.invoker_id:
            await interaction.response.send_message(
                f"{E.WARNING} Only the member who requested this help menu can interact with it.",
                ephemeral=True,
            )
            return

        selected = self.values[0]
        for opt in self.options:
            opt.default = opt.value == selected

        view: HelpView = self.view  # type: ignore
        embed = view.get_embed(selected)
        await interaction.response.edit_message(embed=embed, view=view)


class HelpView(discord.ui.View):
    def __init__(self, ctx: commands.Context, prefix: str):
        super().__init__(timeout=300)
        self.ctx = ctx
        self.prefix = prefix
        self.bot = ctx.bot
        self.message: Optional[discord.Message] = None

        # Row 0: Category Selector Dropdown
        self.select_menu = HelpCategorySelect(ctx.author.id)
        self.add_item(self.select_menu)

        # Row 1: Action Buttons (Invite link + Dismiss button)
        invite_link = _invite_url(ctx.bot)
        self.add_item(
            discord.ui.Button(
                label="Invite Shizu Music",
                url=invite_link,
                style=discord.ButtonStyle.link,
                row=1,
            )
        )
        close_btn = discord.ui.Button(
            label="Close",
            style=discord.ButtonStyle.secondary,
            emoji="✖️",
            row=1,
        )
        close_btn.callback = self.close_callback
        self.add_item(close_btn)

    async def close_callback(self, interaction: discord.Interaction):
        if interaction.user.id != self.ctx.author.id:
            await interaction.response.send_message(
                f"{E.WARNING} Only the member who requested this help menu can dismiss it.",
                ephemeral=True,
            )
            return
        await interaction.response.defer()
        if self.message:
            try:
                await self.message.delete()
            except discord.HTTPException:
                pass
        self.stop()

    async def on_timeout(self):
        for item in self.children:
            if hasattr(item, "disabled"):
                item.disabled = True
        if self.message:
            try:
                await self.message.edit(view=self)
            except discord.HTTPException:
                pass

    def get_embed(self, category: str) -> discord.Embed:
        bot_user = self.bot.user
        bot_avatar = bot_user.display_avatar.url if bot_user else None
        p = self.prefix

        if category == "music":
            embed = discord.Embed(
                title=f"{E.MUSIC} Music & Playback Commands",
                description=(
                    "Crystal-clear audio streaming with responsive controls. "
                    f"Use `{p}<command>` or `/slash` commands.\n\u200b"
                ),
                color=config.EMBED_COLOR,
            )
            embed.set_author(name=f"{config.NAME} • Command Center", icon_url=bot_avatar)
            embed.add_field(
                name=f"{E.MUSIC} Playback Controls",
                value=(
                    f"• `{p}play <song/url>` — Stream music from YouTube, Spotify, SoundCloud, JioSaavn\n"
                    f"• `{p}pause` — Pause current playback stream\n"
                    f"• `{p}resume` — Resume currently paused track\n"
                    f"• `{p}stop` — Stop playback, clear queue & leave voice\n"
                    f"• `{p}skip` — Skip to the next queued track\n"
                    f"• `{p}replay` — Restart current track from 0:00\n"
                    f"• `{p}seek <time/%>` — Jump to a specific second or percentage"
                ),
                inline=False,
            )
            embed.add_field(
                name=f"{E.VOICE} Queue & Navigation",
                value=(
                    f"• `{p}nowplaying` (`{p}np`) — Show current Pillow banner & live track info\n"
                    f"• `{p}queue` — Display all upcoming tracks with page navigation\n"
                    f"• `{p}clearqueue` — Wipe all pending songs from the queue\n"
                    f"• `{p}shuffle` — Randomize the order of queued tracks\n"
                    f"• `{p}loop` — Toggle repeat mode on the current track\n"
                    f"• `{p}autoplay` — Toggle smart recommendation autoplay"
                ),
                inline=False,
            )
            embed.add_field(
                name=f"{E.TICK} Voice Channel & Session",
                value=(
                    f"• `{p}join` — Summon the bot to your current voice channel\n"
                    f"• `{p}disconnect` — Disconnect the bot from voice\n"
                    f"• `{p}247` — Toggle 24/7 continuous voice mode (never leaves)\n"
                    f"• `{p}volume <1-300>` — Adjust volume gain percentage (100% default)"
                ),
                inline=False,
            )
            embed.set_footer(
                text=f"Page 2/5 • Type {p}help <command> for detailed parameter usage!",
                icon_url=bot_avatar,
            )
            return embed

        elif category == "remix":
            embed = discord.Embed(
                title=f"{E.REMIX_BTN} Audio Effects & Filters",
                description=(
                    "Studio-grade audio processing powered by custom FFmpeg filter chains. "
                    "All effects apply in real-time with zero audio buffering.\n\u200b"
                ),
                color=config.EMBED_COLOR,
            )
            embed.set_author(name=f"{config.NAME} • Command Center", icon_url=bot_avatar)
            embed.add_field(
                name=f"{E.REMIX_BTN} Interactive Remix Console",
                value=(
                    f"• `{p}remix` (aliases: `console`, `fxpanel`)\n"
                    "  Opens an interactive button console to toggle 8D, Lofi, Nightcore, "
                    "Atmos, Bass, Speed, and Echo on the fly."
                ),
                inline=False,
            )
            embed.add_field(
                name=f"{E.REMIX_BASS} Bassboost & Equalizer",
                value=(
                    f"• `{p}bass <0-25>` — Set exact hardware bass boost level in dB\n"
                    f"• `{p}volume <1-300>` — Digital output gain percentage"
                ),
                inline=False,
            )
            embed.add_field(
                name=f"{E.REMIX_8D} Filter Presets",
                value=(
                    f"• `{p}fx <preset|off>` — Instant toggle for presets (`lofi`, `nightcore`, `8d`, `atmos`, `crystal`, `deep`)\n"
                    f"• `{p}filter enable` — Open dropdown menu to choose and activate presets\n"
                    f"• `{p}filter disable` — Reset all active filters back to clean default audio"
                ),
                inline=False,
            )
            embed.set_footer(
                text=f"Page 3/5 • Audio filters stack and persist per-session • Thanks for choosing {config.NAME}!",
                icon_url=bot_avatar,
            )
            return embed

        elif category == "settings":
            embed = discord.Embed(
                title=f"{E.TICK} Server Configuration",
                description=(
                    "Custom guild settings, prefix configuration, and session security.\n\u200b"
                ),
                color=config.EMBED_COLOR,
            )
            embed.set_author(name=f"{config.NAME} • Command Center", icon_url=bot_avatar)
            embed.add_field(
                name=f"{E.TICK} Prefix Settings",
                value=(
                    f"• `{p}setprefix <new_prefix>` — Set a custom prefix for this server *(Requires Manage Server)*\n"
                    f"• `{p}prefix` — Check the current prefix active in this server"
                ),
                inline=False,
            )
            embed.add_field(
                name=f"{E.VOICE} Smart Session Protection",
                value=(
                    "• **Session Ownership** — The member who requests music controls buttons & playback\n"
                    "• **Smart Transfer** — Session automatically transfers to listeners if the owner leaves\n"
                    "• **Server Mute Protection** — Auto-pauses and cleans up UI if bot is muted\n"
                    "• **Auto Offline Alert** — Announces when the bot is restarting and edits back when online"
                ),
                inline=False,
            )
            embed.set_footer(
                text=f"Page 4/5 • Prefix changes apply instantly • Thanks for choosing {config.NAME}!",
                icon_url=bot_avatar,
            )
            return embed

        elif category == "info":
            latency = round(self.bot.latency * 1000)
            guilds = len(self.bot.guilds)
            vcs = len(self.bot.voice_clients)
            embed = discord.Embed(
                title=f"{E.ONLINE} System Information & Links",
                description=(
                    "Real-time system diagnostics and connectivity stats.\n\u200b"
                ),
                color=config.EMBED_COLOR,
            )
            embed.set_author(name=f"{config.NAME} • Command Center", icon_url=bot_avatar)
            embed.add_field(
                name=f"{E.ONLINE} Connectivity & Statistics",
                value=(
                    f"• **Gateway Latency:** `{latency} ms`\n"
                    f"• **Servers Connected:** `{guilds}` Guilds\n"
                    f"• **Active Voice Sessions:** `{vcs}` Voice Channels\n"
                    f"• **Playback Engine:** `FFmpeg Native + yt-dlp`"
                ),
                inline=False,
            )
            embed.add_field(
                name=f"{E.TICK} Supported Platforms",
                value=(
                    f"{E.SPOTIFY} **Spotify** • {E.YOUTUBE} **YouTube** • {E.SOUNDCLOUD} **SoundCloud** • {E.JIOSAAVN} **JioSaavn**"
                ),
                inline=False,
            )
            embed.add_field(
                name=f"{E.MUSIC} Developer Credits",
                value="Developed with ❤️ by **viper & prashu**.",
                inline=False,
            )
            embed.set_footer(
                text=f"Page 5/5 • Thanks for choosing {config.NAME}!",
                icon_url=bot_avatar,
            )
            return embed

        # Default: Home Overview
        total_cmds = len(set(self.bot.walk_commands()))
        slash_cmds = len(self.bot.tree.get_commands())
        embed = discord.Embed(
            description=(
                f"{E.MUSIC} **Welcome to {config.NAME} Help Center!**\n"
                "Next-generation 24/7 Discord audio streaming with rich remix audio effects, "
                "custom Pillow banners, and seamless voice controls.\n\n"
                f"{E.VOICE} **Server Prefix:** `{p}` or slash (`/`)\n"
                f"{E.TICK} **Commands Available:** `{total_cmds}` Prefix • `{slash_cmds}` Slash\n"
                f"{E.ONLINE} **System Status:** `Operational • 24/7 Active`\n\n"
                "__**Select a category from the dropdown below to explore:**__\n"
                f"• {E.MUSIC} **Music & Playback** — Playback controls, queue & loop\n"
                f"• {E.REMIX_BTN} **Remix & Audio FX** — Interactive console, bassboost & filters\n"
                f"• {E.TICK} **Server Configuration** — Custom prefix & session protection\n"
                f"• {E.ONLINE} **Bot Info & Connectivity** — System specs, sources & latency"
            ),
            color=config.EMBED_COLOR,
        )
        embed.set_author(name=f"{config.NAME} • Command Center", icon_url=bot_avatar)
        embed.add_field(
            name="📌 Quick Start Guide",
            value=(
                f"1. Connect to any voice channel in this server\n"
                f"2. Type `{p}play <song title or URL>` to begin listening\n"
                f"3. Use the interactive player buttons to control playback effortlessly"
            ),
            inline=False,
        )
        embed.set_footer(
            text=f"Page 1/5 • Select a category from the menu below • Thanks for choosing {config.NAME}!",
            icon_url=bot_avatar,
        )
        return embed
