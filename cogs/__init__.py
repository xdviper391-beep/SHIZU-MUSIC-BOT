from __future__ import annotations

from colorama import Fore, Style, init

from core import ShizuMusic

# ---------- Commands ----------
from .commands.editemojis import EditEmojis
from .commands.filters import FilterCog
from .commands.help import Help
from .commands.music import Music
from .commands.owner import Owner
from .commands.prefix import Prefix
from .commands.remix import Remix

# ---------- Events ----------
from .events.Errors import Errors
from .events.GuildEvents import GuildEvents

init(autoreset=True)


async def setup(bot: ShizuMusic):
    cogs_to_load = [Help, Music, FilterCog, Remix, Owner, EditEmojis, Prefix, Errors, GuildEvents]  # Music first: Remix / filters use its player

    for cog in cogs_to_load:
        await bot.add_cog(cog(bot))
        print(Fore.GREEN + Style.BRIGHT + f"Loaded cog: {cog.__name__}")
    print(Fore.GREEN + Style.BRIGHT + "All cogs loaded successfully.")
