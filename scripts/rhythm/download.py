"""Download audio from YouTube URLs via yt-dlp, caching by URL hash.

Each URL gets its own cache subdir: {cache_dir}/{hash}/
  - audio.m4a   — extracted audio
  - meta.json   — {title, duration, channel, id, url}
"""
from __future__ import annotations

import hashlib
import json
from pathlib import Path


def _cache_key(url: str) -> str:
    return hashlib.sha1(url.encode("utf-8")).hexdigest()[:16]


def download_audio(url: str, cache_dir: Path) -> tuple[Path, dict]:
    """Download audio from a YouTube URL. Returns (audio_path, metadata).

    Cached by SHA1(url). Reuses existing download if audio.m4a and meta.json both exist.
    """
    import yt_dlp

    key = _cache_key(url)
    subdir = cache_dir / key
    subdir.mkdir(parents=True, exist_ok=True)
    audio_path = subdir / "audio.m4a"
    meta_path = subdir / "meta.json"

    if audio_path.exists() and meta_path.exists():
        return audio_path, json.loads(meta_path.read_text())

    ydl_opts = {
        "format": "bestaudio/best",
        "postprocessors": [{"key": "FFmpegExtractAudio", "preferredcodec": "m4a"}],
        "outtmpl": str(subdir / "audio.%(ext)s"),
        "quiet": True,
        "no_warnings": True,
        "noprogress": True,
    }
    with yt_dlp.YoutubeDL(ydl_opts) as ydl:
        info = ydl.extract_info(url, download=True)

    meta = {
        "id": info.get("id"),
        "title": info.get("title"),
        "channel": info.get("channel") or info.get("uploader"),
        "duration": info.get("duration"),
        "url": url,
        "cache_key": key,
    }
    meta_path.write_text(json.dumps(meta, indent=2))

    if not audio_path.exists():
        # yt-dlp occasionally names the postprocessed file with a different extension
        candidates = list(subdir.glob("audio.*"))
        if not candidates:
            raise RuntimeError(f"yt-dlp succeeded but no audio file found in {subdir}")
        candidates[0].rename(audio_path)

    return audio_path, meta
