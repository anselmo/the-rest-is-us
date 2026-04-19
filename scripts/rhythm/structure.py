"""Silence-based structural segmentation of an episode.

Detects segment boundaries from long silences, estimates cold-open length,
segment count, and per-segment durations.
"""
from __future__ import annotations

from pathlib import Path


# Top-DB threshold for librosa.effects.split: how many dB below peak counts as silent.
# 30 dB is conservative — catches genuine pauses without chopping quiet speech.
_SILENCE_TOP_DB = 30


def detect_segments(audio_path: Path, min_silence_sec: float = 2.5) -> dict:
    """Split audio at silences ≥ min_silence_sec.

    Returns:
      episode_duration_sec: float
      cold_open_duration_sec: float    — time until first long silence
      segment_count: int
      segment_durations_sec: list[float]
      segment_starts_sec: list[float]
    """
    import librosa
    import numpy as np

    audio, sr = librosa.load(str(audio_path), sr=None, mono=True)
    duration = len(audio) / sr

    # librosa.effects.split returns non-silent intervals as [start, end] sample pairs.
    intervals = librosa.effects.split(audio, top_db=_SILENCE_TOP_DB)
    if len(intervals) == 0:
        return {
            "episode_duration_sec": duration,
            "cold_open_duration_sec": 0.0,
            "segment_count": 0,
            "segment_durations_sec": [],
            "segment_starts_sec": [],
        }

    min_silence_samples = int(min_silence_sec * sr)

    # Group consecutive non-silent intervals into segments. A segment break is a
    # silence >= min_silence_samples.
    segment_starts: list[int] = [int(intervals[0, 0])]
    segment_ends: list[int] = []
    for prev, curr in zip(intervals, intervals[1:]):
        silence_len = int(curr[0] - prev[1])
        if silence_len >= min_silence_samples:
            segment_ends.append(int(prev[1]))
            segment_starts.append(int(curr[0]))
    segment_ends.append(int(intervals[-1, 1]))

    segment_durations_samples = np.array(segment_ends) - np.array(segment_starts)
    segment_durations_sec = (segment_durations_samples / sr).tolist()
    segment_starts_sec = (np.array(segment_starts) / sr).tolist()

    cold_open_sec = segment_durations_sec[0] if segment_durations_sec else 0.0

    return {
        "episode_duration_sec": float(duration),
        "cold_open_duration_sec": float(cold_open_sec),
        "segment_count": len(segment_durations_sec),
        "segment_durations_sec": segment_durations_sec,
        "segment_starts_sec": segment_starts_sec,
    }
