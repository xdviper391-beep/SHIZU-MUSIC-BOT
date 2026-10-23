"""Central configuration. Everything comes from the environment / .env file."""
from __future__ import annotations

import os
import shutil
from pathlib import Path
from typing import List, Optional

from dotenv import dotenv_values, load_dotenv

BASE_DIR = Path(__file__).resolve().parent.parent
load_dotenv(BASE_DIR / ".env")

DB_DIR = BASE_DIR / "db"
FONT_PATH = BASE_DIR / "utils" / "arial.ttf"


def _env(name: str, default: str = "") -> str:
    return (os.getenv(name) or default).strip()


def _env_bool(name: str, default: bool = False) -> bool:
    value = _env(name)
    if not value:
        return default
    return value.lower() in {"1", "true", "yes", "on", "y"}


def _env_int(name: str, default: Optional[int] = None) -> Optional[int]:
    value = _env(name)
    try:
        return int(value) if value else default
    except ValueError:
        return default


def _env_int_list(name: str) -> List[int]:
    out: List[int] = []
    for part in _env(name).split(","):
        part = part.strip()
        if part.isdigit():
            out.append(int(part))
    return out


# ── Discord ──────────────────────────────────────────────
TOKEN = _env("DISCORD_TOKEN") or _env("TOKEN")
# NOTE: never read the process-wide PREFIX variable: Termux sets PREFIX=/data/data/com.termux/files/usr
# for itself, which used to become the bot's prefix. Only BOT_PREFIX (or PREFIX written in .env) counts.
_file_env = dotenv_values(BASE_DIR / ".env")


def _pick_prefix() -> str:
    for value in (os.getenv("BOT_PREFIX"), _file_env.get("BOT_PREFIX"), _file_env.get("PREFIX")):
        value = (value or "").strip()
        if value and len(value) <= 5 and "/" not in value[1:]:
            return value
    return "."


DEFAULT_PREFIX = _pick_prefix()
OWNER_IDS = _env_int_list("OWNER_IDS") + _env_int_list("OWNER_ID")   # from .env only; blank = the application owner
SHARD_COUNT = _env_int("SHARD_COUNT")
SYNC_COMMANDS = _env_bool("SYNC_COMMANDS", True)
ENABLE_JISHAKU = _env_bool("ENABLE_JISHAKU", False)

# ── Branding ─────────────────────────────────────────────
NAME = "Shizu Music"
DEVELOPERS = "viper & prashu"
BotName = NAME

# ── Behaviour ────────────────────────────────────────────
INACTIVITY_TIMEOUT = _env_int("INACTIVITY_TIMEOUT", 120) or 120
KEEP_ALIVE = _env_bool("KEEP_ALIVE", False) or bool(os.getenv("PORT")) or bool(os.getenv("RENDER"))
KEEP_ALIVE_PORT = _env_int("PORT", 8080) or 8080

# ── FFmpeg / yt-dlp playback ─────────────────────────────
FFMPEG_PATH = _env("FFMPEG_PATH")            # blank = "ffmpeg" on PATH
if not FFMPEG_PATH and not shutil.which("ffmpeg"):
    # Hosts without apt (bot-hosting.net etc.): use the FFmpeg binary bundled in the imageio-ffmpeg pip package.
    try:
        import imageio_ffmpeg

        FFMPEG_PATH = imageio_ffmpeg.get_ffmpeg_exe()
    except Exception:
        pass
YTDL_COOKIEFILE = _env("YTDL_COOKIEFILE")    # optional cookies.txt (YouTube bot checks / age-restricted)
if not YTDL_COOKIEFILE:
    for _candidate in (BASE_DIR / "cookies.txt", Path("cookies.txt"), Path("/home/container/cookies.txt")):
        if _candidate.is_file() and _candidate.stat().st_size > 0:
            YTDL_COOKIEFILE = str(_candidate.resolve())
            break

# ── Lavalink Node (Track & Metadata Resolver) ─────────────
LAVALINK_HOST = _env("LAVALINK_HOST")
if LAVALINK_HOST.startswith("http://"):
    LAVALINK_HOST = LAVALINK_HOST[7:]
elif LAVALINK_HOST.startswith("https://"):
    LAVALINK_HOST = LAVALINK_HOST[8:]
LAVALINK_HOST = LAVALINK_HOST.rstrip("/")
LAVALINK_PORT = _env_int("LAVALINK_PORT", 443) or 443
LAVALINK_PASSWORD = _env("LAVALINK_PASSWORD")
LAVALINK_SECURE = _env_bool("LAVALINK_SECURE", True)
YOUTUBE_REFRESH_TOKEN = _env("YOUTUBE_REFRESH_TOKEN")

# ── Optional Spotify fallback ────────────────────────────
SPOTIFY_CLIENT_ID = _env("SPOTIFY_CLIENT_ID")
SPOTIFY_CLIENT_SECRET = _env("SPOTIFY_CLIENT_SECRET")

# Profile Theme & Embed Color
def _get_color() -> int:
    val = _env('BOT_COLOR')
    if not val:
        return 0x8A2BE2
    try:
        if val.startswith('#'):
            return int(val[1:], 16)
        if val.startswith('0x'):
            return int(val, 16)
        return int(val)
    except ValueError:
        return 0x8A2BE2

BOT_COLOR = _get_color()
EMBED_COLOR = BOT_COLOR

# Dynamic Presence & Bio Rotation
STATUS_INTERVAL = _env_int('STATUS_ROTATION_INTERVAL', 30) or 30
BIO_INTERVAL = _env_int('BIO_ROTATION_INTERVAL', 600) or 600

# ── Server Join/Removal Notifications & Feedback ─────────
SUPPORT_URL = _env("SUPPORT_URL") or "https://discord.gg/"
REVIEW_URL = _env("REVIEW_URL") or "https://top.gg/bot/1560322217374388246"
INVITE_URL = _env("INVITE_URL")
ENABLE_JOIN_DM = _env_bool("ENABLE_JOIN_DM", True)
ENABLE_REMOVE_DM = _env_bool("ENABLE_REMOVE_DM", True)
ENABLE_FEEDBACK_DM = _env_bool("ENABLE_FEEDBACK_DM", True)
FEEDBACK_COOLDOWN = _env_int("FEEDBACK_COOLDOWN", 86400) or 86400

# ── Optional Proxy for Discord API (to bypass datacenter IP bans) ─
DISCORD_PROXY = _env("DISCORD_PROXY") or _env("HTTPS_PROXY") or _env("HTTP_PROXY")
