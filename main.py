"""Shizu Music - entry point.

    1. pip install -r requirements.txt
    2. copy .env.example to .env and fill in DISCORD_TOKEN
    3. install FFmpeg (or set FFMPEG_PATH in .env)
    4. python main.py
"""
from __future__ import annotations

import asyncio
import logging
import os
import signal
import sys
from threading import Thread

import discord

from utils import config  # loads .env
from utils.privacy import install_redaction

if config.ENABLE_JISHAKU:
    os.environ.setdefault("JISHAKU_NO_DM_TRACEBACK", "False")
    os.environ.setdefault("JISHAKU_HIDE", "True")
    os.environ.setdefault("JISHAKU_NO_UNDERSCORE", "True")
    os.environ.setdefault("JISHAKU_FORCE_PAGINATOR", "True")

from core.TestingMusic import TestingMusic  # noqa: E402


def keep_alive() -> None:
    """Optional tiny web server for hosts that require an open port (KEEP_ALIVE=true)."""
    from flask import Flask

    app = Flask(__name__)

    @app.route("/")
    def home():
        return "Shizu Music"

    def run():
        app.run(host="0.0.0.0", port=config.KEEP_ALIVE_PORT)

    Thread(target=run, daemon=True).start()


async def main() -> None:
    if not config.TOKEN:
        sys.exit("Missing bot token. Copy .env.example to .env and set DISCORD_TOKEN=your_token")

    if config.KEEP_ALIVE:
        keep_alive()

    bot = TestingMusic()
    try:
        loop = asyncio.get_running_loop()
        for sig in (signal.SIGINT, signal.SIGTERM):
            try:
                loop.add_signal_handler(sig, lambda: asyncio.create_task(bot.close()))
            except (NotImplementedError, AttributeError):
                pass
    except Exception:
        pass

    async with bot:
        await bot.start(config.TOKEN)


if __name__ == "__main__":
    discord.utils.setup_logging(level=logging.INFO)
    install_redaction()  # keep the token / API keys out of logs
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        pass
