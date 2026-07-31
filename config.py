# Spotify API Credentials
# Set these via environment variables when building (GitHub Secrets) or running.
# The binary will have these baked in — your users never see them.

import os

SPOTIFY_CLIENT_ID = os.environ.get("SPOTIFY_CLIENT_ID", "YOUR_CLIENT_ID_HERE")
SPOTIFY_CLIENT_SECRET = os.environ.get("SPOTIFY_CLIENT_SECRET", "YOUR_CLIENT_SECRET_HERE")
REDIRECT_URI = "http://localhost:5000/callback"
