#!/data/data/com.termux/files/usr/bin/bash
# Shizu Music - one-shot Termux setup. Run:  bash setup_termux.sh
set -e
cd "$(dirname "$0")"

echo "==> [1/4] Installing Termux packages (a few minutes the first time)..."
pkg update -y
pkg upgrade -y -o Dpkg::Options::="--force-confnew"
pkg install -y python ffmpeg libsodium libffi openssl clang make binutils python-pillow nodejs   # nodejs = JS runtime yt-dlp needs for YouTube

echo "==> [2/4] Installing Python libraries..."
# pure-python builds of the aiohttp parts + system libsodium = much faster, fewer build errors on Termux
export SODIUM_INSTALL=system
export AIOHTTP_NO_EXTENSIONS=1 MULTIDICT_NO_EXTENSIONS=1 YARL_NO_EXTENSIONS=1
export FROZENLIST_NO_EXTENSIONS=1 PROPCACHE_NO_EXTENSIONS=1
python -c "import PIL" 2>/dev/null || pip install --no-cache-dir pillow
pip install --no-cache-dir -r requirements.txt

echo "==> [3/4] Bot token"
[ -f .env ] || cp .env.example .env
if ! grep -qE '^DISCORD_TOKEN=.+' .env; then
  echo "Paste your bot token (Discord Developer Portal > your app > Bot > Reset Token)."
  read -r -p "Token: " TOKEN
  TOKEN="$(printf '%s' "$TOKEN" | tr -d '[:space:]')"
  if [ -z "$TOKEN" ]; then
    echo "No token entered. Put it in .env as DISCORD_TOKEN=... then run: bash start.sh"
    exit 1
  fi
  sed -i "s|^DISCORD_TOKEN=.*|DISCORD_TOKEN=${TOKEN}|" .env
fi

echo "==> [4/4] Starting Shizu Music (the invite link prints once it is online)..."
exec bash start.sh
