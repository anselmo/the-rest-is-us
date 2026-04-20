import random
import re
from itertools import cycle
from pathlib import Path

from pydub import AudioSegment
from pydub.silence import detect_leading_silence

from hn_signal.config import (
    BREAK_POST_SILENCE_MS,
    BREAK_PRE_SILENCE_MS,
    BREAKER_BED_HOLD_MS,
    BREAKER_DIR,
    BREAKER_FADE_OUT_MS,
    BREAKER_PATTERN,
    BREAKER_SWELL_HOLD_MS,
    HOST1,
    HOST2,
    INTRO_BED_DURATION_MS,
    INTRO_FADE_OUT_MS,
    INTRO_MUSIC_PATH,
    INTRO_POST_SILENCE_MS,
    INTRO_SWELL_HOLD_MS,
    MUSIC_BED_DB,
    MUSIC_FADE_IN_MS,
    MUSIC_SWELL_DB,
    MUSIC_SWELL_RAMP_MS,
    OUTRO_BED_DURATION_MS,
    OUTRO_MUSIC_PATH,
    TTS_TRIM_SILENCE_CHUNK_MS,
    TTS_TRIM_SILENCE_THRESHOLD_DBFS,
    log,
)
from hn_signal.tts_gemini import _generate_audio_gemini


def _build_turn_pattern() -> re.Pattern:
    """Build turn-parsing regex from active host names."""
    h1 = HOST1["full_name"].split()[0].upper()
    h2 = HOST2["full_name"].split()[0].upper()
    return re.compile(rf"^({h1}|{h2}):\s*", re.MULTILINE)


TURN_PATTERN = _build_turn_pattern()
BREAK_MARKER = re.compile(r"^\[BREAK\]$", re.MULTILINE)


def _parse_turns(script: str) -> list[tuple[str, str]]:
    """Parse script into [(speaker, text), ...] turns."""
    matches = list(TURN_PATTERN.finditer(script))
    if not matches:
        return []

    turns = []
    for i, match in enumerate(matches):
        speaker = match.group(1)
        start = match.end()
        end = matches[i + 1].start() if i + 1 < len(matches) else len(script)
        text = script[start:end].strip()
        if text:
            turns.append((speaker, text))
    return turns


def _find_cold_open_end(turns: list[tuple[str, str]]) -> int:
    """Find the turn index where the cold open ends (after the 'Rest of Us' mention)."""
    for i, (_speaker, text) in enumerate(turns):
        if "rest of us" in text.lower():
            return i + 1
    # Fallback: assume first 2 turns are the cold open
    return min(2, len(turns))


def _turns_to_script(turns: list[tuple[str, str]]) -> str:
    """Convert a list of (speaker, text) turns back to script format."""
    return "\n".join(f"{speaker}: {text}" for speaker, text in turns)


# ---------------------------------------------------------------------------
# Breaker clips (story separators)
# ---------------------------------------------------------------------------

def _split_at_breaks(script: str) -> list[str]:
    """Split script at [BREAK] markers, returning segment scripts."""
    parts = BREAK_MARKER.split(script)
    return [p.strip() for p in parts if p.strip()]


def _load_breakers() -> list[AudioSegment]:
    """Load all breaker clips from assets directory at their native level."""
    paths = sorted(BREAKER_DIR.glob(BREAKER_PATTERN))
    if not paths:
        log.warning("No breaker clips found matching %s in %s", BREAKER_PATTERN, BREAKER_DIR)
        return []
    breakers = [AudioSegment.from_mp3(str(p)) for p in paths]
    log.info("Loaded %d breaker clips from %s", len(breakers), BREAKER_DIR)
    return breakers


# ---------------------------------------------------------------------------
# Silence trim + music envelope shaping
# ---------------------------------------------------------------------------


def _trim_trailing_silence(segment: AudioSegment) -> AudioSegment:
    """Strip trailing silence so music-placement anchors land on real speech end."""
    trailing_ms = detect_leading_silence(
        segment.reverse(),
        silence_threshold=TTS_TRIM_SILENCE_THRESHOLD_DBFS,
        chunk_size=TTS_TRIM_SILENCE_CHUNK_MS,
    )
    if trailing_ms > 0:
        return segment[: len(segment) - trailing_ms]
    return segment


def _shape_music(
    music: AudioSegment,
    bed_ms: int,
    swell_hold_ms: int | None,
    fade_out_ms: int,
) -> AudioSegment:
    """
    Build a music segment with a bed → swell → optional fade-out envelope.

    Regions (ms, by offset into the returned segment):
      [0, MUSIC_FADE_IN_MS)          : silence → bed fade-in
      [MUSIC_FADE_IN_MS, bed_ms)     : hold at bed
      [bed_ms, bed_ms + ramp)        : bed → swell linear ramp
      [ramp end, swell_end)          : hold at swell (swell_hold_ms, or remainder if None)
      [swell_end, + fade_out_ms)     : swell → silence fade-out
    """
    ramp_start = bed_ms
    ramp_end = bed_ms + MUSIC_SWELL_RAMP_MS

    if swell_hold_ms is None:
        swell_end = len(music) - fade_out_ms
    else:
        swell_end = ramp_end + swell_hold_ms

    if swell_end <= ramp_end:
        log.warning(
            "Music file too short for requested envelope (len=%dms, need=%dms); truncating",
            len(music), ramp_end + fade_out_ms,
        )
        swell_end = ramp_end

    fade_in = music[:MUSIC_FADE_IN_MS].apply_gain(MUSIC_BED_DB).fade_in(MUSIC_FADE_IN_MS)
    bed_hold = music[MUSIC_FADE_IN_MS:ramp_start].apply_gain(MUSIC_BED_DB)
    ramp = music[ramp_start:ramp_end].fade(
        from_gain=MUSIC_BED_DB,
        to_gain=MUSIC_SWELL_DB,
        start=0,
        duration=MUSIC_SWELL_RAMP_MS,
    )
    swell_hold = music[ramp_end:swell_end].apply_gain(MUSIC_SWELL_DB)

    shaped = fade_in + bed_hold + ramp + swell_hold
    if fade_out_ms > 0:
        fade_out = music[swell_end:swell_end + fade_out_ms].apply_gain(MUSIC_SWELL_DB).fade_out(fade_out_ms)
        shaped = shaped + fade_out
    return shaped


# ---------------------------------------------------------------------------
# Intro/outro music
# ---------------------------------------------------------------------------

def _add_intro(cold_open: AudioSegment, conversation: AudioSegment) -> AudioSegment:
    """Bed intro music under the last INTRO_BED_DURATION_MS of the cold open, swell, fade."""
    cold_open = _trim_trailing_silence(cold_open)
    if not INTRO_MUSIC_PATH.exists():
        log.warning("No intro music found at %s, skipping", INTRO_MUSIC_PATH)
        return cold_open + AudioSegment.silent(duration=INTRO_POST_SILENCE_MS) + conversation

    intro_raw = AudioSegment.from_mp3(str(INTRO_MUSIC_PATH))
    intro_shaped = _shape_music(
        intro_raw,
        bed_ms=INTRO_BED_DURATION_MS,
        swell_hold_ms=INTRO_SWELL_HOLD_MS,
        fade_out_ms=INTRO_FADE_OUT_MS,
    )
    overlap_pos = max(0, len(cold_open) - INTRO_BED_DURATION_MS)
    tail_ms = max(0, len(intro_shaped) - (len(cold_open) - overlap_pos)) + INTRO_POST_SILENCE_MS
    extended = cold_open + AudioSegment.silent(duration=tail_ms)
    result = extended.overlay(intro_shaped, position=overlap_pos)
    log.info(
        "Intro music shaped (%.1fs) bed-under-%.1fs, swell %dms, fade %dms",
        len(intro_shaped) / 1000,
        INTRO_BED_DURATION_MS / 1000,
        INTRO_SWELL_HOLD_MS,
        INTRO_FADE_OUT_MS,
    )
    return result + conversation


def _add_outro(body: AudioSegment) -> AudioSegment:
    """Bed outro music under the last OUTRO_BED_DURATION_MS of dialogue, swell to end."""
    body = _trim_trailing_silence(body)
    if not OUTRO_MUSIC_PATH.exists():
        log.warning("No outro music found at %s, skipping", OUTRO_MUSIC_PATH)
        return body

    outro_raw = AudioSegment.from_mp3(str(OUTRO_MUSIC_PATH))
    outro_shaped = _shape_music(
        outro_raw,
        bed_ms=OUTRO_BED_DURATION_MS,
        swell_hold_ms=None,
        fade_out_ms=0,
    )
    overlap_pos = max(0, len(body) - OUTRO_BED_DURATION_MS)
    tail_ms = max(0, len(outro_shaped) - (len(body) - overlap_pos))
    extended = body + AudioSegment.silent(duration=tail_ms)
    result = extended.overlay(outro_shaped, position=overlap_pos)
    log.info(
        "Outro music shaped (%.1fs) bed-under-%.1fs, swell to end",
        len(outro_shaped) / 1000,
        OUTRO_BED_DURATION_MS / 1000,
    )
    return result


def _shape_breaker(breaker: AudioSegment) -> AudioSegment:
    """Envelope a breaker clip: fade-in → bed hold → swell ramp → swell hold → fade-out."""
    return _shape_music(
        breaker,
        bed_ms=BREAKER_BED_HOLD_MS + MUSIC_FADE_IN_MS,
        swell_hold_ms=BREAKER_SWELL_HOLD_MS,
        fade_out_ms=BREAKER_FADE_OUT_MS,
    )


# ---------------------------------------------------------------------------
# Public API — routes to configured backend
# ---------------------------------------------------------------------------

def generate_audio(script: str, output_path: Path) -> tuple[Path, int]:
    turns = _parse_turns(script)
    split = _find_cold_open_end(turns)
    cold_open_script = _turns_to_script(turns[:split])

    # Slice raw script at the conversation start to preserve [BREAK] markers
    # (_turns_to_script would discard them).
    matches = list(TURN_PATTERN.finditer(script))
    if split < len(matches):
        conversation_text = script[matches[split].start():]
    else:
        conversation_text = _turns_to_script(turns[split:])

    log.info("Script split: %d cold-open turns, %d conversation turns", split, len(turns) - split)

    # Split conversation at [BREAK] markers
    segments = _split_at_breaks(conversation_text)
    if len(segments) <= 1:
        segments = [conversation_text]
        log.info("No [BREAK] markers found, treating conversation as single segment")
    else:
        log.info("Found %d segments separated by %d [BREAK] markers", len(segments), len(segments) - 1)

    cold_open = _generate_audio_gemini(cold_open_script)
    segment_audios = []
    for i, seg_script in enumerate(segments):
        log.info("Generating TTS for segment %d/%d (%d chars)", i + 1, len(segments), len(seg_script))
        segment_audios.append(_generate_audio_gemini(seg_script))

    # Trim trailing silence from each segment so break timing anchors on real speech end
    segment_audios = [_trim_trailing_silence(s) for s in segment_audios]

    # Assemble conversation with shaped breaker clips between segments
    if len(segment_audios) > 1:
        all_breakers = _load_breakers()
        if all_breakers:
            breaker_pool = list(all_breakers)
            random.shuffle(breaker_pool)
            breaker_cycle = cycle(breaker_pool)
            log.info(
                "Inserting breakers at all %d break positions (shuffled pool of %d, cycling)",
                len(segment_audios) - 1, len(all_breakers),
            )
        else:
            breaker_cycle = None

        conversation = segment_audios[0]
        for i in range(1, len(segment_audios)):
            if breaker_cycle is not None:
                breaker_shaped = _shape_breaker(next(breaker_cycle))
                conversation = (
                    conversation
                    + AudioSegment.silent(duration=BREAK_PRE_SILENCE_MS)
                    + breaker_shaped
                    + AudioSegment.silent(duration=BREAK_POST_SILENCE_MS)
                    + segment_audios[i]
                )
            else:
                conversation = (
                    conversation
                    + AudioSegment.silent(duration=BREAK_PRE_SILENCE_MS + BREAK_POST_SILENCE_MS)
                    + segment_audios[i]
                )
    else:
        conversation = segment_audios[0]

    with_intro = _add_intro(cold_open, conversation)
    final = _add_outro(with_intro)

    output_path.parent.mkdir(parents=True, exist_ok=True)
    final.export(str(output_path), format="mp3", bitrate="192k")
    duration_seconds = len(final) // 1000
    log.info("Audio exported: %s (%d seconds)", output_path, duration_seconds)
    return output_path, duration_seconds
