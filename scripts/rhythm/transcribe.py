"""whisperX wrapper: full transcription + diarization + word alignment.

Returns an AlignedTranscript — ordered word list and aggregated turn list.
Cached as JSON next to the audio file.

On M-series Mac, we pin device="cpu" and compute_type="int8" because MPS
support in faster-whisper/whisperx is incomplete as of 2026-04.
"""
from __future__ import annotations

import json
import os
import re
from dataclasses import asdict, dataclass, field
from pathlib import Path


@dataclass
class Word:
    word: str
    start: float
    end: float
    speaker: str


@dataclass
class Turn:
    speaker: str
    text: str
    start: float
    end: float
    words: list[Word] = field(default_factory=list)


@dataclass
class AlignedTranscript:
    audio_path: str
    duration_sec: float
    words: list[Word]
    turns: list[Turn]
    source: str  # "whisperx-full" or "whisperx-forced-align"


# Gap threshold for splitting consecutive same-speaker words into separate turns.
# 1.5s is "long enough to feel like a turn boundary but not a breath pause".
_TURN_SPLIT_GAP_SEC = 1.5


def _group_words_into_turns(words: list[Word]) -> list[Turn]:
    turns: list[Turn] = []
    current: list[Word] = []
    for w in words:
        if not current:
            current.append(w)
            continue
        same_speaker = w.speaker == current[-1].speaker
        gap = w.start - current[-1].end
        if same_speaker and gap < _TURN_SPLIT_GAP_SEC:
            current.append(w)
        else:
            turns.append(_turn_from_words(current))
            current = [w]
    if current:
        turns.append(_turn_from_words(current))
    return turns


def _turn_from_words(words: list[Word]) -> Turn:
    text = " ".join(w.word.strip() for w in words if w.word.strip())
    return Turn(
        speaker=words[0].speaker,
        text=text,
        start=words[0].start,
        end=words[-1].end,
        words=words,
    )


def _save(cache_file: Path, transcript: AlignedTranscript) -> None:
    payload = {
        "audio_path": transcript.audio_path,
        "duration_sec": transcript.duration_sec,
        "source": transcript.source,
        "words": [asdict(w) for w in transcript.words],
        "turns": [
            {"speaker": t.speaker, "text": t.text, "start": t.start, "end": t.end}
            for t in transcript.turns
        ],
    }
    cache_file.write_text(json.dumps(payload, indent=2))


def _load(cache_file: Path) -> AlignedTranscript:
    data = json.loads(cache_file.read_text())
    words = [Word(**w) for w in data["words"]]
    turns = _group_words_into_turns(words)
    return AlignedTranscript(
        audio_path=data["audio_path"],
        duration_sec=data["duration_sec"],
        words=words,
        turns=turns,
        source=data["source"],
    )


def transcribe_full(
    audio_path: Path,
    cache_dir: Path,
    model: str = "medium.en",
    hf_token: str | None = None,
    min_speakers: int | None = None,
    max_speakers: int | None = None,
) -> AlignedTranscript:
    """Transcribe + diarize + word-align via whisperX. Caches to JSON by (audio_stem, model).

    min_speakers/max_speakers are optional hints for diarization. Leave both None to
    let pyannote auto-detect (recommended when the reference show's host count is unknown).
    """
    cache_file = cache_dir / f"{audio_path.stem}.{model}.whisperx.json"
    if cache_file.exists():
        return _load(cache_file)

    hf_token = hf_token or os.getenv("HF_TOKEN")
    if not hf_token:
        raise RuntimeError(
            "HF_TOKEN not set. Get a free token at huggingface.co/settings/tokens and accept the "
            "user agreements at:\n"
            "  - https://hf.co/pyannote/speaker-diarization-3.1\n"
            "  - https://hf.co/pyannote/segmentation-3.0\n"
            "  - https://hf.co/pyannote/speaker-diarization-community-1  (required by 3.1 as of 2026-04)"
        )

    import whisperx
    from whisperx.diarize import DiarizationPipeline

    device = "cpu"
    compute_type = "int8"

    audio = whisperx.load_audio(str(audio_path))
    duration_sec = len(audio) / 16_000.0  # whisperx loads at 16kHz

    asr = whisperx.load_model(model, device, compute_type=compute_type)
    result = asr.transcribe(audio, batch_size=16)
    language = result.get("language", "en")

    align_model, metadata = whisperx.load_align_model(language_code=language, device=device)
    result = whisperx.align(
        result["segments"], align_model, metadata, audio, device, return_char_alignments=False
    )

    diarize_pipeline = DiarizationPipeline(
        model_name="pyannote/speaker-diarization-3.1",
        token=hf_token,
        device=device,
    )
    diarize_kwargs: dict = {}
    if min_speakers is not None:
        diarize_kwargs["min_speakers"] = min_speakers
    if max_speakers is not None:
        diarize_kwargs["max_speakers"] = max_speakers
    diarize_segments = diarize_pipeline(audio, **diarize_kwargs)
    result = whisperx.assign_word_speakers(diarize_segments, result)

    words: list[Word] = []
    for seg in result["segments"]:
        for w in seg.get("words", []):
            # Some words lack alignment (e.g., single punctuation); skip if no start.
            if "start" not in w or "end" not in w:
                continue
            words.append(
                Word(
                    word=w.get("word", "").strip(),
                    start=float(w["start"]),
                    end=float(w["end"]),
                    speaker=w.get("speaker", "UNKNOWN"),
                )
            )

    turns = _group_words_into_turns(words)
    transcript = AlignedTranscript(
        audio_path=str(audio_path),
        duration_sec=duration_sec,
        words=words,
        turns=turns,
        source="whisperx-full",
    )
    _save(cache_file, transcript)
    return transcript


def _transcribe_only(audio_path: Path, model: str) -> tuple[list[Word], float]:
    """Transcribe + word-align via whisperX, no diarization. Returns (words, duration)."""
    import whisperx

    device = "cpu"
    compute_type = "int8"
    audio = whisperx.load_audio(str(audio_path))
    duration_sec = len(audio) / 16_000.0

    asr = whisperx.load_model(model, device, compute_type=compute_type)
    result = asr.transcribe(audio, batch_size=16)
    language = result.get("language", "en")
    align_model, metadata = whisperx.load_align_model(language_code=language, device=device)
    result = whisperx.align(
        result["segments"], align_model, metadata, audio, device, return_char_alignments=False
    )

    words: list[Word] = []
    for seg in result["segments"]:
        for w in seg.get("words", []):
            if "start" not in w or "end" not in w:
                continue
            words.append(
                Word(
                    word=w.get("word", "").strip(),
                    start=float(w["start"]),
                    end=float(w["end"]),
                    speaker="",  # filled in by forced_align
                )
            )
    return words, duration_sec


def forced_align(
    audio_path: Path,
    script_text: str,
    cache_dir: Path,
    host1: str,
    host2: str,
    model: str = "medium.en",
) -> AlignedTranscript:
    """Align own audio to canonical KIT:/DEAN: script for speaker labels + timings.

    Strategy: whisperx transcribes own audio (no diarization); we then align
    whisper's word sequence to the canonical script's word sequence (difflib
    SequenceMatcher) and propagate the canonical speaker labels to whisper's
    timed words. Whisper errors get the nearest matched speaker.
    """
    import difflib

    from rhythm._script_parse import parse_turns as _parse_turns

    cache_file = cache_dir / f"{audio_path.stem}.{model}.forced.whisperx.json"
    if cache_file.exists():
        return _load(cache_file)

    # 1. Canonical word list with per-word speaker.
    canonical_turns = _parse_turns(script_text, host1, host2)
    canonical_pairs: list[tuple[str, str]] = []  # (speaker, word)
    for speaker, text in canonical_turns:
        for word in re.findall(r"\b[\w']+\b", text):
            canonical_pairs.append((speaker, word))

    # 2. Whisper word list with timings (no speakers yet).
    whisper_words, duration_sec = _transcribe_only(audio_path, model)

    # 3. Sequence-align whisper's words to canonical words.
    whisper_norm = [re.sub(r"[^\w']", "", w.word).lower() for w in whisper_words]
    canonical_norm = [w.lower() for _, w in canonical_pairs]

    sm = difflib.SequenceMatcher(a=whisper_norm, b=canonical_norm, autojunk=False)
    for block in sm.get_matching_blocks():
        for offset in range(block.size):
            w_idx = block.a + offset
            c_idx = block.b + offset
            if w_idx < len(whisper_words) and c_idx < len(canonical_pairs):
                whisper_words[w_idx].speaker = canonical_pairs[c_idx][0]

    # 4. Fill unmatched whisper words with the most recent matched speaker.
    last_speaker = host1.upper()
    for w in whisper_words:
        if w.speaker:
            last_speaker = w.speaker
        else:
            w.speaker = last_speaker

    turns = _group_words_into_turns(whisper_words)
    transcript = AlignedTranscript(
        audio_path=str(audio_path),
        duration_sec=duration_sec,
        words=whisper_words,
        turns=turns,
        source="whisperx-forced-align",
    )
    _save(cache_file, transcript)
    return transcript
