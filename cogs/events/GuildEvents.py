"""Bot Server Join & Removal Notification System.

Handles:
1. Detecting new guild joins, notifying bot owners via DM, and sending a welcome DM
   to the verified inviter (without falsely identifying the server owner).
2. Detecting guild removals, classifying kicks and bans via audit-log data where permitted,
   notifying bot owners, and sending a respectful, rate-limited feedback prompt
   to the person who kicked the bot (if reliably identified).
"""
from __future__ import annotations

import asyncio
import json
import logging
import time
from typing import Dict, List, Optional, Set

import discord
from discord.ext import commands

from utils import config
from utils.Tools import getConfig

log = logging.getLogger("shizumusic.guild_events")
feedback_log = logging.getLogger("shizumusic.feedback")

FEEDBACK_FILE = config.DB_DIR / "feedback.json"


def _invite_url(bot: commands.Bot) -> str:
    """Generate dynamic bot invite URL with recommended music permissions."""
    if config.INVITE_URL:
        return config.INVITE_URL
    if not bot.user:
        return "https://discord.com"
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


def save_feedback(record: dict) -> None:
    """Persist user feedback into db/feedback.json."""
    try:
        data: list = []
        if FEEDBACK_FILE.exists():
            try:
                data = json.loads(FEEDBACK_FILE.read_text(encoding="utf-8"))
                if not isinstance(data, list):
                    data = []
            except Exception:
                data = []
        data.append(record)
        FEEDBACK_FILE.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")
    except Exception:
        log.warning("Could not persist feedback entry to %s", FEEDBACK_FILE, exc_info=True)


class FeedbackModal(discord.ui.Modal):
    """Optional written feedback form submitted by a member who kicked the bot."""

    def __init__(self, cog: "GuildEvents", guild_id: int, guild_name: str, actor: discord.abc.User, rating: Optional[int] = None):
        super().__init__(title=f"{config.NAME} Feedback"[:45])
        self.cog = cog
        self.guild_id = guild_id
        self.guild_name = guild_name
        self.actor = actor
        self.rating = rating

        self.comment_input = discord.ui.TextInput(
            label="What can we improve?",
            style=discord.TextStyle.paragraph,
            placeholder="Tell us why the bot was removed or any issues you experienced...",
            max_length=1000,
            required=True,
        )
        self.add_item(self.comment_input)

    async def on_submit(self, interaction: discord.Interaction):
        comment = str(self.comment_input.value).strip()
        record = {
            "timestamp": int(time.time()),
            "user_id": self.actor.id,
            "user_name": str(self.actor),
            "guild_id": self.guild_id,
            "guild_name": self.guild_name,
            "rating": self.rating,
            "comment": comment,
        }
        save_feedback(record)
        feedback_log.info(
            "Feedback from %s (%s) for guild %s (%s): %s/5 stars — %s",
            self.actor.id, self.actor.name, self.guild_id, self.guild_name, self.rating, comment
        )

        # Notify bot owners
        await self.cog.notify_owners_feedback(
            actor=self.actor,
            guild_id=self.guild_id,
            guild_name=self.guild_name,
            rating=self.rating,
            comment=comment,
        )

        embed = discord.Embed(
            title="✅ Thank you for your feedback!",
            description=(
                "Your input has been delivered directly to the developers. "
                "It helps us improve **Shizu Music** for everyone!\n\n"
                f"If you ever wish to try the bot again in the future: [Re-invite Bot]({_invite_url(self.cog.bot)})"
            ),
            color=0x1DB954,
        )
        await interaction.response.edit_message(embed=embed, view=None)


class KickedFeedbackView(discord.ui.View):
    """Interactive rating buttons (1-5 stars) and optional feedback prompt."""

    def __init__(self, cog: "GuildEvents", guild_id: int, guild_name: str, actor: discord.abc.User):
        super().__init__(timeout=600)
        self.cog = cog
        self.guild_id = guild_id
        self.guild_name = guild_name
        self.actor = actor

        # Star Rating buttons (Row 0)
        for stars in range(1, 6):
            btn = discord.ui.Button(
                label=f"{stars} ⭐",
                style=discord.ButtonStyle.secondary,
                custom_id=f"rate_{stars}",
                row=0,
            )
            btn.callback = self._make_rating_callback(stars)
            self.add_item(btn)

        # Detailed feedback button (Row 1)
        write_btn = discord.ui.Button(
            label="Write Detailed Feedback",
            emoji="📝",
            style=discord.ButtonStyle.primary,
            custom_id="write_feedback",
            row=1,
        )
        write_btn.callback = self.write_callback
        self.add_item(write_btn)

        # Dismiss button (Row 1)
        dismiss_btn = discord.ui.Button(
            label="Dismiss",
            emoji="✖️",
            style=discord.ButtonStyle.secondary,
            custom_id="dismiss",
            row=1,
        )
        dismiss_btn.callback = self.dismiss_callback
        self.add_item(dismiss_btn)

        # External Links (Row 2)
        if config.SUPPORT_URL:
            self.add_item(
                discord.ui.Button(
                    label="Support Server",
                    url=config.SUPPORT_URL,
                    style=discord.ButtonStyle.link,
                    row=2,
                )
            )
        if config.REVIEW_URL:
            self.add_item(
                discord.ui.Button(
                    label="Review Bot",
                    url=config.REVIEW_URL,
                    style=discord.ButtonStyle.link,
                    row=2,
                )
            )

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        return interaction.user.id == self.actor.id

    def _make_rating_callback(self, stars: int):
        async def callback(interaction: discord.Interaction):
            record = {
                "timestamp": int(time.time()),
                "user_id": self.actor.id,
                "user_name": str(self.actor),
                "guild_id": self.guild_id,
                "guild_name": self.guild_name,
                "rating": stars,
                "comment": None,
            }
            save_feedback(record)
            feedback_log.info(
                "Quick Rating from %s (%s) for guild %s (%s): %d/5 stars",
                self.actor.id, self.actor.name, self.guild_id, self.guild_name, stars
            )

            await self.cog.notify_owners_feedback(
                actor=self.actor,
                guild_id=self.guild_id,
                guild_name=self.guild_name,
                rating=stars,
                comment=None,
            )

            embed = discord.Embed(
                title="✅ Thank you!",
                description=(
                    f"You gave **{config.NAME}** a **{stars}/5 ⭐** rating.\n"
                    "We appreciate your feedback and hope to see you again!\n\n"
                    f"• [Support Server]({config.SUPPORT_URL}) • [Re-invite Bot]({_invite_url(self.cog.bot)})"
                ),
                color=0x1DB954,
            )
            await interaction.response.edit_message(embed=embed, view=None)
            self.stop()

        return callback

    async def write_callback(self, interaction: discord.Interaction):
        modal = FeedbackModal(
            cog=self.cog,
            guild_id=self.guild_id,
            guild_name=self.guild_name,
            actor=self.actor,
            rating=None,
        )
        await interaction.response.send_modal(modal)

    async def dismiss_callback(self, interaction: discord.Interaction):
        await interaction.response.edit_message(
            content="Feedback prompt dismissed. Thank you for your time!",
            embed=None,
            view=None,
        )
        self.stop()

    async def on_timeout(self):
        for item in self.children:
            if hasattr(item, "disabled"):
                item.disabled = True


class GuildEvents(commands.Cog, name="GuildEvents"):
    """Listens for server additions, removals, kicks, and bans."""

    def __init__(self, bot: commands.Bot):
        self.bot = bot
        # Debounce caches to prevent duplicate alerts from reconnects / sharding
        self._recent_joins: Dict[int, float] = {}
        self._recent_removals: Dict[int, dict] = {}
        self._processed_removals: Set[int] = set()
        self._feedback_cooldowns: Dict[int, float] = {}

    async def get_owners(self) -> List[discord.User]:
        """Resolve all configured bot owners dynamically."""
        owner_ids: Set[int] = set(config.OWNER_IDS)

        # Discord.py bot attributes
        if self.bot.owner_ids:
            owner_ids.update(self.bot.owner_ids)
        elif self.bot.owner_id:
            owner_ids.add(self.bot.owner_id)

        # Application owner fallback if OWNER_IDS was empty
        if not owner_ids and getattr(self.bot, "application", None):
            app = self.bot.application
            if app and app.owner:
                if isinstance(app.owner, discord.Team):
                    for member in app.owner.members:
                        owner_ids.add(member.id)
                else:
                    owner_ids.add(app.owner.id)

        owners: List[discord.User] = []
        for uid in owner_ids:
            user = self.bot.get_user(uid)
            if user is None:
                try:
                    user = await self.bot.fetch_user(uid)
                except (discord.NotFound, discord.HTTPException):
                    user = None
            if user and not user.bot:
                owners.append(user)
        return owners

    async def notify_owners_feedback(
        self,
        actor: discord.abc.User,
        guild_id: int,
        guild_name: str,
        rating: Optional[int],
        comment: Optional[str],
    ) -> None:
        """Forward user feedback directly to bot owners."""
        owners = await self.get_owners()
        if not owners:
            return

        now = int(time.time())
        rating_str = f"{rating}/5 ⭐" if rating else "Not specified"
        embed = discord.Embed(
            title="⭐ New Server Removal Feedback Received",
            color=0xFEE75C,
        )
        embed.add_field(name="User", value=f"{actor.mention} (**{actor.name}** \u2022 `{actor.id}`)", inline=False)
        embed.add_field(name="Server", value=f"**{guild_name}** (`{guild_id}`)", inline=False)
        embed.add_field(name="Star Rating", value=f"`{rating_str}`", inline=True)
        embed.add_field(name="Submitted At", value=f"<t:{now}:R>", inline=True)
        embed.add_field(name="Feedback / Comments", value=f"```{comment or 'No written comment provided'}```", inline=False)
        embed.set_footer(text=f"{config.NAME} • Feedback Collector")

        for owner in owners:
            try:
                await owner.send(embed=embed)
            except (discord.Forbidden, discord.HTTPException):
                pass

    # ═════════════════════════════════════════════════════════════════════════
    #  1. AUDIT LOG TRACKING (Pre-removal Kick & Ban capture)
    # ═════════════════════════════════════════════════════════════════════════
    @commands.Cog.listener()
    async def on_audit_log_entry_create(self, entry: discord.AuditLogEntry):
        """Gateway audit log listener to capture kick / ban actors before guild drops."""
        if not self.bot.user or not entry.target or entry.target.id != self.bot.user.id:
            return

        now = time.time()
        guild = getattr(entry, "guild", None)
        guild_id = guild.id if guild else int(getattr(entry, "guild_id", 0) or 0)
        guild_name = guild.name if guild else "Unknown Guild"

        if entry.action == discord.AuditLogAction.kick:
            self._recent_removals[guild_id] = {
                "action": "kick",
                "actor": entry.user,
                "reason": getattr(entry, "reason", None),
                "time": now,
                "guild_name": guild_name,
                "guild_id": guild_id,
            }
            log.info("Recorded kick audit log entry for bot in guild %s by %s", guild_id, entry.user)
        elif entry.action == discord.AuditLogAction.ban:
            self._recent_removals[guild_id] = {
                "action": "ban",
                "actor": entry.user,
                "reason": getattr(entry, "reason", None),
                "time": now,
                "guild_name": guild_name,
                "guild_id": guild_id,
            }
            log.info("Recorded ban audit log entry for bot in guild %s by %s", guild_id, entry.user)

    @commands.Cog.listener()
    async def on_member_ban(self, guild: discord.Guild, user: discord.abc.User):
        """Fallback listener for ban event targeting the bot."""
        if not self.bot.user or user.id != self.bot.user.id:
            return
        if guild.id not in self._recent_removals:
            self._recent_removals[guild.id] = {
                "action": "ban",
                "actor": None,
                "reason": None,
                "time": time.time(),
                "guild_name": guild.name,
                "guild_id": guild.id,
            }
            log.info("Recorded on_member_ban for bot in guild %s", guild.id)

    # ═════════════════════════════════════════════════════════════════════════
    #  2. GUILD JOIN NOTIFICATION & WELCOME
    # ═════════════════════════════════════════════════════════════════════════
    @commands.Cog.listener()
    async def on_guild_join(self, guild: discord.Guild):
        """Triggered when the bot is added to a new server."""
        now = time.time()
        # Debounce multiple events within 15 seconds
        if now - self._recent_joins.get(guild.id, 0) < 15:
            return
        self._recent_joins[guild.id] = now

        log.info("Bot added to new guild: %s (ID: %s) with %s members", guild.name, guild.id, guild.member_count)

        # Allow guild state and authorization audit log entry to settle
        await asyncio.sleep(1.0)

        # ── Verify inviter via audit log ──────────────────────
        inviter: Optional[discord.abc.User] = None
        inviter_method: str = "Unknown"

        me = guild.me or (await guild.fetch_member(self.bot.user.id) if self.bot.user else None)
        if me and me.guild_permissions.view_audit_log:
            try:
                async for entry in guild.audit_logs(limit=5, action=discord.AuditLogAction.bot_add):
                    if entry.target and self.bot.user and entry.target.id == self.bot.user.id:
                        inviter = entry.user
                        inviter_method = "Verified via Audit Log"
                        break
            except (discord.Forbidden, discord.HTTPException) as exc:
                log.warning("Could not query audit log on guild %s: %s", guild.id, exc)

        if inviter:
            inviter_str = f"{inviter.mention} (**{inviter.name}** \u2022 `{inviter.id}`)"
        else:
            inviter_str = "Unknown (Grant bot 'View Audit Log' permission to identify inviter)"

        # ── Send Owner Notification DM ────────────────────────
        owners = await self.get_owners()
        join_timestamp = int(now)

        embed = discord.Embed(
            title="📥 Joined a New Server!",
            description=f"**{config.NAME}** has been invited to a new Discord server.",
            color=0x1DB954,
        )
        if guild.icon:
            embed.set_thumbnail(url=guild.icon.url)

        embed.add_field(name="Server Name", value=f"**{guild.name}**", inline=True)
        embed.add_field(name="Server ID", value=f"`{guild.id}`", inline=True)

        # Server Owner
        owner_text = f"<@{guild.owner_id}>"
        owner_member = guild.owner or (self.bot.get_user(guild.owner_id) if guild.owner_id else None)
        if owner_member:
            owner_text = f"{owner_member.mention} (**{owner_member.name}**)"
        embed.add_field(name="Server Owner", value=owner_text, inline=True)

        count_str = f"`{guild.member_count:,}` members" if guild.member_count else "`Unknown`"
        embed.add_field(name="Member Count", value=count_str, inline=True)
        embed.add_field(name="Invited By", value=f"{inviter_str} *({inviter_method})*", inline=True)
        embed.add_field(name="Total Servers", value=f"`{len(self.bot.guilds)}` servers", inline=True)
        embed.add_field(name="Joined At", value=f"<t:{join_timestamp}:F> (<t:{join_timestamp}:R>)", inline=False)
        embed.set_footer(
            text=f"{config.NAME} • Server Monitor",
            icon_url=self.bot.user.display_avatar.url if self.bot.user else None,
        )

        for owner in owners:
            try:
                await owner.send(embed=embed)
            except discord.Forbidden:
                log.warning("Could not send join DM to bot owner %s (DMs closed)", owner.id)
            except discord.HTTPException:
                pass

        # ── Send Inviter Welcome DM (Only if reliably verified!) ──
        if inviter and not inviter.bot and config.ENABLE_JOIN_DM:
            guild_data = await getConfig(guild.id)
            prefix = guild_data.get("prefix", config.DEFAULT_PREFIX)

            welcome_embed = discord.Embed(
                title=f"🎵 Thanks for adding {config.NAME}!",
                description=(
                    f"Hello **{inviter.display_name}**! Thank you for inviting **{config.NAME}** to **{guild.name}**.\n\n"
                    "Here's a quick guide to get crystal-clear 24/7 music streaming in your server:"
                ),
                color=config.EMBED_COLOR,
            )
            welcome_embed.add_field(
                name="▶️ Quick Start",
                value=(
                    f"1. Connect to any voice channel in **{guild.name}**\n"
                    f"2. Type `{prefix}play <song title or URL>` (or `/play <song>`)\n"
                    f"3. An interactive player card will post with real-time controls"
                ),
                inline=False,
            )
            welcome_embed.add_field(
                name="🛠️ Useful Features & Commands",
                value=(
                    f"• `{prefix}help` — Interactive command center\n"
                    f"• `{prefix}setprefix <prefix>` — Set custom server prefix *(Requires Manage Server)*\n"
                    f"• `{prefix}247` — Stay in voice channel 24/7 with autoplay\n"
                    f"• `{prefix}remix` — Audio effects console (8D, Bassboost, Lofi, Atmos)"
                ),
                inline=False,
            )
            links: List[str] = []
            if config.SUPPORT_URL:
                links.append(f"[Support Server]({config.SUPPORT_URL})")
            if config.REVIEW_URL:
                links.append(f"[Review Bot]({config.REVIEW_URL})")
            invite_url = _invite_url(self.bot)
            if invite_url:
                links.append(f"[Invite Link]({invite_url})")

            if links:
                welcome_embed.add_field(name="🔗 Useful Links", value=" • ".join(links), inline=False)

            welcome_embed.set_footer(
                text=f"Server: {guild.name} • Server ID: {guild.id}",
                icon_url=guild.icon.url if guild.icon else None,
            )

            try:
                await inviter.send(embed=welcome_embed)
                log.info("Sent welcome DM to verified inviter %s (%s)", inviter.id, inviter.name)
            except discord.Forbidden:
                log.info("Could not send welcome DM to inviter %s (%s): DMs closed", inviter.id, inviter.name)
            except discord.HTTPException:
                pass

    # ═════════════════════════════════════════════════════════════════════════
    #  3. GUILD REMOVAL NOTIFICATION & KICK FEEDBACK
    # ═════════════════════════════════════════════════════════════════════════
    @commands.Cog.listener()
    async def on_guild_remove(self, guild: discord.Guild):
        """Triggered when the bot is removed from a server (kick, ban, leave, or guild deleted)."""
        now = time.time()
        # Avoid duplicate removal processing within 30 seconds
        if guild.id in self._processed_removals:
            return
        self._processed_removals.add(guild.id)
        # Auto-clean processed set after some time
        self.bot.loop.call_later(60, lambda: self._processed_removals.discard(guild.id))

        log.info("Bot removed from guild: %s (ID: %s)", guild.name, guild.id)

        # Allow audit-log gateway events in-flight to arrive
        await asyncio.sleep(1.0)

        # Check recorded pre-removal audit data
        removal_info = self._recent_removals.pop(guild.id, None)
        action: str = "removed_or_left"
        actor: Optional[discord.abc.User] = None
        reason: Optional[str] = None

        if removal_info and (now - removal_info["time"] < 60):
            action = removal_info["action"]
            actor = removal_info["actor"]
            reason = removal_info["reason"]

        # Format classification explanation honestly based on available Discord API data
        if action == "kick":
            if actor:
                status_str = f"👞 **Kicked by:** {actor.mention} (**{actor.name}** \u2022 `{actor.id}`)"
            else:
                status_str = "👞 **Kicked** (Actor unidentified — Discord denies audit log queries after removal)"
        elif action == "ban":
            if actor:
                status_str = f"🔨 **Banned by:** {actor.mention} (**{actor.name}** \u2022 `{actor.id}`)"
            else:
                status_str = "🔨 **Banned** (Actor unidentified — Discord denies audit log queries after removal)"
        else:
            status_str = "📤 **Removed / Kicked / Left** (Actor unconfirmed — audit log event was not received prior to guild removal)"

        # ── Send Owner Removal DM ──────────────────────────────
        if config.ENABLE_REMOVE_DM:
            owners = await self.get_owners()
            remove_timestamp = int(now)

            embed = discord.Embed(
                title="📤 Removed from Server",
                description=f"**{config.NAME}** has been removed from or left a server.",
                color=0xFF0000,
            )
            if guild.icon:
                embed.set_thumbnail(url=guild.icon.url)

            embed.add_field(name="Server Name", value=f"**{guild.name}**", inline=True)
            embed.add_field(name="Server ID", value=f"`{guild.id}`", inline=True)
            embed.add_field(name="Server Owner", value=f"<@{guild.owner_id}>", inline=True)

            count_str = f"`{guild.member_count:,}` members" if guild.member_count else "`Unknown`"
            embed.add_field(name="Member Count", value=count_str, inline=True)
            embed.add_field(name="Removal Status", value=status_str, inline=False)
            if reason:
                embed.add_field(name="Reason", value=f"`{reason}`", inline=False)

            embed.add_field(name="Total Servers Remaining", value=f"`{len(self.bot.guilds)}` servers", inline=True)
            embed.add_field(name="Removal Time", value=f"<t:{remove_timestamp}:F> (<t:{remove_timestamp}:R>)", inline=False)
            embed.set_footer(
                text=f"{config.NAME} • Server Removal Monitor",
                icon_url=self.bot.user.display_avatar.url if self.bot.user else None,
            )

            for owner in owners:
                try:
                    await owner.send(embed=embed)
                except discord.Forbidden:
                    log.warning("Could not send removal DM to bot owner %s (DMs closed)", owner.id)
                except discord.HTTPException:
                    pass

        # ── Send Polite Feedback DM to Kicked Actor (If verified!) ─
        if action == "kick" and actor and not actor.bot and config.ENABLE_FEEDBACK_DM:
            # Respect user cooldown / anti-spam (Default: max 1 request per user per 24 hours)
            last_request = self._feedback_cooldowns.get(actor.id, 0)
            if now - last_request < config.FEEDBACK_COOLDOWN:
                log.info("Skipping feedback DM to %s (%s): on cooldown", actor.id, actor.name)
                return
            self._feedback_cooldowns[actor.id] = now

            feedback_embed = discord.Embed(
                title=f"💬 Quick Feedback for {config.NAME}",
                description=(
                    f"Hello **{actor.display_name}**,\n"
                    f"We noticed that **{config.NAME}** was recently removed from **{guild.name}**.\n\n"
                    "We're constantly striving to make the bot better. If you have a quick moment, "
                    "would you mind sharing what could be improved? *(Completely optional)*"
                ),
                color=config.EMBED_COLOR,
            )
            feedback_embed.add_field(
                name="Rate your experience:",
                value="Click a star button below (1–5 ⭐) or write detailed feedback:",
                inline=False,
            )
            feedback_embed.set_footer(
                text=f"Server ID: {guild.id} • Thanks for trying Shizu Music!",
                icon_url=guild.icon.url if guild.icon else None,
            )

            view = KickedFeedbackView(
                cog=self,
                guild_id=guild.id,
                guild_name=guild.name,
                actor=actor,
            )

            try:
                await actor.send(embed=feedback_embed, view=view)
                log.info("Sent polite kick feedback DM to %s (%s) for guild %s", actor.id, actor.name, guild.id)
            except discord.Forbidden:
                log.info("Could not send feedback DM to user %s (%s): DMs closed", actor.id, actor.name)
            except discord.HTTPException as exc:
                log.warning("Error sending feedback DM to %s: %s", actor.id, exc)


async def setup(bot: commands.Bot):
    await bot.add_cog(GuildEvents(bot))
