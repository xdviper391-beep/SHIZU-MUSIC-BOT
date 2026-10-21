"""`.editemojis` - change the button emojis for every server (bot owner only).

    .editemojis      opens a panel of buttons. Tap a button, send its new emoji, done.

Two pages: "Player" (the buttons under the now-playing card) and "Remix" (the Remix console). Normal emoji and
server / animated emoji from any server both work. An emoji from another server is copied into the bot's own
application emoji first (utils/emoji_sync.py), so it shows the same everywhere. The choice is saved once
(db/button_emojis.json, see utils/button_emojis.py), so every server gets the same emoji from the next player
message / console on. Type `reset` in the pop-up to go back to the default.
"""
from __future__ import annotations

import logging
from typing import Optional

import discord
from discord.ext import commands

from core import ShizuMusic
from utils import button_emojis as BE
from utils.emoji_sync import ensure_app_emoji

log = logging.getLogger("shizumusic.editemojis")

GREY = discord.Color.from_rgb(43, 45, 49)
PAGES = {"player": ("Player buttons", BE.PLAYER_SLOTS), "remix": ("Remix console", BE.REMIX_SLOTS)}


class EmojiModal(discord.ui.Modal):
    """The pop-up behind a slot button: paste the new emoji."""

    def __init__(self, editor: "EmojiEditor", slot: str, label: str) -> None:
        super().__init__(title=f"Emoji for {label}"[:45])
        self.editor = editor
        self.slot = slot
        self.emoji = discord.ui.TextInput(
            label="Emoji (or type reset)",
            placeholder="\U0001f600   or   <a:name:id>   or   reset",
            default=BE.get(slot)[:100],
            min_length=1,
            max_length=100,
        )
        self.add_item(self.emoji)

    async def on_submit(self, interaction: discord.Interaction) -> None:
        await interaction.response.defer()
        raw = str(self.emoji.value).strip()
        copied = True
        if raw.lower() in {"reset", "default"}:
            value: Optional[str] = None
        else:
            value = BE.parse(raw)
            if value is None:
                await interaction.followup.send(
                    "That isn't a single emoji. Send one emoji like \U0001f600 or `<a:name:id>` (type "
                    "`\\:emojiname:` in chat to get the code), or type `reset`.",
                    ephemeral=True,
                )
                return
            bot = self.editor.bot
            value, copied = await ensure_app_emoji(bot, bot.session, value)

        before = BE.stored(self.slot)
        BE.set_emoji(self.slot, value)
        self.editor.build()
        try:
            # Discord has the last word: if it refuses the emoji on a button, nothing is kept.
            await interaction.edit_original_response(embed=self.editor.embed(), view=self.editor)
        except discord.HTTPException:
            BE.set_emoji(self.slot, before)
            self.editor.build()
            await interaction.followup.send("Discord didn't accept that emoji, so nothing was changed.", ephemeral=True)
            return
        if value and not copied:
            await interaction.followup.send(
                "Saved, but I couldn't copy that emoji into the bot's own emoji, so it may only show in servers "
                "where the bot can see it.",
                ephemeral=True,
            )

    async def on_error(self, interaction: discord.Interaction, error: Exception) -> None:
        log.error("Edit emojis pop-up failed", exc_info=error)
        text = "Sorry, that didn't work. Please try again."
        if interaction.response.is_done():
            await interaction.followup.send(text, ephemeral=True)
        else:
            await interaction.response.send_message(text, ephemeral=True)


class EmojiEditor(discord.ui.View):
    """Row 0: Player | Remix | Reset page.  Rows 1-4: one button per slot, showing its current emoji."""

    def __init__(self, bot: ShizuMusic, owner_id: int, page: str = "player") -> None:
        super().__init__(timeout=600)
        self.bot = bot
        self.owner_id = owner_id
        self.page = page
        self.message: Optional[discord.Message] = None
        self.build()

    def build(self) -> None:
        self.clear_items()
        for key, (title, _) in PAGES.items():
            button = discord.ui.Button(
                label=title,
                style=discord.ButtonStyle.primary if key == self.page else discord.ButtonStyle.secondary,
                row=0,
            )
            button.callback = self._switch(key)
            self.add_item(button)
        reset = discord.ui.Button(label="Reset page", style=discord.ButtonStyle.danger, row=0)
        reset.callback = self._reset
        self.add_item(reset)

        for index, (slot, label) in enumerate(PAGES[self.page][1]):
            button = discord.ui.Button(
                label=label, emoji=BE.get(slot), style=discord.ButtonStyle.secondary, row=1 + index // 5
            )
            button.callback = self._pick(slot, label)
            self.add_item(button)

    def embed(self) -> discord.Embed:
        embed = discord.Embed(
            title=f"Button emojis \u2014 {PAGES[self.page][0]}",
            description=(
                "Tap a button, then send its new emoji. It applies to **every server**, from the next player "
                "message on."
            ),
            color=GREY,
        )
        embed.set_footer(text="Normal or animated emoji, from any server. Type reset in the pop-up for the default.")
        return embed

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if interaction.user.id == self.owner_id and await self.bot.is_owner(interaction.user):
            return True
        await interaction.response.send_message("Only the bot owner can change the button emojis.", ephemeral=True)
        return False

    def _switch(self, page: str):
        async def callback(interaction: discord.Interaction) -> None:
            self.page = page
            self.build()
            await interaction.response.edit_message(embed=self.embed(), view=self)
        return callback

    def _pick(self, slot: str, label: str):
        async def callback(interaction: discord.Interaction) -> None:
            await interaction.response.send_modal(EmojiModal(self, slot, label))
        return callback

    async def _reset(self, interaction: discord.Interaction) -> None:
        BE.reset([slot for slot, _ in PAGES[self.page][1]])
        self.build()
        await interaction.response.edit_message(embed=self.embed(), view=self)

    async def on_timeout(self) -> None:
        for child in self.children:
            child.disabled = True
        if self.message is not None:
            try:
                await self.message.edit(view=self)
            except discord.HTTPException:
                pass


class EditEmojis(commands.Cog):
    """Bot-owner only. Hidden from help, silent for everyone else."""

    def __init__(self, bot: ShizuMusic):
        self.bot = bot

    async def cog_check(self, ctx: commands.Context) -> bool:
        if not await self.bot.is_owner(ctx.author):
            raise commands.NotOwner()  # Errors cog stays silent for this
        return True

    @commands.command(
        name="editemojis",
        aliases=["editemoji", "emojiedit", "buttonemojis"],
        hidden=True,
        usage="editemojis",
        help="Change the player and Remix button emojis for every server.",
    )
    async def editemojis(self, ctx: commands.Context):
        view = EmojiEditor(self.bot, ctx.author.id)
        view.message = await ctx.send(embed=view.embed(), view=view)


async def setup(bot: ShizuMusic) -> None:
    await bot.add_cog(EditEmojis(bot))
