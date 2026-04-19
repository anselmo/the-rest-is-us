"""Aggregation utilities: combine per-episode metrics into a single-side profile.

Used by both the reference side (whisperx-full transcripts) and the own side
(forced-aligned own transcripts).
"""
from __future__ import annotations

import statistics
from typing import Any


def _mean_stdev(values: list[float]) -> dict:
    if not values:
        return {"mean": 0.0, "stdev": 0.0, "n": 0}
    if len(values) == 1:
        return {"mean": float(values[0]), "stdev": 0.0, "n": 1}
    return {
        "mean": float(statistics.fmean(values)),
        "stdev": float(statistics.pstdev(values)),
        "n": len(values),
    }


def _flatten(profile: dict, prefix: str = "") -> dict[str, float]:
    """Flatten a nested metric dict into dotted keys with numeric leaves."""
    flat: dict[str, float] = {}
    for k, v in profile.items():
        key = f"{prefix}.{k}" if prefix else k
        if isinstance(v, dict):
            flat.update(_flatten(v, key))
        elif isinstance(v, (int, float)):
            flat[key] = float(v)
        elif isinstance(v, list) and v and all(isinstance(x, (int, float)) for x in v):
            flat[f"{key}.mean"] = float(statistics.fmean(v))
    return flat


def aggregate_side(per_episode: list[dict]) -> dict:
    """Collapse a list of per-episode metric dicts to a side profile.

    Numeric leaves become {mean, stdev, n}. Structural 'segment_durations_sec'
    and similar list fields are summarized to mean only.
    """
    if not per_episode:
        return {"episode_count": 0}

    flat_per_ep = [_flatten(ep) for ep in per_episode]
    all_keys: set[str] = set()
    for f in flat_per_ep:
        all_keys.update(f.keys())

    out: dict[str, Any] = {"episode_count": len(per_episode)}
    for key in sorted(all_keys):
        values = [f[key] for f in flat_per_ep if key in f]
        out[key] = _mean_stdev(values)
    return out


def build_diff(ref_profile: dict, own_profile: dict) -> list[dict]:
    """Return a list of row dicts suitable for a markdown table.

    Each row: {metric, ref_mean, ref_stdev, own_mean, own_stdev, delta, direction}
    """
    rows = []
    skip = {"episode_count"}
    keys = sorted(set(ref_profile.keys()) | set(own_profile.keys()))
    for key in keys:
        if key in skip:
            continue
        ref = ref_profile.get(key, {})
        own = own_profile.get(key, {})
        if not isinstance(ref, dict) or not isinstance(own, dict):
            continue
        ref_mean = ref.get("mean", 0.0)
        own_mean = own.get("mean", 0.0)
        delta = own_mean - ref_mean
        if ref_mean != 0:
            direction = "own is lower" if delta < 0 else "own is higher" if delta > 0 else "match"
        else:
            direction = "ref is zero"
        rows.append({
            "metric": key,
            "ref_mean": ref_mean,
            "ref_stdev": ref.get("stdev", 0.0),
            "own_mean": own_mean,
            "own_stdev": own.get("stdev", 0.0),
            "delta": delta,
            "direction": direction,
        })
    return rows
