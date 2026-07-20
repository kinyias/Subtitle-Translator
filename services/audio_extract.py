"""ffmpeg-based audio extraction to shrink large media before upload.

A 2-hour video can be several gigabytes; uploading it whole is slow, memory
heavy (``upload_audio_file`` reads the entire file into RAM) and unnecessary for
speech-to-text. Speech recognition only needs a mono, ~16 kHz track, so we
transcode the input to a small MP3 first and upload that instead.

Typical result: a 2 GB / 2 h video becomes a ~30-60 MB MP3, with no loss of
recognition quality (STT back-ends downsample to ~16 kHz regardless).

Usage::

    upload_path, cleanup = prepare_audio_for_upload(input_path, logger)
    try:
        ... upload upload_path ...
    finally:
        cleanup()

If ffmpeg is unavailable the original path is returned unchanged (with a
warning) so the pipeline still works, just without the size optimization.
"""
from __future__ import annotations

import os
import subprocess
import tempfile
from pathlib import Path
from typing import Callable, Optional, Tuple

from utils.helpers import base_dir
from utils.logger import AppLogger

# Extensions we always transcode (container video formats).
_VIDEO_EXTS = {
    ".mp4", ".mov", ".mkv", ".avi", ".flv", ".webm", ".wmv",
    ".m4v", ".mpg", ".mpeg", ".ts", ".3gp",
}
# Audio inputs above this size are re-encoded too (e.g. huge WAV/FLAC);
# smaller audio files are uploaded as-is to skip a needless transcode.
_REENCODE_ABOVE_BYTES = 25 * 1024 * 1024

# ASR-optimized output: mono, 16 kHz, modest MP3 bitrate. Enough for accurate
# recognition while keeping even multi-hour files small.
_TARGET_SAMPLE_RATE = "16000"
_TARGET_CHANNELS = "1"
_TARGET_BITRATE = "64k"

# Suppress the ffmpeg console window on Windows (frozen GUI build).
_NO_WINDOW = getattr(subprocess, "CREATE_NO_WINDOW", 0) if os.name == "nt" else 0


def find_ffmpeg() -> Optional[str]:
    """Locate an ffmpeg executable.

    Search order: a binary bundled next to the app (``bin/ffmpeg`` or
    ``ffmpeg`` in :func:`base_dir`), then the ``imageio-ffmpeg`` package if
    installed, then whatever is on ``PATH``. Returns ``None`` when none found.
    """
    exe = "ffmpeg.exe" if os.name == "nt" else "ffmpeg"
    root = base_dir()
    for candidate in (root / "bin" / exe, root / exe):
        if candidate.is_file():
            return str(candidate)

    try:  # optional dependency; provides a bundled ffmpeg binary
        import imageio_ffmpeg  # type: ignore

        path = imageio_ffmpeg.get_ffmpeg_exe()
        if path and Path(path).is_file():
            return path
    except Exception:
        pass

    import shutil

    return shutil.which("ffmpeg")


def _needs_extraction(path: str) -> bool:
    ext = Path(path).suffix.lower()
    if ext in _VIDEO_EXTS:
        return True
    try:
        return os.path.getsize(path) > _REENCODE_ABOVE_BYTES
    except OSError:
        return False


def prepare_audio_for_upload(
    input_path: str, logger: AppLogger
) -> Tuple[str, Callable[[], None]]:
    """Return ``(upload_path, cleanup)`` for *input_path*.

    When the input is a video or a large audio file and ffmpeg is available, a
    compact temporary MP3 is produced and its path returned; ``cleanup`` deletes
    it. Otherwise the original path is returned and ``cleanup`` is a no-op.
    """
    noop: Callable[[], None] = lambda: None

    if not _needs_extraction(input_path):
        return input_path, noop

    ffmpeg = find_ffmpeg()
    if not ffmpeg:
        logger.warning(
            "ffmpeg not found; uploading the original file. Install ffmpeg (add "
            "it to PATH or place it in the app's 'bin' folder) to shrink large "
            "videos before upload."
        )
        return input_path, noop

    fd, out_path = tempfile.mkstemp(prefix="subtrans_audio_", suffix=".mp3")
    os.close(fd)

    def cleanup() -> None:
        try:
            os.remove(out_path)
        except OSError:
            pass

    try:
        size_in = os.path.getsize(input_path)
    except OSError:
        size_in = 0
    logger.info(
        f"Extracting audio with ffmpeg (mono {_TARGET_SAMPLE_RATE} Hz MP3) "
        f"from {_human(size_in)} input ..."
    )

    cmd = [
        ffmpeg, "-y",
        "-i", input_path,
        "-vn",                       # drop video
        "-ac", _TARGET_CHANNELS,     # mono
        "-ar", _TARGET_SAMPLE_RATE,  # 16 kHz
        "-b:a", _TARGET_BITRATE,
        "-map_metadata", "-1",       # strip metadata
        "-f", "mp3",
        out_path,
    ]

    try:
        proc = subprocess.run(
            cmd,
            stdin=subprocess.DEVNULL,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            creationflags=_NO_WINDOW,
        )
    except OSError as exc:
        cleanup()
        logger.warning(f"Could not run ffmpeg ({exc}); uploading original file.")
        return input_path, noop

    if proc.returncode != 0 or not os.path.getsize(out_path):
        tail = (proc.stdout or b"").decode("utf-8", "replace")[-500:]
        cleanup()
        logger.warning(
            f"ffmpeg extraction failed (exit {proc.returncode}); uploading "
            f"original file.\n{tail}"
        )
        return input_path, noop

    size_out = os.path.getsize(out_path)
    ratio = f" ({size_in / size_out:.0f}x smaller)" if size_out and size_in else ""
    logger.success(f"Extracted audio: {_human(size_out)}{ratio}.")
    return out_path, cleanup


def _human(size: int) -> str:
    value = float(size)
    for unit in ("B", "KB", "MB", "GB", "TB"):
        if value < 1024.0:
            return f"{value:.0f} {unit}" if unit == "B" else f"{value:.1f} {unit}"
        value /= 1024.0
    return f"{value:.1f} PB"
