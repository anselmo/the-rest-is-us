"""Macro (transcript-only) and micro (audio-timing) metric computation.

All functions take an AlignedTranscript (from transcribe.py) and return nested dicts.
Pure stdlib — safe to import without `--extra rhythm`.
"""
from __future__ import annotations

import re
import statistics
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from rhythm.transcribe import AlignedTranscript, Turn


# Fillers we count toward filler density (case-insensitive, multi-word phrases allowed).
_FILLER_PHRASES = [
    r"\bum\b",
    r"\buh\b",
    r"\buhm\b",
    r"\berm\b",
    r"\blike\b",        # high-frequency; dominates density — flagged separately in report
    r"\byou know\b",
    r"\bi mean\b",
    r"\bkind of\b",
    r"\bsort of\b",
    r"\bbasically\b",
]
_FILLER_RE = re.compile("|".join(_FILLER_PHRASES), re.IGNORECASE)

_SENTENCE_END_RE = re.compile(r"[.!?](?:\s|$)")
_WORD_RE = re.compile(r"\b[\w']+\b")


def _words_in(text: str) -> list[str]:
    return _WORD_RE.findall(text)


def _count_sentences(text: str) -> int:
    # Count terminal punctuation. Ellipses (...) don't count.
    cleaned = text.replace("...", " ").replace("…", " ")
    count = len(_SENTENCE_END_RE.findall(cleaned))
    return max(count, 1)  # a turn is at least one sentence even without terminal punctuation


def _percentile(values: list[float], p: float) -> float:
    if not values:
        return 0.0
    # statistics.quantiles with n=100 is unreliable at extremes; use sort + index.
    s = sorted(values)
    k = (len(s) - 1) * p
    lo = int(k)
    hi = min(lo + 1, len(s) - 1)
    frac = k - lo
    return s[lo] * (1 - frac) + s[hi] * frac


def _turn_summary(turns: list["Turn"]) -> dict:
    """Aggregated per-speaker turn-level shape."""
    out: dict = {"overall": {}, "per_speaker": {}}
    all_lengths = [len(_words_in(t.text)) for t in turns]
    out["overall"] = {
        "turn_count": len(turns),
        "turn_length_words_p50": _percentile(all_lengths, 0.5),
        "turn_length_words_p90": _percentile(all_lengths, 0.9),
        "turn_length_words_max": max(all_lengths, default=0),
        "turn_length_words_mean": statistics.fmean(all_lengths) if all_lengths else 0.0,
    }
    speakers = sorted({t.speaker for t in turns})
    for spk in speakers:
        lengths = [len(_words_in(t.text)) for t in turns if t.speaker == spk]
        out["per_speaker"][spk] = {
            "turn_count": len(lengths),
            "turn_length_words_p50": _percentile(lengths, 0.5),
            "turn_length_words_p90": _percentile(lengths, 0.9),
            "turn_length_words_max": max(lengths, default=0),
            "turn_length_words_mean": statistics.fmean(lengths) if lengths else 0.0,
        }
    return out


def macro_metrics(transcript: "AlignedTranscript") -> dict:
    """Transcript-only metrics. See plan 'Macro' section."""
    turns = transcript.turns
    total_words = sum(len(_words_in(t.text)) for t in turns)

    short_reactions = sum(1 for t in turns if len(_words_in(t.text)) <= 5)
    long_turns = sum(1 for t in turns if _count_sentences(t.text) >= 3)
    question_turns = sum(1 for t in turns if t.text.rstrip().endswith("?"))
    filler_count = sum(len(_FILLER_RE.findall(t.text)) for t in turns)

    return {
        "total_words": total_words,
        "turns_per_episode": len(turns),
        "one_word_reaction_rate": short_reactions / len(turns) if turns else 0.0,
        "long_turn_rate": long_turns / len(turns) if turns else 0.0,
        "question_rate": question_turns / len(turns) if turns else 0.0,
        "filler_density_per_100_words": (filler_count / total_words * 100) if total_words else 0.0,
        **_turn_summary(turns),
    }


def micro_metrics(transcript: "AlignedTranscript") -> dict:
    """Word-timing metrics. Requires word start/end timestamps. See plan 'Micro' section."""
    words = transcript.words
    duration = transcript.duration_sec or 1.0

    # WPM: words per minute. Overall = total words / (duration_sec / 60).
    wpm_overall = len(words) / (duration / 60.0) if duration > 0 else 0.0

    wpm_per_speaker: dict = {}
    speakers = sorted({w.speaker for w in words})
    for spk in speakers:
        spk_words = [w for w in words if w.speaker == spk]
        if not spk_words:
            continue
        # Speaker airtime = sum of turn durations where that speaker was active.
        spk_airtime = sum(w.end - w.start for w in spk_words)
        # More accurate: use turn boundaries (end - start) because word-duration sum underestimates.
        spk_turns = [t for t in transcript.turns if t.speaker == spk]
        spk_airtime_turns = sum(t.end - t.start for t in spk_turns)
        airtime = max(spk_airtime, spk_airtime_turns, 1.0)
        wpm_per_speaker[spk] = len(spk_words) / (airtime / 60.0)

    # Inter-turn gap: silence between end of one turn and start of the next.
    # Only count gaps between turns with different speakers (handoff gaps).
    turns = transcript.turns
    handoff_gaps_ms: list[float] = []
    for prev, curr in zip(turns, turns[1:]):
        if prev.speaker != curr.speaker:
            gap_sec = max(curr.start - prev.end, 0.0)
            handoff_gaps_ms.append(gap_sec * 1000.0)

    # Within-turn pauses: gaps ≥ 200ms between consecutive words in the same turn.
    within_turn_pauses_ms: list[float] = []
    for turn in turns:
        for w1, w2 in zip(turn.words, turn.words[1:]):
            gap_sec = w2.start - w1.end
            if gap_sec >= 0.2:
                within_turn_pauses_ms.append(gap_sec * 1000.0)

    return {
        "wpm_overall": wpm_overall,
        "wpm_per_speaker": wpm_per_speaker,
        "inter_turn_gap_ms": {
            "count": len(handoff_gaps_ms),
            "p50": _percentile(handoff_gaps_ms, 0.5),
            "p90": _percentile(handoff_gaps_ms, 0.9),
            "mean": statistics.fmean(handoff_gaps_ms) if handoff_gaps_ms else 0.0,
            "stdev": statistics.pstdev(handoff_gaps_ms) if len(handoff_gaps_ms) > 1 else 0.0,
        },
        "within_turn_pause_ms": {
            "count": len(within_turn_pauses_ms),
            "p50": _percentile(within_turn_pauses_ms, 0.5),
            "p90": _percentile(within_turn_pauses_ms, 0.9),
        },
    }
