#!/usr/bin/env python3
"""
Spotify Downloader v2 — Web UI + orchestration layer.
Uses modular spotify_dl package for all business logic.

Usage: python app.py
"""

import os
import sys
import time
import logging
import webbrowser
import threading
from pathlib import Path

from flask import Flask, jsonify, request, send_from_directory, redirect
from flask_cors import CORS

from spotify_dl.config import Config
from spotify_dl.cache import DownloadCache
from spotify_dl.models import Track, DownloadResult, DownloadStatus
from spotify_dl.spotify import SpotifyAuthManager, fetch_all_liked_tracks
from spotify_dl.downloader import download_track, run_download_job
from spotify_dl.job_state import DownloadJobState

# ── PyInstaller resource path ─────────────────────────────────────────

def _resource_path(relative_path: str) -> str:
    try:
        base = sys._MEIPASS
    except AttributeError:
        base = os.path.abspath(".")
    return os.path.join(base, relative_path)


# ── Config ────────────────────────────────────────────────────────────

cfg = Config()
YT_DLP_PATH = _resource_path("yt-dlp.exe") if sys.platform == "win32" else "yt-dlp"
FFMPEG_PATH = _resource_path("ffmpeg.exe") if sys.platform == "win32" else "ffmpeg"

# ── Logging ────────────────────────────────────────────────────────────

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    datefmt="%H:%M:%S",
)
logger = logging.getLogger("spotify-dl")

# ── Stateful singletons ────────────────────────────────────────────────

cache = DownloadCache(cfg.cache_dir / "download_cache.json")
job_state = DownloadJobState()
auth_manager: SpotifyAuthManager | None = None
sp_client = None  # spotipy.Spotify client after auth exchange


def _init_auth_manager():
    global auth_manager
    if auth_manager is None:
        auth_manager = SpotifyAuthManager(
            client_id=cfg.spotify_client_id,
            client_secret=cfg.spotify_client_secret,
            redirect_uri=cfg.redirect_uri,
            scope=cfg.scope,
        )


# ── Flask app ──────────────────────────────────────────────────────────

app = Flask(__name__, template_folder="templates")
app.secret_key = os.urandom(24)
CORS(app)


def ensure_dirs():
    cfg.cache_dir.mkdir(parents=True, exist_ok=True)
    cfg.download_dir.mkdir(parents=True, exist_ok=True)


# ── Routes ─────────────────────────────────────────────────────────────

@app.route("/")
def index():
    return send_from_directory("templates", "index.html")


@app.route("/api/auth-url")
def auth_url():
    _init_auth_manager()
    return jsonify({"url": auth_manager.get_authorize_url()})


@app.route("/callback")
def callback():
    code = request.args.get("code")
    if not code:
        return "Missing authorization code", 400
    return redirect(f"http://127.0.0.1:{cfg.port}/?auth_code={code}")


def _enrich_tracks_with_download_status(tracks: list[Track]) -> list[dict]:
    """Mark tracks as downloaded if they exist in cache + on disk."""
    result = []
    for t in tracks:
        d = t.to_dict()
        d["downloaded"] = (
            cache.has(t.id)
            and (cfg.download_dir / cache.get(t.id)["file"]).exists()
        )
        result.append(d)
    return result


def _find_orphans(tracks: list[Track]) -> list[dict]:
    """Find cached files for tracks no longer in the liked library."""
    liked_ids = {t.id for t in tracks}
    orphans = []
    for track_id, info in cache.all().items():
        if track_id not in liked_ids:
            file_path = cfg.download_dir / info["file"]
            if file_path.exists():
                orphans.append({
                    "track_id": track_id,
                    "file": info["file"],
                    "song": info.get("song", "?"),
                    "artist": info.get("artist", "?"),
                })
    return orphans


@app.route("/api/library")
def library():
    if sp_client is None:
        return jsonify({"error": "Not logged in"}), 401
    try:
        tracks = fetch_all_liked_tracks(sp_client)
        job_state.set_tracks(tracks)
        enriched = _enrich_tracks_with_download_status(tracks)
        orphans = _find_orphans(tracks)
        return jsonify({
            "tracks": enriched,
            "count": len(enriched),
            "orphaned": orphans,
            "orphaned_count": len(orphans),
        })
    except Exception as e:
        logger.exception("Error fetching library")
        return jsonify({"error": str(e)}), 500


@app.route("/api/exchange", methods=["POST"])
def exchange():
    global sp_client
    data = request.get_json()
    code = data.get("code")
    if not code:
        return jsonify({"error": "Missing code"}), 400

    try:
        _init_auth_manager()
        sp_client = auth_manager.complete_auth(code)
        tracks = fetch_all_liked_tracks(sp_client)
        job_state.set_tracks(tracks)
        enriched = _enrich_tracks_with_download_status(tracks)
        orphans = _find_orphans(tracks)
        return jsonify({
            "tracks": enriched,
            "count": len(enriched),
            "orphaned": orphans,
            "orphaned_count": len(orphans),
        })
    except Exception as e:
        logger.exception("Auth exchange failed")
        return jsonify({"error": str(e)}), 500


@app.route("/api/scan")
def scan():
    tracks = job_state.tracks
    if not tracks:
        return jsonify({"error": "No tracks — log in first"}), 400

    new_tracks = []
    already_downloaded = []
    orphans = _find_orphans(tracks)

    for t in tracks:
        if cache.has(t.id) and (cfg.download_dir / cache.get(t.id)["file"]).exists():
            already_downloaded.append(t.to_dict())
        else:
            new_tracks.append(t.to_dict())

    return jsonify({
        "new_count": len(new_tracks),
        "already_count": len(already_downloaded),
        "orphaned_count": len(orphans),
        "new_tracks": new_tracks,
        "already_tracks": already_downloaded,
        "orphaned_tracks": orphans,
    })


@app.route("/api/download", methods=["POST"])
def start_download():
    if job_state.running:
        return jsonify({"error": "A download is already in progress"}), 400

    data = request.get_json() or {}
    track_ids = data.get("track_ids", None)
    tracks = job_state.tracks

    if track_ids:
        id_set = set(track_ids)
        tracks = [t for t in tracks if t.id in id_set]

    if not tracks:
        return jsonify({"error": "No tracks to download"}), 400

    job_state.reset()
    job_state.start_downloading(len(tracks))

    def _on_result(result: DownloadResult):
        if result.status == DownloadStatus.SUCCESS:
            job_state.increment_completed()
        elif result.status == DownloadStatus.SKIPPED:
            job_state.increment_skipped()
        else:
            job_state.increment_failed()
            job_state.add_error(f"{result.artist} - {result.title}: {result.error}")

    def _worker():
        try:
            run_download_job(
                tracks=tracks,
                cache=cache,
                download_dir=cfg.download_dir,
                max_concurrent=cfg.max_concurrent,
                ytdlp_path=YT_DLP_PATH,
                ffmpeg_path=FFMPEG_PATH,
                on_result=_on_result,
            )
            job_state.mark_done()
        except Exception as exc:
            logger.exception("Download job crashed")
            job_state.mark_error(str(exc))

    thread = threading.Thread(target=_worker, daemon=True)
    thread.start()

    return jsonify({"message": f"Downloading {len(tracks)} songs", "count": len(tracks)})


@app.route("/api/cleanup", methods=["POST"])
def cleanup():
    data = request.get_json() or {}
    track_ids = data.get("track_ids", [])
    liked_ids = {t.id for t in job_state.tracks}
    removed = 0

    if track_ids:
        for tid in track_ids:
            if tid in cache.all():
                info = cache.get(tid)
                file_path = cfg.download_dir / info["file"]
                if file_path.exists():
                    try:
                        file_path.unlink()
                    except OSError:
                        pass
                    removed += 1
                cache.remove(tid)
    else:
        for tid in list(cache.all().keys()):
            if tid not in liked_ids:
                info = cache.get(tid)
                file_path = cfg.download_dir / info["file"]
                if file_path.exists():
                    try:
                        file_path.unlink()
                    except OSError:
                        pass
                    removed += 1
                cache.remove(tid)

    return jsonify({"removed": removed})


@app.route("/api/progress")
def progress():
    return jsonify(job_state.to_dict())


@app.route("/api/config")
def get_config():
    return jsonify({
        "download_dir": str(cfg.download_dir),
        "max_concurrent": cfg.max_concurrent,
    })


# ── Main ────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    ensure_dirs()
    threading.Timer(1.5, lambda: webbrowser.open(f"http://localhost:{cfg.port}")).start()
    print("🎵 Spotify Downloader v2 starting...")
    print(f"📁 Downloads go to: {cfg.download_dir}")
    print(f"🔧 Cache stored in: {cfg.cache_dir}")
    print(f"🌐 Opening http://localhost:{cfg.port} in your browser...")
    app.run(port=cfg.port, debug=False, host="127.0.0.1")
