"""Remix engine: effect definitions, state and the FFmpeg filter compiler.

No discord imports in here on purpose, so the maths can be tested on its own.

How it works
------------
The music player (cogs/commands/music.py `MusicPlayer`) plays through FFmpeg. Every effect is a small
recipe that is merged into ONE `-af` chain (see `build_filters`). The result is stored ON the player
(`player.audio_filters`, `player.speed`, `player.volume`) and `player.reload_audio()` restarts FFmpeg at
the current position so the change is heard at once. The Remix cog, the filter commands and the buttons
all go through `commit()` below, so there is exactly one effect state per guild: `player.remix_state`.

    Speed / Slow      atempo                         (faster / slower, same pitch)
    High / Low        asetrate + aresample + atempo  (higher / lower pitch, same speed)
    Bass              bass shelf, 0 - 25 dB          Deep: extra sub-bass peaks
    LPF / HPF         lowpass / highpass
    Spatial / 8D / Atmos   stereowiden + apulsator (+ a little air)  (a simulation, not licensed Dolby Atmos)
    Crystal HD        gentle clarity EQ (less mud, more presence + air)
    Lofi              soft low-pass + warm EQ + tape wobble (vibrato)
    Echo / Reverb     aecho
    Stutter           tremolo      Karaoke   stereotools (centre cut)

Honest limits
-------------
* The dB numbers are NOMINAL: neighbouring EQ filters overlap, so the real peak can read higher. An
  `alimiter` at the end of the chain stops the EQ boosts (big bass / Deep) from clipping.
* Volume is applied AFTER FFmpeg (live, no restart). Above 100% it is plain digital gain, so loud
  tracks can still clip there.
* Every chain is test-run through your FFmpeg before it is used (`validate_chain`), so an effect your
  build doesn't have is refused instead of killing the stream.
"""
from __future__ import annotations

import asyncio
import copy
import logging
import os
from dataclasses import dataclass, field
from typing import Dict, Iterable, List, Optional, Tuple

from utils import emojis as E

log = logging.getLogger("testingmusic.remix")

SAMPLE_RATE = 48000       # what discord.py asks FFmpeg for (48 kHz stereo s16le)
MAX_VOLUME = 300          # player volume, percent
MIN_VOLUME = 1
MAX_BASS_DB = 25
BASS_STEPS: Tuple[int, ...] = (0, 6, 12, 18, 25)          # what the Bass button cycles through
VOLUME_STEPS: Tuple[int, ...] = (100, 150, 200, 250, 300)  # what the Vol button cycles through



# ═════════════════════════════════════════════════════════════════════════════
#  1. EFFECT LIST  (order = button order)
# ═════════════════════════════════════════════════════════════════════════════
@dataclass(frozen=True)
class Effect:
    key: str
    label: str
    emoji: str
    name: str            # long name for "Effects: ..."
    group: str           # effects with the same group replace each other ("" = free)
    blurb: str           # one line for the help message


_EFFECT_LIST: List[Effect] = [
    # row 0 - quality + space
    Effect("crystal",    "Crystal",  getattr(E, "REMIX_CRYSTAL", "\U0001f48e"), "Crystal HD",   "",      "clearer vocals + air, less mud"),
    Effect("spatial",    "Spatial",  getattr(E, "VOICE", "\U0001f3a7"), "Spatial",      "space", "wide, slowly moving stage (best on headphones)"),
    Effect("eight_d",    "8D",       getattr(E, "REMIX_8D", "\U0001f300"), "8D",           "space", "sound circles around your head"),
    Effect("atmos",      "Atmos",    getattr(E, "MUSIC", "\U0001f30c"), "Atmos style",  "space", "big 3D / surround feel (simulated)"),
    Effect("lofi",       "Lofi",     getattr(E, "REMIX_LOFI", "\U0001f4fb"), "Lofi",         "",      "warm, soft, tape wobble"),
    # row 1 - speed / pitch / pulse
    Effect("speed",      "Speed",    getattr(E, "BTN_FORWARD", "\u26a1"),     "Speed",        "tempo", "faster, same pitch"),
    Effect("slow",       "Slow",     getattr(E, "BTN_REWIND", "\U0001f40c"), "Slow",         "tempo", "slower, same pitch"),
    Effect("pitch_up",   "High",     getattr(E, "BTN_SKIP", "\U0001f43f\ufe0f"), "Pitch up",   "pitch", "higher pitch, same speed"),
    Effect("pitch_down", "Low",      getattr(E, "BTN_PREVIOUS", "\U0001f479"), "Pitch down",   "pitch", "lower pitch, same speed"),
    Effect("stutter",    "Stut",     getattr(E, "BTN_LOOP", "\U0001f504"), "Stutter",      "",      "choppy on/off pulse"),
    # row 2 - (Bass + Vol are steppers, drawn by the cog) + filters + echo
    Effect("lpf",        "LPF",      getattr(E, "SOUNDCLOUD", "\U0001f30a"), "Low-pass",     "",      "muffled, keeps the lows"),
    Effect("hpf",        "HPF",      getattr(E, "SPOTIFY", "\U0001f52a"), "High-pass",    "",      "thin, keeps the highs"),
    Effect("echo",       "Echo",     getattr(E, "VOICE", "\U0001f50a"), "Echo",         "echo",  "repeating tail"),
    # row 3
    Effect("reverb",     "Reverb",   getattr(E, "MUSIC", "\U0001f3db\ufe0f"), "Reverb", "echo",  "small room space"),
    Effect("deep",       "Deep",     getattr(E, "REMIX_BASS", "\U0001f4a5"), "Deep bass",    "",      "extra sub-bass under everything"),
    Effect("karaoke",    "Karaoke",  getattr(E, "REMIX_KARAOKE", "\U0001f3a4"), "Karaoke",      "",      "cuts the centre vocals"),
]
EFFECTS: Dict[str, Effect] = {e.key: e for e in _EFFECT_LIST}

# Presets for `.fx <name>` and `.filter enable`. "bass" is the bass dB (0 = leave alone).
PRESETS: Dict[str, dict] = {
    "crystal":      {"fx": {"crystal"}},
    "spatial":      {"fx": {"spatial", "crystal"}},
    "atmos":        {"fx": {"atmos", "crystal"}},
    "8d":           {"fx": {"eight_d"}},
    "lofi":         {"fx": {"lofi"}},
    "nightcore":    {"fx": {"speed", "pitch_up"}},
    "vaporwave":    {"fx": {"slow", "pitch_down"}},
    "slowed":       {"fx": {"slow", "lofi"}},
    "slowedreverb": {"fx": {"slow", "reverb", "lofi"}},
    "bassboost":    {"fx": {"crystal"}, "bass": 18},
    "megabass":     {"fx": {"deep"}, "bass": 25},
    "party":        {"fx": {"atmos", "crystal"}, "bass": 12},
    "headphones":   {"fx": {"spatial", "crystal"}, "bass": 6},
    "echo":         {"fx": {"echo"}},
    "reverb":       {"fx": {"reverb"}},
    "karaoke":      {"fx": {"karaoke"}},
}


# ═════════════════════════════════════════════════════════════════════════════
#  2. STATE
# ═════════════════════════════════════════════════════════════════════════════
@dataclass
class RemixState:
    active: set = field(default_factory=set)
    bass_db: int = 0
    volume: int = 100
    preset: Optional[str] = None

    # -- read ------------------------------------------------------------------
    @property
    def is_default(self) -> bool:
        return not self.active and self.bass_db == 0 and self.volume == 100

    @property
    def needs_limiter(self) -> bool:
        """True when the chain ends with a limiter (big bass boosts clip without one)."""
        return self.bass_db > 12 or "deep" in self.active

    @property
    def loud(self) -> bool:
        """Volume above 100% is digital gain applied after FFmpeg (no limiter there)."""
        return self.volume > 100

    @property
    def label(self) -> str:
        if self.preset:
            return self.preset
        names = [e.name for e in _EFFECT_LIST if e.key in self.active]
        if self.bass_db:
            names.insert(0, f"Bass {self.bass_db} dB")
        return " + ".join(names)

    # -- change ----------------------------------------------------------------
    def toggle(self, key: str) -> None:
        self.preset = None
        if key in self.active:
            self.active.discard(key)
            return
        group = EFFECTS[key].group
        if group:
            self.active -= {k for k, e in EFFECTS.items() if e.group == group}
        self.active.add(key)

    def cycle_bass(self) -> int:
        self.preset = None
        higher = [s for s in BASS_STEPS if s > self.bass_db]
        self.bass_db = higher[0] if higher else 0
        return self.bass_db

    def cycle_volume(self) -> int:
        self.preset = None
        higher = [s for s in VOLUME_STEPS if s > self.volume]
        self.volume = higher[0] if higher else VOLUME_STEPS[0]
        return self.volume

    def set_bass(self, db: int) -> None:
        self.preset = None
        self.bass_db = max(0, min(MAX_BASS_DB, int(db)))

    def set_volume(self, level: int) -> None:
        self.volume = max(MIN_VOLUME, min(MAX_VOLUME, int(level)))

    def clear(self, keep_volume: bool = True) -> None:
        self.active = set()
        self.bass_db = 0
        self.preset = None
        if not keep_volume:
            self.volume = 100

    def apply_preset(self, name: str) -> bool:
        data = PRESETS.get(name.lower())
        if data is None:
            return False
        self.active = set(data["fx"])
        self.bass_db = int(data.get("bass", 0))
        self.preset = name.lower()
        return True


# ═════════════════════════════════════════════════════════════════════════════
#  3. COMPILER  ->  FFmpeg `-af` chain
# ═════════════════════════════════════════════════════════════════════════════
@dataclass(frozen=True)
class FilterChain:
    af: str = ""          # value for FFmpeg's -af ("" = no filters at all)
    speed: float = 1.0    # net playback speed of the chain (source seconds per output second)

    @property
    def active(self) -> bool:
        return bool(self.af)


def _atempo(factor: float) -> List[str]:
    """`atempo` stages for `factor` (older FFmpeg builds only accept 0.5 .. 2.0 per stage)."""
    parts: List[str] = []
    while factor > 2.0:
        parts.append("atempo=2.0")
        factor /= 2.0
    while factor < 0.5:
        parts.append("atempo=0.5")
        factor /= 0.5
    if abs(factor - 1.0) > 1e-3:
        parts.append(f"atempo={factor:.4f}")
    return parts


def build_filters(state: RemixState) -> FilterChain:
    """The FFmpeg chain for this state (`FilterChain()` = everything off).

    Order: tempo / pitch first (so every later time based effect - echo delay, tremolo, 8D sweep - runs
    in real time), then band limits and EQ, then stereo effects, echo, and the limiter last.
    """
    active = state.active
    f: List[str] = []

    # -- speed / pitch (Speed, Slow, High, Low) --
    speed = 1.25 if "speed" in active else 0.8 if "slow" in active else 1.0
    pitch = 1.25 if "pitch_up" in active else 0.8 if "pitch_down" in active else 1.0
    if pitch != 1.0:
        # asetrate changes pitch AND tempo by `pitch`; atempo then corrects the tempo to `speed`.
        f += [f"asetrate={round(SAMPLE_RATE * pitch)}", f"aresample={SAMPLE_RATE}"]
    f += _atempo(speed / pitch)

    # -- band limits --
    if "hpf" in active:
        f.append("highpass=f=800")
    if "lpf" in active:
        f.append("lowpass=f=800")
    elif "lofi" in active:
        f += ["highpass=f=70", "lowpass=f=4500"]

    # -- equalising --
    if state.bass_db:
        f.append(f"bass=g={state.bass_db}:f=110:w=0.6")
    if "deep" in active:
        f += ["equalizer=f=42:t=q:w=0.8:g=7", "equalizer=f=70:t=q:w=1:g=4"]
    if "crystal" in active:
        f += ["equalizer=f=250:t=q:w=1:g=-2", "equalizer=f=3000:t=q:w=0.7:g=2.5", "treble=g=3:f=8000:w=0.7"]
    if "lofi" in active:
        f.append("equalizer=f=220:t=q:w=1:g=2.5")

    # -- stereo space (Spatial / 8D / Atmos) --
    if "eight_d" in active:
        f.append("apulsator=mode=sine:hz=0.2:amount=1")
    elif "atmos" in active:
        f += ["stereowiden=delay=18:feedback=0.25:crossfeed=0.25:drymix=0.85",
              "apulsator=mode=sine:hz=0.05:amount=0.3",
              "treble=g=2.5:f=9000:w=0.7"]
    elif "spatial" in active:
        f += ["stereowiden=delay=15:feedback=0.2:crossfeed=0.2:drymix=0.9",
              "apulsator=mode=sine:hz=0.08:amount=0.35"]

    # -- modulation --
    if "lofi" in active:
        f.append("vibrato=f=1.5:d=0.1")          # tape wobble
    if "stutter" in active:
        f.append("tremolo=f=7:d=0.95")
    if "karaoke" in active:
        f.append("stereotools=mlev=0.015625")    # centre channel (the vocals) almost out

    # -- echo / reverb --
    if "echo" in active:
        f.append("aecho=0.8:0.85:350:0.45")
    elif "reverb" in active:
        f.append("aecho=0.8:0.88:40|70|110|160:0.45|0.35|0.28|0.2")
    elif "atmos" in active:
        f.append("aecho=0.85:0.85:45:0.25")      # a touch of room for the Atmos feel

    if state.needs_limiter:
        f.append("alimiter=limit=0.95:attack=5:release=50:level=0")

    if not f:
        return FilterChain()
    # Fix the format first: float samples (EQ boosts can't clip mid-chain), stereo, 48 kHz
    # (asetrate needs the exact base rate, a few filters need stereo).
    f.insert(0, f"aformat=sample_fmts=fltp:sample_rates={SAMPLE_RATE}:channel_layouts=stereo")
    return FilterChain(",".join(f), speed)


def summarize(state: RemixState) -> str:
    """One line for the panel header."""
    parts = [f"Effects: **{state.label or 'off'}**"]
    if state.bass_db and state.preset:
        parts[0] = f"Effects: **{state.label}** (Bass {state.bass_db} dB)"
    parts.append(f"Volume: **{state.volume}%**")
    return "  |  ".join(parts)


def effect_keys(keys: Iterable[str]) -> List[str]:
    return [k for k in EFFECTS if k in set(keys)]


def get_state(player) -> RemixState:
    """THE effect state of a guild: it lives on the player (`player.remix_state`), created on first use.

    The player owns the volume (`player.volume`, changed by `.volume`, the Vol button and the console),
    so it is copied into the state on every call: commands and buttons can never disagree about it.
    """
    state = getattr(player, "remix_state", None)
    if not isinstance(state, RemixState):
        state = RemixState()
        player.remix_state = state
    try:
        volume = int(getattr(player, "volume", 100) or 100)
    except (TypeError, ValueError):
        volume = 100
    state.volume = max(MIN_VOLUME, min(MAX_VOLUME, volume))
    return state


def banner_chips(state: RemixState) -> List[str]:
    """Short labels for the now-playing banner (Bass 18 dB, Atmos, Vol 200% ...)."""
    chips = []
    if state.bass_db:
        chips.append(f"Bass {state.bass_db} dB")
    chips += [e.name for e in _EFFECT_LIST if e.key in state.active]
    if state.volume != 100:
        chips.append(f"Vol {state.volume}%")
    return chips


# ═════════════════════════════════════════════════════════════════════════════
#  4. ENGINE  (shared by the Remix cog, the filter commands and the buttons)
# ═════════════════════════════════════════════════════════════════════════════
OFF_WORDS = {"off", "clear", "none", "reset", "disable"}

# Effects the installed FFmpeg can't run (filled by `probe_effects`, mutated in place).
UNSUPPORTED: set = set()


class RemixError(Exception):
    """Something went wrong applying effects (the message is safe to show to users)."""


def ffmpeg_executable() -> str:
    try:
        from utils.config import FFMPEG_PATH
    except Exception:  # standalone use / tests: no discord, no .env
        FFMPEG_PATH = os.getenv("FFMPEG_PATH", "")
    return FFMPEG_PATH or "ffmpeg"


def lock_for(player) -> asyncio.Lock:
    """One lock per player: effect changes are applied one at a time."""
    lock = getattr(player, "remix_lock", None)
    if not isinstance(lock, asyncio.Lock):
        lock = asyncio.Lock()
        player.remix_lock = lock
    return lock


async def validate_chain(af: str, *, timeout: float = 10.0) -> Optional[str]:
    """Test-run `af` on 0.2 s of silence. None = the installed FFmpeg accepts it, else the error text."""
    try:
        proc = await asyncio.create_subprocess_exec(
            ffmpeg_executable(), "-hide_banner", "-loglevel", "error", "-nostdin",
            "-f", "lavfi", "-i", f"anullsrc=r={SAMPLE_RATE}:cl=stereo", "-t", "0.2",
            "-af", af, "-f", "null", "-",
            stdout=asyncio.subprocess.DEVNULL, stderr=asyncio.subprocess.PIPE,
        )
    except (FileNotFoundError, PermissionError, OSError):
        return None  # no FFmpeg at all: playback reports that itself
    try:
        _, err = await asyncio.wait_for(proc.communicate(), timeout)
    except asyncio.TimeoutError:
        proc.kill()
        return None  # can't tell: let it through
    if proc.returncode == 0:
        return None
    lines = err.decode(errors="replace").strip().splitlines()
    return lines[-1] if lines else "FFmpeg rejected the filter chain"


async def probe_effects() -> set:
    """Find the effects the installed FFmpeg can't run and remember them in `UNSUPPORTED`."""
    sem = asyncio.Semaphore(4)

    async def check(key: str) -> Optional[str]:
        chain = build_filters(RemixState(active={key}))
        async with sem:
            err = await validate_chain(chain.af)
        if err:
            log.warning("FFmpeg can't run the %r effect: %s", key, err)
            return key
        return None

    results = await asyncio.gather(*(check(k) for k in EFFECTS))
    bad = {k for k in results if k}
    UNSUPPORTED.clear()
    UNSUPPORTED.update(bad)
    return bad


async def apply_state(player, state: RemixState, *, reload: bool = True) -> None:
    """Make `state` the player's real settings: volume, `-af` chain, speed. Raises RemixError, changing nothing,
    if FFmpeg can't run it. Call with `lock_for(player)` held (see `commit`)."""
    blocked = [EFFECTS[k].name for k in sorted(state.active) if k in UNSUPPORTED]
    if blocked:
        raise RemixError(f"Your FFmpeg build can't run: {', '.join(blocked)}.")
    chain = build_filters(state)
    if chain.af:
        error = await validate_chain(chain.af)
        if error:
            log.warning("FFmpeg refused the chain %r: %s", chain.af, error)
            raise RemixError("Your FFmpeg build refused that effect combination.")

    changed = chain.af != player.audio_filters or abs(chain.speed - player.speed) > 1e-6
    player.set_volume(state.volume)          # live: no restart needed
    player.audio_filters = chain.af
    player.speed = chain.speed
    player.remix_state = state
    if changed and reload and player.current is not None:
        try:
            await player.reload_audio()      # restarts FFmpeg at the current position
        except Exception as exc:
            log.warning("Could not restart the audio with the new effects", exc_info=True)
            raise RemixError("Couldn't restart the audio with the new effects. Try again.") from exc


async def commit(player, new: RemixState, *, reload: bool = True) -> None:
    async with lock_for(player):
        await apply_state(player, new, reload=reload)
    # Optional hook: something that wants to know when the effects changed can hang a callback here.
    notify = getattr(player, "on_remix_change", None)
    if callable(notify):
        try:
            notify()
        except Exception:
            log.debug("on_remix_change callback failed", exc_info=True)


async def set_preset(player, name: str) -> Tuple[bool, str]:
    """Used by `.fx` and `.filter`. Returns (ok, note for the user)."""
    key = name.lower().replace(" ", "").replace("-", "")
    new = copy.deepcopy(get_state(player))
    if key in OFF_WORDS:
        new.clear(keep_volume=True)
        await commit(player, new)
        return True, ""
    key = {"eightd": "8d", "bass": "bassboost"}.get(key, key)
    if not new.apply_preset(key):
        return False, f"Unknown preset `{name}`."
    note = ""
    dropped = [EFFECTS[k].name for k in sorted(new.active) if k in UNSUPPORTED]
    if dropped:
        new.active -= UNSUPPORTED
        note = f"Skipped {', '.join(dropped)}: your FFmpeg build can't run it."
    await commit(player, new)
    return True, note
