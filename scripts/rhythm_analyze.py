"""Rhythm extraction CLI — compare a reference podcast against your own episodes.

Prerequisites:
  uv sync --extra rhythm
  HF_TOKEN set in .env — accept user agreements for:
    https://hf.co/pyannote/speaker-diarization-3.1
    https://hf.co/pyannote/segmentation-3.0
    https://hf.co/pyannote/speaker-diarization-community-1
  ffmpeg (brew install ffmpeg)

Usage:
  uv run python scripts/rhythm_analyze.py \\
      --refs "https://youtube.com/watch?v=..." "https://youtube.com/watch?v=..." \\
      --own-dir episodes/ \\
      [--model medium.en] [--limit-refs N] [--limit-own N] \\
      [--stage download|transcribe|metrics|all] \\
      [--skip-patches]
"""
from __future__ import annotations

import argparse
import datetime as dt
import os
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
CACHE_DIR = PROJECT_ROOT / "scripts" / "rhythm_cache"
REPORTS_DIR = PROJECT_ROOT / "scripts" / "rhythm_reports"

sys.path.insert(0, str(PROJECT_ROOT / "scripts"))

from dotenv import load_dotenv  # noqa: E402

load_dotenv(PROJECT_ROOT / ".env")


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--refs", nargs="+", required=True, help="Reference YouTube URLs")
    p.add_argument("--own-dir", type=Path, default=PROJECT_ROOT / "episodes")
    p.add_argument("--model", default="medium.en")
    p.add_argument("--limit-refs", type=int)
    p.add_argument("--limit-own", type=int)
    p.add_argument(
        "--stage",
        choices=["download", "transcribe", "metrics", "all"],
        default="all",
        help="Stop after this stage",
    )
    p.add_argument("--skip-patches", action="store_true", help="Skip Claude-drafted patch suggestions")
    p.add_argument("--output-dir", type=Path, default=None, help="Override output dir")
    p.add_argument("--host1", default="KIT")
    p.add_argument("--host2", default="DEAN")
    return p.parse_args(argv)


def _pair_own_episodes(own_dir: Path) -> list[tuple[Path, Path]]:
    """Return [(audio, script), ...] pairs, sorted by date descending."""
    pairs: list[tuple[Path, Path]] = []
    for audio in sorted(own_dir.glob("*.mp3"), reverse=True):
        script = own_dir / f"{audio.stem}-script.txt"
        if script.exists():
            pairs.append((audio, script))
    return pairs


def _per_episode_bundle(
    transcript, audio_path: Path, stage: str
) -> dict:
    """Compute macro/micro/structure/energy metrics for one episode. stage kept for progress prints."""
    from rhythm import energy, metrics, structure

    print(f"  [{stage}] metrics — macro/micro ...", flush=True)
    macro = metrics.macro_metrics(transcript)
    micro = metrics.micro_metrics(transcript)
    print(f"  [{stage}] metrics — structure (silence-based segments) ...", flush=True)
    struct = structure.detect_segments(audio_path)
    print(f"  [{stage}] metrics — energy (RMS + F0) ...", flush=True)
    nrg = energy.energy_profile(audio_path)

    # Keep only numeric leaves for aggregation; drop curves (we'll pass them separately)
    nrg_numeric = {
        "rms_dynamic_range_db": nrg["rms_dynamic_range_db"],
        "pitch_f0_mean_hz": nrg["pitch_f0_mean_hz"],
        "pitch_f0_std_hz": nrg["pitch_f0_std_hz"],
    }
    return {
        "macro": macro,
        "micro": micro,
        "structure": {k: v for k, v in struct.items() if not isinstance(v, list)},
        "energy": nrg_numeric,
        "_curves": {"rms": nrg["rms_curve"], "f0": nrg["pitch_f0_curve_hz"]},
    }


def _collect_ref(url: str, refs_cache: Path, model: str, hf_token: str) -> tuple:
    from rhythm import download, transcribe

    print(f"[ref] {url}", flush=True)
    audio_path, meta = download.download_audio(url, refs_cache)
    print(f"  \u2713 {meta.get('title')}  ({(meta.get('duration') or 0) // 60} min)", flush=True)
    t = transcribe.transcribe_full(audio_path, audio_path.parent, model=model, hf_token=hf_token)
    print(f"  \u2713 transcribed: {len(t.words)} words, {len(t.turns)} turns", flush=True)
    return t, meta, audio_path


def _collect_own(audio: Path, script: Path, host1: str, host2: str, model: str) -> tuple:
    from rhythm import transcribe

    print(f"[own] {audio.name}", flush=True)
    cache = CACHE_DIR / "own"
    cache.mkdir(parents=True, exist_ok=True)
    t = transcribe.forced_align(
        audio, script.read_text(), cache, host1=host1, host2=host2, model=model
    )
    print(f"  \u2713 aligned: {len(t.words)} words, {len(t.turns)} turns", flush=True)
    return t, {"path": str(audio), "duration_sec": t.duration_sec}, audio


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    from rhythm import aggregate, report

    refs_cache = CACHE_DIR / "refs"
    refs_cache.mkdir(parents=True, exist_ok=True)

    urls = args.refs[: args.limit_refs] if args.limit_refs else args.refs
    hf_token = os.getenv("HF_TOKEN") or ""

    # Stage 1: download (all URLs, cheap)
    for url in urls:
        from rhythm import download
        audio_path, meta = download.download_audio(url, refs_cache)
        print(f"[download] {meta.get('title')}  ({audio_path.stat().st_size / 1e6:.0f} MB)")

    if args.stage == "download":
        return 0

    # Stage 2: transcribe (refs + own)
    ref_bundles: list[tuple] = []  # (transcript, meta, audio_path)
    for url in urls:
        ref_bundles.append(_collect_ref(url, refs_cache, args.model, hf_token))

    own_pairs = _pair_own_episodes(args.own_dir)
    if args.limit_own:
        own_pairs = own_pairs[: args.limit_own]
    own_bundles: list[tuple] = []
    for audio, script in own_pairs:
        own_bundles.append(_collect_own(audio, script, args.host1, args.host2, args.model))

    if args.stage == "transcribe":
        return 0

    # Stage 3: per-episode metric bundles
    ref_per_ep: list[dict] = []
    ref_meta: list[dict] = []
    for t, m, ap in ref_bundles:
        ref_per_ep.append(_per_episode_bundle(t, ap, "ref"))
        ref_meta.append(m)

    own_per_ep: list[dict] = []
    own_meta: list[dict] = []
    for t, m, ap in own_bundles:
        own_per_ep.append(_per_episode_bundle(t, ap, "own"))
        own_meta.append(m)

    # Stage 4: aggregate + diff
    # Strip _curves before aggregation (they're lists of floats, handled specially in report)
    def _strip_curves(eps):
        return [{k: v for k, v in ep.items() if k != "_curves"} for ep in eps]

    ref_profile = aggregate.aggregate_side(_strip_curves(ref_per_ep))
    own_profile = aggregate.aggregate_side(_strip_curves(own_per_ep))
    diff_rows = aggregate.build_diff(ref_profile, own_profile)

    # Stage 5: patch drafter (Claude)
    patches_md = ""
    if not args.skip_patches:
        print("[patches] drafting prompt-patch suggestions via Claude ...", flush=True)
        prompts_path = PROJECT_ROOT / "src" / "hn_signal" / "prompts.py"
        config_path = PROJECT_ROOT / "src" / "hn_signal" / "config.py"
        sources = {}
        if prompts_path.exists():
            sources["prompts.py (BEAT_SHEET_PROMPT, SYSTEM_PROMPT, REFINEMENT_PROMPT)"] = (
                prompts_path.read_text()
            )
        if config_path.exists():
            # Only the HOST_PROFILES director_note fields are relevant; include whole file for context
            sources["config.py (HOST_PROFILES director_notes)"] = config_path.read_text()
        patches_md = report.draft_patches(diff_rows, sources)
    else:
        patches_md = "# Prompt patch suggestions\n\n_(skipped via --skip-patches)_\n"

    # Stage 6: write outputs
    out_dir = args.output_dir or (REPORTS_DIR / dt.date.today().isoformat())
    ref_transcripts = [b[0] for b in ref_bundles]
    report.write_outputs(
        out_dir=out_dir,
        ref_profile=ref_profile,
        own_profile=own_profile,
        diff_rows=diff_rows,
        ref_meta=ref_meta,
        own_meta=own_meta,
        ref_transcripts=ref_transcripts,
        patches_md=patches_md,
    )
    print(f"[done] \u2192 {out_dir}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
