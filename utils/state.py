from __future__ import annotations

import json
import logging
import os
import time
from typing import Any, Dict, Optional

log = logging.getLogger("shizumusic.state")
STATE_FILE = os.path.join(os.path.dirname(os.path.dirname(__file__)), "db", "bot_state.json")


def _read_state() -> Dict[str, Any]:
    if not os.path.exists(STATE_FILE):
        return {"guilds": {}}
    try:
        with open(STATE_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        log.warning("Could not read bot state file %s", STATE_FILE, exc_info=True)
        return {"guilds": {}}


def _write_state(data: Dict[str, Any]) -> None:
    os.makedirs(os.path.dirname(STATE_FILE), exist_ok=True)
    tmp = STATE_FILE + ".tmp"
    try:
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2)
        os.replace(tmp, STATE_FILE)
    except Exception:
        log.warning("Could not write bot state file %s", STATE_FILE, exc_info=True)


def record_channel(guild_id: int, channel_id: int) -> None:
    data = _read_state()
    guilds = data.setdefault("guilds", {})
    gid_str = str(guild_id)
    entry = guilds.setdefault(gid_str, {})
    entry["channel_id"] = channel_id
    entry["updated_at"] = time.time()
    _write_state(data)


def set_offline_msg(guild_id: int, channel_id: int, message_id: int) -> None:
    data = _read_state()
    guilds = data.setdefault("guilds", {})
    gid_str = str(guild_id)
    entry = guilds.setdefault(gid_str, {})
    entry["channel_id"] = channel_id
    entry["offline_msg_id"] = message_id
    entry["updated_at"] = time.time()
    _write_state(data)


def get_all_guild_states() -> Dict[str, Dict[str, Any]]:
    return _read_state().get("guilds", {})


def clear_offline_msg(guild_id: int) -> None:
    data = _read_state()
    guilds = data.setdefault("guilds", {})
    gid_str = str(guild_id)
    if gid_str in guilds:
        guilds[gid_str]["offline_msg_id"] = None
        _write_state(data)
