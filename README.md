# Shizu Music

Developed by **viper & prashu**.

One merged music bot (the full `olympus-music-bot` + the `olympus-music-standalone` version),
updated for current libraries. Prefix **and** slash commands, interactive player buttons,
audio filters, queue / loop / autoplay.

**Music engine:** everything plays through **FFmpeg + yt-dlp** (no Lavalink, no Wavelink). Install FFmpeg on your system
(or set `FFMPEG_PATH` in `.env`). The Remix console, `fx`, `bass`, `volume` and `filter` commands all share ONE effect
state per server, stored on the music player.

## Setup on Termux (Android)

```bash
termux-setup-storage                      # one time: allow storage access
pkg install -y unzip
cp ~/storage/downloads/shizumusic.zip ~ && cd ~ && unzip shizumusic.zip && cd shizumusic
bash setup_termux.sh                      # installs everything, asks for the bot token, starts the bot
```

When the bot is online the console prints the **invite link**. Next time just run `bash start.sh`.
Enable **Message Content Intent** on the Bot page of the Developer Portal first.

## Setup

```bash
python -m venv .venv && source .venv/bin/activate     # Windows: .venv\Scripts\activate
pip install -r requirements.txt
cp .env.example .env                                   # then edit .env
python main.py
```

In the Discord Developer Portal enable **Message Content Intent** (the only privileged intent used).

### `.env`

| Variable | Purpose |
|---|---|
| `DISCORD_TOKEN` | Bot token (required). `TOKEN` also works. |
| `BOT_PREFIX` | Default prefix, `.` if blank. A server that already has a prefix saved in `db/prefix.db` keeps it (delete that file to reset everyone to `.`). |
| `FFMPEG_PATH` | Full path to the FFmpeg executable (blank = `ffmpeg` on PATH). |
| `YTDL_COOKIEFILE` | Optional cookies.txt for YouTube bot checks / age-restricted videos. |
| `OWNER_IDS` | Comma-separated owner user IDs (your Discord ID, not hard-coded anywhere). Blank = the application owner. |
| `ENABLE_JISHAKU` | `true` loads jishaku (owner-only code execution). Off by default. |
| `INACTIVITY_TIMEOUT` | Seconds alone in voice before leaving (default 120). |
| `SYNC_COMMANDS` | Sync slash commands on start (default true). |
| `KEEP_ALIVE` / `PORT` | Tiny Flask web server for hosts that need an open port. |
| `SPOTIFY_CLIENT_ID` / `SPOTIFY_CLIENT_SECRET` | Optional: lets the bot read Spotify links (it looks the tracks up and plays the matching YouTube audio). |

## Player buttons

The now-playing card has just four buttons, so the channel stays clean on every song (grey = off, green = on):

| Auto | Pause / Play | Next | Others |
|---|---|---|---|

**Others** opens a private panel (only you see it, same as the Remix console) with the rest:

| Row | Buttons |
|---|---|
| 1 | Prev, -10s, +10s, Replay |
| 2 | Shuffle, Loop (green while on), Remix, Stop |

**Remix** swaps that panel for the Remix console (every effect) in the same private message; **Back** returns.
**One message for everything.** The reply to a command or button ("Added … to the queue", "Skipped by …",
"Paused by …", effects, volume, loop ...) is written into the player card itself: reply line, then the poster,
then the buttons. Nothing is posted next to the card. `skip` / `play` on an idle player put their reply on the
next song's card. Without a card (nothing playing yet, `join`, `stop`, errors) a normal reply message is used.

Only one card is kept in the channel: a new song's card replaces the old one, and when the session ends the
last card stays without buttons.

## Button emojis (`.editemojis`)

Bot owner only. `.editemojis` opens a panel with a button for every player button and every Remix console
button (two pages). Tap one, send the new emoji, done. Normal and animated emoji from any server work; one from
a server the bot is not in is copied into the bot's own application emoji so it shows the same everywhere. The
choice is saved once in `db/button_emojis.json` and applies to **every server**, from the next player message
(or console) on. Type `reset` in the pop-up to go back to the emoji pack in `utils/emojis.py`.

## Remix console

`.remix` opens the console (**Others > Remix** on the player card opens it privately).
Grey = off, green = on (Clear FX is red while there is something to clear). Other commands: `.fx <preset|off>`, `.bass <0-25>`, `.volume <1-300>`.

| Row | Buttons |
|---|---|
| 1 | Speed, Slow, High (pitch up), Low (pitch down) |
| 2 | **Bass** (taps through 6 / 12 / 18 / 25 dB), Deep, LPF, HPF |
| 3 | Echo, Reverb, Stutter, **Vol** (150 / 200 / 250 / 300%) |
| 4 | Crystal HD, Spatial, 8D, Atmos style |
| 5 | Lofi, Karaoke, Clear FX, How it works |

Presets: `crystal spatial atmos 8d lofi nightcore vaporwave slowed slowedreverb bassboost megabass party headphones echo reverb karaoke`.

Speed/Slow, High/Low, Echo/Reverb and Spatial/8D/Atmos replace each other, everything else stacks. Effects stay on between
songs. Session ownership rules apply (only the session owner can change effects).

**How it works:** the console, `.fx`, `.bass`, `.filter` and the buttons all change the same per-server state
(`utils/remix.py`). That state is compiled to one FFmpeg `-af` chain, test-run through *your* FFmpeg first (a chain it
rejects is refused and nothing changes), stored on the player, and FFmpeg is restarted at the current position so you hear
it at once (expect a very short gap). **Volume** is live gain and never restarts the song. On start the bot also checks
which effects your FFmpeg build can run; any it can't are greyed out in the console.

**What to expect (honest notes)**

* **Bass dB is nominal.** It is a bass shelf (110 Hz) from 0 to 25 dB. A limiter is added automatically above 12 dB and for
  Deep, so big bass doesn't clip. Treat the number as a strength scale, not a measured level.
* **Volume above 100% is digital gain** applied after FFmpeg, so loud tracks can still crackle there (no limiter on that
  stage). Stay at or below ~150% for loud music.
* **Speed / Slow / High / Low** keep the progress position and seek buttons exact (the player counts the real playback speed).
* **Spatial / 8D / Atmos style** are stereo effects (stereo widening + a slow left/right sweep). They feel 3D on headphones
  but are not licensed Dolby Atmos and are not HRTF binaural audio.
* **Crystal HD** is a gentle clarity EQ (less mud, more presence and air). The real limits on "Spotify quality" are the
  source (YouTube ~128-160 kbps) and the Discord channel bitrate: set the voice channel bitrate to the maximum.
* The filter chains were verified against FFmpeg 6.1 (every effect and preset, speed/pitch timing, clipping). The bot itself
  was not run against live Discord while it was written (no network), and the audio itself needs your ears.

## Banner

The now-playing banner is drawn with Pillow in `utils/banner.py` (blurred artwork background, rounded cover, title, artist,
waveform strip in a colour taken from the artwork, source / duration chips and chips for the active remix effects).
Fonts live in `data/fonts` (Poppins, covers Latin and Hindi, SIL OFL). No template image is needed any more.

## FFmpeg and yt-dlp

* **FFmpeg** must be installed (it is not a pip package): Windows `winget install Gyan.FFmpeg`, Debian/Ubuntu
  `apt install ffmpeg`, macOS `brew install ffmpeg`, or set `FFMPEG_PATH` in `.env`. Any recent build works; the console
  greys out an effect your build can't run.
* **yt-dlp** is installed by `requirements.txt`. YouTube changes often: if search or playback suddenly fails, run
  `pip install -U yt-dlp`. If YouTube asks to "confirm you're not a bot", export a `cookies.txt` and set `YTDL_COOKIEFILE`.
* `discord.py[voice]` brings PyNaCl for voice. If discord.py ever complains about `davey`, run `pip install davey`.

## Commands

`play` `search` `nowplaying` `queue` `clearqueue` `skip` `pause` `resume` `stop` `loop` `autoplay`
`shuffle` `seek` `replay` `volume` (1-300) `join` `disconnect` `remix` `fx` `bass` `filter enable` `filter disable` `help`

All of them also work as slash commands (except `help`).

### Session ownership

Whoever starts a music session in a server (by making the bot join or play) owns it. Only they can
change it: add songs, skip, pause, stop, volume, filters, loop, autoplay and the player buttons.
Everyone else gets the same style of reply: *"Only @owner can use this command. They started the music
session in this server."* Read-only commands (`nowplaying`, `queue`) stay open to people in the voice channel.

Safety valve: if the owner leaves the voice channel for 60 seconds, the next person in the channel who
uses a command takes the session over (change `SESSION_GRACE` in `utils/session.py`, or set it very high
to disable). The session also ends when the bot leaves.

### Owner-only no-prefix (np) commands

Hidden from help and silent for anyone who isn't a bot owner (`OWNER_IDS`, or the application owner).
Users on the list can run commands without a prefix (`play despacito`).

| Command | What it does |
|---|---|
| `np add <user> [duration]` | Add a user. Duration `30m` `12h` `7d` `2w` or `permanent` (default) |
| `np remove <user>` | Remove a user (`rm`, `delete`) |
| `np list` | Paged list with expiry times (`all`) |

Stored in `db/np.db`, expired entries clean themselves up.

## Privacy

* Nothing personal ships in the zip: no token, no database, no keys.
* Your own values (token, Spotify keys) live only in your local `.env` (git-ignored).
* They are scrubbed from every log line and traceback (`utils/privacy.py`).

## What changed vs. the two originals

* **Libraries:** `discord.py[voice] 2.7.x` + `yt-dlp` + FFmpeg (Wavelink is gone). No more `pip install` at startup,
  no `os.system("clear")`, no module-level `asyncio.run`, and no second bot instance created in `help.py`.
* **Lavalink:** removed completely (cog, helpers, settings). Nothing needs an external node any more.
* **Secrets removed:** Spotify client ID/secret that were hard-coded in the bot are gone (now env, optional).
  **Rotate those Spotify credentials** since they were in the zip.
* **Security:** the original loaded jishaku with two hard-coded owner IDs, giving those accounts code
  execution on whoever hosted the bot. Now opt-in and uses *your* owner IDs.
* **Intents:** `Intents.all()` → default + Message Content.
* **Playback fixes:** one "now playing" card per track (also for autoplay); "previous" plays the previous
  track instead of appending it to the end; autoplay is no longer switched off on every `play`; loop no longer
  re-posts the card or loops a failing track; skip/stop no longer double-advance; broken track errors are
  reported instead of silently swallowed; slash `play`/`search` defer so they don't time out;
  `search` buttons match the real result count; durations are `mm:ss`; long titles are trimmed on the card.
* **Idle leave** rewritten (checks who is actually in the bot's channel, works with the narrower intents).
* **New:** owner-only `np` commands, session ownership lock, log redaction.
* **Errors:** unexpected exceptions are logged with a traceback and the user gets a short message.
* **Databases** are created automatically in `./db` (paths no longer depend on the working directory).
* Help text now describes the music bot instead of the "50+ systems" full bot.
* **Emoji** (`utils/emojis.py`) can come from any server. At startup `utils/emoji_sync.py` copies each one into the
  bot's own *application emoji* (Developer Portal → your app → Emojis) so they render everywhere, even where the bot
  isn't in the emoji's server. The first start takes a few seconds; later starts reuse the copies. Needs discord.py 2.5+.
  To change an emoji, paste a new `<:name:id>` into `utils/emojis.py`. It must still exist on Discord.

See `LICENSE.txt` for the original license terms.


## Hosting 24/7 and YouTube blocking

- **No cookies needed.** If YouTube refuses a request, the bot automatically retries with other YouTube clients
  (tv, web_safari, android_vr, mweb, ios...) and remembers the one that works. If YouTube blocks everything,
  it plays the same song from SoundCloud. `start.sh` also updates yt-dlp on every start.
- Install **Node.js** (`pkg install nodejs`, already done by `setup_termux.sh`): yt-dlp needs a JS runtime for YouTube.
- **Home / phone internet works best.** Cloud servers (VPS) have datacenter IPs that YouTube blocks more often.
- `bash start.sh` restarts the bot automatically if it crashes. Use `tmux` or Termux wake-lock to keep it alive.

## Hosting on bot-hosting.net (panel hosts)

1. Upload the files so that `main.py` is at the top level (not inside an extra folder). Do **not** upload your `.env`;
   set `DISCORD_TOKEN` (and optionally `BOT_PREFIX`) in the panel's *Startup / Environment variables* instead.
2. Startup file: `main.py`. Dependencies: the uploaded `requirements.txt` is installed automatically
   (it includes `imageio-ffmpeg`, which gives the bot FFmpeg without apt).
3. Start the server and read the console. "Loaded & Online!" means it works.
#   S H I Z U - M U S I C - B O T  
 #   S H I Z U - M U S I C - B O T  
 #   S H I Z U - M U S I C - B O T  
 #   S H I Z U - M U S I C - B O T  
 
