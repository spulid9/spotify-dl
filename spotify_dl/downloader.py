"""Track downloader — yt-dlp search + download, ffmpeg tagging, cache management."""

from __future__ import annotations

import subprocess
import time
import urllib.request
import logging
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor, as_completed
import threading

from spotify_dl.models import Track, DownloadResult, DownloadStatus
from spotify_dl.cache import DownloadCache
from spotify_dl.tagger import tag_file
from spotify_dl.retry import retry, RetryExhaustedError

logger = logging.getLogger(__name__)

# Windows: suppress console popup from subprocess.
NO_WINDOW_FLAG = getattr(subprocess, "CREATE_NO_WINDOW", 0)

DEFAULT_TIMEOUT = 120
YTDLP_RETRIES = 3
YTDLP_PATH = "yt-dlp"
FFMPEG_PATH = "ffmpeg"
SEARCH_TEMPLATE = "ytsearch:{artist} - {title} audio"


@retry(max_retries=YTDLP_RETRIES, delay=2.0, backoff=1.5, on=(subprocess.TimeoutExpired,))
def _run_ytdlp(query: str, output_path: Path, ffmpeg_dir: str | None = None) -> subprocess.CompletedProcess:
    """Run yt-dlp with retries on timeout. Raises RetryExhaustedError if all fail."""
    cmd = [
        YTDLP_PATH,
        "-x", "--audio-format", "mp3",
        "--output", str(output_path),
        "--no-playlist",
        "--quiet", "--no-warnings",
        "--retries", "3",
        "--extractor-args", "youtube:player_client=android,web_safari,ios",
        query,
    ]
    if ffmpeg_dir:
        cmd.insert(cmd.index("--quiet"), "--ffmpeg-location")
        cmd.insert(cmd.index("--quiet"), ffmpeg_dir)

    return subprocess.run(
        cmd,
        capture_output=True,
        text=True,
        timeout=DEFAULT_TIMEOUT,
        creationflags=NO_WINDOW_FLAG,
    )


def _find_temp_output(download_dir: Path, temp_stem: str) -> Path | None:
    """Find the temp file yt-dlp actually wrote (may have any extension)."""
    matches = sorted(download_dir.glob(f"{temp_stem}.*"))
    return matches[0] if matches else None


def download_track(
    track: Track,
    cache: DownloadCache,
    download_dir: Path,
    ytdlp_path: str = "yt-dlp",
    ffmpeg_path: str = "ffmpeg",
) -> DownloadResult:
    """Download a single track: yt-dlp search → ffmpeg tag → cache update.

    Returns DownloadResult with status (success/skipped/failed).
    """
    global YTDLP_PATH, FFMPEG_PATH
    YTDLP_PATH = ytdlp_path
    FFMPEG_PATH = ffmpeg_path

    output_path = download_dir / track.output_filename
    temp_stem = track.temp_filename_stem

    # ── Check cache ──────────────────────────────────────────────────
    if cache.has(track.id):
        cached = cache.get(track.id)
        if cached and (download_dir / cached["file"]).exists():
            return DownloadResult.skipped(track.id, track.name, track.artist)

    if output_path.exists():
        # File exists from outside cache — register and skip
        cache.set(track.id, {
            "file": track.output_filename,
            "song": track.name,
            "artist": track.artist,
            "album": track.album,
            "downloaded_at": time.strftime("%Y-%m-%dT%H:%M:%S"),
        })
        return DownloadResult.skipped(track.id, track.name, track.artist)

    # ── Download from YouTube ────────────────────────────────────────
    download_dir.mkdir(parents=True, exist_ok=True)
    query = SEARCH_TEMPLATE.format(artist=track.artist, title=track.name)

    try:
        ffmpeg_dir = str(Path(ffmpeg_path).parent) if Path(ffmpeg_path).parent.parts else None
        result = _run_ytdlp(query, download_dir / f"{temp_stem}.%(ext)s", ffmpeg_dir)
    except RetryExhaustedError as e:
        return DownloadResult.failed(track.id, track.name, track.artist,
                                     f"yt-dlp timeout after {e.attempts} attempts")

    temp_path = _find_temp_output(download_dir, temp_stem)
    if result.returncode != 0 or not temp_path:
        detail = (result.stderr or "")[-300:] if result.stderr else "no output"
        return DownloadResult.failed(track.id, track.name, track.artist,
                                     f"yt-dlp failed: {detail}")

    # ── Download cover art ───────────────────────────────────────────
    cover_path: Path | None = None
    if track.album_art:
        try:
            cover_path = download_dir / track.cover_temp_stem
            urllib.request.urlretrieve(track.album_art, str(cover_path))
        except Exception as e:
            logger.warning("Failed to download cover for %s: %s", track.id, e)
            cover_path = None

    # ── Tag with ffmpeg ──────────────────────────────────────────────
    ok = tag_file(temp_path, output_path, track, cover_path, ffmpeg_path=ffmpeg_path)

    # ── Cleanup temp files ───────────────────────────────────────────
    for p in [temp_path, cover_path]:
        if p and p.exists():
            try:
                p.unlink()
            except OSError:
                pass

    if ok and output_path.exists():
        cache.set(track.id, {
            "file": track.output_filename,
            "song": track.name,
            "artist": track.artist,
            "album": track.album,
            "downloaded_at": time.strftime("%Y-%m-%dT%H:%M:%S"),
        })
        return DownloadResult.success(track.id, track.name, track.artist)

    return DownloadResult.failed(track.id, track.name, track.artist,
                                 "ffmpeg output missing")


def run_download_job(
    tracks: list[Track],
    cache: DownloadCache,
    download_dir: Path,
    max_concurrent: int = 3,
    ytdlp_path: str = "yt-dlp",
    ffmpeg_path: str = "ffmpeg",
    on_result: callable[[DownloadResult], None] | None = None,
) -> dict[str, int]:
    """Run a batch download. Returns aggregate stats.

    Args:
        tracks: Tracks to download.
        cache: Download cache instance.
        download_dir: Output directory.
        max_concurrent: Max parallel downloads.
        ytdlp_path: Path to yt-dlp binary.
        ffmpeg_path: Path to ffmpeg binary.
        on_result: Optional callback for each completed track result.
    """
    stats = {"completed": 0, "skipped": 0, "failed": 0}
    semaphore = threading.Semaphore(max_concurrent)

    def _download_one(track: Track) -> DownloadResult:
        with semaphore:
            return download_track(track, cache, download_dir, ytdlp_path, ffmpeg_path)

    with ThreadPoolExecutor(max_workers=max_concurrent) as executor:
        futures = {executor.submit(_download_one, t): t for t in tracks}
        for future in as_completed(futures):
            try:
                result = future.result()
            except Exception as e:
                t = futures[future]
                result = DownloadResult.failed(t.id, t.name, t.artist, f"unexpected: {e}")

            if result.status == DownloadStatus.SUCCESS:
                stats["completed"] += 1
            elif result.status == DownloadStatus.SKIPPED:
                stats["skipped"] += 1
            else:
                stats["failed"] += 1

            if on_result:
                try:
                    on_result(result)
                except Exception:
                    pass

    return stats
