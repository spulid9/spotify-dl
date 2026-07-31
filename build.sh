#!/usr/bin/env bash
# Build script: creates a standalone Windows .exe with PyInstaller.
# Run on Windows with yt-dlp.exe and ffmpeg.exe in the current directory.

set -euo pipefail

# Ensure binary dependencies exist
for BIN in yt-dlp.exe ffmpeg.exe; do
    if [ ! -f "$BIN" ]; then
        echo "ERROR: $BIN not found in current directory. Download it first."
        exit 1
    fi
done

pyinstaller --onefile \
  --name "SpotifyDownloader" \
  --add-data "templates:templates" \
  --add-binary "yt-dlp.exe:." \
  --add-binary "ffmpeg.exe:." \
  --add-data "spotify_dl:spotify_dl" \
  --hidden-import flask_cors \
  --hidden-import spotify_dl \
  --hidden-import spotify_dl.config \
  --hidden-import spotify_dl.cache \
  --hidden-import spotify_dl.models \
  --hidden-import spotify_dl.spotify \
  --hidden-import spotify_dl.downloader \
  --hidden-import spotify_dl.retry \
  --hidden-import spotify_dl.tagger \
  --hidden-import spotify_dl.job_state \
  --noconsole \
  app.py

echo ""
echo "✅ Build complete: dist/SpotifyDownloader.exe"
