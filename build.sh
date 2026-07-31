pyinstaller --onefile \
  --name "SpotifyDownloader" \
  --add-data "templates:templates" \
  --add-binary "yt-dlp.exe:." \
  --add-binary "ffmpeg.exe:." \
  --hidden-import flask_cors \
  --noconsole \
  app.py
