#!/usr/bin/env python3
"""
Spotify Downloader — Single executable app.
Logs into Spotify, fetches your liked songs, downloads from YouTube,
tags with proper metadata, and caches progress.
"""

import os
import sys
import json
import time

import threading
import urllib.request
import subprocess
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor, as_completed

import spotipy
from spotipy.oauth2 import SpotifyOAuth
from spotipy.cache_handler import MemoryCacheHandler
from flask import Flask, jsonify, request, send_from_directory, redirect
from flask_cors import CORS

# ── Config ──────────────────────────────────────────────────────────────

from config import SPOTIFY_CLIENT_ID, SPOTIFY_CLIENT_SECRET, REDIRECT_URI

SCOPE = "user-library-read"

# ── App data directories ────────────────────────────────────────────────

if sys.platform == "win32":
    APP_DATA = Path(os.environ.get("APPDATA", Path.home() / "AppData" / "Roaming")) / "SpotifyDownloader"
else:
    APP_DATA = Path.home() / ".config" / "spotify-downloader"

CACHE_FILE = APP_DATA / "download_cache.json"

DOWNLOAD_DIR = Path.home() / "Downloads" / "spotify-music"
MAX_CONCURRENT = 3
MAX_SONGS = 200

# ── Flask app ───────────────────────────────────────────────────────────

app = Flask(__name__)
app.secret_key = os.urandom(24)
CORS(app)

# Track current download job state
download_job = {
    "running": False,
    "total": 0,
    "completed": 0,
    "skipped": 0,
    "failed": 0,
    "current_song": "",
    "errors": [],
    "tracks": [],
    "status": "idle",  # idle | scanning | ready | downloading | done | error
}


def ensure_dirs():
    APP_DATA.mkdir(parents=True, exist_ok=True)
    DOWNLOAD_DIR.mkdir(parents=True, exist_ok=True)


def load_cache():
    if CACHE_FILE.exists():
        try:
            return json.loads(CACHE_FILE.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            return {}
    return {}


def save_cache(cache):
    CACHE_FILE.write_text(json.dumps(cache, indent=2), encoding="utf-8")





# ── Download logic ──────────────────────────────────────────────────────

def download_song(track, cache, semaphore):
    """Download a single track: yt-dlp → ffmpeg tag → cache update."""
    track_id = track["id"]
    artist = track["artist"]
    title = track["name"]
    album = track["album"]
    track_num = track.get("track_number", 1)
    cover_url = track.get("album_art")

    safe_artist = "".join(c for c in artist if c.isalnum() or c in " ._-'").strip()
    safe_title = "".join(c for c in title if c.isalnum() or c in " ._-'").strip()
    output_filename = f"{safe_artist} - {safe_title}.mp3"
    output_path = DOWNLOAD_DIR / output_filename
    temp_path = DOWNLOAD_DIR / f"__temp_{track_id}.mp3"

    # Check cache
    if track_id in cache:
        cached_file = DOWNLOAD_DIR / cache[track_id]["file"]
        if cached_file.exists():
            return {"status": "skipped", "track_id": track_id, "title": title, "artist": artist}

    # Check if file already exists from a previous run
    if output_path.exists():
        cache[track_id] = {
            "file": output_filename,
            "song": title,
            "artist": artist,
            "album": album,
            "downloaded_at": time.strftime("%Y-%m-%dT%H:%M:%S"),
        }
        save_cache(cache)
        return {"status": "skipped", "track_id": track_id, "title": title, "artist": artist}

    with semaphore:
        download_job["current_song"] = f"{artist} - {title}"

        try:
            # Step 1: Download audio from YouTube via yt-dlp
            query = f"{artist} - {title} audio"
            yt_cmd = [
                "yt-dlp",
                "-x", "--audio-format", "mp3",
                "--output", str(temp_path),
                "--no-playlist",
                "--quiet",
                "--no-warnings",
                f"ytsearch:{query}",
            ]
            result = subprocess.run(yt_cmd, capture_output=True, text=True, timeout=120)

            if result.returncode != 0 or not temp_path.exists():
                return {"status": "failed", "track_id": track_id, "title": title, "artist": artist, "error": "yt-dlp failed"}

            # Step 2: Download cover art
            cover_path = None
            if cover_url:
                try:
                    cover_path = DOWNLOAD_DIR / f"__cover_{track_id}.jpg"
                    urllib.request.urlretrieve(cover_url, cover_path)
                except Exception:
                    cover_path = None

            # Step 3: Tag and rename with ffmpeg
            ffmpeg_cmd = [
                "ffmpeg", "-y",
                "-i", str(temp_path),
                "-metadata", f"title={title}",
                "-metadata", f"artist={artist}",
                "-metadata", f"album={album}",
                "-metadata", f"track={track_num}",
                "-codec", "copy",
            ]
            if cover_path and cover_path.exists():
                ffmpeg_cmd.extend(["-i", str(cover_path), "-map", "0:a", "-map", "1:v", "-disposition:v", "attached_pic"])

            ffmpeg_cmd.append(str(output_path))
            subprocess.run(ffmpeg_cmd, capture_output=True, text=True, timeout=60)

            # Cleanup temp files
            if temp_path.exists():
                temp_path.unlink()
            if cover_path and cover_path.exists():
                cover_path.unlink()

            if output_path.exists():
                cache[track_id] = {
                    "file": output_filename,
                    "song": title,
                    "artist": artist,
                    "album": album,
                    "downloaded_at": time.strftime("%Y-%m-%dT%H:%M:%S"),
                }
                save_cache(cache)
                return {"status": "success", "track_id": track_id, "title": title, "artist": artist}
            else:
                return {"status": "failed", "track_id": track_id, "title": title, "artist": artist, "error": "ffmpeg output missing"}

        except subprocess.TimeoutExpired:
            return {"status": "failed", "track_id": track_id, "title": title, "artist": artist, "error": "timeout"}
        except Exception as e:
            return {"status": "failed", "track_id": track_id, "title": title, "artist": artist, "error": str(e)}


def run_download_job(tracks, cache):
    """Run the full download job for a list of tracks."""
    download_job["running"] = True
    download_job["status"] = "downloading"
    download_job["total"] = len(tracks)
    download_job["completed"] = 0
    download_job["skipped"] = 0
    download_job["failed"] = 0
    download_job["errors"] = []

    semaphore = threading.Semaphore(MAX_CONCURRENT)

    with ThreadPoolExecutor(max_workers=MAX_CONCURRENT) as executor:
        futures = {executor.submit(download_song, t, cache, semaphore): t for t in tracks}

        for future in as_completed(futures):
            try:
                result = future.result()
                if result["status"] == "success":
                    download_job["completed"] += 1
                elif result["status"] == "skipped":
                    download_job["skipped"] += 1
                else:
                    download_job["failed"] += 1
                    download_job["errors"].append(f"{result.get('artist', '?')} - {result.get('title', '?')}: {result.get('error', 'unknown')}")
            except Exception as e:
                download_job["failed"] += 1
                download_job["errors"].append(f"Unexpected error: {str(e)}")

    download_job["current_song"] = ""
    download_job["running"] = False
    download_job["status"] = "done"
    save_cache(cache)


# ── Routes ──────────────────────────────────────────────────────────────

@app.route("/")
def index():
    return send_from_directory("templates", "index.html")


@app.route("/api/auth-url")
def auth_url():
    """Get the Spotify authorization URL."""
    oauth = SpotifyOAuth(
        client_id=SPOTIFY_CLIENT_ID,
        client_secret=SPOTIFY_CLIENT_SECRET,
        redirect_uri=REDIRECT_URI,
        scope=SCOPE,
        cache_handler=MemoryCacheHandler(),
    )
    return jsonify({"url": oauth.get_authorize_url()})


@app.route("/callback")
def callback():
    """Handle Spotify OAuth callback and redirect back to the app."""
    code = request.args.get("code")
    if not code:
        return "Missing authorization code", 400
    return redirect(f"http://localhost:5000/?auth_code={code}")


@app.route("/api/exchange", methods=["POST"])
def exchange():
    """Exchange auth code for token and fetch liked songs."""
    data = request.get_json()
    code = data.get("code")
    if not code:
        return jsonify({"error": "Missing code"}), 400

    try:
        sp = spotipy.Spotify(auth_manager=SpotifyOAuth(
            client_id=SPOTIFY_CLIENT_ID,
            client_secret=SPOTIFY_CLIENT_SECRET,
            redirect_uri=REDIRECT_URI,
            scope=SCOPE,
            cache_handler=MemoryCacheHandler(),
            open_browser=False,
        ))
        sp.auth_manager.get_access_token(code)

        # Fetch liked songs (up to MAX_SONGS)
        results = sp.current_user_saved_tracks(limit=50)
        tracks = []
        while len(tracks) < MAX_SONGS and results:
            for item in results["items"]:
                t = item["track"]
                tracks.append({
                    "id": t["id"],
                    "name": t["name"],
                    "artist": t["artists"][0]["name"],
                    "album": t["album"]["name"],
                    "track_number": t.get("track_number", 1),
                    "album_art": t["album"]["images"][0]["url"] if t["album"].get("images") else None,
                })
                if len(tracks) >= MAX_SONGS:
                    break
            results = sp.next(results) if results and results.get("next") else None

        download_job["tracks"] = tracks
        return jsonify({"tracks": tracks, "count": len(tracks)})

    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route("/api/scan")
def scan():
    """Compare liked songs with cache and return what's new/missing."""
    cache = load_cache()
    tracks = download_job.get("tracks", [])

    new_tracks = []
    already_downloaded = []
    orphaned = []

    for t in tracks:
        if t["id"] in cache:
            cached_file = DOWNLOAD_DIR / cache[t["id"]]["file"]
            if cached_file.exists():
                already_downloaded.append(t)
                continue
        new_tracks.append(t)

    # Check for orphaned files (cached but no longer liked)
    liked_ids = {t["id"] for t in tracks}
    for track_id, info in cache.items():
        if track_id not in liked_ids:
            file_path = DOWNLOAD_DIR / info["file"]
            if file_path.exists():
                orphaned.append({"track_id": track_id, "file": info["file"], "song": info["song"], "artist": info["artist"]})

    return jsonify({
        "new_count": len(new_tracks),
        "already_count": len(already_downloaded),
        "orphaned_count": len(orphaned),
        "new_tracks": new_tracks,
        "already_tracks": already_downloaded,
        "orphaned_tracks": orphaned,
    })


@app.route("/api/download", methods=["POST"])
def start_download():
    """Start downloading songs."""
    if download_job["running"]:
        return jsonify({"error": "A download is already in progress"}), 400

    data = request.get_json() or {}
    track_ids = data.get("track_ids", None)
    cache = load_cache()
    tracks = download_job.get("tracks", [])

    if track_ids:
        tracks = [t for t in tracks if t["id"] in track_ids]

    if not tracks:
        return jsonify({"error": "No tracks to download"}), 400

    download_job["errors"] = []

    thread = threading.Thread(target=run_download_job, args=(tracks, cache), daemon=True)
    thread.start()

    return jsonify({"message": f"Downloading {len(tracks)} songs", "count": len(tracks)})


@app.route("/api/cleanup", methods=["POST"])
def cleanup():
    """Remove orphaned files (songs no longer liked)."""
    data = request.get_json() or {}
    track_ids = data.get("track_ids", [])
    cache = load_cache()
    removed = 0

    if track_ids:
        for tid in track_ids:
            if tid in cache:
                file_path = DOWNLOAD_DIR / cache[tid]["file"]
                if file_path.exists():
                    file_path.unlink()
                    removed += 1
                del cache[tid]
    else:
        # Remove all orphaned
        liked_ids = {t["id"] for t in download_job.get("tracks", [])}
        to_delete = [tid for tid, info in cache.items() if tid not in liked_ids]
        for tid in to_delete:
            file_path = DOWNLOAD_DIR / cache[tid]["file"]
            if file_path.exists():
                file_path.unlink()
            del cache[tid]
            removed += 1

    save_cache(cache)
    return jsonify({"removed": removed})


@app.route("/api/progress")
def progress():
    """Get current download progress."""
    return jsonify({
        "running": download_job["running"],
        "status": download_job["status"],
        "total": download_job["total"],
        "completed": download_job["completed"],
        "skipped": download_job["skipped"],
        "failed": download_job["failed"],
        "current_song": download_job["current_song"],
        "errors": download_job["errors"][-10:],  # last 10 errors
    })


if __name__ == "__main__":
    ensure_dirs()
    print("🎵 Spotify Downloader starting...")
    print(f"📁 Downloads go to: {DOWNLOAD_DIR}")
    print(f"🔧 Config stored in: {APP_DATA}")
    print(f"🌐 Open http://localhost:5000 in your browser")
    app.run(port=5000, debug=False, host="127.0.0.1")
