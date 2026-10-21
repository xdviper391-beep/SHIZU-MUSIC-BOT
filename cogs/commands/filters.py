from __future__ import annotations

from typing import Optional

import discord
from discord.ext import commands

from utils import config
from utils import emojis as E
from utils.remix import PRESETS, RemixError, get_state, set_preset
from utils.session import can_control, denied_text
from utils.Tools import blacklist_check, ignore_check

from .music import MusicPlayer


class FilterSelect(discord.ui.View):
    def __init__(self, cog: "FilterCog", ctx: commands.Context, options: list[discord.SelectOption]):
        super().__init__(timeout=120)
        self.cog = cog
        self.ctx = ctx
        self.message: Optional[discord.Message] = None

        select = discord.ui.Select(placeholder="Choose a filter...", options=options)
        select.callback = self.on_select
        self.add_item(select)

        cancel = discord.ui.Button(label="Cancel", style=discord.ButtonStyle.red)
        cancel.callback = self.on_cancel
        self.add_item(cancel)

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if interaction.user.id == self.ctx.author.id:
            return True
        await interaction.response.send_message("Only the command author can use this menu.", ephemeral=True)
        return False

    def disable_all(self) -> None:
        for child in self.children:
            child.disabled = True
        self.stop()

    async def on_select(self, interaction: discord.Interaction) -> None:
        await interaction.response.defer()
        selected = interaction.data["values"][0].lower()
        await self.cog.apply_filter(self.ctx, selected)
        self.disable_all()
        await interaction.message.edit(view=self)

    async def on_cancel(self, interaction: discord.Interaction) -> None:
        self.disable_all()
        await interaction.response.defer()
        await interaction.message.delete()

    async def on_timeout(self) -> None:
        if self.message:
            self.disable_all()
            try:
                await self.message.edit(view=self)
            except discord.HTTPException:
                pass


class FilterCog(commands.Cog):
    """`filter enable` / `filter disable`: thin front end for the SAME effect state as `.fx` and `.remix`.

    There is no state here: the current filter is read from the player (utils/remix.py `get_state`) and
    every change goes through `utils.remix.set_preset`, so it works even if the Remix cog is not loaded.
    """

    def __init__(self, bot: commands.Bot):
        self.bot = bot

    async def cog_check(self, ctx: commands.Context) -> bool:
        if ctx.guild is None:
            raise commands.NoPrivateMessage()
        return True

    def _player(self, ctx: commands.Context) -> Optional[MusicPlayer]:
        vc = ctx.voice_client
        return vc if isinstance(vc, MusicPlayer) else None

    async def apply_filter(self, ctx: commands.Context, filter_name: str):
        player = self._player(ctx)
        if not player or not player.playing:
            await ctx.send(embed=discord.Embed(description=f"{E.WARNING} I'm not playing anything.", color=0xFF0000))
            return

        if ctx.author.voice is None or ctx.author.voice.channel != player.channel:
            await ctx.send(embed=discord.Embed(description=f"{E.WARNING} You need to be in the same voice channel as me.", color=0xFF0000))
            return

        if not can_control(player, ctx.author.id):
            await ctx.send(embed=discord.Embed(description=denied_text(player), color=0xFF0000))
            return

        try:
            ok, note = await set_preset(player, filter_name)
        except RemixError as exc:  # carries a user-safe message
            await ctx.send(embed=discord.Embed(description=f"{E.WARNING} {exc}", color=0xFF0000))
            return
        if not ok:
            await ctx.send(embed=discord.Embed(description=f"{E.WARNING} {note}", color=0xFF0000))
            return
        text = f"{E.TICK} Filter set to **{filter_name}**." + (f"\n{note}" if note else "")
        await self._say(ctx, text, 0x1DB954, ack=False)  # the filter menu already answered a slash command

    async def _say(self, ctx: commands.Context, text: str, color: int, **kwargs) -> None:
        """The reply goes inside the player card (one message); a normal reply if there is no card."""
        music = self.bot.get_cog("Music")
        if music is not None:
            await music.note(ctx, text, color, **kwargs)
        else:
            await ctx.send(embed=discord.Embed(description=text, color=color))

    @commands.hybrid_group(invoke_without_command=True, help="Manage audio filters.")
    @blacklist_check()
    @ignore_check()
    @commands.cooldown(1, 3, commands.BucketType.user)
    async def filter(self, ctx: commands.Context):
        prefix = ctx.clean_prefix
        await ctx.send(embed=discord.Embed(
            description=f"{E.MUSIC} Use `{prefix}filter enable` to enable a filter or `{prefix}filter disable` to disable the current filter.",
            color=0x5865F2,
        ))

    @filter.command(help="Enable a filter.")
    @blacklist_check()
    @ignore_check()
    @commands.cooldown(1, 3, commands.BucketType.user)
    async def enable(self, ctx: commands.Context):
        player = self._player(ctx)
        if not player or not player.playing:
            await ctx.send(embed=discord.Embed(description=f"{E.WARNING} I'm not connected to a voice channel.", color=0xFF0000))
            return

        if ctx.author.voice is None or ctx.author.voice.channel != player.channel:
            await ctx.send(embed=discord.Embed(description=f"{E.WARNING} You need to be in the same voice channel as me.", color=0xFF0000))
            return

        if not can_control(player, ctx.author.id):
            await ctx.send(embed=discord.Embed(description=denied_text(player), color=0xFF0000))
            return

        filter_options = [
            discord.SelectOption(label=name.title(), value=name, description=f"Apply the {name} preset")
            for name in PRESETS
        ]

        view = FilterSelect(self, ctx, filter_options)
        state = get_state(player)
        current_filter = state.label or "None"
        embed = discord.Embed(title=f"{E.MUSIC} Enable Audio Filter", description="Choose a filter from the menu below to apply:", color=0x5865F2)
        embed.add_field(name="Current Filter", value=f"`{current_filter}`", inline=False)
        embed.set_footer(text=f"Thanks for choosing {config.NAME}!")
        view.message = await ctx.send(embed=embed, view=view)

    @filter.command(help="Disable the current filter.")
    @blacklist_check()
    @ignore_check()
    @commands.cooldown(1, 3, commands.BucketType.user)
    async def disable(self, ctx: commands.Context):
        player = self._player(ctx)
        if not player or not player.playing:
            await ctx.send(embed=discord.Embed(description=f"{E.WARNING} I'm not connected to a voice channel.", color=0xFF0000))
            return

        if ctx.author.voice is None or ctx.author.voice.channel != player.channel:
            await ctx.send(embed=discord.Embed(description=f"{E.WARNING} You need to be in the same voice channel as me.", color=0xFF0000))
            return

        if not can_control(player, ctx.author.id):
            await ctx.send(embed=discord.Embed(description=denied_text(player), color=0xFF0000))
            return

        try:
            await set_preset(player, "off")
        except RemixError as exc:
            await ctx.send(embed=discord.Embed(description=f"{E.WARNING} {exc}", color=0xFF0000))
            return
        await self._say(ctx, f"{E.TICK} Filter disabled.", 0x1DB954)


"""
Developed by viper & prashu.
"""
