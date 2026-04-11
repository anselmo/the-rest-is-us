import random
import re
from pathlib import Path

from pydub import AudioSegment

from hn_signal.config import (
    BREAKER_CROSSFADE_MS,
    BREAKER_DIR,
    BREAKER_PATTERN,
    BREAKER_VOLUME_DB,
    INTRO_CROSSFADE_MS,
    INTRO_MUSIC_PATH,
    MAX_BREAKERS_PER_EPISODE,
    MUSIC_VOLUME_DB,
    OUTRO_FADE_IN_MS,
    OUTRO_MUSIC_PATH,
    TTS_BACKEND,
    log,
)

TURN_PATTERN = re.compile(r"^(KIT|DEAN):\s*", re.MULTILINE)
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
    """Load all breaker clips from assets directory."""
    paths = sorted(BREAKER_DIR.glob(BREAKER_PATTERN))
    if not paths:
        log.warning("No breaker clips found matching %s in %s", BREAKER_PATTERN, BREAKER_DIR)
        return []
    breakers = []
    for p in paths:
        clip = AudioSegment.from_mp3(str(p)) + BREAKER_VOLUME_DB
        breakers.append(clip)
    log.info("Loaded %d breaker clips from %s", len(breakers), BREAKER_DIR)
    return breakers


def _select_break_positions(num_breaks: int, max_breakers: int) -> list[int]:
    """Pick evenly-spaced break positions when there are more breaks than max."""
    if num_breaks <= max_breakers:
        return list(range(num_breaks))
    step = num_breaks / (max_breakers + 1)
    positions = [int(round(step * (i + 1))) - 1 for i in range(max_breakers)]
    return sorted(set(min(p, num_breaks - 1) for p in positions))


# ---------------------------------------------------------------------------
# Intro/outro music
# ---------------------------------------------------------------------------

def _add_music(cold_open: AudioSegment, conversation: AudioSegment) -> AudioSegment:
    """Assemble final audio: cold_open + intro music + conversation + outro music."""
    # Intro music sits between cold open and conversation
    if INTRO_MUSIC_PATH.exists():
        intro = AudioSegment.from_mp3(str(INTRO_MUSIC_PATH)) + MUSIC_VOLUME_DB
        result = cold_open.append(intro, crossfade=INTRO_CROSSFADE_MS)
        result = result.append(conversation, crossfade=INTRO_CROSSFADE_MS)
        log.info("Intro music added between cold open and conversation (%.1fs, %dms crossfade)", len(intro) / 1000, INTRO_CROSSFADE_MS)
    else:
        log.warning("No intro music found at %s, skipping", INTRO_MUSIC_PATH)
        result = cold_open + conversation

    # Outro music fades in under the final lines
    if OUTRO_MUSIC_PATH.exists():
        outro = AudioSegment.from_mp3(str(OUTRO_MUSIC_PATH)) + MUSIC_VOLUME_DB
        fade_ms = min(OUTRO_FADE_IN_MS, len(outro), len(result))
        outro = outro.fade_in(fade_ms)
        overlap_pos = len(result) - fade_ms
        tail_ms = max(0, len(outro) - fade_ms)
        result = result + AudioSegment.silent(duration=tail_ms)
        result = result.overlay(outro, position=overlap_pos)
        log.info("Outro music added (%.1fs, %dms fade-in under dialogue)", len(outro) / 1000, fade_ms)
    else:
        log.warning("No outro music found at %s, skipping", OUTRO_MUSIC_PATH)

    return result


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

    # Route to TTS backend
    if TTS_BACKEND == "gemini":
        from hn_signal.tts_gemini import _generate_audio_gemini
        tts_fn = _generate_audio_gemini
        bitrate = "192k"
    elif TTS_BACKEND == "elevenlabs":
        from hn_signal.tts_elevenlabs import _generate_audio_elevenlabs
        tts_fn = _generate_audio_elevenlabs
        bitrate = "128k"
    else:
        raise ValueError(f"Unknown TTS_BACKEND: {TTS_BACKEND!r} (expected 'gemini' or 'elevenlabs')")

    cold_open = tts_fn(cold_open_script)
    segment_audios = []
    for i, seg_script in enumerate(segments):
        log.info("Generating TTS for segment %d/%d (%d chars)", i + 1, len(segments), len(seg_script))
        segment_audios.append(tts_fn(seg_script))

    # Assemble conversation with breaker clips between segments
    if len(segment_audios) > 1:
        all_breakers = _load_breakers()
        num_breaks = len(segment_audios) - 1
        if all_breakers:
            positions = _select_break_positions(num_breaks, MAX_BREAKERS_PER_EPISODE)
            selected = random.sample(all_breakers, min(len(positions), len(all_breakers)))
            log.info("Inserting %d breakers at positions %s", len(selected), positions)
        else:
            positions, selected = [], []

        conversation = segment_audios[0]
        clip_idx = 0
        for i in range(1, len(segment_audios)):
            if (i - 1) in positions and clip_idx < len(selected):
                breaker = selected[clip_idx]
                clip_idx += 1
                cf = min(BREAKER_CROSSFADE_MS, len(conversation) // 2, len(breaker) // 2)
                conversation = conversation.append(breaker, crossfade=cf)
                cf2 = min(BREAKER_CROSSFADE_MS, len(conversation) // 2, len(segment_audios[i]) // 2)
                conversation = conversation.append(segment_audios[i], crossfade=cf2)
            else:
                conversation = conversation + segment_audios[i]
    else:
        conversation = segment_audios[0]

    final = _add_music(cold_open, conversation)

    output_path.parent.mkdir(parents=True, exist_ok=True)
    final.export(str(output_path), format="mp3", bitrate=bitrate)
    duration_seconds = len(final) // 1000
    log.info("Audio exported: %s (%d seconds)", output_path, duration_seconds)
    return output_path, duration_seconds
