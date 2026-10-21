from __future__ import annotations

import logging
from typing import Optional

import discord
from discord import app_commands
from discord.ext import commands

from core import Context, ShizuMusic
from utils import config
from utils import emojis as E
from utils.Tools import blacklist_check, getConfig, ignore_check, updateConfig

log = logging.getLogger("shizumusic.prefix")


class Prefix(commands.Cog):
    """Server prefix management."""

    def __init__(self, bot: ShizuMusic):
        self.bot = bot

    async def cog_check(self, ctx: Context) -> bool:
        if ctx.guild is None:
            raise commands.NoPrivateMessage()
        return True

    @commands.hybrid_command(
        name="setprefix",
        aliases=["changeprefix", "prefixset"],
        usage="setprefix <new_prefix>",
        help="Change the bot's command prefix for this server (Requires Manage Server).",
    )
    @app_commands.describe(new_prefix="The new command prefix (1-5 characters)")
    @commands.has_permissions(manage_guild=True)
    @blacklist_check()
    @ignore_check()
    @commands.cooldown(1, 3, commands.BucketType.guild)
    async def setprefix(self, ctx: Context, new_prefix: str):
        prefix_clean = new_prefix.strip()
        if not (1 <= len(prefix_clean) <= 5) or any(c in prefix_clean for c in (" ", "`", "<", ">", "@", "#")):
            embed = discord.Embed(
                description=f"{E.WARNING} The prefix must be between 1 and 5 characters long and cannot contain spaces, backticks, or mentions.",
                color=0xFF0000,
            )
            embed.set_author(name="Invalid Prefix", icon_url=self.bot.user.display_avatar.url)
            embed.set_footer(text=f"Thanks for choosing {config.NAME}!")
            await ctx.send(embed=embed)
            return

        await updateConfig(ctx.guild.id, {"prefix": prefix_clean})
        embed = discord.Embed(
            description=(
                f"{E.TICK} Successfully updated server prefix to `{prefix_clean}`\n\n"
                f"You can now run commands using `{prefix_clean}play`, `{prefix_clean}help`, etc."
            ),
            color=0x1DB954,
        )
        embed.set_author(name="Prefix Updated", icon_url=self.bot.user.display_avatar.url)
        embed.set_footer(text=f"Thanks for choosing {config.NAME}!")
        await ctx.send(embed=embed)

    @setprefix.error
    async def setprefix_error(self, ctx: Context, error: Exception):
        if isinstance(error, commands.MissingPermissions):
            embed = discord.Embed(
                description=f"{E.WARNING} You need **Manage Server** permission to change the bot prefix.",
                color=0xFF0000,
            )
            embed.set_author(name="Missing Permissions", icon_url=self.bot.user.display_avatar.url)
            embed.set_footer(text=f"Thanks for choosing {config.NAME}!")
            await ctx.send(embed=embed)
        elif isinstance(error, commands.MissingRequiredArgument):
            data = await getConfig(ctx.guild.id)
            current = data["prefix"]
            embed = discord.Embed(
                description=f"{E.WARNING} Please provide a new prefix! Example: `{current}setprefix !`",
                color=0xFF0000,
            )
            embed.set_author(name="Missing Argument", icon_url=self.bot.user.display_avatar.url)
            embed.set_footer(text=f"Thanks for choosing {config.NAME}!")
            await ctx.send(embed=embed)

    @commands.hybrid_command(
        name="prefix",
        usage="prefix [new_prefix]",
        help="View or change the server prefix.",
    )
    @app_commands.describe(new_prefix="Optional new prefix to set (requires Manage Server)")
    @blacklist_check()
    @ignore_check()
    @commands.cooldown(1, 3, commands.BucketType.user)
    async def prefix_cmd(self, ctx: Context, new_prefix: Optional[str] = None):
        if new_prefix is not None:
            if not ctx.author.guild_permissions.manage_guild and not ctx.author.guild_permissions.administrator:
                embed = discord.Embed(
                    description=f"{E.WARNING} You need **Manage Server** permission to change the bot prefix.",
                    color=0xFF0000,
                )
                embed.set_author(name="Missing Permissions", icon_url=self.bot.user.display_avatar.url)
                embed.set_footer(text=f"Thanks for choosing {config.NAME}!")
                await ctx.send(embed=embed)
                return
            await self.setprefix(ctx, new_prefix=new_prefix)
            return

        data = await getConfig(ctx.guild.id)
        current = data["prefix"]
        embed = discord.Embed(
            description=(
                f"{E.MUSIC} The current prefix for this server is `{current}`\n\n"
                f"To change it, use `{current}setprefix <new_prefix>`"
            ),
            color=0x5865F2,
        )
        embed.set_author(name=f"{config.NAME} • Prefix", icon_url=self.bot.user.display_avatar.url)
        embed.set_footer(text=f"Thanks for choosing {config.NAME}!")
        await ctx.send(embed=embed)


async def setup(bot: ShizuMusic):
    await bot.add_cog(Prefix(bot))
