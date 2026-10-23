"""shizumusic main music cog: discord.py voice + yt-dlp + FFmpeg.

No Lavalink, no Wavelink. Same commands, replies, permissions, embeds and buttons as the old Lavalink cog;
only the playback engine underneath changed. This cog does not import the Remix cog: the "Remix" button
looks it up at click time (`bot.get_cog("Remix")`), so music works with or without it.

How it is put together
    * `MusicPlayer` is a `discord.VoiceClient` subclass (one per guild, created by
      `channel.connect(cls=MusicPlayer)`). The queue, current track, volume, loop / autoplay flags and
      the FFmpeg filter chain all live ON the player, so commands, buttons and the Remix cog
      read and write the very same state. `ctx.voice_client` IS the player.
    * Stream URLs are resolved lazily right before a track plays (queued links never go stale).
    * Playback position is counted from the PCM frames actually sent, so pause / seek / speed stay exact.

Requirements: `pip install -U "discord.py[voice]" yt-dlp` and FFmpeg on PATH (or FFMPEG_PATH in .env).
Optional .env: FFMPEG_PATH, YTDL_COOKIEFILE (cookies.txt for YouTube bot checks / age-restricted videos).
"""
from __future__ import annotations

import asyncio
import io
import logging
import os
import random
import re
import shlex
import shutil
import sys
import time
import urllib.parse
from collections import deque
from dataclasses import dataclass, field
from functools import partial
from pathlib import Path
from typing import Any, Optional

import aiohttp
import discord
import yt_dlp
from discord.ext import commands, tasks
from discord.ui import Button, View

from core import ShizuMusic
from utils import DescriptionEmbedPaginator, Paginator, config
from utils import button_emojis as BE
from utils import emojis as E
from utils.banner import player_effect_chips, render_banner
from utils.session import SESSION_GRACE, can_control, denied_text, refresh_owner_presence, start_session
from utils.Tools import blacklist_check, getConfig, ignore_check

log = logging.getLogger("shizumusic.music")

# ───────────────────────────── configuration ─────────────────────────────
MIN_VOLUME = 1
MAX_VOLUME = 300          # percent; above 100 is digital gain (clips on loud tracks)
DEFAULT_VOLUME = 100
MAX_QUEUE = 500
MAX_PLAYLIST = 100        # tracks imported from one playlist URL
HISTORY_SIZE = 10         # tracks remembered for the "previous" button
URL_REFRESH_AFTER = 45 * 60   # re-resolve stream URLs older than this (seconds)
EXTRACT_TIMEOUT = 45
FRAME_SECONDS = 0.02      # one discord.py PCM frame = 20 ms

FFMPEG_EXECUTABLE = config.FFMPEG_PATH or "ffmpeg"

_BASE_OPTS: dict[str, Any] = {
    "format": "bestaudio/best",
    "format_sort": ["abr", "asr", "acodec:opus"],   # highest bitrate / sample rate first
    "quiet": True,
    "no_warnings": True,
    "skip_download": True,
    "socket_timeout": 15,
    "retries": 3,
    "geo_bypass": True,
    "source_address": "0.0.0.0",   # IPv4 only: YouTube often blocks IPv6 ranges
    "http_headers": {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/130.0.0.0 Safari/537.36",
        "Accept": "*/*",
        "Accept-Language": "en-US,en;q=0.9",
    },
}
if config.YTDL_COOKIEFILE:
    _BASE_OPTS["cookiefile"] = config.YTDL_COOKIEFILE
# YouTube's player needs a JavaScript runtime (Node / Deno) for yt-dlp to solve its challenges.
_JS_RUNTIMES = {name: {} for name in ("deno", "node", "bun") if shutil.which(name)}
if _JS_RUNTIMES:
    _BASE_OPTS["js_runtimes"] = _JS_RUNTIMES
    _BASE_OPTS["remote_components"] = ["ejs:github"]   # lets yt-dlp fetch its challenge-solver script

# Bot-check bypass WITHOUT cookies: when YouTube refuses one "player client", try the next one.
# The first one that works is remembered and tried first next time.
CLIENT_LADDER: list[Optional[list[str]]] = [
    None,                           # yt-dlp's own default clients (uses cookies if available)
    ["android"],                    # Android client: highest success rate on datacenter IPs without cookies
    ["android_vr"],
    ["tv_embedded"],
    ["web_embedded"],
    ["tv", "web_safari"],
    ["ios"],
    ["mweb"],
]
_client_start = 0

# Full extraction of one video / the first search hit (gives a stream URL).
SINGLE_OPTS: dict[str, Any] = {**_BASE_OPTS, "noplaylist": True}
# Fast "flat" extraction for playlists and search result lists (no stream URLs yet).
FLAT_OPTS: dict[str, Any] = {
    **_BASE_OPTS,
    "noplaylist": False,
    "extract_flat": "in_playlist",
    "playlistend": MAX_PLAYLIST,
}


# ───────────────────────────── errors ─────────────────────────────
class MusicError(Exception):
    """A problem worth showing to the user as-is (core Errors cog reads `user_message`)."""

    @property
    def user_message(self) -> str:
        return str(self)


# ───────────────────────────── helpers ─────────────────────────────
def format_duration(ms: int) -> str:
    seconds = max(int(ms // 1000), 0)
    hours, rest = divmod(seconds, 3600)
    minutes, secs = divmod(rest, 60)
    return f"{hours}:{minutes:02}:{secs:02}" if hours else f"{minutes:02}:{secs:02}"


def shorten(text: str, limit: int) -> str:
    text = text or ""
    return text if len(text) <= limit else text[: limit - 1].rstrip() + "…"


def md_link(title: str, uri: Optional[str], limit: int = 80) -> str:
    clean = shorten(title, limit).replace("[", "(").replace("]", ")")
    return f"[{clean}]({uri})" if uri else clean


def embed_of(text: str, color: Optional[int] = None) -> discord.Embed:
    if color is None or color == 0x000000:
        color = config.EMBED_COLOR
    return discord.Embed(description=text, color=color)


def track_duration(track: "Track") -> str:
    if track.is_stream:
        return "LIVE"
    return format_duration(track.length) if track.length > 0 else "??:??"


def source_info(track: "Track") -> tuple[str, int, str]:
    """(display name, embed colour, emoji) for the track's source."""
    source = (track.source or "").lower()
    if "spotify" in source:
        return "Spotify", 0x1DB954, E.SPOTIFY
    if "saavn" in source:
        return "JioSaavn", 0x00E6A7, E.JIOSAAVN
    if "youtube" in source:
        return "YouTube", 0xFF0000, E.YOUTUBE
    if "soundcloud" in source:
        return "SoundCloud", 0xFF5500, E.SOUNDCLOUD
    return (source.title() or "Unknown"), 0xFF5500, ""


def create_progress_bar(completed: float, total: float, length: int = 10) -> str:
    ratio = 0.0 if total <= 0 else min(max(completed / total, 0.0), 1.0)
    filled = int(length * ratio)
    return "█" * filled + "░" * (length - filled)


def clean_song_name(title: Optional[str]) -> str:
    """Extract a simple, clean song name without artist, actors, movie names, or video noise."""
    if not title:
        return "Music"
    # 1. Take first part before pipe, bullet, or slash
    t = re.split(r"\s*[|•]\s*", title)[0].strip()

    # Helper to strip bracketed noise
    noise_pattern = (
        r"[\(\[\{]\s*(?:official\s*(?:music\s*)?video|official\s*audio|lyrics?|lyric\s*video|"
        r"audio|video|visualizer|full\s*(?:video\s*)?song|video\s*song|4k|hd|remastered|"
        r"extended|feat\.?.*?|ft\.?.*?|prod\.?.*?|from\s+.*?|from\s*[\"'].*?[\"']|"
        r"music\s*video|official\s*video\s*remastered)\s*[\)\]\}]"
    )
    t = re.sub(noise_pattern, "", t, flags=re.IGNORECASE).strip()

    # 2. Strip 'ft.' or 'feat.' or 'featuring' at end
    t = re.sub(r"\s+(?:feat|ft|featuring)\.?\s+.*$", "", t, flags=re.IGNORECASE).strip()

    # 3. Handle 'Artist - Song' or 'Song - Artist' or 'Song - Tag'
    dash_split = re.split(r"\s+[-–—]\s+", t)
    if len(dash_split) == 2:
        p1, p2 = dash_split[0].strip(), dash_split[1].strip()
        p2_clean = re.sub(noise_pattern, "", p2, flags=re.IGNORECASE).strip()
        if re.search(r"^(?:video\s*song|full\s*song|audio|video|lyrics?|music)$", p2_clean, re.IGNORECASE):
            t = p1
        elif re.search(r"^(?:video\s*song|full\s*song|audio|video|lyrics?|music)$", p1, re.IGNORECASE):
            t = p2_clean
        else:
            t = p2_clean if len(p2_clean) >= 2 else p1
    elif len(dash_split) > 2:
        t = dash_split[-1].strip() or dash_split[0].strip()

    t = re.sub(noise_pattern, "", t, flags=re.IGNORECASE).strip()
    t = re.sub(r"[\"'\u201c\u201d]", "", t).strip(" -–—:;,")
    return t or title


async def set_vc_status(channel: Optional[discord.abc.GuildChannel], text: Optional[str]) -> None:
    """Set (or clear) the voice-channel status. Silently ignored if the bot lacks permission."""
    if channel is None:
        return
    try:
        await channel.edit(status=shorten(text, 500) if text else None)
    except (discord.HTTPException, TypeError):
        pass


def _is_url(text: str) -> bool:
    return bool(re.match(r"^https?://", text, re.IGNORECASE))


def _looks_like_playlist(url: str) -> bool:
    u = url.lower()
    if "list=" in u and "v=" not in u and "youtu.be/" not in u:
        return True
    return any(hint in u for hint in ("/playlist", "/sets/", "/album/", "/albums/"))


def _friendly_error(exc: Exception) -> str:
    text = str(exc).lower()
    if "sign in to confirm" in text or "not a bot" in text:
        return "YouTube blocked that request (bot check). Try again in a moment or use a different song."
    if "private video" in text:
        return "That video is private."
    if "age" in text and ("restrict" in text or "verify" in text or "confirm" in text):
        return "That video is age-restricted and I can't play it."
    if "not available in your country" in text or ("geo" in text and "restrict" in text):
        return "That video isn't available in my region."
    if "unsupported url" in text:
        return "I don't support that link. Try a YouTube/SoundCloud URL or a search phrase."
    if "premieres in" in text or "live event will begin" in text:
        return "That stream hasn't started yet."
    if "video unavailable" in text or "has been removed" in text or "no longer available" in text:
        return "That video is unavailable."
    return "I couldn't find or load that track. Try another URL or search phrase."


# ───────────────────────────── tracks & yt-dlp ─────────────────────────────
@dataclass(eq=False)
class Track:
    title: str
    author: str = ""
    uri: Optional[str] = None          # page URL shown in embeds
    length: int = 0                    # milliseconds, 0 = unknown
    artwork: Optional[str] = None
    is_stream: bool = False
    source: str = ""                   # "youtube", "soundcloud", "spotify"...
    query: Optional[str] = None        # search phrase for tracks that still need a URL (Spotify imports)
    stream_url: Optional[str] = None   # direct audio URL, filled in lazily
    resolved_at: float = 0.0
    recommended: bool = False          # picked by autoplay
    retries: int = 0
    http_headers: dict[str, str] = field(default_factory=dict)

    @property
    def is_seekable(self) -> bool:
        return not self.is_stream and self.length > 0

    @property
    def stale(self) -> bool:
        return not self.stream_url or (time.monotonic() - self.resolved_at) > URL_REFRESH_AFTER

    def apply_info(self, data: dict) -> None:
        """Update from a full yt-dlp info dict (also refreshes the stream URL)."""
        url = data.get("url")
        if not url:
            raise MusicError("That result did not provide a playable audio stream.")
        self.stream_url = url
        self.is_stream = bool(data.get("is_live"))
        duration = data.get("duration")
        self.length = 0 if self.is_stream else int(float(duration) * 1000) if duration else self.length
        self.title = data.get("title") or self.title
        self.author = data.get("uploader") or data.get("channel") or data.get("artist") or self.author
        self.artwork = data.get("thumbnail") or self.artwork
        self.uri = data.get("webpage_url") or data.get("original_url") or self.uri
        self.source = (data.get("extractor_key") or data.get("extractor") or self.source or "").lower()
        self.resolved_at = time.monotonic()
        headers = data.get("http_headers")
        if not headers:
            for f in (data.get("requested_formats") or []) + (data.get("formats") or []):
                if isinstance(f, dict) and f.get("http_headers"):
                    if f.get("url") == url:
                        headers = f.get("http_headers")
                        break
                    if not headers:
                        headers = f.get("http_headers")
        self.http_headers = dict(headers) if headers else {}


def _first_entry(data: Any) -> dict:
    if not data:
        raise MusicError("No track was found.")
    if "entries" in data:
        data = next((e for e in (data["entries"] or []) if e), None)
        if not data:
            raise MusicError("No playable result was found.")
    return data


def track_from_info(data: Any) -> Track:
    data = _first_entry(data)
    track = Track(title=data.get("title") or "Unknown title")
    track.apply_info(data)
    if not track.uri:
        raise MusicError("That result has no usable link.")
    return track


def track_from_entry(entry: dict) -> Optional[Track]:
    """Build an unresolved Track from a flat playlist / search entry."""
    title = entry.get("title") or "Unknown title"
    if title in ("[Private video]", "[Deleted video]"):
        return None
    url = entry.get("webpage_url") or entry.get("url")
    ie_key = str(entry.get("ie_key") or "").lower()
    if (not url or not _is_url(url)) and entry.get("id") and ie_key == "youtube":
        url = f"https://www.youtube.com/watch?v={entry['id']}"
    if not url or not _is_url(url):
        return None
    artwork = entry.get("thumbnail")
    if not artwork and isinstance(entry.get("thumbnails"), list) and entry["thumbnails"]:
        artwork = entry["thumbnails"][-1].get("url")
    live = bool(entry.get("is_live")) or entry.get("live_status") == "is_live"
    duration = entry.get("duration")
    return Track(
        title=title,
        author=entry.get("uploader") or entry.get("channel") or "",
        uri=url,
        length=0 if live or not duration else int(float(duration) * 1000),
        artwork=artwork,
        is_stream=live,
        source=ie_key or ("youtube" if "youtu" in url else ""),
    )


_extract_sem = asyncio.Semaphore(3)


_BLOCK_HINTS = ("sign in", "not a bot", "po token", "requested format is not available", "http error 403",
                "forbidden", "confirm your age", "player response", "unable to extract", "no video formats")


async def ytdl_extract(query: str, opts: dict[str, Any]) -> Any:
    """yt-dlp extraction with automatic YouTube client fallback (no cookies required)."""
    global _client_start

    cookie_path = config.YTDL_COOKIEFILE
    if not cookie_path or not os.path.isfile(cookie_path):
        for cand in (config.BASE_DIR / "cookies.txt", Path("cookies.txt"), Path("/home/container/cookies.txt")):
            if cand.is_file() and cand.stat().st_size > 0:
                cookie_path = str(cand.resolve())
                config.YTDL_COOKIEFILE = cookie_path
                _BASE_OPTS["cookiefile"] = cookie_path
                SINGLE_OPTS["cookiefile"] = cookie_path
                FLAT_OPTS["cookiefile"] = cookie_path
                log.info("Detected and loaded cookies from %s", cookie_path)
                break

    def run(options: dict[str, Any]) -> Any:
        with yt_dlp.YoutubeDL(options) as ydl:
            return ydl.extract_info(query, download=False)

    is_youtube = query.startswith(("ytsearch", "ytmsearch")) or "youtube.com" in query or "youtu.be" in query
    order = [(_client_start + i) % len(CLIENT_LADDER) for i in range(len(CLIENT_LADDER))] if is_youtube else [0]
    last_exc: Optional[Exception] = None
    async with _extract_sem:
        for idx in order:
            clients = CLIENT_LADDER[idx]
            options = dict(opts)
            if config.YTDL_COOKIEFILE and os.path.isfile(config.YTDL_COOKIEFILE):
                options["cookiefile"] = config.YTDL_COOKIEFILE
            if clients:
                options["extractor_args"] = {"youtube": {"player_client": clients}}
            try:
                data = await asyncio.wait_for(asyncio.to_thread(run, options), EXTRACT_TIMEOUT)
            except asyncio.TimeoutError:
                raise MusicError("Looking that up took too long. Try again in a moment.") from None
            except MusicError:
                raise
            except Exception as exc:
                last_exc = exc
                if is_youtube and any(h in str(exc).lower() for h in _BLOCK_HINTS):
                    log.info("YouTube client %s refused %r (%s); trying the next one", clients or "default", query, exc)
                    continue
                log.warning("yt-dlp failed for %r: %s", query, exc)
                raise MusicError(_friendly_error(exc)) from exc
            if is_youtube and idx != _client_start:
                log.info("YouTube client %s works now; using it first", clients or "default")
                _client_start = idx
            return data
    log.warning("yt-dlp failed for %r on every client: %s", query, last_exc)
    raise MusicError(_friendly_error(last_exc) if last_exc else "I couldn't load that track.")


async def resolve_track(track: Track) -> None:
    """(Re)fetch a fresh stream URL for a track (by link, or by search phrase for Spotify imports)."""
    target = track.uri or (f"ytsearch1:{track.query}" if track.query else None)
    if not target:
        raise MusicError("That track has no link to play from.")
    try:
        track.apply_info(_first_entry(await ytdl_extract(target, SINGLE_OPTS)))
    except MusicError:
        # YouTube refused every client: play the same song from SoundCloud instead.
        phrase = track.query or f"{track.title} {track.author}".strip()
        log.info("Falling back to SoundCloud for %r", phrase)
        track.apply_info(_first_entry(await ytdl_extract(f"scsearch1:{phrase}", SINGLE_OPTS)))


def _track_from_lavalink_info(info: dict) -> Optional[Track]:
    if not info or not info.get("uri"):
        return None
    return Track(
        title=info.get("title") or "Unknown title",
        author=info.get("author") or "",
        uri=info.get("uri"),
        length=max(0, int(info.get("length") or 0)),
        artwork=info.get("artworkUrl"),
        is_stream=bool(info.get("isStream")),
        source=str(info.get("sourceName") or "youtube").lower(),
    )


async def lavalink_load_tracks(query: str, count: int = 10) -> Optional[tuple[Optional[str], list[Track]]]:
    """Resolve a query or link via the configured Lavalink node (which uses the YouTube OAuth refresh token)."""
    if not config.LAVALINK_HOST:
        return None
    scheme = "https" if config.LAVALINK_SECURE else "http"
    port = f":{config.LAVALINK_PORT}" if config.LAVALINK_PORT not in (80, 443) else ""
    ident = query if _is_url(query) else f"ytsearch:{query}"
    url = f"{scheme}://{config.LAVALINK_HOST}{port}/v4/loadtracks?identifier=" + urllib.parse.quote(ident)
    headers = {"Authorization": config.LAVALINK_PASSWORD}
    timeout = aiohttp.ClientTimeout(total=8)
    try:
        async with aiohttp.ClientSession(timeout=timeout) as session:
            async with session.get(url, headers=headers) as resp:
                if resp.status != 200:
                    return None
                data = await resp.json()
                load_type = data.get("loadType")
                if load_type == "search":
                    items = data.get("data", [])
                    tracks = [t for t in (_track_from_lavalink_info(it.get("info", {})) for it in items) if t]
                    return (None, tracks[:count]) if tracks else None
                elif load_type == "track":
                    item = data.get("data", {})
                    track = _track_from_lavalink_info(item.get("info", {}))
                    return (None, [track]) if track else None
                elif load_type == "playlist":
                    pdata = data.get("data", {})
                    pinfo = pdata.get("info", {})
                    name = pinfo.get("name") or "Playlist"
                    tracks = [t for t in (_track_from_lavalink_info(it.get("info", {})) for it in pdata.get("tracks", [])) if t]
                    return (name, tracks[:count]) if tracks else None
    except Exception as exc:
        log.debug("Lavalink resolution skipped (%s): %s", query, exc)
    return None


async def search_tracks(query: str, prefix: str = "ytsearch", count: int = 5) -> list[Track]:
    if prefix == "ytsearch" and config.LAVALINK_HOST:
        lava_res = await lavalink_load_tracks(query, count=count)
        if lava_res and lava_res[1]:
            return lava_res[1][:count]
    try:
        data = await ytdl_extract(f"{prefix}{count}:{query}", FLAT_OPTS)
    except MusicError:
        if prefix != "ytsearch":
            raise
        data = await ytdl_extract(f"scsearch{count}:{query}", FLAT_OPTS)  # YouTube blocked: use SoundCloud
    entries = [e for e in ((data or {}).get("entries") or []) if e]
    return [t for t in (track_from_entry(e) for e in entries) if t][:count]


async def load_tracks(query: str) -> tuple[Optional[str], list[Track]]:
    """User input -> (playlist name or None, tracks). Accepts a URL, a playlist URL or search text."""
    query = query.strip().strip("<>")
    if not query:
        raise MusicError("Give me a song name or a URL.")
    if config.LAVALINK_HOST:
        lava_res = await lavalink_load_tracks(query)
        if lava_res and lava_res[1]:
            return lava_res[0], lava_res[1]
    if _is_url(query):
        if _looks_like_playlist(query):
            data = await ytdl_extract(query, FLAT_OPTS)
            entries = [e for e in ((data or {}).get("entries") or []) if e]
            tracks = [t for t in (track_from_entry(e) for e in entries) if t]
            if not tracks:
                raise MusicError("That playlist is empty or unavailable.")
            return (data or {}).get("title") or "Playlist", tracks
        return None, [track_from_info(await ytdl_extract(query, SINGLE_OPTS))]
    try:
        return None, [track_from_info(await ytdl_extract(f"ytsearch1:{query}", SINGLE_OPTS))]
    except MusicError:
        return None, [track_from_info(await ytdl_extract(f"scsearch1:{query}", SINGLE_OPTS))]


GENERIC_WORDS = {
    "songs", "mix", "mashup", "playlist", "dj", "hits", "jukebox", "album", "albums", "latest", "top", "best",
    "nonstop", "non-stop", "collection", "remix", "remixes", "bgm", "folk", "melody", "melodies", "party", "vibes",
}
QUEUE_BATCH = 10          # songs queued for a generic search like "telugu dj songs"


def _norm_title(title: str) -> str:
    return re.sub(r"[^a-z0-9]+", "", re.sub(r"\(.*?\)|\[.*?\]", "", (title or "").lower()))


def is_generic_query(query: str) -> bool:
    words = set(re.findall(r"[\w-]+", query.lower()))
    return bool(words & GENERIC_WORDS)


async def smart_search(query: str, recent: set[str], taken: set[str]) -> list[Track]:
    """Plain-text search that never hands back the same song twice in a row.

    - "telugu dj songs" style (generic) queries: pull ~25 results, drop recent / duplicate titles,
      shuffle and queue QUEUE_BATCH different songs.
    - A specific song name: the best result that was not played recently (falls back to the top hit).
    """
    generic = is_generic_query(query)
    found = await search_tracks(query, "ytsearch", 25 if generic else 8)
    if not found:
        raise MusicError("No results found.")
    fresh, seen = [], set(taken)
    for track in found:
        key = _norm_title(track.title)
        if track.uri in recent or key in seen:
            continue
        seen.add(key)
        fresh.append(track)
    if generic:
        random.shuffle(fresh or found)
        picks = (fresh or found)[:QUEUE_BATCH]
        return picks
    return [(fresh or found)[0]]


async def find_recommendation(seed: Track, exclude: set[str]) -> Optional[Track]:
    """Autoplay: the next song YouTube would suggest after `seed` (its "mix" playlist)."""
    video_id = None
    match = re.search(r"(?:v=|youtu\.be/)([A-Za-z0-9_-]{11})", seed.uri or "")
    if match:
        video_id = match.group(1)
    if video_id:
        data = await ytdl_extract(f"https://www.youtube.com/watch?v={video_id}&list=RD{video_id}", FLAT_OPTS)
        candidates = [t for t in (track_from_entry(e) for e in ((data or {}).get("entries") or []) if e) if t]
    else:
        candidates = await search_tracks(f"{seed.title} {seed.author}".strip(), "ytsearch", 5)
    played = {_norm_title(seed.title)}
    fresh = [c for c in candidates if c.uri and c.uri not in exclude and _norm_title(c.title) not in played]
    if fresh:
        candidate = random.choice(fresh[:8])  # vary the pick instead of always taking the first suggestion
        candidate.recommended = True
        return candidate
    return None


# ───────────────────────────── audio source ─────────────────────────────
try:  # discord.py itself needs audioop (audioop-lts on Python 3.13+), so this normally succeeds
    import audioop

    def _scale(data: bytes, factor: float) -> bytes:
        return audioop.mul(data, 2, factor)  # saturates instead of wrapping

except ImportError:  # pragma: no cover - slow pure-Python fallback
    import array

    def _scale(data: bytes, factor: float) -> bytes:
        samples = array.array("h")
        samples.frombytes(data)
        if sys.byteorder == "big":
            samples.byteswap()
        out = array.array("h", (max(-32768, min(32767, int(s * factor))) for s in samples))
        if sys.byteorder == "big":
            out.byteswap()
        return out.tobytes()


class PlayerSource(discord.AudioSource):
    """FFmpeg PCM stream with live volume (up to 300%) and an exact frame counter."""

    def __init__(self, inner: discord.AudioSource, volume: float, speed: float = 1.0):
        self.inner = inner
        self.volume = volume
        self.speed = speed        # playback-speed multiplier of the FFmpeg filter chain (for position tracking)
        self.frames = 0

    def read(self) -> bytes:
        data = self.inner.read()
        if not data:
            return data
        self.frames += 1
        factor = self.volume
        return data if factor == 1.0 else _scale(data, factor)

    def cleanup(self) -> None:
        self.inner.cleanup()

    def is_opus(self) -> bool:
        return False


class TrackQueue(deque):
    @property
    def is_empty(self) -> bool:
        return not self

    def shuffle(self) -> None:
        items = list(self)
        random.shuffle(items)
        self.clear()
        self.extend(items)


# ───────────────────────────── the player ─────────────────────────────
class MusicPlayer(discord.VoiceClient):
    """Per-guild player: voice connection + queue + FFmpeg playback state.

    State that anything else (commands, buttons, the Remix cog) may read or write:
        queue, current, history, loop_mode, autoplay, volume (percent),
        audio_filters (FFmpeg `-af` chain, "" = none), speed (multiplier the chain applies),
        remix_state (the effect state, see utils/remix.py), ctx, session_owner_id.
    After changing `audio_filters` / `speed`, call `await player.reload_audio()`.
    """

    def __init__(self, client: discord.Client, channel: discord.abc.Connectable):
        super().__init__(client, channel)
        self.cog: Optional["Music"] = None
        self.ctx: Optional[commands.Context] = None
        self.queue: TrackQueue = TrackQueue()
        self.history: list[Track] = []
        self.current: Optional[Track] = None
        self.loop_mode: bool = False
        self.autoplay: bool = False
        self.volume: int = DEFAULT_VOLUME
        self.audio_filters: str = ""
        self.speed: float = 1.0
        self.remix_state = None                    # utils.remix.RemixState, created on first use (get_state)
        self.session_owner_id: Optional[int] = None
        self.transferred: bool = False
        self._handled_disconnect: bool = False
        self.owner_absent_since: Optional[float] = None
        self.stay: bool = False                          # 24/7 mode: never leave, keep playing via autoplay
        self.awaiting_owner: bool = False                # owner left an empty channel: waiting for Continue / Stop
        self.card: Optional["MusicControlView"] = None   # the one live now-playing card
        self.pending_note: Optional[str] = None          # reply that goes on the NEXT card (skip, first play)
        self.play_lock = asyncio.Lock()
        self._gen = 0                              # bumped on every (re)start / stop; stale callbacks are ignored
        self._audio: Optional[PlayerSource] = None
        self._offset = 0.0                         # track position (s) the current source started from

    # ── state ───────────────────────────────────────────
    @property
    def playing(self) -> bool:
        """True while a track is loaded (paused counts, like the old player)."""
        return self.current is not None and self.is_connected()

    @property
    def paused(self) -> bool:
        return self.is_paused()

    @property
    def position(self) -> int:
        """Position in the current track, in milliseconds."""
        if self._audio is None:
            return 0
        seconds = self._offset + self._audio.frames * FRAME_SECONDS * self._audio.speed
        if self.current is not None and self.current.length:
            seconds = min(seconds, self.current.length / 1000)
        return int(seconds * 1000)

    def set_volume(self, level: int) -> None:
        self.volume = max(MIN_VOLUME, min(MAX_VOLUME, int(level)))
        if self._audio is not None:
            self._audio.volume = self.volume / 100

    # ── FFmpeg ──────────────────────────────────────────
    def _make_source(self, track: Track, start: float) -> PlayerSource:
        if not shutil.which(FFMPEG_EXECUTABLE):
            raise MusicError("FFmpeg is not installed or is not on PATH. Install it or set FFMPEG_PATH in .env.")
        before = "-nostdin -reconnect 1 -reconnect_streamed 1 -reconnect_delay_max 5 -probesize 1M -analyzeduration 1M"
        if start > 0 and track.is_seekable:
            before += f" -ss {start:.2f}"
        if track.http_headers:
            header_lines = "".join(f"{k}: {v}\r\n" for k, v in track.http_headers.items() if k and v)
            if header_lines:
                before += f" -headers {shlex.quote(header_lines)}"
        else:
            default_ua = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/130.0.0.0 Safari/537.36"
            before += f" -user_agent {shlex.quote(default_ua)}"
        options = "-vn -bufsize 512k"   # discord.py automatically passes -f s16le -ar 48000 -ac 2
        if self.audio_filters:
            options += f' -af "{self.audio_filters}"'
        inner = discord.FFmpegPCMAudio(
            track.stream_url, executable=FFMPEG_EXECUTABLE, before_options=before, options=options
        )
        return PlayerSource(inner, self.volume / 100, self.speed)

    async def _start(self, track: Track, *, start: float = 0.0, announce: bool = True) -> bool:
        """Resolve + play `track`. Call with play_lock held.

        False only when this track failed (caller should move on); True when it started,
        or when playback was superseded / disconnected meanwhile.
        """
        if not self.is_connected():
            self.current = None
            return True
        self._gen += 1
        gen = self._gen
        if self.is_playing() or self.is_paused():
            self.stop()  # its `after` callback is ignored (generation changed)
        self.current = track
        try:
            if track.stale:
                await resolve_track(track)
            source = await asyncio.to_thread(self._make_source, track, start)
        except Exception as exc:
            if isinstance(exc, MusicError):
                reason = str(exc)
            else:
                log.exception("Could not prepare %r", track.title)
                reason = "unexpected error (see console)"
            self._track_failed(track, reason)
            return False
        if gen != self._gen or not self.is_connected():
            source.cleanup()  # stopped / replaced while we were resolving
            return True

        self._audio = source
        self._offset = start

        def after(error: Optional[Exception]) -> None:
            try:
                asyncio.run_coroutine_threadsafe(self._after(gen, error), self.loop)
            except RuntimeError:
                pass

        try:
            # Encode at the channel's full bitrate (max 510 kbps) in full-band music mode, like Spotify-grade audio.
            bitrate = max(64, min(510, (getattr(self.channel, "bitrate", 96000) or 96000) // 1000))
            self.play(
                source, after=after,
                application="audio", bitrate=bitrate, fec=True, expected_packet_loss=0.05,
                bandwidth="full", signal_type="music",
            )
        except Exception:
            source.cleanup()
            log.exception("VoiceClient.play failed")
            self._track_failed(track, "I couldn't start the audio stream.")
            return False

        if not self.history or self.history[-1] is not track:
            self.history.append(track)
            if len(self.history) > HISTORY_SIZE:
                self.history.pop(0)
        if announce and self.cog is not None:
            self.cog.spawn(self.cog.on_track_start(self, track))
        return True

    def _track_failed(self, track: Track, reason: str) -> None:
        log.warning("Track failed to play: %s (%s)", track.title, reason)
        if self.cog is not None:
            self.cog.spawn(self.cog.on_track_failed(self, track, reason))

    async def _pick_next(self, skipped: bool, failed: bool) -> tuple[Optional[Track], bool]:
        """(next track, is_repeat)."""
        current = self.current
        if current is not None and not failed and self.loop_mode and not skipped:
            return current, True
        if self.queue:
            return self.queue.popleft(), False
        if (self.autoplay or self.stay) and current is not None:  # 24/7 mode always autoplays
            try:
                seen = {t.uri for t in self.history if t.uri}
                if self.cog is not None:
                    seen |= set(self.cog.recent.get(self.guild.id, ()))  # never repeat recently played songs
                return await find_recommendation(current, seen), False
            except Exception:
                log.warning("Autoplay could not find a track", exc_info=True)
        return None, False

    async def _advance(self, *, skipped: bool = False, failed: bool = False) -> None:
        """Move on to the next track (loop / queue / autoplay), skipping ones that fail. Needs play_lock."""
        while True:
            track, repeat = await self._pick_next(skipped, failed)
            if track is None:
                self._gen += 1
                if self.is_playing() or self.is_paused():
                    self.stop()
                self.current = None
                self._audio = None
                if self.cog is not None:
                    await self.cog.finish_playback(self)
                return
            if repeat:
                track.retries = 0
            if await self._start(track, announce=not repeat):
                return
            skipped = failed = True

    async def _after(self, gen: int, error: Optional[Exception]) -> None:
        """Called (on the loop) when FFmpeg stops sending audio."""
        try:
            if gen != self._gen or not self.is_connected():
                return
            if error:
                log.error("Voice playback error in guild %s: %s", self.guild.id, error)
            async with self.play_lock:
                if gen != self._gen:
                    return
                track, audio = self.current, self._audio
                if track is not None and audio is not None:
                    played = audio.frames * FRAME_SECONDS
                    remaining = (track.length / 1000 - self._offset) if track.length else 999
                    if played < 3 and remaining > 10:
                        # Stream died instantly (expired URL / network blip).
                        if track.retries < 1:
                            track.retries += 1
                            track.stream_url = None
                            log.info("Stream for %r ended early; retrying with a fresh URL", track.title)
                            if not await self._start(track, start=self._offset, announce=False):
                                await self._advance(skipped=True, failed=True)
                            return
                        track.retries = 0
                        self._track_failed(track, "the stream keeps stopping")
                        await self._advance(skipped=True, failed=True)
                        return
                    track.retries = 0
                await self._advance()
        except Exception:
            log.exception("after-track handler failed")

    # ── public controls ─────────────────────────────────
    async def enqueue(self, tracks: list[Track], *, front: bool = False) -> bool:
        """Add tracks; start playing if idle. Returns True if playback was started by this call."""
        async with self.play_lock:
            room = MAX_QUEUE - len(self.queue)
            if room <= 0:
                raise MusicError(f"The queue is full ({MAX_QUEUE} tracks).")
            tracks = tracks[:room]
            if front:
                self.queue.extendleft(reversed(tracks))
            else:
                self.queue.extend(tracks)
            if self.current is None:
                await self._advance()
                return True
        return False

    async def skip(self) -> None:
        async with self.play_lock:
            await self._advance(skipped=True)

    async def previous(self) -> Optional[Track]:
        async with self.play_lock:
            if len(self.history) <= 1:
                return None
            self.history.pop()
            track = self.history[-1]
            if not await self._start(track):
                await self._advance(skipped=True, failed=True)
            return track

    async def seek(self, milliseconds: int) -> None:
        """Restart the current track at `milliseconds` (keeps paused state)."""
        async with self.play_lock:
            track = self.current
            if track is None or not self.is_connected():
                return
            was_paused = self.is_paused()
            if not await self._start(track, start=max(milliseconds, 0) / 1000, announce=False):
                await self._advance(skipped=True, failed=True)
                return
            if was_paused and self.is_playing():
                self.pause()

    async def reload_audio(self) -> None:
        """Re-apply `volume`-independent settings (`audio_filters`, `speed`) at the current position."""
        if self.current is not None:
            await self.seek(self.position if self.current.is_seekable else 0)

    async def shutdown(self) -> None:
        """Stop everything and leave the voice channel."""
        if self.cog is not None:
            await self.cog.retire_card(self)
        if self.cog is not None:
            self.cog.end_session(self.guild.id)  # intentional end: no "disconnected by" notice
        self.pending_note = None
        self._gen += 1
        self.queue.clear()
        self.current = None
        self._audio = None
        try:
            await self.disconnect(force=True)
        except Exception:
            log.warning("Failed to disconnect cleanly", exc_info=True)


# ───────────────────────── optional Spotify fallback ─────────────────────────
class SpotifyAPI:
    """Resolves Spotify links to track names so they can be matched on YouTube.

    Only active when SPOTIFY_CLIENT_ID and SPOTIFY_CLIENT_SECRET are set in .env.
    """

    BASE_URL = "https://api.spotify.com/v1"
    TOKEN_URL = "https://accounts.spotify.com/api/token"
    LINK_RE = re.compile(r"https?://open\.spotify\.com/(?:intl-[a-z]+/)?(track|playlist|album)/([A-Za-z0-9]+)")

    def __init__(self, client_id: str, client_secret: str, session_getter):
        self.client_id = client_id
        self.client_secret = client_secret
        self._session_getter = session_getter
        self._token: Optional[str] = None
        self._expires = 0.0

    @property
    def enabled(self) -> bool:
        return bool(self.client_id and self.client_secret)

    def parse(self, link: str) -> Optional[tuple[str, str]]:
        match = self.LINK_RE.match(link)
        return (match.group(1), match.group(2)) if match else None

    async def _ensure_token(self, force: bool = False) -> None:
        if not force and self._token and time.monotonic() < self._expires:
            return
        auth = aiohttp.BasicAuth(self.client_id, self.client_secret)
        async with self._session_getter().post(
            self.TOKEN_URL, auth=auth, data={"grant_type": "client_credentials"}
        ) as resp:
            if resp.status != 200:
                raise RuntimeError(f"Spotify token request failed ({resp.status})")
            payload = await resp.json()
        self._token = payload["access_token"]
        self._expires = time.monotonic() + int(payload.get("expires_in", 3600)) - 30

    async def get(self, endpoint: str, params: Optional[dict] = None) -> dict:
        for attempt in range(2):
            await self._ensure_token(force=attempt > 0)
            headers = {"Authorization": f"Bearer {self._token}"}
            async with self._session_getter().get(f"{self.BASE_URL}/{endpoint}", headers=headers, params=params) as resp:
                if resp.status == 401 and attempt == 0:
                    continue
                if resp.status != 200:
                    raise RuntimeError(f"Spotify API returned {resp.status}")
                return await resp.json()
        raise RuntimeError("Spotify request failed")


# ───────────────────────────── views ─────────────────────────────
class PlatformSelectView(View):
    # yt-dlp has no JioSaavn *search* (JioSaavn links still play); YouTube and SoundCloud search work.
    PLATFORMS = [
        ("YouTube", "ytsearch", discord.ButtonStyle.red),
        ("SoundCloud", "scsearch", discord.ButtonStyle.grey),
    ]

    def __init__(self, cog: "Music", ctx: commands.Context, query: str):
        super().__init__(timeout=60)
        self.cog = cog
        self.ctx = ctx
        self.query = query
        for name, source, style in self.PLATFORMS:
            button = Button(label=name, style=style)
            button.callback = self._make_callback(name, source)
            self.add_item(button)

    def _make_callback(self, name: str, source: str):
        async def callback(interaction: discord.Interaction):
            if interaction.user != self.ctx.author:
                await interaction.response.send_message("Only the command author can select a platform.", ephemeral=True)
                return
            await interaction.response.edit_message(content=f"Searching on {name}...", embed=None, view=None)
            await self.perform_search(name, source)
            try:
                await interaction.delete_original_response()
            except discord.HTTPException:
                pass

        return callback

    async def perform_search(self, name: str, source: str) -> None:
        try:
            results = await search_tracks(self.query, source, 5)
        except MusicError as exc:
            await self.ctx.send(embed=embed_of(f"{E.WARNING} {exc}", 0xFF0000))
            return
        except Exception:
            log.warning("Search on %s failed", name, exc_info=True)
            await self.ctx.send(embed=embed_of(f"Couldn't search {name} right now.", 0xFF0000))
            return

        if not results:
            await self.ctx.send(embed=embed_of("No results found.", 0xFF0000))
            return

        embed = discord.Embed(title=shorten(f"Top {len(results)} Results for '{self.query}' ({name})", 256), color=0x1DB954)
        for i, track in enumerate(results, start=1):
            link = f" | [Link]({track.uri})" if track.uri else ""
            embed.add_field(
                name=f"{i}. {shorten(track.title, 240)}",
                value=f"Duration: {track_duration(track)}{link}",
                inline=False,
            )
        await self.ctx.send(embed=embed, view=SearchResultView(self.cog, self.ctx, results))


class SearchResultView(View):
    def __init__(self, cog: "Music", ctx: commands.Context, results: list[Track]):
        super().__init__(timeout=60)
        self.cog = cog
        self.ctx = ctx
        self.results = results
        for i in range(len(results)):
            button = Button(label=str(i + 1), style=discord.ButtonStyle.primary)
            button.callback = self._make_callback(i)
            self.add_item(button)

    def _make_callback(self, index: int):
        async def callback(interaction: discord.Interaction):
            if interaction.user != self.ctx.author:
                await interaction.response.send_message("Only the command author can select a track.", ephemeral=True)
                return

            await interaction.response.defer()
            vc = await self.cog.ensure_player(self.ctx)
            if vc is None:
                return

            track = self.results[index]
            try:
                started = await vc.enqueue([track])
            except MusicError as exc:
                await interaction.followup.send(f"{E.WARNING} {exc}")
                return
            if started:
                await interaction.followup.send(f"Started playing `{track.title}`.")
            else:
                await interaction.followup.send(f"Added `{track.title}` to the queue.")

        return callback


def format_session_users(
    player_or_owner_id: Any,
    trigger_user: discord.abc.User,
    guild: Optional[discord.Guild] = None,
) -> tuple[str, str, bool]:
    """Return (owner_text, trigger_text, is_owner) formatted with <@id> and **display_name**."""
    if isinstance(player_or_owner_id, int):
        owner_id = player_or_owner_id
    elif player_or_owner_id is None:
        owner_id = None
    else:
        owner_id = getattr(player_or_owner_id, "session_owner_id", None)

    owner_member = guild.get_member(owner_id) if (guild and owner_id) else None
    owner_text = f"{owner_member.mention} (**{owner_member.display_name}**)" if owner_member else (f"<@{owner_id}>" if owner_id else "Session Author")
    trigger_text = f"{trigger_user.mention} (**{trigger_user.display_name}**)"
    is_owner = bool(owner_id and trigger_user.id == owner_id)
    return owner_text, trigger_text, is_owner


class _PlayerView(View):
    """Base of the player card and the private Others panel: same player, same checks."""

    def __init__(self, player: MusicPlayer, *, timeout: float):
        super().__init__(timeout=timeout)
        self.player = player

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        vc = interaction.guild.voice_client if interaction.guild else None
        if vc is None or vc is not self.player or not self.player.playing:
            await interaction.response.send_message("I'm not currently playing this anymore.", ephemeral=True)
            return False

        voice = getattr(interaction.user, "voice", None)
        if not (voice and voice.channel and voice.channel.id == vc.channel.id):
            await interaction.response.send_message(
                embed=embed_of("Only members in the same voice channel as me can control the player."),
                ephemeral=True,
            )
            return False

        if not can_control(vc, interaction.user.id):
            await interaction.response.send_message(embed=embed_of(denied_text(vc), 0xFF0000), ephemeral=True)
            return False
        return True

    async def say(self, text: str) -> None:
        """The reply to a button press goes INTO the player card (no extra message in the channel)."""
        card = self.player.card
        if card is not None:
            await card.update(text)


class MusicControlView(_PlayerView):
    """The player card: only four buttons, so the channel stays clean on every song.

        Auto | Pause/Play | Next | Others

    Everything else (previous, stop, seek, replay, shuffle, loop, the remix effects) is in the private
    "Others" panel that only the person who pressed the button sees. Emoji come from utils/button_emojis.py.
    """

    def __init__(self, player: MusicPlayer):
        super().__init__(player, timeout=7200)
        self.message: Optional[discord.Message] = None
        self.embed: Optional[discord.Embed] = None  # set when the card is posted; replies are written into it
        self.sync()

    def sync(self) -> None:
        """grey = off, green = on; Pause <-> Play follows the player."""
        paused = self.player.paused
        self.pause_button.label = "Play" if paused else "Pause"
        self.pause_button.emoji = BE.get("resume" if paused else "pause")
        self.pause_button.style = discord.ButtonStyle.success if paused else discord.ButtonStyle.primary
        self.autoplay_button.style = discord.ButtonStyle.success if (self.player.autoplay or self.player.stay) else discord.ButtonStyle.secondary
        self.autoplay_button.emoji = BE.get("autoplay")
        self.skip_button.emoji = BE.get("skip")
        self.others_button.emoji = BE.get("others")

    def refresh(self, text: Optional[str] = None) -> dict:
        """Edit arguments for the card: `text` becomes the reply line of the embed, buttons follow the player."""
        self.sync()
        if self.embed is None:
            return {"view": self}
        if text:
            self.embed.description = text
        return {"embed": self.embed, "view": self}

    async def update(self, text: Optional[str] = None) -> None:
        """Edit the card message in place (reply + poster + buttons stay ONE message)."""
        if self.message is None:
            return
        try:
            await self.message.edit(**self.refresh(text))
        except discord.HTTPException:
            pass

    async def on_timeout(self) -> None:
        if self.message:
            try:
                await self.message.edit(view=None)
            except discord.HTTPException:
                pass

    @discord.ui.button(label="Auto", style=discord.ButtonStyle.secondary, row=0)
    async def autoplay_button(self, interaction: discord.Interaction, button: Button):
        if self.player.stay:
            await interaction.response.send_message(
                embed=embed_of(f"{E.WARNING} Autoplay is locked on while 24/7 mode is enabled.", 0xFF0000), ephemeral=True
            )
            return
        self.player.autoplay = not self.player.autoplay
        state = "enabled" if self.player.autoplay else "disabled"
        owner_text, trigger_text, is_owner = format_session_users(self.player, interaction.user, interaction.guild)
        if is_owner:
            msg = f"{E.TICK} Autoplay {state} by session author {trigger_text}."
        else:
            msg = f"{E.TICK} Autoplay {state} by {trigger_text} (Session Author: {owner_text})."
        await interaction.response.edit_message(**self.refresh(msg))

    @discord.ui.button(label="Pause", style=discord.ButtonStyle.primary, row=0)
    async def pause_button(self, interaction: discord.Interaction, button: Button):
        title = self.player.current.title if self.player.current else "Unknown"
        owner_text, trigger_text, is_owner = format_session_users(self.player, interaction.user, interaction.guild)
        if self.player.paused:
            self.player.resume()
            await set_vc_status(self.player.channel, f"🎶 {clean_song_name(title)}")
            text = f"{E.BTN_RESUME} Resumed by session author {trigger_text}." if is_owner else f"{E.BTN_RESUME} Resumed by {trigger_text} (Session Author: {owner_text})."
        else:
            self.player.pause()
            await set_vc_status(self.player.channel, f"⏸️ {clean_song_name(title)}")
            text = f"{E.BTN_PAUSE} Paused by session author {trigger_text}." if is_owner else f"{E.BTN_PAUSE} Paused by {trigger_text} (Session Author: {owner_text})."
        await interaction.response.edit_message(**self.refresh(text))

    @discord.ui.button(label="Next", style=discord.ButtonStyle.secondary, row=0)
    async def skip_button(self, interaction: discord.Interaction, button: Button):
        if self.player.autoplay or not self.player.queue.is_empty:
            await interaction.response.defer()  # the reply goes on the next song's card, no extra message
            owner_text, trigger_text, is_owner = format_session_users(self.player, interaction.user, interaction.guild)
            self.player.pending_note = (
                f"{E.BTN_SKIP} Skipped by session author {trigger_text}."
                if is_owner
                else f"{E.BTN_SKIP} Skipped by {trigger_text} (Session Author: {owner_text})."
            )
            await self.player.skip()
        else:
            await interaction.response.send_message("No song in queue to skip.", ephemeral=True)

    @discord.ui.button(label="Others", style=discord.ButtonStyle.secondary, row=0)
    async def others_button(self, interaction: discord.Interaction, button: Button):
        await show_others(interaction, self.player)


EMBED_GREY = 0x2B2D31


class OthersPanel(_PlayerView):
    """Private panel (ephemeral, like the Remix console) with every button that is not on the card.

        Prev | -10s    | +10s   | Replay
        Shuffle | Loop  | Remix  | Stop

    "Remix" swaps this page for the Remix console (all effects) inside the same private message; that page
    has a Back button that returns here.
    """

    def __init__(self, player: MusicPlayer):
        super().__init__(player, timeout=600)
        self._interaction: Optional[discord.Interaction] = None
        for button, slot in (
            (self.previous_button, "previous"), (self.rewind_button, "rewind"), (self.forward_button, "forward"),
            (self.replay_button, "replay"), (self.shuffle_button, "shuffle"), (self.loop_button, "loop"),
            (self.remix_button, "remix"), (self.stop_button, "stop"),
        ):
            button.emoji = BE.get(slot)
        self.sync()

    def sync(self) -> None:
        self.loop_button.style = discord.ButtonStyle.success if self.player.loop_mode else discord.ButtonStyle.secondary
        self.stay_button.style = discord.ButtonStyle.success if self.player.stay else discord.ButtonStyle.secondary

    def embed(self) -> discord.Embed:
        player = self.player
        track = player.current
        now = md_link(track.title, track.uri, 60) if track else "Nothing"
        state = lambda on: "on" if on else "off"  # noqa: E731
        return discord.Embed(
            title="Player controls",
            description=(
                f"**Now playing:** {now}\n"
                f"Loop **{state(player.loop_mode)}** \u2022 Auto **{state(player.autoplay)}** \u2022 24/7 **{state(player.stay)}** \u2022 Queue **{len(player.queue)}**"
            ),
            color=EMBED_GREY,
        )

    async def on_timeout(self) -> None:
        for child in self.children:
            child.disabled = True
        try:
            if self._interaction is not None:
                await self._interaction.edit_original_response(view=self)
        except (discord.NotFound, discord.HTTPException):
            pass

    async def _seek(self, interaction: discord.Interaction, target, text: str) -> None:
        current = self.player.current
        if current is None or not current.is_seekable:
            await interaction.response.send_message("This track can't be seeked.", ephemeral=True)
            return
        await interaction.response.defer()
        await self.player.seek(target(current))
        await self.say(text)

    @discord.ui.button(label="Prev", style=discord.ButtonStyle.secondary, row=0)
    async def previous_button(self, interaction: discord.Interaction, button: Button):
        if len(self.player.history) <= 1:
            await interaction.response.send_message("No previous track available.", ephemeral=True)
            return
        await interaction.response.defer()  # the reply goes on the previous song's card
        owner_text, trigger_text, is_owner = format_session_users(self.player, interaction.user, interaction.guild)
        self.player.pending_note = (
            f"{E.BTN_PREVIOUS} Playing previous track by session author {trigger_text}."
            if is_owner
            else f"{E.BTN_PREVIOUS} Playing previous track by {trigger_text} (Session Author: {owner_text})."
        )
        if await self.player.previous() is None:
            self.player.pending_note = None
            await interaction.followup.send("No previous track available.", ephemeral=True)

    @discord.ui.button(label="24/7", emoji="\u267e\ufe0f", style=discord.ButtonStyle.secondary, row=2)
    async def stay_button(self, interaction: discord.Interaction, button: Button):
        player = self.player
        player.stay = not player.stay
        if player.stay:
            player.autoplay = True
        self.sync()
        await interaction.response.edit_message(embed=self.embed(), view=self)
        state = "enabled" if player.stay else "disabled"
        owner_text, trigger_text, is_owner = format_session_users(self.player, interaction.user, interaction.guild)
        text = (
            f"{E.TICK} 24/7 mode {state} by session author {trigger_text}."
            if is_owner
            else f"{E.TICK} 24/7 mode {state} by {trigger_text} (Session Author: {owner_text})."
        )
        await self.say(text)

    @discord.ui.button(label="\u221210s", style=discord.ButtonStyle.secondary, row=0)
    async def rewind_button(self, interaction: discord.Interaction, button: Button):
        owner_text, trigger_text, is_owner = format_session_users(self.player, interaction.user, interaction.guild)
        text = (
            f"{E.BTN_REWIND} Rewound 10 seconds by session author {trigger_text}."
            if is_owner
            else f"{E.BTN_REWIND} Rewound 10 seconds by {trigger_text} (Session Author: {owner_text})."
        )
        await self._seek(interaction, lambda track: max(self.player.position - 10000, 0), text)

    @discord.ui.button(label="+10s", style=discord.ButtonStyle.secondary, row=0)
    async def forward_button(self, interaction: discord.Interaction, button: Button):
        owner_text, trigger_text, is_owner = format_session_users(self.player, interaction.user, interaction.guild)
        text = (
            f"{E.BTN_FORWARD} Forwarded 10 seconds by session author {trigger_text}."
            if is_owner
            else f"{E.BTN_FORWARD} Forwarded 10 seconds by {trigger_text} (Session Author: {owner_text})."
        )
        await self._seek(interaction, lambda track: min(self.player.position + 10000, max(track.length - 1000, 0)), text)

    @discord.ui.button(label="Replay", style=discord.ButtonStyle.secondary, row=0)
    async def replay_button(self, interaction: discord.Interaction, button: Button):
        await interaction.response.defer()
        await self.player.seek(0)
        owner_text, trigger_text, is_owner = format_session_users(self.player, interaction.user, interaction.guild)
        text = (
            f"{E.BTN_REPLAY} Replaying current track by session author {trigger_text}."
            if is_owner
            else f"{E.BTN_REPLAY} Replaying current track by {trigger_text} (Session Author: {owner_text})."
        )
        await self.say(text)

    @discord.ui.button(label="Shuffle", style=discord.ButtonStyle.secondary, row=1)
    async def shuffle_button(self, interaction: discord.Interaction, button: Button):
        if self.player.queue.is_empty:
            await interaction.response.send_message("Queue is empty.", ephemeral=True)
            return
        self.player.queue.shuffle()
        await interaction.response.defer()
        owner_text, trigger_text, is_owner = format_session_users(self.player, interaction.user, interaction.guild)
        text = (
            f"{E.BTN_SHUFFLE} Queue shuffled by session author {trigger_text}."
            if is_owner
            else f"{E.BTN_SHUFFLE} Queue shuffled by {trigger_text} (Session Author: {owner_text})."
        )
        await self.say(text)

    @discord.ui.button(label="Loop", style=discord.ButtonStyle.secondary, row=1)
    async def loop_button(self, interaction: discord.Interaction, button: Button):
        self.player.loop_mode = not self.player.loop_mode
        self.sync()
        await interaction.response.edit_message(embed=self.embed(), view=self)
        state = "enabled" if self.player.loop_mode else "disabled"
        owner_text, trigger_text, is_owner = format_session_users(self.player, interaction.user, interaction.guild)
        text = (
            f"{E.BTN_LOOP} Loop {state} by session author {trigger_text}."
            if is_owner
            else f"{E.BTN_LOOP} Loop {state} by {trigger_text} (Session Author: {owner_text})."
        )
        await self.say(text)

    @discord.ui.button(label="Remix", style=discord.ButtonStyle.secondary, row=1)
    async def remix_button(self, interaction: discord.Interaction, button: Button):
        cog = interaction.client.get_cog("Remix")
        if cog is None:
            await interaction.response.send_message("The remix console isn't available right now.", ephemeral=True)
            return
        self.stop()  # this page is replaced; its timeout must not edit the console page
        await cog.open_panel(interaction, self.player, back=partial(show_others, player=self.player, edit=True), edit=True)

    @discord.ui.button(label="Stop", style=discord.ButtonStyle.danger, row=1)
    async def stop_button(self, interaction: discord.Interaction, button: Button):
        player, ctx = self.player, self.player.ctx
        await interaction.response.edit_message(content="Stopped and disconnected.", embed=None, view=None)
        self.stop()
        await set_vc_status(player.channel, None)
        player._handled_disconnect = True
        cog = interaction.client.get_cog("Music")
        if cog is not None:
            cog.forget_guild(interaction.guild.id)
        owner_id = player.session_owner_id
        await player.shutdown()  # also takes the buttons off the player card
        if ctx is not None:
            guild = ctx.guild
            owner_member = guild.get_member(owner_id) if (guild and owner_id) else None
            owner_text = f"{owner_member.mention} (**{owner_member.display_name}**)" if owner_member else (f"<@{owner_id}>" if owner_id else "Session Author")
            trigger_text = f"{interaction.user.mention} (**{interaction.user.display_name}**)"

            if owner_id and interaction.user.id == owner_id:
                desc = f"{E.BTN_STOP} Music session stopped and disconnected by session author {trigger_text}."
            else:
                desc = (
                    f"{E.BTN_STOP} **Music Session Stopped & Disconnected**\n\n"
                    f"• **Session Author:** {owner_text}\n"
                    f"• **Triggered by:** {trigger_text}"
                )
            embed = embed_of(desc, 0xFF0000)
            embed.set_author(name="Session Stopped", icon_url=interaction.client.user.display_avatar.url)
            embed.set_footer(text=f"Thanks for choosing {config.NAME}!")
            try:
                await ctx.channel.send(embed=embed, allowed_mentions=discord.AllowedMentions(users=True))
            except discord.HTTPException:
                pass


async def show_others(interaction: discord.Interaction, player: MusicPlayer, *, edit: bool = False) -> None:
    """Open the private Others panel (edit=True: swap it into the message the click came from)."""
    panel = OthersPanel(player)
    panel._interaction = interaction
    if edit:
        await interaction.response.edit_message(embed=panel.embed(), view=panel)
    else:
        await interaction.response.send_message(embed=panel.embed(), view=panel, ephemeral=True)


class ContinueView(View):
    """Yes / No prompt shown to the owner who left an otherwise empty voice channel."""

    def __init__(self, cog: "Music", player: MusicPlayer, owner_id: int):
        super().__init__(timeout=60)
        self.cog, self.player, self.owner_id = cog, player, owner_id
        self.message: Optional[discord.Message] = None

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if interaction.user.id != self.owner_id:
            await interaction.response.send_message(
                embed=embed_of(f"{E.WARNING} Only <@{self.owner_id}> can answer this.", 0xFF0000), ephemeral=True
            )
            return False
        return True

    @discord.ui.button(label="Yes", style=discord.ButtonStyle.success)
    async def yes(self, interaction: discord.Interaction, button: Button):
        player = self.player
        if not player.is_connected():
            await interaction.response.edit_message(content="The music session is already over.", embed=None, view=None)
            self.stop()
            return
        if self.owner_id not in player.channel.voice_states:
            await interaction.response.send_message(
                embed=embed_of(f"{E.WARNING} Join {player.channel.mention} first, then press **Yes**.", 0xFF0000),
                ephemeral=True,
            )
            return
        self.cog.resume_after_owner(player)
        self.stop()
        trigger_text = f"{interaction.user.mention} (**{interaction.user.display_name}**)"
        embed = embed_of(f"{E.TICK} Music session continued by session author {trigger_text}.", 0x1DB954)
        embed.set_author(name="Session Continued", icon_url=interaction.client.user.display_avatar.url)
        embed.set_footer(text=f"Thanks for choosing {config.NAME}!")
        await interaction.response.edit_message(
            content=None, embed=embed, view=None
        )

    @discord.ui.button(label="No", style=discord.ButtonStyle.danger)
    async def no(self, interaction: discord.Interaction, button: Button):
        self.stop()
        guild = interaction.guild
        owner_member = guild.get_member(self.owner_id) if (guild and self.owner_id) else None
        owner_text = f"{owner_member.mention} (**{owner_member.display_name}**)" if owner_member else f"<@{self.owner_id}>"
        trigger_text = f"{interaction.user.mention} (**{interaction.user.display_name}**)"
        if interaction.user.id == self.owner_id:
            desc = f"{E.BTN_STOP} Music session stopped by session author {trigger_text}."
        else:
            desc = (
                f"{E.BTN_STOP} **Music Session Stopped**\n\n"
                f"• **Session Author:** {owner_text}\n"
                f"• **Triggered by:** {trigger_text}"
            )
        embed = embed_of(desc, 0xFF0000)
        embed.set_author(name="Session Stopped", icon_url=interaction.client.user.display_avatar.url)
        embed.set_footer(text=f"Thanks for choosing {config.NAME}!")
        await interaction.response.edit_message(content=None, embed=embed, view=None)
        await self.cog.close_session(self.player)

    async def on_timeout(self) -> None:
        player = self.player
        if player.is_connected() and player.awaiting_owner:
            await self.cog.close_session(player)
            if self.message is not None:
                try:
                    await self.message.edit(
                        content=None,
                        embed=embed_of(f"{E.WARNING} No answer from <@{self.owner_id}>. Music session ended.", 0xFF0000),
                        view=None,
                    )
                except discord.HTTPException:
                    pass


class Music(commands.Cog):
    def __init__(self, client: ShizuMusic):
        self.client = client
        self._alone_since: dict[int, float] = {}
        # guild_id -> (owner_id, text_channel_id): live sessions, used for the "disconnected by" notice
        self._sessions: dict[int, tuple[int, int]] = {}
        # guild_id -> last played track links; survives stop / rejoin so searches don't repeat songs
        self.recent: dict[int, deque] = {}
        self._tasks: set[asyncio.Task] = set()
        self.spotify = SpotifyAPI(
            config.SPOTIFY_CLIENT_ID,
            config.SPOTIFY_CLIENT_SECRET,
            lambda: self.client.session,
        )

    async def cog_load(self) -> None:
        if not shutil.which(FFMPEG_EXECUTABLE):
            log.warning("FFmpeg was not found (%s). Playback will fail until it is installed.", FFMPEG_EXECUTABLE)
        self.idle_monitor.start()

    async def cog_unload(self) -> None:
        self.idle_monitor.cancel()
        for task in list(self._tasks):
            task.cancel()
        for vc in list(self.client.voice_clients):
            if isinstance(vc, MusicPlayer):
                await vc.shutdown()

    async def cog_check(self, ctx: commands.Context) -> bool:
        if ctx.guild is None:
            raise commands.NoPrivateMessage()
        return True

    # ── bookkeeping ─────────────────────────────────────
    def spawn(self, coro) -> None:
        """Run a coroutine in the background (keeps a reference so it isn't garbage collected)."""
        task = asyncio.create_task(coro)
        self._tasks.add(task)
        task.add_done_callback(self._tasks.discard)

    def forget_guild(self, guild_id: int) -> None:
        self._alone_since.pop(guild_id, None)
        self._sessions.pop(guild_id, None)

    def end_session(self, guild_id: int) -> None:
        self._sessions.pop(guild_id, None)

    # ── idle / alone-in-channel monitor ─────────────────
    @tasks.loop(seconds=30)
    async def idle_monitor(self) -> None:
        try:
            now = time.monotonic()
            for vc in list(self.client.voice_clients):
                if not isinstance(vc, MusicPlayer) or vc.channel is None:
                    continue
                guild_id = vc.guild.id
                refresh_owner_presence(vc)
                absent = getattr(vc, "owner_absent_since", None)
                if absent is not None and now - absent >= SESSION_GRACE:
                    if await self.hand_over_session(vc):  # owner left: pass control to someone still in voice
                        continue
                if vc.awaiting_owner or vc.stay:
                    self._alone_since.pop(guild_id, None)
                    continue  # prompt pending, or 24/7 mode: never leave on our own
                if self.has_listeners(vc.channel):
                    self._alone_since.pop(guild_id, None)
                    continue
                since = self._alone_since.setdefault(guild_id, now)
                if now - since >= config.INACTIVITY_TIMEOUT:
                    await self.leave_inactive(vc)
        except Exception:
            log.exception("idle monitor failed")

    def resume_after_owner(self, player: MusicPlayer) -> None:
        player.awaiting_owner = False
        player.owner_absent_since = None
        self._alone_since.pop(player.guild.id, None)
        if player.is_paused():
            player.resume()

    async def close_session(self, player: MusicPlayer) -> None:
        player.awaiting_owner = False
        await set_vc_status(player.channel, None)
        self.forget_guild(player.guild.id)
        await player.shutdown()

    async def ask_owner_to_continue(self, player: MusicPlayer, owner_id: int) -> None:
        """Owner left and nobody else is in voice: pause and ask them whether to continue."""
        player.awaiting_owner = True
        self._alone_since.pop(player.guild.id, None)  # the prompt has its own timeout
        ctx = player.ctx  # the music keeps playing while we wait
        if ctx is None:
            return
        view = ContinueView(self, player, owner_id)
        embed = embed_of(
            f"{E.WARNING} <@{owner_id}> You left the voice channel and no one is listening. "
            "Do you want to continue the music session?",
            0xFF0000,
        )
        embed.set_author(name="Session Inactive", icon_url=self.client.user.display_avatar.url)
        embed.set_footer(text=f"Thanks for choosing {config.NAME}!")
        try:
            view.message = await ctx.channel.send(
                embed=embed, view=view,
                allowed_mentions=discord.AllowedMentions(users=True),
            )
        except discord.HTTPException:
            await self.close_session(player)

    async def hand_over_session(self, player: MusicPlayer) -> bool:
        """Owner left the voice channel: give control to a random member still there and announce it."""
        old_id = player.session_owner_id
        channel = player.channel
        if old_id is None or channel is None:
            return False
        candidates = []
        for user_id in channel.voice_states:
            member = channel.guild.get_member(user_id)
            if member is not None and not member.bot and user_id != old_id:
                candidates.append(member)
        if player.awaiting_owner:
            return True
        if not candidates and player.stay:
            return True  # 24/7 mode: nobody to ask, just keep playing
        if not candidates:
            await self.ask_owner_to_continue(player, old_id)
            return True
        new_owner = random.choice(candidates)
        start_session(player, new_owner.id)
        player.transferred = True
        self._sessions[player.guild.id] = (new_owner.id, (player.ctx.channel.id if player.ctx else 0))
        ctx = player.ctx
        if ctx is not None:
            old_member = channel.guild.get_member(old_id)
            old_text = f"{old_member.mention} (**{old_member.display_name}**)" if old_member else f"<@{old_id}>"
            new_text = f"{new_owner.mention} (**{new_owner.display_name}**)"
            embed = discord.Embed(
                description=(
                    f"{E.WARNING} **Session Control Transferred**\n\n"
                    f"• **Session Author:** {old_text}\n"
                    f"• **New Controller:** {new_text}\n\n"
                    f"Session author {old_text} left the voice channel. "
                    f"Music session control has been transferred to {new_text}."
                ),
                color=0xFF0000,
            )
            embed.set_author(name="Session Control Transferred", icon_url=self.client.user.display_avatar.url)
            embed.set_footer(text=f"Thanks for choosing {config.NAME}!")
            try:
                await ctx.channel.send(
                    embed=embed,
                    allowed_mentions=discord.AllowedMentions(users=True),
                )
            except discord.HTTPException:
                pass
        return True

    def has_listeners(self, channel: discord.abc.GuildChannel) -> bool:
        """True if anyone other than bots is in the voice channel.

        Uses voice states instead of channel.members so it also works for users who were
        already in voice before the bot started (they may not be in the member cache).
        """
        my_id = self.client.user.id
        for user_id in channel.voice_states:
            if user_id == my_id:
                continue
            member = channel.guild.get_member(user_id)
            if member is None or not member.bot:
                return True
        return False

    @idle_monitor.before_loop
    async def _before_idle_monitor(self) -> None:
        await self.client.wait_until_ready()

    async def leave_inactive(self, player: MusicPlayer) -> None:
        player._handled_disconnect = True
        ctx = player.ctx
        await set_vc_status(player.channel, None)
        self.forget_guild(player.guild.id)
        await self._drop_card(player.card, delete=True)
        player.card = None
        await player.shutdown()
        if ctx is None:
            return
        minutes = max(config.INACTIVITY_TIMEOUT // 60, 1)
        ended = discord.Embed(
            description=f"{E.WARNING} Bot has been disconnected due to inactivity (idle in Voice Channel) for more than {minutes} minute(s).",
            color=0xFF0000,
        )
        ended.set_author(name="Inactive Timeout", icon_url=self.client.user.display_avatar.url)
        ended.set_footer(text=f"Thanks for choosing {config.NAME}!")
        try:
            await ctx.channel.send(embed=ended)
        except discord.HTTPException:
            pass

    # ── player card ─────────────────────────────────────
    async def build_player_card(
        self, track: Track, player: MusicPlayer, effects: tuple = ()
    ) -> Optional[discord.File]:
        """The Pillow banner (utils/banner.py). Needs no template file, only Pillow."""
        artwork: Optional[bytes] = None
        if track.artwork:
            try:
                timeout = aiohttp.ClientTimeout(total=8)
                async with self.client.session.get(track.artwork, timeout=timeout) as resp:
                    if resp.status == 200:
                        artwork = await resp.read()
            except (aiohttp.ClientError, asyncio.TimeoutError):
                artwork = None
        name, _, _ = source_info(track)

        owner_id = player.session_owner_id
        owner_member = player.channel.guild.get_member(owner_id) if (owner_id and player.channel) else None
        owner_name = owner_member.display_name if owner_member else "Owner"
        if getattr(player, "transferred", False):
            session_status = f"session transferred - @{owner_name}"
        else:
            session_status = f"session connected - @{owner_name}"

        data = await asyncio.to_thread(
            render_banner,
            artwork=artwork,
            title=track.title,
            artist=track.author or "",
            duration=track_duration(track),
            source=name,
            session_text=session_status,
            effects=list(effects),
        )
        return discord.File(io.BytesIO(data), filename="player.png")

    async def display_player_embed(
        self, player: MusicPlayer, track: Track, ctx: commands.Context, autoplay: bool = False
    ) -> None:
        channel = ctx.channel
        if ctx.guild:
            from utils.state import record_channel
            record_channel(ctx.guild.id, channel.id)
        me = ctx.guild.me if ctx.guild else None
        if me is not None and not channel.permissions_for(me).send_messages:
            return

        name, color, emoji = source_info(track)

        embed = discord.Embed(title=f"**{shorten(track.title, 240)}**", color=color)
        embed.add_field(name="Author", value=f"`{shorten(track.author or 'Unknown', 200)}`")
        embed.add_field(name="Duration", value=f"`{track_duration(track)}`")
        if track.uri:
            embed.add_field(name="Source", value=f"[{emoji} Listen on {name}]({track.uri})")
        else:
            embed.add_field(name="Source", value=f"{emoji} {name}")

        owner_id = player.session_owner_id or (ctx.author.id if ctx else None)
        owner_member = ctx.guild.get_member(owner_id) if (owner_id and ctx.guild) else None
        owner_name = owner_member.display_name if owner_member else (ctx.author.display_name if ctx else "Owner")
        owner_mention = f"<@{owner_id}>" if owner_id else f"@{owner_name}"

        if getattr(player, "transferred", False):
            session_footer = f"Session Control: @{owner_name}"
            session_field_val = f"Transferred to {owner_mention}"
        else:
            session_footer = f"Session Connected: @{owner_name}"
            session_field_val = f"Connected by {owner_mention}"

        embed.add_field(name="Session", value=session_field_val)
        embed.set_footer(
            text=session_footer + (" • (Autoplay Mode)" if autoplay else ""),
            icon_url=owner_member.display_avatar.url if owner_member else ctx.author.display_avatar.url
        )

        file: Optional[discord.File] = None
        if me is None or channel.permissions_for(me).attach_files:
            try:
                file = await self.build_player_card(track, player, player_effect_chips(player))
            except Exception:
                log.warning("Could not build the player card", exc_info=True)
        if file is not None:
            embed.set_image(url="attachment://player.png")
        elif track.artwork:
            embed.set_thumbnail(url=track.artwork)

        note, player.pending_note = player.pending_note, None
        if note:
            embed.description = note  # the reply to the command that started / changed this song
        view = MusicControlView(player)
        view.embed = embed
        view.message = await channel.send(embed=embed, file=file or discord.utils.MISSING, view=view)
        previous, player.card = player.card, view
        await self._drop_card(previous, delete=True)  # one card at a time: the old song's card goes away

    @staticmethod
    async def _drop_card(view: Optional[MusicControlView], *, delete: bool) -> None:
        if view is None or view.message is None:
            return
        view.stop()
        try:
            if delete:
                await view.message.delete()
            else:
                await view.message.edit(view=None)
        except discord.HTTPException:
            pass

    async def ack(self, ctx: commands.Context) -> None:
        """A slash command must be answered, but here the answer is the player card: remove the placeholder."""
        interaction = getattr(ctx, "interaction", None)
        if interaction is None:
            return
        try:
            if not interaction.response.is_done():
                await interaction.response.defer(ephemeral=True)
            await interaction.delete_original_response()
        except discord.HTTPException:
            pass

    async def note(
        self, ctx: commands.Context, text: str, color: int = 0x000000, *, next_card: bool = False, ack: bool = True
    ) -> None:
        """Reply INSIDE the player card, so reply + poster + buttons are one message.

        The card is edited in place. next_card=True puts the text on the next card that gets posted (first song
        after `play`, `skip`). With no player card to use this is a normal reply message.
        ack=False when the slash command already answered with something else (e.g. the filter menu).
        """
        player = ctx.voice_client if isinstance(ctx.voice_client, MusicPlayer) else None
        card = player.card if player is not None else None
        if player is not None and next_card:
            player.pending_note = text
        elif card is not None and card.message is not None:
            await card.update(text)
        else:
            await ctx.send(embed=embed_of(text, color))
            return
        if ack:
            await self.ack(ctx)

    async def retire_card(self, player: MusicPlayer) -> None:
        """Session over: keep the last card in the chat but take its buttons off."""
        card, player.card = player.card, None
        player.pending_note = None
        await self._drop_card(card, delete=False)

    # ── player events (called by MusicPlayer) ───────────
    async def on_track_start(self, player: MusicPlayer, track: Track) -> None:
        try:
            if not player.is_connected() or player.current is not track:
                return  # skipped / replaced before we got to announce it
            await set_vc_status(player.channel, f"🎶 {clean_song_name(track.title)}")
            if track.uri:
                self.recent.setdefault(player.guild.id, deque(maxlen=60)).append(track.uri)
            ctx = player.ctx
            if ctx is None:
                return
            await self.display_player_embed(player, track, ctx, autoplay=track.recommended)
        except discord.HTTPException:
            log.warning("Could not post the player card", exc_info=True)
        except Exception:
            log.exception("track start handler failed")

    async def on_track_failed(self, player: MusicPlayer, track: Track, reason: str) -> None:
        ctx = player.ctx
        if ctx is None:
            return
        try:
            await ctx.channel.send(
                embed=embed_of(f"{E.WARNING} I couldn't play **{shorten(track.title, 100)}**: {reason} Skipping.", 0xFF0000)
            )
        except discord.HTTPException:
            pass

    async def finish_playback(self, player: MusicPlayer) -> None:
        if getattr(player, "_handled_disconnect", False) or not player.is_connected():
            return
        if player.stay:
            return  # 24/7 mode: stay in the channel (autoplay normally keeps it going)
        ctx = player.ctx
        await set_vc_status(player.channel, None)
        self.forget_guild(player.guild.id)
        await self._drop_card(player.card, delete=True)
        player.card = None
        await player.shutdown()
        if ctx is None:
            return
        ended = discord.Embed(
            description=f"{E.MUSIC} All tracks have been played, leaving the voice channel.",
            color=0xFF0000,
        )
        ended.set_author(name="Queue Ended", icon_url=self.client.user.display_avatar.url)
        ended.set_footer(text=f"Thanks for choosing {config.NAME}!")
        try:
            await ctx.channel.send(embed=ended)
        except discord.HTTPException:
            pass

    # ── playback flow ───────────────────────────────────
    async def ensure_player(self, ctx: commands.Context) -> Optional[MusicPlayer]:
        """Return the guild's player for the author's voice channel (connecting if needed)."""
        if ctx.guild and ctx.channel:
            from utils.state import record_channel
            record_channel(ctx.guild.id, ctx.channel.id)

        voice = ctx.author.voice
        if not voice or not voice.channel:
            await ctx.send(embed=embed_of(f"{E.WARNING} You need to be in a voice channel to use this command."))
            return None

        vc = ctx.voice_client
        if vc is not None and not isinstance(vc, MusicPlayer):
            await ctx.send(embed=embed_of(f"{E.WARNING} I'm already using voice in this server."))
            return None

        if vc is not None and not vc.is_connected():  # stale, half-dead client
            try:
                await vc.disconnect(force=True)
            except Exception:
                pass
            vc = None

        if vc is not None:
            if vc.channel != voice.channel:
                await ctx.send(embed=embed_of(f"{E.WARNING} You must be connected to {vc.channel.mention} to play."))
                return None
            if not can_control(vc, ctx.author.id):
                await ctx.send(embed=embed_of(denied_text(vc), 0xFF0000))
                return None
        else:
            perms = voice.channel.permissions_for(ctx.guild.me)
            if not perms.connect or not perms.speak:
                await ctx.send(
                    embed=embed_of(
                        f"{E.WARNING} I need **Connect** and **Speak** permissions in {voice.channel.mention}.", 0xFF0000
                    )
                )
                return None
            try:
                vc = await voice.channel.connect(cls=MusicPlayer, timeout=20, self_deaf=True)
            except Exception:
                log.warning("Could not join voice channel %s", voice.channel.id, exc_info=True)
                await ctx.send(
                    embed=embed_of(f"{E.WARNING} I couldn't join {voice.channel.mention}. Check my permissions and try again.", 0xFF0000)
                )
                return None
            vc.cog = self
            start_session(vc, ctx.author.id)  # whoever starts the session owns it
            self._sessions[ctx.guild.id] = (ctx.author.id, ctx.channel.id)

        vc.ctx = ctx
        return vc

    async def play_source(self, ctx: commands.Context, query: str) -> None:
        vc = await self.ensure_player(ctx)
        if vc is None:
            return

        query = query.strip().strip("<>")

        if self.spotify.enabled:
            parsed = self.spotify.parse(query)
            if parsed:
                await self.handle_spotify_link(ctx, vc, *parsed)
                return

        try:
            if _is_url(query):
                playlist_name, tracks = await load_tracks(query)
            else:
                playlist_name = None
                history = self.recent.setdefault(ctx.guild.id, deque(maxlen=60))
                taken = {_norm_title(t.title) for t in list(vc.queue) + ([vc.current] if vc.current else [])}
                tracks = await smart_search(query, set(history), taken)
                if len(tracks) > 1:
                    playlist_name = f"{shorten(query, 60)} (shuffled)"
        except MusicError as exc:
            await ctx.send(embed=embed_of(f"{E.WARNING} {exc}", 0xFF0000))
            return
        except Exception:
            log.warning("Search failed for %r", query, exc_info=True)
            await ctx.send(embed=embed_of(f"{E.WARNING} I couldn't load that. The source may be unavailable or blocked.", 0xFF0000))
            return

        if not tracks:
            await ctx.send(embed=embed_of("No results found."))
            return

        if playlist_name is not None:
            added = f"{E.ADD} Added playlist **{shorten(playlist_name, 100)}** with **{len(tracks)} songs** to the queue."
        else:
            added = f"{E.ADD} Added {md_link(tracks[0].title, tracks[0].uri)} to the queue."
        await self.note(ctx, added, next_card=(vc.card is None or vc.current is None))  # idle player: it goes on the card about to be posted

        try:
            await vc.enqueue(tracks)
        except MusicError as exc:
            vc.pending_note = None
            await ctx.send(embed=embed_of(f"{E.WARNING} {exc}", 0xFF0000))

    async def handle_spotify_link(self, ctx: commands.Context, vc: MusicPlayer, kind: str, spotify_id: str) -> None:
        def entry(item: dict) -> Track:
            artists = ", ".join(artist["name"] for artist in item.get("artists", []))
            return Track(
                title=item["name"],
                author=artists,
                length=int(item.get("duration_ms") or 0),
                source="spotify",
                query=f"{item['name']} {artists}".strip(),  # matched on YouTube right before it plays
            )

        try:
            if kind == "track":
                info = await self.spotify.get(f"tracks/{spotify_id}")
                label, tracks = info["name"], [entry(info)]
            elif kind == "playlist":
                info = await self.spotify.get(f"playlists/{spotify_id}")
                items = [item.get("track") for item in info.get("tracks", {}).get("items", [])]
                label, tracks = info.get("name", "playlist"), [entry(t) for t in items if t]
            else:
                info = await self.spotify.get(f"albums/{spotify_id}")
                label, tracks = info.get("name", "album"), [entry(t) for t in info.get("tracks", {}).get("items", [])]
        except Exception:
            log.warning("Spotify lookup failed", exc_info=True)
            await ctx.send(embed=embed_of(f"{E.WARNING} I couldn't read that Spotify link.", 0xFF0000))
            return

        tracks = tracks[:MAX_PLAYLIST]
        if not tracks:
            await ctx.send(embed=embed_of("No tracks found in that Spotify link."))
            return

        added = f"{E.ADD} Added **{len(tracks)}** track(s) from **{shorten(label, 100)}** to the queue."
        await self.note(ctx, added, next_card=(vc.card is None or vc.current is None))
        try:
            await vc.enqueue(tracks)
        except MusicError as exc:
            vc.pending_note = None
            await ctx.send(embed=embed_of(f"{E.WARNING} {exc}", 0xFF0000))

    # ── shared command guard ────────────────────────────
    async def control_player(
        self,
        ctx: commands.Context,
        *,
        need_playing: bool = True,
        missing: str = "No song is currently playing.",
        owner_only: bool = True,
    ) -> Optional[MusicPlayer]:
        vc = ctx.voice_client
        if not isinstance(vc, MusicPlayer) or (need_playing and not vc.playing):
            await ctx.send(embed=embed_of(f"{E.WARNING} {missing}"))
            return None

        voice = ctx.author.voice
        if not voice or not voice.channel or voice.channel.id != vc.channel.id:
            await ctx.send(
                embed=embed_of(f"{E.WARNING} You need to be in the same voice channel as me to use this command.", 0xFF0000)
            )
            return None

        if owner_only and not can_control(vc, ctx.author.id):
            await ctx.send(embed=embed_of(denied_text(vc), 0xFF0000))
            return None
        return vc

    # ── commands ────────────────────────────────────────
    @commands.hybrid_command(name="play", aliases=["p"], usage="play <query>", help="Plays a song or playlist.")
    @blacklist_check()
    @ignore_check()
    @commands.cooldown(1, 3, commands.BucketType.user)
    async def play(self, ctx: commands.Context, *, query: str):
        await ctx.defer()
        await self.play_source(ctx, query)

    @commands.hybrid_command(name="search", usage="search <query>", help="Searches music from multiple platforms.")
    @blacklist_check()
    @ignore_check()
    @commands.cooldown(1, 3, commands.BucketType.user)
    async def search2(self, ctx: commands.Context, *, query: str):
        if not ctx.author.voice:
            await ctx.send(embed=embed_of(f"{E.WARNING} You need to be in a voice channel to use this command."))
            return

        vc = ctx.voice_client
        if (
            isinstance(vc, MusicPlayer)
            and vc.channel == ctx.author.voice.channel
            and not can_control(vc, ctx.author.id)
        ):
            await ctx.send(embed=embed_of(denied_text(vc), 0xFF0000))
            return

        embed = discord.Embed(
            title="Select a platform to search from:",
            description="Click a button below to choose.",
            color=0xFF0000,
        )
        await ctx.send(embed=embed, view=PlatformSelectView(self, ctx, query))

    @commands.hybrid_command(
        name="nowplaying", aliases=["nop", "current"], usage="nowplaying", help="Shows the info about current playing song."
    )
    @blacklist_check()
    @ignore_check()
    @commands.cooldown(1, 3, commands.BucketType.user)
    async def nowplaying(self, ctx: commands.Context):
        vc = await self.control_player(ctx, owner_only=False)
        if vc is None or vc.current is None:
            return

        track = vc.current
        position = vc.position / 1000
        length = track.length / 1000
        name, color, _ = source_info(track)

        embed = discord.Embed(title="Now Playing", color=color)
        embed.add_field(name="Track", value=md_link(track.title, track.uri), inline=False)
        embed.add_field(name="Song By", value=track.author or "Unknown", inline=False)
        if track.is_stream:
            embed.add_field(name="Progress", value="🔴 LIVE", inline=False)
        else:
            bar = create_progress_bar(position, length, 10)
            embed.add_field(
                name="Progress",
                value=f"{format_duration(vc.position)} [{bar}] {track_duration(track)}",
                inline=False,
            )
            embed.add_field(name="Duration", value=track_duration(track), inline=False)
        embed.add_field(name="Queue Length", value=str(len(vc.queue)), inline=False)
        embed.add_field(name="Source", value=f"{name} - [Link]({track.uri})" if track.uri else name, inline=False)
        if track.artwork:
            embed.set_thumbnail(url=track.artwork)
        embed.set_footer(text=f"Requested by {ctx.author.display_name}", icon_url=ctx.author.display_avatar.url)
        await ctx.send(embed=embed)

    @commands.hybrid_command(name="autoplay", usage="autoplay", help="Toggles autoplay mode.")
    @blacklist_check()
    @ignore_check()
    @commands.cooldown(1, 3, commands.BucketType.user)
    async def autoplay(self, ctx: commands.Context):
        vc = await self.control_player(ctx)
        if vc is None:
            return
        if vc.stay:
            await ctx.send(embed=embed_of(f"{E.WARNING} Autoplay is locked on while 24/7 mode is enabled.", 0xFF0000))
            return
        vc.autoplay = not vc.autoplay
        state = "enabled" if vc.autoplay else "disabled"
        owner_text, trigger_text, is_owner = format_session_users(vc, ctx.author, ctx.guild)
        if is_owner:
            msg = f"{E.TICK} Autoplay {state} by session author {trigger_text}."
        else:
            msg = f"{E.TICK} Autoplay {state} by {trigger_text} (Session Author: {owner_text})."
        await self.note(ctx, msg)

    @commands.hybrid_command(name="loop", usage="loop", help="Toggles loop mode.")
    @blacklist_check()
    @ignore_check()
    @commands.cooldown(1, 3, commands.BucketType.user)
    async def loop(self, ctx: commands.Context):
        vc = await self.control_player(ctx)
        if vc is None:
            return
        vc.loop_mode = not vc.loop_mode
        state = "enabled" if vc.loop_mode else "disabled"
        owner_text, trigger_text, is_owner = format_session_users(vc, ctx.author, ctx.guild)
        if is_owner:
            msg = f"{E.BTN_LOOP} Loop {state} by session author {trigger_text}."
        else:
            msg = f"{E.BTN_LOOP} Loop {state} by {trigger_text} (Session Author: {owner_text})."
        await self.note(ctx, msg)

    @commands.hybrid_command(name="pause", usage="pause", help="Pauses the current song.")
    @blacklist_check()
    @ignore_check()
    @commands.cooldown(1, 3, commands.BucketType.user)
    async def pause(self, ctx: commands.Context):
        vc = await self.control_player(ctx)
        if vc is None:
            return
        if vc.paused:
            await ctx.send(embed=embed_of(f"{E.WARNING} Nothing is playing or already paused.", 0xFF0000))
            return
        vc.pause()
        song_title = vc.current.title if vc.current else None
        await set_vc_status(vc.channel, f"⏸️ {clean_song_name(song_title)}")
        owner_text, trigger_text, is_owner = format_session_users(vc, ctx.author, ctx.guild)
        if is_owner:
            msg = f"{E.BTN_PAUSE} Paused by session author {trigger_text}."
        else:
            msg = f"{E.BTN_PAUSE} Paused by {trigger_text} (Session Author: {owner_text})."
        await self.note(ctx, msg)

    @commands.hybrid_command(name="resume", aliases=["unpause"], usage="resume", help="Resumes the paused song.")
    @blacklist_check()
    @ignore_check()
    @commands.cooldown(1, 3, commands.BucketType.user)
    async def resume(self, ctx: commands.Context):
        vc = await self.control_player(ctx)
        if vc is None:
            return
        if not vc.paused:
            await ctx.send(embed=embed_of(f"{E.WARNING} Player is not paused.", 0xFF0000))
            return
        vc.resume()
        song_title = vc.current.title if vc.current else None
        await set_vc_status(vc.channel, f"🎶 {clean_song_name(song_title)}")
        owner_text, trigger_text, is_owner = format_session_users(vc, ctx.author, ctx.guild)
        if is_owner:
            msg = f"{E.BTN_RESUME} Resumed by session author {trigger_text}."
        else:
            msg = f"{E.BTN_RESUME} Resumed by {trigger_text} (Session Author: {owner_text})."
        await self.note(ctx, msg)

    @commands.hybrid_command(name="skip", aliases=["next"], usage="skip", help="Skips the current song.")
    @blacklist_check()
    @ignore_check()
    @commands.cooldown(1, 3, commands.BucketType.user)
    async def skip(self, ctx: commands.Context):
        vc = await self.control_player(ctx)
        if vc is None:
            return
        if vc.autoplay or not vc.queue.is_empty:
            await ctx.defer()
            owner_text, trigger_text, is_owner = format_session_users(vc, ctx.author, ctx.guild)
            if is_owner:
                msg = f"{E.BTN_SKIP} Skipped by session author {trigger_text}."
            else:
                msg = f"{E.BTN_SKIP} Skipped by {trigger_text} (Session Author: {owner_text})."
            await self.note(ctx, msg, next_card=True)
            await vc.skip()
        else:
            await ctx.send(embed=embed_of(f"{E.WARNING} No song is playing or in the queue to skip.", 0xFF0000))

    @commands.hybrid_command(name="shuffle", usage="shuffle", help="Shuffles the queue.")
    @blacklist_check()
    @ignore_check()
    @commands.cooldown(1, 3, commands.BucketType.user)
    async def shuffle(self, ctx: commands.Context):
        vc = await self.control_player(ctx)
        if vc is None:
            return
        if vc.queue.is_empty:
            await ctx.send(embed=embed_of(f"{E.WARNING} Queue is empty.", 0xFF0000))
            return
        vc.queue.shuffle()
        owner_text, trigger_text, is_owner = format_session_users(vc, ctx.author, ctx.guild)
        if is_owner:
            msg = f"{E.BTN_SHUFFLE} Queue shuffled by session author {trigger_text}."
        else:
            msg = f"{E.BTN_SHUFFLE} Queue shuffled by {trigger_text} (Session Author: {owner_text})."
        await self.note(ctx, msg)

    @commands.hybrid_command(name="stop", usage="stop", help="Stops the current song and clears the queue.")
    @blacklist_check()
    @ignore_check()
    @commands.cooldown(1, 3, commands.BucketType.user)
    async def stop(self, ctx: commands.Context):
        vc = await self.control_player(ctx, need_playing=False, missing="I'm not connected to any voice channel.")
        if vc is None:
            return
        await set_vc_status(vc.channel, None)
        vc.queue.clear()
        vc.pending_note = None
        owner_text, trigger_text, is_owner = format_session_users(vc, ctx.author, ctx.guild)
        vc._handled_disconnect = True
        self.forget_guild(ctx.guild.id)
        await vc.shutdown()
        if is_owner:
            desc = f"{E.BTN_STOP} Stopped and queue cleared by session author {trigger_text}."
        else:
            desc = (
                f"{E.BTN_STOP} **Music Session Stopped**\n\n"
                f"• **Session Author:** {owner_text}\n"
                f"• **Triggered by:** {trigger_text}\n\n"
                f"Stopped and queue cleared by {trigger_text}."
            )
        embed = embed_of(desc, 0xFF0000)
        embed.set_author(name="Session Stopped", icon_url=self.client.user.display_avatar.url)
        embed.set_footer(text=f"Thanks for choosing {config.NAME}!")
        await ctx.send(embed=embed, allowed_mentions=discord.AllowedMentions(users=True))

    @commands.hybrid_command(
        name="volume",
        aliases=["vol"],
        usage="volume <1-300>",
        help=f"Sets the volume of the player ({MIN_VOLUME}-{MAX_VOLUME}%, above 100% can distort).",
    )
    @blacklist_check()
    @ignore_check()
    @commands.cooldown(1, 3, commands.BucketType.user)
    async def volume(self, ctx: commands.Context, level: int):
        vc = await self.control_player(ctx, need_playing=False, missing="I'm not connected to a voice channel.")
        if vc is None:
            return
        if not MIN_VOLUME <= level <= MAX_VOLUME:
            await ctx.send(embed=embed_of(f"{E.WARNING} Volume must be between {MIN_VOLUME} and {MAX_VOLUME}.", 0xFF0000))
            return
        vc.set_volume(level)  # one shared value: the Remix console / Vol button / card read the same player.volume
        owner_text, trigger_text, is_owner = format_session_users(vc, ctx.author, ctx.guild)
        if is_owner:
            text = f"{E.VOICE} Volume set to {level}% by session author {trigger_text}."
        else:
            text = f"{E.VOICE} Volume set to {level}% by {trigger_text} (Session Author: {owner_text})."
        if level > 150:
            text += "\nAbove 150% loud tracks can distort."
        await self.note(ctx, text)

    @commands.hybrid_command(name="queue", aliases=["q"], usage="queue", help="Shows the current queue.")
    @blacklist_check()
    @ignore_check()
    @commands.cooldown(1, 3, commands.BucketType.user)
    async def queue(self, ctx: commands.Context):
        vc = await self.control_player(ctx, need_playing=False, missing="The queue is currently empty.", owner_only=False)
        if vc is None:
            return
        if vc.queue.is_empty:
            await ctx.send(embed=embed_of(f"{E.WARNING} The queue is currently empty."))
            return

        entries = [
            f"{index + 1}. {md_link(f'{track.title} - {track.author}' if track.author else track.title, track.uri)}"
            for index, track in enumerate(vc.queue)
        ]
        embeds = DescriptionEmbedPaginator(
            entries=entries,
            title="Current Queue",
            description="List of upcoming songs.",
            per_page=10,
            color=0x000000,
        ).get_pages()
        await Paginator(ctx, embeds).paginate()

    @commands.hybrid_command(name="clearqueue", usage="clearqueue", help="Clears the queue.")
    @blacklist_check()
    @ignore_check()
    @commands.cooldown(1, 3, commands.BucketType.user)
    async def clearqueue(self, ctx: commands.Context):
        vc = await self.control_player(ctx, need_playing=False, missing="No Queue to clear.")
        if vc is None:
            return
        if vc.queue.is_empty:
            await ctx.send(embed=embed_of(f"{E.WARNING} No Queue to clear.", 0xFF0000))
            return
        vc.queue.clear()
        owner_text, trigger_text, is_owner = format_session_users(vc, ctx.author, ctx.guild)
        if is_owner:
            msg = f"{E.TICK} Queue has been cleared by session author {trigger_text}."
        else:
            msg = f"{E.TICK} Queue has been cleared by {trigger_text} (Session Author: {owner_text})."
        await self.note(ctx, msg, 0x1DB954)

    @commands.hybrid_command(name="replay", usage="replay", help="Replays the current song.")
    @blacklist_check()
    @ignore_check()
    @commands.cooldown(1, 3, commands.BucketType.user)
    async def replay(self, ctx: commands.Context):
        vc = await self.control_player(ctx)
        if vc is None:
            return
        await ctx.defer()
        await vc.seek(0)
        owner_text, trigger_text, is_owner = format_session_users(vc, ctx.author, ctx.guild)
        if is_owner:
            msg = f"{E.BTN_REPLAY} Replaying the current track by session author {trigger_text}."
        else:
            msg = f"{E.BTN_REPLAY} Replaying the current track by {trigger_text} (Session Author: {owner_text})."
        await self.note(ctx, msg, 0x1DB954)

    @commands.hybrid_command(name="join", aliases=["connect"], usage="join", help="Joins the voice channel.")
    @blacklist_check()
    @ignore_check()
    @commands.cooldown(1, 3, commands.BucketType.user)
    async def join(self, ctx: commands.Context):
        if not ctx.author.voice or not ctx.author.voice.channel:
            await ctx.send(embed=embed_of(f"{E.WARNING} You need to join a voice channel first.", 0xFF0000))
            return
        if ctx.voice_client is not None:
            await ctx.send(embed=embed_of(f"{E.WARNING} I'm already connected to {ctx.voice_client.channel.mention}.", 0xFF0000))
            return
        vc = await self.ensure_player(ctx)
        if vc is not None:
            owner_text, trigger_text, is_owner = format_session_users(vc, ctx.author, ctx.guild)
            embed = embed_of(f"{E.VOICE} Joined {vc.channel.mention} by session author {trigger_text}.", 0x1DB954)
            embed.set_author(name="Session Connected", icon_url=self.client.user.display_avatar.url)
            embed.set_footer(text=f"Thanks for choosing {config.NAME}!")
            await ctx.send(embed=embed, allowed_mentions=discord.AllowedMentions(users=True))

    @commands.hybrid_command(
        name="247", aliases=["stay", "24/7"], usage="247", help="Toggles 24/7 mode: I stay in voice and keep playing songs with autoplay."
    )
    @blacklist_check()
    @ignore_check()
    @commands.cooldown(1, 3, commands.BucketType.user)
    async def stay247(self, ctx: commands.Context):
        vc = await self.control_player(ctx, need_playing=False, missing="I'm not connected to any voice channel.")
        if vc is None:
            return
        vc.stay = not vc.stay
        owner_text, trigger_text, is_owner = format_session_users(vc, ctx.author, ctx.guild)
        if vc.stay:
            vc.autoplay = True
            if is_owner:
                text = f"{E.TICK} 24/7 mode **enabled** by session author {trigger_text}. I'll keep playing songs with autoplay and won't leave."
            else:
                text = f"{E.TICK} 24/7 mode **enabled** by {trigger_text} (Session Author: {owner_text}). I'll keep playing songs with autoplay and won't leave."
        else:
            if is_owner:
                text = f"{E.TICK} 24/7 mode **disabled** by session author {trigger_text}. I'll leave when idle or alone."
            else:
                text = f"{E.TICK} 24/7 mode **disabled** by {trigger_text} (Session Author: {owner_text}). I'll leave when idle or alone."
        embed = embed_of(text, 0x1DB954)
        embed.set_author(name="24/7 Mode", icon_url=self.client.user.display_avatar.url)
        embed.set_footer(text=f"Thanks for choosing {config.NAME}!")
        await ctx.send(embed=embed, allowed_mentions=discord.AllowedMentions(users=True))

    @commands.hybrid_command(
        name="disconnect", aliases=["dc", "leave"], usage="disconnect", help="Disconnects the bot from the voice channel."
    )
    @blacklist_check()
    @ignore_check()
    @commands.cooldown(1, 3, commands.BucketType.user)
    async def disconnect(self, ctx: commands.Context):
        vc = await self.control_player(ctx, need_playing=False, missing="I'm not connected to any voice channel.")
        if vc is None:
            return
        await set_vc_status(vc.channel, None)
        owner_text, trigger_text, is_owner = format_session_users(vc, ctx.author, ctx.guild)
        vc._handled_disconnect = True
        self.forget_guild(ctx.guild.id)
        await vc.shutdown()
        if is_owner:
            desc = f"{E.BTN_STOP} Disconnected from the voice channel by session author {trigger_text}."
        else:
            desc = (
                f"{E.BTN_STOP} **Voice Session Disconnected**\n\n"
                f"• **Session Author:** {owner_text}\n"
                f"• **Triggered by:** {trigger_text}\n\n"
                f"Disconnected from the voice channel by {trigger_text}."
            )
        embed = embed_of(desc, 0x1DB954)
        embed.set_author(name="Disconnected", icon_url=self.client.user.display_avatar.url)
        embed.set_footer(text=f"Thanks for choosing {config.NAME}!")
        await ctx.send(embed=embed, allowed_mentions=discord.AllowedMentions(users=True))

    @commands.hybrid_command(name="seek", usage="seek <percentage>", help="Seeks to a specific percentage of the song.")
    @blacklist_check()
    @ignore_check()
    @commands.cooldown(1, 3, commands.BucketType.user)
    async def seek(self, ctx: commands.Context, percentage: int):
        if not 1 <= percentage <= 100:
            await ctx.send(embed=embed_of(f"{E.WARNING} Please provide a percentage between 1 and 100.", 0xFF0000))
            return
        vc = await self.control_player(ctx)
        if vc is None:
            return
        track = vc.current
        if track is None or not track.is_seekable:
            await ctx.send(embed=embed_of(f"{E.WARNING} This track can't be seeked.", 0xFF0000))
            return
        await ctx.defer()
        await vc.seek(int(track.length * (percentage / 100)))
        owner_text, trigger_text, is_owner = format_session_users(vc, ctx.author, ctx.guild)
        if is_owner:
            msg = f"{E.TICK} Seeked to {percentage}% by session author {trigger_text}."
        else:
            msg = f"{E.TICK} Seeked to {percentage}% by {trigger_text} (Session Author: {owner_text})."
        await self.note(ctx, msg, 0x1DB954)

    # ── voice events ────────────────────────────────────
    async def find_muter(self, guild: discord.Guild) -> Optional[discord.abc.User]:
        """Best effort: who server-muted the bot."""
        try:
            async for entry in guild.audit_logs(limit=10, action=discord.AuditLogAction.member_update):
                if getattr(entry, "target", None) is not None and entry.target.id == self.client.user.id:
                    if getattr(entry.after, "mute", None) is True:
                        return entry.user
        except Exception:
            pass
        return None

    async def find_disconnector(self, guild: discord.Guild) -> Optional[discord.abc.User]:
        """Best effort: who disconnected / moved / kicked the bot."""
        try:
            for action in (
                discord.AuditLogAction.member_disconnect,
                discord.AuditLogAction.member_move,
                discord.AuditLogAction.kick,
                discord.AuditLogAction.channel_delete,
            ):
                async for entry in guild.audit_logs(limit=10, action=action):
                    if action == discord.AuditLogAction.member_disconnect:
                        return entry.user
                    elif action == discord.AuditLogAction.member_move:
                        if getattr(entry, "target", None) is None or getattr(entry, "target", None).id == self.client.user.id:
                            return entry.user
                    elif action == discord.AuditLogAction.kick:
                        if getattr(entry, "target", None) is not None and entry.target.id == self.client.user.id:
                            return entry.user
                    elif action == discord.AuditLogAction.channel_delete:
                        return entry.user
        except Exception:
            pass
        return None

    @commands.Cog.listener()
    async def on_voice_state_update(self, member: discord.Member, before: discord.VoiceState, after: discord.VoiceState):
        if self.client.user is None:
            return
        if member.id != self.client.user.id:
            # The session owner left the bot's voice channel -> hand control to someone still there.
            vc = member.guild.voice_client
            if (
                isinstance(vc, MusicPlayer)
                and vc.session_owner_id == member.id
                and before.channel is not None
                and before.channel == vc.channel
                and after.channel != vc.channel
            ):
                await self.hand_over_session(vc)
            elif (
                isinstance(vc, MusicPlayer)
                and vc.awaiting_owner
                and vc.session_owner_id == member.id
                and after.channel is not None
                and after.channel == vc.channel
            ):
                self.resume_after_owner(vc)  # owner came back before answering
            elif (
                isinstance(vc, MusicPlayer)
                and vc.stay
                and not member.bot
                and after.channel is not None
                and after.channel == vc.channel
                and before.channel != vc.channel
                and vc.session_owner_id is not None
                and vc.session_owner_id not in vc.channel.voice_states
            ):
                # 24/7 mode and the owner is gone: the first person to join takes the session
                old_id = vc.session_owner_id
                start_session(vc, member.id)
                vc.transferred = True
                if vc.ctx is not None:
                    self._sessions[vc.guild.id] = (member.id, vc.ctx.channel.id)
                    old_member = member.guild.get_member(old_id) if old_id else None
                    old_text = f"{old_member.mention} (**{old_member.display_name}**)" if old_member else (f"<@{old_id}>" if old_id else "Session Author")
                    new_text = f"{member.mention} (**{member.display_name}**)"
                    try:
                        embed = discord.Embed(
                            description=(
                                f"{E.WARNING} **Session Control Transferred**\n\n"
                                f"• **Session Author:** {old_text}\n"
                                f"• **New Controller:** {new_text}\n\n"
                                f"Session author {old_text} is not in the voice channel. "
                                f"Music session control has been taken by {new_text}."
                            ),
                            color=0xFF0000,
                        )
                        embed.set_author(name="Session Control Transferred", icon_url=self.client.user.display_avatar.url)
                        embed.set_footer(text=f"Thanks for choosing {config.NAME}!")
                        await vc.ctx.channel.send(
                            embed=embed,
                            allowed_mentions=discord.AllowedMentions(users=True),
                        )
                    except discord.HTTPException:
                        pass
            return

        # Check if the bot was server muted
        if not before.mute and after.mute and after.channel is not None:
            vc = member.guild.voice_client
            if isinstance(vc, MusicPlayer):
                vc._handled_disconnect = True
                if vc.is_playing():
                    vc.pause()
                await self._drop_card(vc.card, delete=True)
                vc.card = None

                session = self._sessions.get(member.guild.id)
                self.forget_guild(member.guild.id)
                owner_id, channel_id = (session if session else (vc.session_owner_id, (vc.ctx.channel.id if vc.ctx else 0)))
                channel = member.guild.get_channel(channel_id) if channel_id else (vc.ctx.channel if vc.ctx else None)

                await asyncio.sleep(1)
                by = await self.find_muter(member.guild)
                if by is None and before.channel is not None:
                    others = [
                        before.channel.guild.get_member(uid)
                        for uid in before.channel.voice_states
                        if uid != self.client.user.id
                    ]
                    others = [m for m in others if m and not m.bot]
                    if len(others) == 1:
                        by = others[0]

                owner_member = member.guild.get_member(owner_id) if owner_id else None
                owner_text = f"{owner_member.mention} (**{owner_member.display_name}**)" if owner_member else (f"<@{owner_id}>" if owner_id else "Session Author")

                if by is not None:
                    trigger_text = f"{by.mention} (**{by.display_name}**)"
                else:
                    trigger_text = "Unknown User (Grant bot 'View Audit Log' permission to tag exact user)"

                embed = discord.Embed(
                    description=(
                        f"{E.WARNING} **Bot Server Muted — Session Paused**\n\n"
                        f"• **Session Author:** {owner_text}\n"
                        f"• **Triggered by:** {trigger_text}\n\n"
                        f"I have been server muted by {trigger_text}. Pausing music session and disconnecting from voice."
                    ),
                    color=0xFF0000,
                )
                embed.set_author(name="Server Muted", icon_url=self.client.user.display_avatar.url)
                embed.set_footer(text=f"Thanks for choosing {config.NAME}!")

                try:
                    await vc.disconnect(force=True)
                except Exception:
                    pass

                if channel is not None:
                    try:
                        await channel.send(embed=embed, allowed_mentions=discord.AllowedMentions(users=True))
                    except discord.HTTPException:
                        pass
                return

        if before.channel is not None and after.channel is None:
            # Kicked / channel deleted / manual leave: drop our bookkeeping
            vc = member.guild.voice_client
            if isinstance(vc, MusicPlayer):
                if getattr(vc, "_handled_disconnect", False):
                    return
                vc._handled_disconnect = True
                await self._drop_card(vc.card, delete=True)
                vc.card = None

            session = self._sessions.get(member.guild.id)
            self.forget_guild(member.guild.id)
            if session is None:
                return  # we ended it ourselves (stop / disconnect / idle)

            owner_id, channel_id = session
            channel = member.guild.get_channel(channel_id)
            if channel is None:
                return

            await asyncio.sleep(1)  # let the audit log entry appear
            by = await self.find_disconnector(member.guild)
            if by is None and before.channel is not None:
                others = [
                    before.channel.guild.get_member(uid)
                    for uid in before.channel.voice_states
                    if uid != self.client.user.id
                ]
                others = [m for m in others if m and not m.bot]
                if len(others) == 1:
                    by = others[0]

            owner_member = member.guild.get_member(owner_id) if owner_id else None
            owner_text = f"{owner_member.mention} (**{owner_member.display_name}**)" if owner_member else (f"<@{owner_id}>" if owner_id else "Session Author")

            if by is not None:
                trigger_text = f"{by.mention} (**{by.display_name}**)"
            else:
                trigger_text = "Unknown User (Grant bot 'View Audit Log' permission to tag exact user)"

            embed = discord.Embed(
                description=(
                    f"{E.WARNING} **Bot Disconnected — Session Ended**\n\n"
                    f"• **Session Author:** {owner_text}\n"
                    f"• **Triggered by:** {trigger_text}\n\n"
                    f"I have been disconnected from voice by {trigger_text}. Your music session has ended."
                ),
                color=0xFF0000,
            )
            embed.set_author(name="Disconnected", icon_url=self.client.user.display_avatar.url)
            embed.set_footer(text=f"Thanks for choosing {config.NAME}!")
            try:
                await channel.send(embed=embed, allowed_mentions=discord.AllowedMentions(users=True))
            except discord.HTTPException:
                pass
            return

    @commands.Cog.listener()
    async def on_message(self, message: discord.Message):
        """Reply whenever the bot is mentioned (unless the message is a command)."""
        if message.author.bot or message.guild is None or self.client.user is None:
            return
        mentions = (f"<@{self.client.user.id}>", f"<@!{self.client.user.id}>")
        if not any(m in message.content for m in mentions):
            return  # (a reply-ping alone is not a mention of the bot)
        ctx = await self.client.get_context(message)
        if ctx.valid:
            return  # "@bot play ..." is a real command, let it run
        prefix = (await getConfig(message.guild.id))["prefix"]
        embed = discord.Embed(
            description=(
                f"{E.MUSIC} Hey {message.author.mention}! My prefix in this server is `{prefix}`.\n"
                f"Use `{prefix}help` to see my commands, or `{prefix}play <song>` to start music."
            ),
            color=0x000000,
        )
        embed.set_author(name=self.client.user.name, icon_url=self.client.user.display_avatar.url)
        embed.set_footer(text=f"Thanks for choosing {config.NAME}!")
        try:
            await message.channel.send(embed=embed)
        except discord.HTTPException:
            pass
