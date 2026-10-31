"""Modern Components V2 Help Menu for Shizu Music.
Designed with interactive Containers, category navigation, command inspection,
and real animated Discord emojis. Readable and intuitive for Indian Discord communities.
"""
from __future__ import annotations

import logging
from typing import Dict, List, Optional, Tuple

import discord
from discord.ext import commands

from services.style import NO_MENTIONS, fancy, get_embed_color
from utils import config
from utils import emojis as E

log = logging.getLogger("shizumusic.help")


def _invite_url(bot: commands.Bot) -> str:
    """Generate invite link requesting Administrator permission directly."""
    return discord.utils.oauth_url(
        bot.user.id if bot.user else (bot.application_id or 1563258310071812206),
        permissions=discord.Permissions(administrator=True),
        scopes=("bot", "applications.commands"),
    )


# ─────────────────────────────────────────────────────────────────────────────
# Command Catalog with simple, clear descriptions and real usage examples
# ─────────────────────────────────────────────────────────────────────────────
COMMAND_DATA: Dict[str, Dict[str, str]] = {
    # ── Music Playback ──
    "play": {
        "cat": "music",
        "desc": "Play any song name or URL from YouTube, Spotify or SoundCloud.",
        "usage": "play <song title | youtube/spotify link>",
        "example": "play faded alan walker",
        "aliases": "p",
        "rules": "Must be in a voice channel.",
    },
    "search": {
        "cat": "music",
        "desc": "Search songs on YouTube and select from top results interactively.",
        "usage": "search <song name>",
        "example": "search believer imagine dragons",
        "aliases": "find",
        "rules": "Must be in a voice channel.",
    },
    "nowplaying": {
        "cat": "music",
        "desc": "View details of the current playing song with live controls.",
        "usage": "nowplaying",
        "example": "nowplaying",
        "aliases": "np",
        "rules": "Available to all listeners.",
    },
    "join": {
        "cat": "music",
        "desc": "Connect the bot to your current voice channel.",
        "usage": "join",
        "example": "join",
        "aliases": "connect, j",
        "rules": "Must be in a voice channel.",
    },
    "disconnect": {
        "cat": "music",
        "desc": "Disconnect the bot from voice and end the music session.",
        "usage": "disconnect",
        "example": "disconnect",
        "aliases": "dc, leave, stop",
        "rules": "Session author or admin only.",
    },

    # ── Queue Management ──
    "queue": {
        "cat": "queue",
        "desc": "Display all upcoming tracks in the server queue.",
        "usage": "queue [page number]",
        "example": "queue 1",
        "aliases": "q",
        "rules": "Available to all listeners.",
    },
    "clearqueue": {
        "cat": "queue",
        "desc": "Remove all upcoming tracks from the queue while keeping current song.",
        "usage": "clearqueue",
        "example": "clearqueue",
        "aliases": "cq, clear",
        "rules": "Session author or admin only.",
    },
    "shuffle": {
        "cat": "queue",
        "desc": "Randomly mix up the songs in the queue for surprise playback.",
        "usage": "shuffle",
        "example": "shuffle",
        "aliases": "mix",
        "rules": "Session author or admin only.",
    },
    "loop": {
        "cat": "queue",
        "desc": "Toggle repeating the current song or entire queue.",
        "usage": "loop [song | queue | off]",
        "example": "loop song",
        "aliases": "repeat",
        "rules": "Session author or admin only.",
    },
    "autoplay": {
        "cat": "queue",
        "desc": "Automatically find and play similar songs when queue ends.",
        "usage": "autoplay",
        "example": "autoplay",
        "aliases": "auto",
        "rules": "Session author or admin only.",
    },

    # ── Player Controls ──
    "pause": {
        "cat": "player",
        "desc": "Temporarily pause the music playback.",
        "usage": "pause",
        "example": "pause",
        "aliases": "halt",
        "rules": "Session author or admin only.",
    },
    "resume": {
        "cat": "player",
        "desc": "Continue playing the paused track.",
        "usage": "resume",
        "example": "resume",
        "aliases": "unpause",
        "rules": "Session author or admin only.",
    },
    "skip": {
        "cat": "player",
        "desc": "Skip the current track and play the next song in queue.",
        "usage": "skip",
        "example": "skip",
        "aliases": "s, next",
        "rules": "Session author or admin only.",
    },
    "stop": {
        "cat": "player",
        "desc": "Stop music playback immediately and clear the queue.",
        "usage": "stop",
        "example": "stop",
        "aliases": "halt",
        "rules": "Session author or admin only.",
    },
    "seek": {
        "cat": "player",
        "desc": "Jump forward or backward to a specific percentage or time.",
        "usage": "seek <percentage% | mm:ss>",
        "example": "seek 50%  (or seek 1:30)",
        "aliases": "jump",
        "rules": "Session author or admin only.",
    },
    "replay": {
        "cat": "player",
        "desc": "Restart the current playing track from 00:00.",
        "usage": "replay",
        "example": "replay",
        "aliases": "restart",
        "rules": "Session author or admin only.",
    },
    "volume": {
        "cat": "player",
        "desc": "Adjust audio volume between 1% and 300% (default 100%).",
        "usage": "volume <1-300>",
        "example": "volume 120",
        "aliases": "vol, v",
        "rules": "Session author or admin only.",
    },
    "247": {
        "cat": "player",
        "desc": "Keep the bot staying inside your voice channel 24/7 uninterrupted.",
        "usage": "247",
        "example": "247",
        "aliases": "stay, non-stop",
        "rules": "Session author or admin only.",
    },

    # ── Audio FX & Filters ──
    "remix": {
        "cat": "fx",
        "desc": "Open the interactive button panel to toggle audio filters.",
        "usage": "remix",
        "example": "remix",
        "aliases": "effects, panel",
        "rules": "Session author or admin only.",
    },
    "fx": {
        "cat": "fx",
        "desc": "Apply instant audio presets like lofi, 8d, slowed, or nightcore.",
        "usage": "fx <preset name | off>",
        "example": "fx lofi",
        "aliases": "preset",
        "rules": "Session author or admin only.",
    },
    "bass": {
        "cat": "fx",
        "desc": "Set bass boost gain in decibels (0 to 25 dB).",
        "usage": "bass <0-25>",
        "example": "bass 10",
        "aliases": "bb, bassboost",
        "rules": "Session author or admin only.",
    },
    "filter": {
        "cat": "fx",
        "desc": "Enable or disable custom audio equalizer filters.",
        "usage": "filter <enable | disable> [filter name]",
        "example": "filter disable",
        "aliases": "eq",
        "rules": "Session author or admin only.",
    },

    # ── Server Configuration ──
    "prefix": {
        "cat": "settings",
        "desc": "Check the active bot prefix in this server.",
        "usage": "prefix",
        "example": "prefix",
        "aliases": "currentprefix",
        "rules": "Available to all members.",
    },
    "setprefix": {
        "cat": "settings",
        "desc": "Change the bot's command prefix for this server.",
        "usage": "setprefix <new prefix>",
        "example": "setprefix !",
        "aliases": "changeprefix",
        "rules": "Requires Manage Server permission.",
    },
}

CATEGORIES: Tuple[str, ...] = ("home", "music", "queue", "player", "fx", "settings", "info")

CATEGORY_META: Dict[str, Tuple[str, str, str]] = {
    "home": (E.CONFIG, "Home", "Overview, bot stats and getting started"),
    "music": (E.NOTES, "Music", "Play, search, nowplaying, join & disconnect"),
    "queue": (E.SLIDER, "Queue", "Queue view, clear, shuffle, loop & autoplay"),
    "player": (E.HEADPHONES, "Player Controls", "Pause, resume, skip, seek, volume & 24/7"),
    "fx": (E.REMIX, "Remix & FX", "Remix console, bassboost, lofi, 8D & audio filters"),
    "settings": (E.CONFIG, "Settings", "Server prefix and session controls"),
    "info": (E.DOT, "Info & Links", "Latency, music sources, developer credits & invite"),
}


class HelpCategorySelect(discord.ui.Select):
    """Dropdown for picking a category or specific command."""

    def __init__(self, view: "HelpView"):
        self.help_view = view
        options = []
        for cat in CATEGORIES:
            emoji, name, desc = CATEGORY_META[cat]
            options.append(
                discord.SelectOption(
                    label=name,
                    value=f"cat:{cat}",
                    description=desc[:100],
                    emoji=emoji,
                    default=(cat == view.current_category and view.selected_command is None),
                )
            )
        super().__init__(
            placeholder="Select a category to browse...",
            min_values=1,
            max_values=1,
            options=options,
        )

    async def callback(self, interaction: discord.Interaction):
        if not await self.help_view.check_owner(interaction):
            return
        val = self.values[0]
        if val.startswith("cat:"):
            cat = val.split(":", 1)[1]
            self.help_view.current_category = cat
            self.help_view.selected_command = None
        elif val.startswith("cmd:"):
            cmd = val.split(":", 1)[1]
            self.help_view.selected_command = cmd
        self.help_view.render()
        await interaction.response.edit_message(view=self.help_view)


class HelpCommandSelect(discord.ui.Select):
    """Dropdown for selecting an individual command within the current category."""

    def __init__(self, view: "HelpView", commands_in_cat: List[str]):
        self.help_view = view
        options = [
            discord.SelectOption(
                label=f"All {CATEGORY_META[view.current_category][1]} Commands",
                value=f"cat:{view.current_category}",
                description="Show overview list of all commands in this section",
                emoji=CATEGORY_META[view.current_category][0],
                default=(view.selected_command is None),
            )
        ]
        for cmd_name in commands_in_cat:
            cdata = COMMAND_DATA.get(cmd_name, {})
            options.append(
                discord.SelectOption(
                    label=f".{cmd_name}",
                    value=f"cmd:{cmd_name}",
                    description=cdata.get("desc", "")[:100],
                    emoji=E.ARROW_WHITE,
                    default=(view.selected_command == cmd_name),
                )
            )
        super().__init__(
            placeholder="Select a specific command for full usage details...",
            min_values=1,
            max_values=1,
            options=options[:25],
        )

    async def callback(self, interaction: discord.Interaction):
        if not await self.help_view.check_owner(interaction):
            return
        val = self.values[0]
        if val.startswith("cmd:"):
            self.help_view.selected_command = val.split(":", 1)[1]
        elif val.startswith("cat:"):
            self.help_view.selected_command = None
        self.help_view.render()
        await interaction.response.edit_message(view=self.help_view)


class HelpView(discord.ui.LayoutView):
    """Interactive Components V2 Container Help Menu for Shizu Music."""

    def __init__(self, ctx: commands.Context, prefix: str):
        super().__init__(timeout=300)
        self.ctx = ctx
        self.prefix = prefix
        self.bot = ctx.bot
        self.current_category: str = "home"
        self.selected_command: Optional[str] = None
        self.message: Optional[discord.Message] = None
        self.expired: bool = False
        self._interactive_items: list = []
        self.render()

    async def check_owner(self, interaction: discord.Interaction) -> bool:
        """Ensure only the command invoker can control the help menu."""
        if interaction.user.id != self.ctx.author.id:
            await interaction.response.send_message(
                f"{E.OFFLINE} Only {self.ctx.author.mention} can navigate this menu. Please use `{self.prefix}help` to open your own menu.",
                ephemeral=True,
            )
            return False
        return True

    def _render_home(self) -> List[discord.ui.Item]:
        """Render the home overview page."""
        p = self.prefix
        bot = self.bot
        total_cmds = len(set(bot.walk_commands()))
        slash_cmds = len(bot.tree.get_commands())
        ping = round(bot.latency * 1000)
        guild_count = len(bot.guilds)

        items: List[discord.ui.Item] = [
            discord.ui.TextDisplay(
                f"## {E.DJ} {fancy(config.NAME + ' command center')}\n"
                f"{E.ARROW} Enjoy crystal-clear 24/7 music streaming with lag-free high quality audio.\n"
                f"{E.ARROW} Prefix: `{p}` or Slash `/` · Start playing with `{p}play <song title>`."
            ),
            discord.ui.Separator(),
            discord.ui.TextDisplay(
                f"### {E.DOT} {fancy('Quick statistics')}\n"
                f"{E.ARROW} **Latency:** `{ping} ms`\n"
                f"{E.ARROW} **Active Servers:** `{guild_count}`\n"
                f"{E.ARROW} **Total Commands:** `{total_cmds}` Prefix · `{slash_cmds}` Slash\n"
                f"{E.ARROW} **Supported Sources:** YouTube, Spotify, SoundCloud, JioSaavn"
            ),
            discord.ui.Separator(),
            discord.ui.TextDisplay(
                f"### {E.CONFIG} {fancy('Explore categories')}\n"
                f"{E.NOTES} **Music** — Play songs, search YouTube & view live track info\n"
                f"{E.SLIDER} **Queue** — Manage track order, clear, loop, shuffle & autoplay\n"
                f"{E.HEADPHONES} **Player Controls** — Pause, resume, skip, seek, volume & 24/7 mode\n"
                f"{E.REMIX} **Remix & FX** — Real-time audio filters, bassboost, lofi & 8D audio\n"
                f"{E.CONFIG} **Settings** — Custom server prefixes and session rules\n"
                f"{E.DOT} **Info & Links** — Bot connectivity, links and developer credits"
            ),
        ]
        return items

    def _render_info(self) -> List[discord.ui.Item]:
        """Render system info, latency, and credits."""
        bot = self.bot
        ping = round(bot.latency * 1000)
        items: List[discord.ui.Item] = [
            discord.ui.TextDisplay(
                f"## {E.DOT} {fancy('Bot Information & Connectivity')}\n"
                f"{E.ARROW} **Status:** {E.ONLINE} Fully operational\n"
                f"{E.ARROW} **Gateway Ping:** `{ping} ms`\n"
                f"{E.ARROW} **Connected Servers:** `{len(bot.guilds)}`\n"
                f"{E.ARROW} **Voice Connections:** `{len(bot.voice_clients)}` active streams\n"
                f"{E.ARROW} **Audio Engine:** Lavalink v4.2 + YouTube OAuth Refresh Node\n"
                f"{E.ARROW} **Developers:** {config.DEVELOPERS}"
            ),
            discord.ui.Separator(),
            discord.ui.TextDisplay(
                f"### {E.HEART} {fancy('Helpful Links')}\n"
                f"{E.ARROW} Need help setting up or have questions? Join our support server.\n"
                f"{E.ARROW} Want to add Shizu Music to another server? Use the Invite button below."
            ),
        ]
        return items

    def _render_command_detail(self, cmd_name: str) -> List[discord.ui.Item]:
        """Render detailed usage for an individual command."""
        p = self.prefix
        cdata = COMMAND_DATA.get(cmd_name, {})
        desc = cdata.get("desc", "No description provided.")
        usage = cdata.get("usage", f"{cmd_name}")
        example = cdata.get("example", f"{cmd_name}")
        aliases = cdata.get("aliases", "None")
        rules = cdata.get("rules", "None")

        items: List[discord.ui.Item] = [
            discord.ui.TextDisplay(
                f"## {E.NOTES} {fancy('Command')} · `.{cmd_name}`\n"
                f"{E.ARROW} {desc}"
            ),
            discord.ui.Separator(),
            discord.ui.TextDisplay(
                f"### {E.CONFIG} {fancy('Syntax & Usage')}\n"
                f"{E.ARROW} **Usage:** `{p}{usage}`\n"
                f"{E.ARROW} **Example:** `{p}{example}`\n"
                f"{E.ARROW} **Aliases:** `{aliases}`\n"
                f"{E.ARROW} **Permissions / Rule:** {rules}"
            ),
            discord.ui.Separator(),
            discord.ui.TextDisplay(
                f"-# {E.DOT} Tip: You can also execute this command using slash: `/{cmd_name}`."
            ),
        ]
        return items

    def _render_category(self, cat: str) -> List[discord.ui.Item]:
        """Render command list for a specific category."""
        p = self.prefix
        emoji, cat_title, _ = CATEGORY_META[cat]
        cmds_in_cat = [k for k, v in COMMAND_DATA.items() if v.get("cat") == cat]

        lines = []
        for cmd in cmds_in_cat:
            cdata = COMMAND_DATA[cmd]
            lines.append(f"{E.ARROW} `{p}{cmd}` — {cdata['desc']}")

        cmd_text = "\n".join(lines) if lines else f"{E.ARROW} No commands registered in this section."
        items: List[discord.ui.Item] = [
            discord.ui.TextDisplay(
                f"## {emoji} {fancy(cat_title + ' commands')}\n"
                f"{E.ARROW} Pick any command from the dropdown below to see full usage syntax & examples."
            ),
            discord.ui.Separator(),
            discord.ui.TextDisplay(cmd_text),
            discord.ui.Separator(),
            discord.ui.TextDisplay(
                f"-# {E.DOT} Use `{p}help <command>` directly to jump to any specific command."
            ),
        ]
        return items

    def render(self) -> None:
        """Re-render the entire Components V2 Container."""
        self.clear_items()
        cat = self.current_category
        idx = CATEGORIES.index(cat) if cat in CATEGORIES else 0
        total_pages = len(CATEGORIES)

        # 1. Build Content Body
        if self.selected_command:
            body_items = self._render_command_detail(self.selected_command)
        elif cat == "home":
            body_items = self._render_home()
        elif cat == "info":
            body_items = self._render_info()
        else:
            body_items = self._render_category(cat)

        # 2. Build Category Selector Dropdown
        cat_select = HelpCategorySelect(self)
        cat_select.disabled = self.expired

        # 3. Build Navigation Buttons (Home, Prev, Next, Close)
        home_btn = discord.ui.Button(
            label="Home",
            emoji=E.CONFIG,
            style=discord.ButtonStyle.secondary,
            disabled=self.expired or (cat == "home" and self.selected_command is None),
        )
        home_btn.callback = self._on_home

        prev_btn = discord.ui.Button(
            label="Previous",
            emoji=E.ARROW_WHITE,
            style=discord.ButtonStyle.secondary,
            disabled=self.expired or idx == 0,
        )
        prev_btn.callback = self._on_prev

        next_btn = discord.ui.Button(
            label="Next",
            emoji=E.ARROW,
            style=discord.ButtonStyle.primary,
            disabled=self.expired or idx == (total_pages - 1),
        )
        next_btn.callback = self._on_next

        close_btn = discord.ui.Button(
            label="Close",
            emoji=E.OFFLINE,
            style=discord.ButtonStyle.danger,
            disabled=self.expired,
        )
        close_btn.callback = self._on_close

        # 4. Optional Command Dropdown for Current Category
        cmds_in_cat = [k for k, v in COMMAND_DATA.items() if v.get("cat") == cat]
        cmd_row: Optional[discord.ui.ActionRow] = None
        if cmds_in_cat and cat not in ("home", "info"):
            cmd_select = HelpCommandSelect(self, cmds_in_cat)
            cmd_select.disabled = self.expired
            cmd_row = discord.ui.ActionRow(cmd_select)

        # 5. External Link Buttons
        invite_btn = discord.ui.Button(
            label="Invite Bot",
            emoji=E.HEART,
            style=discord.ButtonStyle.link,
            url=_invite_url(self.bot),
        )
        support_url = (config.SUPPORT_URL or "").strip()
        link_buttons = [invite_btn]
        if support_url.startswith("http") and support_url.rstrip("/") not in ("https://discord.gg", "http://discord.gg"):
            link_buttons.append(
                discord.ui.Button(
                    label="Support Server",
                    emoji=E.BELL,
                    style=discord.ButtonStyle.link,
                    url=support_url,
                )
            )

        # 6. Assemble everything into a single Discord Component V2 Container
        container_children: List[discord.ui.Item] = list(body_items)
        container_children.append(discord.ui.Separator())
        container_children.append(discord.ui.ActionRow(cat_select))
        if cmd_row:
            container_children.append(cmd_row)
        container_children.append(discord.ui.ActionRow(home_btn, prev_btn, next_btn, close_btn))
        container_children.append(discord.ui.ActionRow(*link_buttons))
        container_children.append(discord.ui.Separator())

        author_name = getattr(self.ctx.author, "display_name", str(self.ctx.author))
        page_info = f"-# {E.DOT} Section {idx + 1}/{total_pages} • Requested by {author_name}"
        container_children.append(discord.ui.TextDisplay(page_info))

        self.add_item(
            discord.ui.Container(
                *container_children,
                accent_colour=get_embed_color(),
            )
        )
        self._interactive_items = [home_btn, prev_btn, next_btn, close_btn, cat_select]

    # ── Callbacks ──
    async def _on_home(self, interaction: discord.Interaction):
        if not await self.check_owner(interaction):
            return
        self.current_category = "home"
        self.selected_command = None
        self.render()
        await interaction.response.edit_message(view=self)

    async def _on_prev(self, interaction: discord.Interaction):
        if not await self.check_owner(interaction):
            return
        idx = CATEGORIES.index(self.current_category) if self.current_category in CATEGORIES else 0
        self.current_category = CATEGORIES[max(0, idx - 1)]
        self.selected_command = None
        self.render()
        await interaction.response.edit_message(view=self)

    async def _on_next(self, interaction: discord.Interaction):
        if not await self.check_owner(interaction):
            return
        idx = CATEGORIES.index(self.current_category) if self.current_category in CATEGORIES else 0
        self.current_category = CATEGORIES[min(len(CATEGORIES) - 1, idx + 1)]
        self.selected_command = None
        self.render()
        await interaction.response.edit_message(view=self)

    async def _on_close(self, interaction: discord.Interaction):
        if not await self.check_owner(interaction):
            return
        await interaction.response.defer()
        target = self.message or interaction.message
        if target:
            try:
                await target.delete()
            except discord.HTTPException:
                pass
        self.stop()

    async def on_timeout(self) -> None:
        self.expired = True
        self.render()
        if self.message:
            try:
                await self.message.edit(view=self, allowed_mentions=NO_MENTIONS)
            except discord.HTTPException:
                pass


def command_detail_view(cmd_name: str, prefix: str, author_name: str) -> discord.ui.LayoutView:
    """Standalone container view when user types `.help <command>`."""
    cdata = COMMAND_DATA.get(cmd_name.lower())
    view = discord.ui.LayoutView(timeout=120)
    if not cdata:
        view.add_item(
            discord.ui.Container(
                discord.ui.TextDisplay(
                    f"## {E.OFFLINE} {fancy('Command not found')}\n"
                    f"{E.ARROW} No command found matching `{cmd_name}`.\n"
                    f"{E.ARROW} Type `{prefix}help` to view all available commands."
                ),
                accent_colour=discord.Colour.red(),
            )
        )
        return view

    items: List[discord.ui.Item] = [
        discord.ui.TextDisplay(
            f"## {E.NOTES} {fancy('Command Help')} · `.{cmd_name}`\n"
            f"{E.ARROW} {cdata['desc']}"
        ),
        discord.ui.Separator(),
        discord.ui.TextDisplay(
            f"### {E.CONFIG} {fancy('Syntax & Details')}\n"
            f"{E.ARROW} **Usage:** `{prefix}{cdata['usage']}`\n"
            f"{E.ARROW} **Example:** `{prefix}{cdata['example']}`\n"
            f"{E.ARROW} **Aliases:** `{cdata['aliases']}`\n"
            f"{E.ARROW} **Permission / Rule:** {cdata['rules']}"
        ),
        discord.ui.Separator(),
        discord.ui.TextDisplay(f"-# {E.DOT} Requested by {author_name}"),
    ]
    view.add_item(discord.ui.Container(*items, accent_colour=get_embed_color()))
    return view
