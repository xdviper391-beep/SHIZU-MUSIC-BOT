#!/data/data/com.termux/files/usr/bin/bash
# Start Shizu Music and keep it running. Run:  bash start.sh
cd "$(dirname "$0")"
termux-wake-lock 2>/dev/null || true   # keeps Termux alive with the screen off
while true; do
  # YouTube changes often: keep yt-dlp fresh so playback does not get blocked
  pip install -q -U --no-cache-dir "yt-dlp[default]" 2>/dev/null || true
  python main.py
  echo "Bot stopped (exit $?). Restarting in 10 seconds... (Ctrl+C to quit)"
  sleep 10
done
