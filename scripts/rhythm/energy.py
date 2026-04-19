"""librosa-backed energy analysis: RMS loudness curve + F0 pitch.

Heavy deps (librosa, numpy, scipy). Only imported inside the function so
sibling modules stay importable without `--extra rhythm`.
"""
from __future__ import annotations

from pathlib import Path

_RMS_DOWNSAMPLE_POINTS = 60          # target size of the exported loudness curve
_F0_FMIN = 75.0                       # Hz — below typical adult male voice
_F0_FMAX = 400.0                      # Hz — above typical adult female voice
_F0_SAMPLE_STRIDE = 100               # keep every Nth F0 sample to bound JSON size


def energy_profile(audio_path: Path, window_sec: float = 10.0) -> dict:
    """Compute loudness curve, pitch curve, peak locations, dynamic range.

    Returns:
      rms_curve: list[float]               — normalized 0-1, length _RMS_DOWNSAMPLE_POINTS
      rms_peak_locations_pct: list[float]  — positions (0-100%) of top-5 peaks
      rms_dynamic_range_db: float
      pitch_f0_mean_hz: float
      pitch_f0_std_hz: float
      pitch_f0_curve_hz: list[float]       — subsampled F0 trace
    """
    import librosa
    import numpy as np
    from scipy.signal import find_peaks

    audio, sr = librosa.load(str(audio_path), sr=None, mono=True)

    # --- RMS loudness curve ---
    frame_length = int(sr * window_sec)
    hop_length = frame_length  # non-overlapping windows
    rms = librosa.feature.rms(y=audio, frame_length=frame_length, hop_length=hop_length)[0]

    # Downsample to _RMS_DOWNSAMPLE_POINTS by linear interpolation.
    if len(rms) > _RMS_DOWNSAMPLE_POINTS:
        idx = np.linspace(0, len(rms) - 1, _RMS_DOWNSAMPLE_POINTS)
        rms_down = np.interp(idx, np.arange(len(rms)), rms)
    else:
        rms_down = rms

    rms_norm = rms_down / np.max(rms_down) if np.max(rms_down) > 0 else rms_down

    # Dynamic range in dB: 20 * log10(max / min_nonzero)
    nonzero = rms[rms > 0]
    if len(nonzero) > 1:
        dyn_range_db = float(20 * np.log10(np.max(nonzero) / np.min(nonzero)))
    else:
        dyn_range_db = 0.0

    # Top-5 peak locations as % of episode.
    peaks, _ = find_peaks(rms_norm, distance=max(1, _RMS_DOWNSAMPLE_POINTS // 12))
    if len(peaks) > 0:
        sorted_peaks = sorted(peaks, key=lambda i: -rms_norm[i])[:5]
        peak_pcts = sorted([float(p / max(len(rms_norm) - 1, 1) * 100) for p in sorted_peaks])
    else:
        peak_pcts = []

    # --- F0 pitch via yin ---
    # Downsample audio to 16 kHz for F0 estimation (matches whisper anyway) to speed this up.
    if sr > 16_000:
        audio_f0 = librosa.resample(audio, orig_sr=sr, target_sr=16_000)
        f0_sr = 16_000
    else:
        audio_f0 = audio
        f0_sr = sr
    f0 = librosa.yin(audio_f0, fmin=_F0_FMIN, fmax=_F0_FMAX, sr=f0_sr)

    # Filter out unvoiced frames (yin returns fmax-ish values for silence).
    voiced = f0[(f0 > _F0_FMIN * 1.05) & (f0 < _F0_FMAX * 0.95)]
    f0_mean = float(np.mean(voiced)) if len(voiced) else 0.0
    f0_std = float(np.std(voiced)) if len(voiced) else 0.0
    f0_curve = voiced[::_F0_SAMPLE_STRIDE].tolist()

    return {
        "rms_curve": rms_norm.tolist(),
        "rms_peak_locations_pct": peak_pcts,
        "rms_dynamic_range_db": dyn_range_db,
        "pitch_f0_mean_hz": f0_mean,
        "pitch_f0_std_hz": f0_std,
        "pitch_f0_curve_hz": f0_curve,
    }
