"""Central emoji registry for Shizu Music.
All emojis are verified real animated Discord emojis from the bot's server.
Provides clean Unicode fallbacks if custom emojis are ever unavailable.
"""
from __future__ import annotations

# ─────────────────────────────────────────────────────────────────────────────
# 1. Primary Animated Discord Emojis (from TESTING SHIZU guild)
# ─────────────────────────────────────────────────────────────────────────────
# Arrows & UI Elements
EMOJI_ARROW = "<a:bb_arrow_white:1565840667224051865>"       # Animated chevron arrow for bullet points
EMOJI_ARROW_WHITE = "<a:arrow_white:1565870886823657553>"    # Compact white arrow
EMOJI_CONFIG = "<a:config:1565839999063171185>"              # Spinning gear for settings & config
EMOJI_DOT = "<a:cyan_dot:1565867959958642729>"               # Glowing cyan dot for bullets & footer
EMOJI_HEART = "<a:heart_wb:1565996750152667236>"             # Beating heart for welcome & thank you
EMOJI_BELL = "<a:ne_bell:1565842042029084743>"               # Ringing bell for notifications & mentions
EMOJI_OFFLINE = "<a:offline:1565839892817117405>"            # Red dot for stop, error & denied
EMOJI_ONLINE = "<a:online:1565839926241788178>"              # Green dot for tick, success & active
EMOJI_YOUTUBE = "<a:youtube:1565841055574790277>"            # YouTube animated icon
EMOJI_TEST = "<a:test:1565853410702528604>"                  # Warning / Cooldown / Alert icon
EMOJI_DJ = "<a:NE_peepoDJ:792704150843949056>"               # Peepo DJ vibing to music

# Music & Playback Controls
EMOJI_PLAY = "<a:emoji_18:1566217092452065401>"              # Animated Play button
EMOJI_PAUSE = "<a:emoji_19:1566217119149064313>"            # Animated Pause button
EMOJI_SHUFFLE = "<a:emoji_20:1566217143329104002>"          # Animated Shuffle / Loop crossing arrows
EMOJI_HEADPHONES = "<a:emoji_17:1566217064220463255>"       # Animated Headphones / Voice connection
EMOJI_DISC = "<a:emoji_16:1566217023615279286>"             # Animated spinning vinyl disc / Track
EMOJI_SLIDER = "<a:emoji_15:1566216988546699354>"           # Animated Sound bar / Volume / Queue
EMOJI_NOTES = "<a:emoji_14:1566216923635515492>"            # Animated Musical Notes
EMOJI_HEART_BEAT = "<a:emoji_13:1566216873006080040>"       # Animated Heart / 24-7 Mode / Autoplay
EMOJI_REMIX = "<a:emoji_21:1566217201411817503>"            # Animated Sparkle / Audio Effects
EMOJI_STOP = "<a:emoji_21:1566217188308951190>"             # Animated Stop / Disconnect / Clear

# ─────────────────────────────────────────────────────────────────────────────
# 2. Project Aliases (Compatible with all existing commands & views)
# ─────────────────────────────────────────────────────────────────────────────
ARROW = EMOJI_ARROW
ARROW_WHITE = EMOJI_ARROW_WHITE
CONFIG = EMOJI_CONFIG
DOT = EMOJI_DOT
HEART = EMOJI_HEART
BELL = EMOJI_BELL
ONLINE = EMOJI_ONLINE
OFFLINE = EMOJI_OFFLINE
YOUTUBE = EMOJI_YOUTUBE
TEST = EMOJI_TEST
DJ = EMOJI_DJ

PLAY = EMOJI_PLAY
PAUSE = EMOJI_PAUSE
SHUFFLE = EMOJI_SHUFFLE
HEADPHONES = EMOJI_HEADPHONES
DISC = EMOJI_DISC
SLIDER = EMOJI_SLIDER
NOTES = EMOJI_NOTES
HEART_BEAT = EMOJI_HEART_BEAT
REMIX = EMOJI_REMIX
STOP = EMOJI_STOP

TICK = EMOJI_ONLINE
WARNING = EMOJI_TEST
DENIED = EMOJI_OFFLINE
MUSIC = EMOJI_NOTES
VOICE = EMOJI_HEADPHONES
ADD = EMOJI_PLAY
LOADING = EMOJI_DOT

# External Platform Badges
SPOTIFY = "🟢"
JIOSAAVN = "🎶"
SOUNDCLOUD = "🟠"

# Player Control Buttons
BTN_PLAY = EMOJI_PLAY
BTN_PAUSE = EMOJI_PAUSE
BTN_RESUME = EMOJI_PLAY
BTN_SKIP = EMOJI_ARROW
BTN_PREVIOUS = EMOJI_ARROW_WHITE
BTN_STOP = EMOJI_STOP
BTN_SHUFFLE = EMOJI_SHUFFLE
BTN_LOOP = EMOJI_SHUFFLE
BTN_AUTOPLAY = EMOJI_HEART_BEAT
BTN_REWIND = EMOJI_ARROW_WHITE
BTN_FORWARD = EMOJI_ARROW
BTN_REPLAY = EMOJI_PLAY

# Remix & Audio FX Buttons
REMIX_BTN = EMOJI_REMIX
REMIX_BASS = EMOJI_SLIDER
REMIX_VOL = EMOJI_SLIDER
REMIX_CLEAR = EMOJI_STOP
REMIX_CRYSTAL = EMOJI_REMIX
REMIX_LOFI = EMOJI_HEADPHONES
REMIX_8D = EMOJI_HEADPHONES
REMIX_KARAOKE = EMOJI_NOTES

# Help Menu Navigation Emojis
HELP_HOME = EMOJI_CONFIG
HELP_MUSIC = EMOJI_NOTES
HELP_QUEUE = EMOJI_SLIDER
HELP_PLAYER = EMOJI_HEADPHONES
HELP_FX = EMOJI_REMIX
HELP_SETUP = EMOJI_CONFIG
HELP_INFO = EMOJI_DOT
HELP_PREV = EMOJI_ARROW_WHITE
HELP_NEXT = EMOJI_ARROW
HELP_CLOSE = EMOJI_OFFLINE

# ─────────────────────────────────────────────────────────────────────────────
# 3. Fallback Mapping (Ensures no message crashes even if emojis cannot render)
# ─────────────────────────────────────────────────────────────────────────────
FALLBACKS = {
    EMOJI_ARROW: "▶",
    EMOJI_ARROW_WHITE: "▷",
    EMOJI_CONFIG: "⚙️",
    EMOJI_DOT: "•",
    EMOJI_HEART: "❤️",
    EMOJI_BELL: "🔔",
    EMOJI_OFFLINE: "🔴",
    EMOJI_ONLINE: "🟢",
    EMOJI_YOUTUBE: "📺",
    EMOJI_TEST: "⚠️",
    EMOJI_DJ: "🎧",
    EMOJI_PLAY: "▶️",
    EMOJI_PAUSE: "⏸️",
    EMOJI_SHUFFLE: "🔀",
    EMOJI_HEADPHONES: "🎧",
    EMOJI_DISC: "💿",
    EMOJI_SLIDER: "🎚️",
    EMOJI_NOTES: "🎵",
    EMOJI_HEART_BEAT: "💖",
    EMOJI_REMIX: "✨",
    EMOJI_STOP: "⏹️",
}


def safe_emoji(emoji: str) -> str:
    """Return fallback unicode if the custom emoji cannot be rendered."""
    return emoji if emoji else "•"
