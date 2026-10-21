import logging

import discord
from discord.ext import commands

from core import Cog, Context, TestingMusic
from utils import emojis as E
from utils.Tools import get_ignore_data

log = logging.getLogger("testingmusic.errors")


def _unwrap(error: Exception) -> Exception:
    """Dig the real exception out of CommandInvokeError / HybridCommandError wrappers."""
    wrappers = (commands.CommandInvokeError, commands.HybridCommandError)
    while isinstance(error, wrappers) and getattr(error, "original", None) is not None:
        error = error.original
    return error


class Errors(Cog):
    def __init__(self, client: TestingMusic):
        self.client = client

    @commands.Cog.listener()
    async def on_command_error(self, ctx: Context, error):
        if ctx.command is None:
            return

        real = _unwrap(error)
        avatar = ctx.author.display_avatar.url
        bot_avatar = self.client.user.display_avatar.url

        # Errors meant for the user as-is (the music cog's MusicError): show the message, don't log a traceback.
        user_message = getattr(real, "user_message", None)
        if user_message:
            await ctx.send(embed=discord.Embed(description=f"{E.WARNING} {user_message}", color=0xFF0000), delete_after=15)
            return

        if isinstance(error, commands.CommandNotFound):
            return

        if isinstance(error, commands.MissingRequiredArgument):
            await ctx.send_help(ctx.command)
            ctx.command.reset_cooldown(ctx)
            return

        if isinstance(error, commands.CheckFailure) and not isinstance(error, commands.NoPrivateMessage):
            if ctx.guild is None:
                return
            data = await get_ignore_data(ctx.guild.id)
            ch = data["channel"]
            iuser = data["user"]
            cmd = data["command"]
            buser = data["bypassuser"]

            if str(ctx.author.id) in buser:
                return

            if str(ctx.channel.id) in ch:
                await ctx.reply(
                    f"{ctx.author.mention} This **channel** is on the **ignored** list. "
                    "Please try my commands in another channel.",
                    delete_after=8,
                )
                return

            if str(ctx.author.id) in iuser:
                await ctx.reply(
                    f"{ctx.author.mention} You are set as an **ignored user** for this guild. "
                    "Please try my commands or modules in a different guild.",
                    delete_after=8,
                )
                return

            names = {ctx.command.name.strip().lower()}
            names.update(alias.strip().lower() for alias in ctx.command.aliases)
            if names & cmd:
                await ctx.reply(
                    f"{ctx.author.mention} This **command is ignored** in this guild. "
                    "Please use other commands or try this command in a different guild",
                    delete_after=8,
                )
                return
            return

        if isinstance(error, commands.NoPrivateMessage):
            embed = discord.Embed(color=0x000000, description="You can't use my commands in DMs.")
            embed.set_author(name=str(ctx.author), icon_url=avatar)
            embed.set_thumbnail(url=avatar)
            await ctx.reply(embed=embed, delete_after=20)
            return

        if isinstance(error, commands.TooManyArguments):
            await ctx.send_help(ctx.command)
            ctx.command.reset_cooldown(ctx)
            return

        if isinstance(error, commands.CommandOnCooldown):
            embed = discord.Embed(
                color=0x000000,
                description=f"{ctx.author.mention} Whoa, slow down there! You can run the command again in "
                f"**{error.retry_after:.2f}** seconds.",
            )
            embed.set_author(name="Cooldown", icon_url=bot_avatar)
            embed.set_thumbnail(url=bot_avatar)
            embed.set_footer(text=f"Requested by {ctx.author}", icon_url=avatar)
            await ctx.reply(embed=embed, delete_after=10)
            return

        if isinstance(error, commands.MaxConcurrencyReached):
            embed = discord.Embed(
                color=0x000000,
                description=f"{ctx.author.mention} This command is already in progress. "
                "Please let it finish and try again afterward.",
            )
            embed.set_author(name="Command in Progress.", icon_url=bot_avatar)
            embed.set_thumbnail(url=bot_avatar)
            embed.set_footer(text=f"Requested by {ctx.author}", icon_url=avatar)
            await ctx.reply(embed=embed, delete_after=10)
            ctx.command.reset_cooldown(ctx)
            return

        if isinstance(error, commands.MissingPermissions):
            missing = [perm.replace("_", " ").replace("guild", "server").title() for perm in error.missing_permissions]
            fmt = "{}, and {}".format(", ".join(missing[:-1]), missing[-1]) if len(missing) > 2 else " and ".join(missing)
            embed = discord.Embed(
                color=0x000000,
                description=f"You lack the **{fmt}** Permission to run the **{ctx.command.name}** command!",
            )
            embed.set_author(name="Missing Permissions", icon_url=bot_avatar)
            embed.set_thumbnail(url=bot_avatar)
            embed.set_footer(text=f"Requested by {ctx.author}", icon_url=avatar)
            await ctx.reply(embed=embed, delete_after=7)
            ctx.command.reset_cooldown(ctx)
            return

        if isinstance(error, commands.BadArgument):
            await ctx.send_help(ctx.command)
            ctx.command.reset_cooldown(ctx)
            return

        if isinstance(error, commands.BotMissingPermissions):
            missing = ", ".join(perm.replace("_", " ").title() for perm in error.missing_permissions)
            await ctx.reply(
                f"{E.DENIED} I need **{missing}** Permission to run the **{ctx.command.qualified_name}** command!",
                delete_after=7,
            )
            return

        if isinstance(real, discord.HTTPException) and not isinstance(error, commands.CommandInvokeError):
            log.debug("HTTP error while running %s: %s", ctx.command, real)
            return

        # Anything else is a genuine bug / runtime failure: log it instead of swallowing it.
        log.error("Unhandled error in command '%s'", ctx.command.qualified_name, exc_info=real)
        try:
            await ctx.send(
                embed=discord.Embed(
                    description=f"{E.WARNING} Something went wrong while running that command. "
                    "Please try again in a moment.",
                    color=0xFF0000,
                ),
                delete_after=10,
            )
        except discord.HTTPException:
            pass
