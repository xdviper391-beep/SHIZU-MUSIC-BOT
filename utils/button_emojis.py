"""Button emojis: one setting for the whole bot (every server shows the same ones).

The player buttons and the Remix console ask this module for their emoji (`get("pause")`, `get("lofi")` ...).
Out of the box that is the emoji pack in utils/emojis.py (the E.BTN_* ones) and the Remix effect emoji.
The bot owner can change any of them with `.editemojis`; the choices are saved in db/button_emojis.json.

No discord imports in here on purpose, so it can be tested on its own.
"""
from __future__ import annotations

import json
import logging
import os
import re
import unicodedata
from typing import Dict, List, Optional, Tuple

from utils import emojis as E
from utils.config import DB_DIR
from utils.remix import EFFECTS

log = logging.getLogger("testingmusic.button_emojis")

STORE_PATH = DB_DIR / "button_emojis.json"
CUSTOM_RE = re.compile(r"^<(a?):([A-Za-z0-9_]{2,32}):(\d{15,25})>$")

# ── the slots ──────────────────────────────────────────────────────────────────
# (slot, label shown on the button). Player card buttons:
PLAYER_SLOTS: Tuple[Tuple[str, str], ...] = (
    ("previous", "Prev"),
    ("pause", "Pause"),
    ("resume", "Play"),
    ("skip", "Next"),
    ("stop", "Stop"),
    ("rewind", "\u221210s"),
    ("forward", "+10s"),
    ("replay", "Replay"),
    ("shuffle", "Shuffle"),
    ("loop", "Loop"),
    ("autoplay", "Auto"),
    ("remix", "Remix"),
    ("others", "Others"),
)

# Remix console: every effect (emoji comes from utils/remix.py) + the four special buttons.
_CONSOLE_EXTRAS: Tuple[Tuple[str, str, str], ...] = (
    ("bass", "Bass", getattr(E, "REMIX_BASS", "\U0001f5e1\ufe0f")),
    ("vol", "Vol", getattr(E, "REMIX_VOL", "\U0001f4e2")),
    ("clear", "Clear FX", getattr(E, "REMIX_CLEAR", "\U0001f9f9")),
    ("help", "How it works", "\u2139\ufe0f"),
)
REMIX_SLOTS: Tuple[Tuple[str, str], ...] = tuple(
    [(key, fx.label) for key, fx in EFFECTS.items()] + [(slot, label) for slot, label, _ in _CONSOLE_EXTRAS]
)

# slot -> name of the constant in utils/emojis.py (read at call time, so the startup emoji sync is honoured)
_PLAYER_CONSTANTS: Dict[str, str] = {
    "previous": "BTN_PREVIOUS",
    "pause": "BTN_PAUSE",
    "resume": "BTN_RESUME",
    "skip": "BTN_SKIP",
    "stop": "BTN_STOP",
    "rewind": "BTN_REWIND",
    "forward": "BTN_FORWARD",
    "replay": "BTN_REPLAY",
    "shuffle": "BTN_SHUFFLE",
    "loop": "BTN_LOOP",
    "autoplay": "BTN_AUTOPLAY",
    "remix": "REMIX_BTN",
}
_PLAYER_PLAIN: Dict[str, str] = {"remix": getattr(E, "REMIX_BTN", "\U0001f39b\ufe0f"), "others": "\u2699\ufe0f"}
_CONSOLE_PLAIN: Dict[str, str] = {slot: emoji for slot, _, emoji in _CONSOLE_EXTRAS}

ALL_SLOTS = {slot for slot, _ in PLAYER_SLOTS} | {slot for slot, _ in REMIX_SLOTS}


def default(slot: str) -> str:
    """The emoji a slot has when nobody changed it."""
    if slot in _PLAYER_CONSTANTS:
        return getattr(E, _PLAYER_CONSTANTS[slot])
    if slot in _PLAYER_PLAIN:
        return _PLAYER_PLAIN[slot]
    if slot in EFFECTS:
        return EFFECTS[slot].emoji
    return _CONSOLE_PLAIN[slot]


# ── storage ────────────────────────────────────────────────────────────────────
_cache: Optional[Dict[str, str]] = None


def _load() -> Dict[str, str]:
    global _cache
    if _cache is None:
        _cache = {}
        try:
            raw = json.loads(STORE_PATH.read_text(encoding="utf-8"))
            if isinstance(raw, dict):
                _cache = {k: v for k, v in raw.items() if k in ALL_SLOTS and isinstance(v, str) and v}
        except FileNotFoundError:
            pass
        except (OSError, ValueError):
            log.warning("Could not read %s, using the default button emojis", STORE_PATH, exc_info=True)
    return _cache


def _save() -> None:
    data = _load()
    try:
        STORE_PATH.parent.mkdir(parents=True, exist_ok=True)
        tmp = STORE_PATH.with_suffix(".tmp")
        tmp.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
        os.replace(tmp, STORE_PATH)
    except OSError:
        log.warning("Could not save %s", STORE_PATH, exc_info=True)


def get(slot: str) -> str:
    """The emoji to put on a button (a unicode emoji or `<:name:id>` / `<a:name:id>`)."""
    return _load().get(slot) or default(slot)


def stored(slot: str) -> Optional[str]:
    """What the owner saved for this slot, or None when it still uses the default."""
    return _load().get(slot)


def set_emoji(slot: str, value: Optional[str]) -> None:
    """Save an emoji for a slot (None = back to the default)."""
    if slot not in ALL_SLOTS:
        raise KeyError(slot)
    data = _load()
    if value:
        data[slot] = value
    else:
        data.pop(slot, None)
    _save()


def reset(slots: Optional[List[str]] = None) -> None:
    """Back to the defaults (the given slots, or everything)."""
    data = _load()
    for slot in list(data) if slots is None else slots:
        data.pop(slot, None)
    _save()


# ── checking what the owner typed ──────────────────────────────────────────────
def parse(text: str) -> Optional[str]:
    """Return the emoji if `text` is exactly one emoji, else None.

    Accepts `<:name:id>`, `<a:name:id>` and normal unicode emoji. Anything that is not an emoji (letters, digits,
    spaces ...) is refused here; the editor also lets Discord have the last word before anything is saved.
    """
    text = (text or "").strip()
    if CUSTOM_RE.match(text):
        return text
    if not text or len(text) > 24:
        return None
    if "\u20e3" in text and text[0] in "0123456789#*":     # keycap emoji, e.g. 1 + FE0F + 20E3
        return text
    for ch in text:
        if ord(ch) < 128 or unicodedata.category(ch)[0] in "LNZ":
            return None
    return text
