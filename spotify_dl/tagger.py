"""Audio tagger — ffmpeg metadata + album art embedding."""

import subprocess
import logging
from pathlib import Path

from spotify_dl.models import Track

logger = logging.getLogger(__name__)

# Windows: suppress console popup from subprocess.
NO_WINDOW_FLAG = getattr(subprocess, "CREATE_NO_WINDOW", 0)


def build_ffmpeg_args(
    input_path: Path,
    output_path: Path,
    track: Track,
    cover_path: Path | None = None,
) -> list[str]:
    """Build ffmpeg argument list for tagging.

    Order: all -i inputs first, then maps + metadata, then output path last.
    """
    args = ["-y", "-i", str(input_path)]
    if cover_path and cover_path.exists():
        args.extend(["-i", str(cover_path)])

    args.extend([
        "-map", "0:a",
        "-metadata", f"title={track.name}",
        "-metadata", f"artist={track.artist}",
        "-metadata", f"album={track.album}",
        "-metadata", f"track={track.track_number}",
    ])

    if cover_path and cover_path.exists():
        args.extend([
            "-map", "1:v",
            "-disposition:v", "attached_pic",
        ])

    # Copy streams instead of re-encoding (fast)
    args.extend(["-codec", "copy"])
    args.append(str(output_path))
    return args


def tag_file(
    input_path: Path,
    output_path: Path,
    track: Track,
    cover_path: Path | None = None,
    ffmpeg_path: str = "ffmpeg",
    timeout: int = 90,
) -> bool:
    """Tag an audio file with metadata and optional cover art.

    Returns True on success, False on failure.
    """
    args = [ffmpeg_path] + build_ffmpeg_args(input_path, output_path, track, cover_path)

    try:
        result = subprocess.run(
            args,
            capture_output=True,
            text=True,
            timeout=timeout,
            creationflags=NO_WINDOW_FLAG,
        )
        if result.returncode != 0:
            stderr_tail = (result.stderr or "")[-300:]
            logger.error("ffmpeg failed for %s: %s", track.id, stderr_tail)
            # Clean up temp input on failure
            if input_path != output_path and input_path.exists():
                try:
                    input_path.unlink()
                except OSError:
                    pass
            return False
        return True
    except subprocess.TimeoutExpired:
        logger.error("ffmpeg timed out for %s", track.id)
        if input_path != output_path and input_path.exists():
            try:
                input_path.unlink()
            except OSError:
                pass
        return False
    except FileNotFoundError:
        logger.error("ffmpeg binary not found at '%s'", ffmpeg_path)
        return False
    except OSError as e:
        logger.error("ffmpeg OS error for %s: %s", track.id, e)
        return False
