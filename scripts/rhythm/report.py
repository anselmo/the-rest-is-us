"""Assemble markdown report + JSON profile + patch suggestions + annotated excerpts.

report.md      — human-readable, summary table + per-layer sections
profile.json   — machine-readable rhythm profile (ref + own + diff)
patches.md     — Claude-drafted prompt-patch suggestions
excerpts.md    — annotated reference transcript snippets
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from rhythm.transcribe import AlignedTranscript


def _fmt(value: float, digits: int = 1) -> str:
    if abs(value) >= 100:
        return f"{value:.0f}"
    return f"{value:.{digits}f}"


def _ascii_sparkline(values: list[float]) -> str:
    if not values:
        return ""
    chars = "▁▂▃▄▅▆▇█"
    lo, hi = min(values), max(values)
    span = hi - lo or 1
    return "".join(chars[min(int((v - lo) / span * (len(chars) - 1)), len(chars) - 1)] for v in values)


_LAYER_GROUPS: dict[str, str] = {
    # Label -> prefix used to filter the flattened diff rows.
    "Macro (transcript)": "macro",
    "Micro (audio timing)": "micro",
    "Structural": "structure",
    "Energy": "energy",
}


def _render_table(rows: list[dict], key_prefix: str) -> str:
    # Drop per-speaker rows — they're incomparable when ref uses SPEAKER_00..N and own uses KIT/DEAN.
    filtered = [
        r for r in rows
        if r["metric"].startswith(key_prefix)
        and "per_speaker" not in r["metric"]
    ]
    if not filtered:
        return "_(no data)_\n"
    out = ["| Metric | Reference (mean ± σ) | Own (mean ± σ) | Delta | Direction |",
           "|---|---|---|---|---|"]
    for r in filtered:
        label = r["metric"].split(".", 1)[1] if "." in r["metric"] else r["metric"]
        out.append(
            f"| {label} | {_fmt(r['ref_mean'])} ± {_fmt(r['ref_stdev'])} "
            f"| {_fmt(r['own_mean'])} ± {_fmt(r['own_stdev'])} "
            f"| {_fmt(r['delta'], 2)} "
            f"| {r['direction']} |"
        )
    return "\n".join(out) + "\n"


def render_markdown_report(
    ref_profile: dict, own_profile: dict, diff_rows: list[dict], ref_meta: list[dict], own_meta: list[dict]
) -> str:
    lines = [
        "# Rhythm Profile — Reference vs Own",
        "",
        f"- Reference episodes: **{ref_profile.get('episode_count', 0)}**",
        f"- Own episodes: **{own_profile.get('episode_count', 0)}**",
        "",
        "## Reference corpus",
        "",
    ]
    for m in ref_meta:
        title = m.get("title", "?")
        channel = m.get("channel", "?")
        dur = m.get("duration") or 0
        lines.append(f"- [{title}]({m.get('url', '')}) — {channel} — {dur // 60} min")
    lines += ["", "## Own corpus", ""]
    for m in own_meta:
        lines.append(f"- {m.get('path', '?')} — {m.get('duration_sec', 0):.0f}s")

    lines += ["", "---", ""]
    for layer, prefix in _LAYER_GROUPS.items():
        lines.append(f"## {layer}")
        lines.append("")
        lines.append(_render_table(diff_rows, prefix))
        lines.append("")

    # Energy sparkline section
    ref_rms = ref_profile.get("energy.rms_curve_samples", {})
    own_rms = own_profile.get("energy.rms_curve_samples", {})
    if ref_rms or own_rms:
        lines.append("## Energy envelope sparklines")
        lines.append("")
        if ref_rms.get("samples"):
            lines.append(f"Reference: `{_ascii_sparkline(ref_rms['samples'])}`")
        if own_rms.get("samples"):
            lines.append(f"Own:       `{_ascii_sparkline(own_rms['samples'])}`")
        lines.append("")

    return "\n".join(lines)


def render_excerpts(ref_transcripts: list["AlignedTranscript"], max_snippets: int = 10) -> str:
    """Pick N interesting snippets from the reference — rapid-fire exchanges, long gaps, peaks.

    Currently: find the top rapid-fire runs (4+ consecutive short turns under 100ms gaps).
    """
    lines = ["# Reference transcript excerpts", ""]
    rapid_runs: list[dict] = []
    for t in ref_transcripts:
        turns = t.turns
        i = 0
        while i < len(turns):
            j = i
            # Extend run while turns are short (≤8 words) and gaps small (<500ms)
            while (
                j + 1 < len(turns)
                and len(turns[j + 1].text.split()) <= 8
                and turns[j + 1].start - turns[j].end < 0.5
            ):
                j += 1
            if j - i >= 3:
                rapid_runs.append({
                    "transcript": Path(t.audio_path).parent.name,
                    "start": turns[i].start,
                    "turn_count": j - i + 1,
                    "text": "\n".join(f"{tn.speaker}: {tn.text}" for tn in turns[i : j + 1]),
                })
            i = j + 1

    rapid_runs.sort(key=lambda r: -r["turn_count"])
    for idx, run in enumerate(rapid_runs[:max_snippets], 1):
        lines.append(f"### Rapid-fire exchange #{idx} — {run['turn_count']} turns, starts at {run['start']:.0f}s")
        lines.append("")
        lines.append("```")
        lines.append(run["text"])
        lines.append("```")
        lines.append("")
    if not rapid_runs:
        lines.append("_(No rapid-fire runs of 4+ short turns found.)_")
    return "\n".join(lines)


def write_outputs(
    out_dir: Path,
    ref_profile: dict,
    own_profile: dict,
    diff_rows: list[dict],
    ref_meta: list[dict],
    own_meta: list[dict],
    ref_transcripts: list["AlignedTranscript"],
    patches_md: str,
) -> None:
    out_dir.mkdir(parents=True, exist_ok=True)
    report = render_markdown_report(ref_profile, own_profile, diff_rows, ref_meta, own_meta)
    (out_dir / "report.md").write_text(report)
    (out_dir / "profile.json").write_text(
        json.dumps({"reference": ref_profile, "own": own_profile, "diff": diff_rows}, indent=2, default=str)
    )
    (out_dir / "excerpts.md").write_text(render_excerpts(ref_transcripts))
    (out_dir / "patches.md").write_text(patches_md)


# -------------------------------------------------------------------------
# Patch drafter (Claude SDK)
# -------------------------------------------------------------------------

_PATCH_DRAFTER_SYSTEM = """You are a prompt engineer specializing in conversational AI.

You're given:
1. A rhythm-metric diff between a reference podcast ("target style") and the user's own generated podcast.
2. The current prompt templates the user's pipeline uses to generate scripts (beat sheet, dialogue, refinement) and director's notes for TTS.

Your task: propose SPECIFIC, concrete patches to these prompts/director's notes that would close the measured gap.

Each suggestion must:
- Reference a specific metric gap from the diff (cite the numeric delta)
- Quote the exact EXISTING prompt text you'd change (so the user can find it)
- Provide the exact REPLACEMENT text
- Explain in one sentence why this edit would close the metric gap

Do NOT suggest vague edits like "make it more natural". Every suggestion must tie to a measurable metric.
Do NOT suggest more than 5 edits — pick the highest-leverage ones.

Format each suggestion as:
### Suggestion N — {short title}
**Metric gap:** {metric name}: ref={ref_value}, own={own_value}, delta={delta}
**File:** {path}
**Before:**
```
{exact existing text}
```
**After:**
```
{exact replacement text}
```
**Rationale:** {one sentence}
"""


def draft_patches(diff_rows: list[dict], prompt_sources: dict[str, str]) -> str:
    """Use Claude SDK to draft prompt-patch suggestions. Returns markdown for patches.md."""
    import anthropic

    top_gaps = sorted(diff_rows, key=lambda r: -abs(r["delta"]))[:12]
    gap_summary = "\n".join(
        f"- {r['metric']}: ref={_fmt(r['ref_mean'])} own={_fmt(r['own_mean'])} delta={_fmt(r['delta'], 2)}"
        for r in top_gaps
    )
    sources_block = "\n\n".join(f"## {name}\n```\n{text}\n```" for name, text in prompt_sources.items())
    user_msg = f"""## Metric diff (top 12 by absolute delta)

{gap_summary}

## Current prompts / director notes

{sources_block}

Draft up to 5 patches that would close the biggest gaps."""

    client = anthropic.Anthropic()
    resp = client.messages.create(
        model="claude-opus-4-7",
        max_tokens=4096,
        system=_PATCH_DRAFTER_SYSTEM,
        messages=[{"role": "user", "content": user_msg}],
    )
    return "# Prompt patch suggestions\n\n" + resp.content[0].text
