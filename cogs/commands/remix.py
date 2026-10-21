"""Remix console for Shizu Music (FFmpeg version of remix_console.py).

    .remix             open the console (buttons: red = off, green = on)
    .fx <preset|off>   lofi, nightcore, atmos, 8d, crystal, slowedreverb ...  (see `.fx`)
    .bass <0-25>       bass boost in dB
    .volume <1-300>    (in music.py)

The "Remix" button in the player's private Others panel opens the same console (with a Back button).

How effects reach the audio: this cog has NO state of its own. The one effect state per guild lives on the
music player (`player.remix_state`, see utils/remix.py) next to `player.volume` and `player.audio_filters`.
Every change - console button, `.fx`, `.bass`, `.filter`, `.volume` - goes through `utils.remix.commit()`,
which compiles the state to an FFmpeg `-af` chain, test-runs it, stores it on the player and restarts FFmpeg
at the current position. `.volume` and the Vol button change the live gain instead (no restart).
"""
from __future__ import annotations

import asyncio
import copy
import logging
from typing import Callable, Optional

import discord
from discord import app_commands
from discord.ext import commands

from core import ShizuMusic
from utils import button_emojis as BE
from utils import emojis as E
from utils.remix import (
    EFFECTS,
    MAX_BASS_DB,
    PRESETS,
    UNSUPPORTED,
    RemixError,
    RemixState,
    commit,
    get_state,
    lock_for,
    probe_effects,
    set_preset,
    summarize,
)
from utils.session import can_control, denied_text
from utils.Tools import blacklist_check, ignore_check

from .music import MusicPlayer

log = logging.getLogger("shizumusic.remix")

GREY = discord.Color.from_rgb(43, 45, 49)


def _embed(text: str, color: int = 0x000000) -> discord.Embed:
    return discord.Embed(description=text, color=color)


# ═════════════════════════════════════════════════════════════════════════════
#  PANEL  (the console)
# ═════════════════════════════════════════════════════════════════════════════
# Row layout, 4 buttons per row (same look as the old Effects panel): effect keys, or "BASS" / "VOL" / "CLEAR" /
# "HELP" for the special buttons. Grey = off, green = on.
LAYOUT = (
    ("speed", "slow", "pitch_up", "pitch_down"),
    ("BASS", "deep", "lpf", "hpf"),
    ("echo", "reverb", "stutter", "VOL"),
    ("crystal", "spatial", "eight_d", "atmos"),
    ("lofi", "karaoke", "CLEAR", "HELP"),
)


def help_embed() -> discord.Embed:
    width = max(len(e.label) for e in EFFECTS.values()) + 2
    lines = "\n".join(f"{e.label:<{width}}{e.blurb}" for e in EFFECTS.values())
    embed = discord.Embed(
        title="How the Remix Console works",
        description=(
            "Press an effect to switch it on, press it again to switch it off (grey = off, green = on).\n"
            "Effects stack. Speed/Slow, High/Low, Echo/Reverb and Spatial/8D/Atmos replace each other.\n"
            "**Bass** cycles 6 > 12 > 18 > 25 dB > off. **Vol** cycles 150 > 200 > 250 > 300% > 100%."
        ),
        color=GREY,
    )
    embed.add_field(name="Effects", value=f"```\n{lines}\n```", inline=False)
    embed.add_field(
        name="Commands",
        value="```\n.remix            open this console\n.fx <preset|off>  e.g. .fx lofi\n"
        ".bass <0-25>      exact bass boost in dB\n.volume <1-300>   exact volume in %\n```",
        inline=False,
    )
    embed.add_field(name="Presets", value="```\n" + "  ".join(PRESETS) + "\n```", inline=False)
    notes = [
        "Spatial / 8D / Atmos are stereo-based 3D effects (best on headphones), not licensed Dolby Atmos.",
        "Bass dB is nominal (a limiter stops clipping); volume above 100% can distort loud tracks.",
        "A change restarts the song at the same spot, so expect a very short gap.",
        "For the cleanest sound set the voice channel bitrate to the maximum (channel settings).",
    ]
    if UNSUPPORTED:
        names = ", ".join(EFFECTS[k].name for k in sorted(UNSUPPORTED))
        notes.append(f"Dimmed and locked: your FFmpeg build can't run {names}.")
    embed.add_field(name="Good to know", value="\n".join(f"• {n}" for n in notes), inline=False)
    return embed


def panel_embed(state: RemixState) -> discord.Embed:
    embed = discord.Embed(title="\U0001f39b\ufe0f Remix Console", description=summarize(state), color=GREY)
    footer = []
    if state.needs_limiter:
        footer.append("Limiter on (stops the bass boost clipping)")
    if state.loud:
        footer.append("Volume above 100% can distort loud tracks")
    if footer:
        embed.set_footer(text=" | ".join(footer))
    return embed


class RemixPanel(discord.ui.View):
    def __init__(self, cog: "Remix", player: MusicPlayer, *, timeout: float = 600.0, back=None):
        super().__init__(timeout=timeout)
        self._back = back  # set when opened from the player's Others panel: adds a Back button
        self.cog = cog
        self.player = player
        self.message: Optional[discord.Message] = None
        self._interaction: Optional[discord.Interaction] = None  # latest click, used to edit the panel
        self.fx_btns: dict[str, discord.ui.Button] = {}

        for row, keys in enumerate(LAYOUT):
            for key in keys:
                if key == "BASS":
                    self.bass_btn = self._add("Bass", BE.get("bass"), self._bass, row)
                elif key == "VOL":
                    self.vol_btn = self._add("Vol", BE.get("vol"), self._volume, row)
                elif key == "CLEAR":
                    self.clear_btn = self._add("Clear FX", BE.get("clear"), self._clear, row)
                elif key == "HELP":
                    self.help_btn = self._add("How it works", BE.get("help"), self._help, row, discord.ButtonStyle.primary)
                else:
                    fx = EFFECTS[key]
                    self.fx_btns[key] = self._add(fx.label, BE.get(key), self._fx_callback(key), row)
        if back is not None:
            self._add("Back", "\u25c0\ufe0f", self._go_back, len(LAYOUT) - 1, discord.ButtonStyle.primary)
        self.sync()

    # -- building ----------------------------------------------------------------
    def _add(self, label, emoji, callback, row, style=discord.ButtonStyle.secondary) -> discord.ui.Button:
        btn = discord.ui.Button(label=label, emoji=emoji, style=style, row=row)
        btn.callback = callback
        self.add_item(btn)
        return btn

    @property
    def state(self) -> RemixState:
        return get_state(self.player)  # always the player's real state, never a copy kept by the panel

    def sync(self) -> None:
        """grey = off, green = on. Effects the installed FFmpeg can't run are disabled. Clear FX is red while
        there is something to clear."""
        state = self.state
        for key, btn in self.fx_btns.items():
            if key in UNSUPPORTED:
                btn.style, btn.disabled = discord.ButtonStyle.secondary, True
                continue
            btn.style = discord.ButtonStyle.success if key in state.active else discord.ButtonStyle.secondary
        self.bass_btn.label = f"Bass +{state.bass_db}" if state.bass_db else "Bass"
        self.bass_btn.style = discord.ButtonStyle.success if state.bass_db else discord.ButtonStyle.secondary
        self.vol_btn.label = f"Vol {state.volume}%"
        self.vol_btn.style = discord.ButtonStyle.success if state.volume != 100 else discord.ButtonStyle.secondary
        something = bool(state.active or state.bass_db)
        self.clear_btn.disabled = not something
        self.clear_btn.style = discord.ButtonStyle.danger if something else discord.ButtonStyle.secondary

    def embed(self) -> discord.Embed:
        return panel_embed(self.state)

    # -- checks ------------------------------------------------------------------
    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if (interaction.data or {}).get("custom_id") == self.help_btn.custom_id:
            return True  # anyone may read the help
        vc = interaction.guild.voice_client if interaction.guild else None
        if vc is None or vc is not self.player:
            await interaction.response.send_message("I'm not in that voice channel anymore.", ephemeral=True)
            return False
        voice = getattr(interaction.user, "voice", None)
        if not (voice and voice.channel and voice.channel.id == vc.channel.id):
            await interaction.response.send_message("Join my voice channel to use the console.", ephemeral=True)
            return False
        if not can_control(vc, interaction.user.id):
            await interaction.response.send_message(embed=_embed(denied_text(vc), 0xFF0000), ephemeral=True)
            return False
        return True

    # -- callbacks ---------------------------------------------------------------
    def _fx_callback(self, key: str):
        async def callback(interaction: discord.Interaction):
            await self._change(interaction, lambda s: s.toggle(key))
        return callback

    async def _bass(self, interaction: discord.Interaction):
        await self._change(interaction, lambda s: s.cycle_bass())

    async def _volume(self, interaction: discord.Interaction):
        await self._change(interaction, lambda s: s.cycle_volume())

    async def _clear(self, interaction: discord.Interaction):
        await self._change(interaction, lambda s: s.clear(keep_volume=True))

    async def _help(self, interaction: discord.Interaction):
        await interaction.response.send_message(embed=help_embed(), ephemeral=True)

    async def _go_back(self, interaction: discord.Interaction):
        self.stop()  # this page is replaced; its timeout must not edit the page that takes over
        await self._back(interaction)

    async def _change(self, interaction: discord.Interaction, mutate: Callable[[RemixState], object]) -> None:
        if lock_for(self.player).locked():
            await interaction.response.send_message("One moment, still applying the last change.", ephemeral=True)
            return
        await interaction.response.defer()
        new = copy.deepcopy(self.state)
        mutate(new)
        try:
            await commit(self.player, new)
        except RemixError as exc:
            await interaction.followup.send(f"{E.WARNING} {exc}", ephemeral=True)
            return
        self._interaction = interaction
        self.sync()
        try:
            await interaction.edit_original_response(embed=self.embed(), view=self)
        except (discord.NotFound, discord.HTTPException):
            pass

    async def on_timeout(self) -> None:
        for child in self.children:
            child.disabled = True
        try:
            if self._interaction is not None:
                await self._interaction.edit_original_response(view=self)
            elif self.message is not None:
                await self.message.edit(view=self)
        except (discord.NotFound, discord.HTTPException):
            pass


# ═════════════════════════════════════════════════════════════════════════════
#  COG
# ═════════════════════════════════════════════════════════════════════════════
class Remix(commands.Cog):
    def __init__(self, bot: ShizuMusic):
        self.bot = bot

    async def cog_load(self) -> None:
        # Find the effects the installed FFmpeg can't run (greyed out in the console). Never blocks startup.
        try:
            bad = await asyncio.wait_for(probe_effects(), 30)
            if bad:
                log.warning("These effects are disabled (not supported by your FFmpeg): %s", ", ".join(sorted(bad)))
        except Exception:
            log.warning("Could not probe the FFmpeg effects", exc_info=True)

    async def cog_check(self, ctx: commands.Context) -> bool:
        if ctx.guild is None:
            raise commands.NoPrivateMessage()
        return True

    # ── engine (thin wrappers: the logic is shared in utils/remix.py) ──
    def lock_for(self, player: MusicPlayer) -> asyncio.Lock:
        return lock_for(player)

    async def commit(self, player: MusicPlayer, new: RemixState, *, flush: bool = True) -> None:
        """Apply `new` and, only if that worked, make it the player's state."""
        await commit(player, new, reload=flush)

    async def set_preset(self, player: MusicPlayer, name: str) -> tuple[bool, str]:
        """Used by `.fx` and the `.filter` menu. Returns (ok, note for the user)."""
        return await set_preset(player, name)

    async def _say(self, ctx: commands.Context, text: str, color: int = 0x000000) -> None:
        """The reply goes inside the player card (one message); a normal reply if there is no card."""
        music = self.bot.get_cog("Music")
        if music is not None:
            await music.note(ctx, text, color)
        else:
            await ctx.send(embed=_embed(text, color))

    # ── shared checks ───────────────────────────────────
    async def _player_for(self, ctx: commands.Context) -> Optional[MusicPlayer]:
        vc = ctx.voice_client
        if not isinstance(vc, MusicPlayer):
            await ctx.send(embed=_embed(f"{E.WARNING} I'm not connected to a voice channel.", 0xFF0000))
            return None
        voice = ctx.author.voice
        if not (voice and voice.channel and voice.channel.id == vc.channel.id):
            await ctx.send(embed=_embed(f"{E.WARNING} You need to be in the same voice channel as me.", 0xFF0000))
            return None
        if not can_control(vc, ctx.author.id):
            await ctx.send(embed=_embed(denied_text(vc), 0xFF0000))
            return None
        return vc

    # ── the "Remix" button on the now-playing card calls this ──
    async def open_panel(
        self, interaction: discord.Interaction, player: MusicPlayer, *, back=None, edit: bool = False
    ) -> None:
        """Open the console privately. From the player's Others panel: edit=True swaps it into that message and
        `back` (async callable taking the interaction) is what the Back button calls."""
        view = RemixPanel(self, player, back=back)
        view._interaction = interaction
        if edit:
            await interaction.response.edit_message(embed=view.embed(), view=view)
        else:
            await interaction.response.send_message(embed=view.embed(), view=view, ephemeral=True)

    # ── commands ────────────────────────────────────────
    @commands.hybrid_command(
        name="remix",
        aliases=["console", "effects", "fxpanel"],
        usage="remix",
        help="Open the remix console: effects, bass boost up to 25 dB, volume up to 300%.",
    )
    @blacklist_check()
    @ignore_check()
    @commands.cooldown(1, 3, commands.BucketType.user)
    async def remix(self, ctx: commands.Context):
        player = await self._player_for(ctx)
        if player is None:
            return
        view = RemixPanel(self, player)
        view.message = await ctx.send(embed=view.embed(), view=view)

    @commands.hybrid_command(
        name="fx",
        aliases=["preset"],
        usage="fx <preset|off>",
        help="Apply a remix preset (lofi, nightcore, atmos, 8d, crystal, bassboost ...) or `off`.",
    )
    @blacklist_check()
    @ignore_check()
    @commands.cooldown(1, 3, commands.BucketType.user)
    async def fx(self, ctx: commands.Context, preset: Optional[str] = None):
        if preset is None:
            names = ", ".join(f"`{n}`" for n in PRESETS)
            await ctx.send(embed=_embed(f"{E.MUSIC} **Audio FX Presets:** {names}\nUse `{ctx.clean_prefix}fx <name>` or `{ctx.clean_prefix}fx off`.\n"
                                        f"Or open the console with `{ctx.clean_prefix}remix`.", 0x5865F2))
            return
        player = await self._player_for(ctx)
        if player is None:
            return
        try:
            ok, note = await self.set_preset(player, preset)
        except RemixError as exc:
            await ctx.send(embed=_embed(f"{E.WARNING} {exc}", 0xFF0000))
            return
        if not ok:
            await ctx.send(embed=_embed(f"{E.WARNING} {note} Try `{ctx.clean_prefix}fx` to see the list.", 0xFF0000))
            return
        state = get_state(player)
        text = f"{E.TICK} Effects: **{state.label or 'off'}**" + (f" (Bass {state.bass_db} dB)" if state.bass_db and state.preset else "")
        if note:
            text += f"\n{note}"
        await self._say(ctx, text, 0x1DB954)

    @fx.autocomplete("preset")
    async def _fx_autocomplete(self, interaction: discord.Interaction, current: str):
        options = ["off", *PRESETS]
        current = current.lower()
        return [app_commands.Choice(name=o, value=o) for o in options if current in o][:25]

    @commands.hybrid_command(
        name="bass",
        usage="bass <0-25>",
        help=f"Set the bass boost in dB (0 = off, up to {MAX_BASS_DB}).",
    )
    @blacklist_check()
    @ignore_check()
    @commands.cooldown(1, 3, commands.BucketType.user)
    async def bass(self, ctx: commands.Context, db: int):
        player = await self._player_for(ctx)
        if player is None:
            return
        if not 0 <= db <= MAX_BASS_DB:
            await ctx.send(embed=_embed(f"{E.WARNING} Bass must be between 0 and {MAX_BASS_DB} dB.", 0xFF0000))
            return
        new = copy.deepcopy(get_state(player))
        new.set_bass(db)
        try:
            await self.commit(player, new)
        except RemixError as exc:
            await ctx.send(embed=_embed(f"{E.WARNING} {exc}", 0xFF0000))
            return
        text = f"{E.VOICE} Bass boost set to **{db} dB**." if db else f"{E.VOICE} Bass boost off."
        if db >= 18:
            text += "\nBig bass + high volume can distort. Lower it if you hear crackling."
        await self._say(ctx, text)


async def setup(bot: ShizuMusic) -> None:  # lets `load_extension` work too; cogs/__init__ adds it normally
    await bot.add_cog(Remix(bot))
