"""Music session ownership.

The member who starts a session in a server (by making the bot join / play) owns it.
Only they may change it: queue songs, skip, pause, stop, volume, filters, player buttons...

Safety valve: if the owner leaves the voice channel for SESSION_GRACE seconds, the session
is handed to the next person in the channel who uses a command, so the bot can't get stuck.
"""
from __future__ import annotations

import time
from typing import Optional

from utils import emojis as E

SESSION_GRACE = 60  # seconds the owner may be away before the session can be taken over


def start_session(player, user_id: int) -> None:
    player.session_owner_id = user_id
    player.owner_absent_since = None


def session_owner_id(player) -> Optional[int]:
    return getattr(player, "session_owner_id", None)


def refresh_owner_presence(player, now: Optional[float] = None) -> None:
    """Track whether the owner is still in the bot's voice channel."""
    owner_id = session_owner_id(player)
    channel = getattr(player, "channel", None)
    if owner_id is None or channel is None:
        return
    now = time.monotonic() if now is None else now
    if owner_id in channel.voice_states:
        player.owner_absent_since = None
    elif getattr(player, "owner_absent_since", None) is None:
        player.owner_absent_since = now


def can_control(player, user_id: int, now: Optional[float] = None) -> bool:
    """True only for the session owner (callers check same-voice-channel first).

    Nobody else may queue, skip, edit filters or touch the player while the session lives.
    """
    owner_id = session_owner_id(player)
    return owner_id is None or owner_id == user_id


def denied_text(player) -> str:
    return (
        f"{E.WARNING} Only <@{session_owner_id(player)}> can use this command. "
        "They started the music session in this server."
    )
