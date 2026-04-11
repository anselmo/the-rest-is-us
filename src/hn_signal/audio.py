import re
from pathlib import Path

from pydub import AudioSegment

from hn_signal.config import (
    INTRO_CROSSFADE_MS,
    INTRO_MUSIC_PATH,
    MUSIC_VOLUME_DB,
    OUTRO_FADE_IN_MS,
    OUTRO_MUSIC_PATH,
    TTS_BACKEND,
    log,
)

TURN_PATTERN = re.compile(r"^(KIT|DEAN):\s*", re.MULTILINE)


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
    conversation_script = _turns_to_script(turns[split:])
    log.info("Script split: %d cold-open turns, %d conversation turns", split, len(turns) - split)

    if TTS_BACKEND == "gemini":
        from hn_signal.tts_gemini import _generate_audio_gemini

        cold_open = _generate_audio_gemini(cold_open_script)
        conversation = _generate_audio_gemini(conversation_script)
        bitrate = "192k"
    elif TTS_BACKEND == "elevenlabs":
        from hn_signal.tts_elevenlabs import _generate_audio_elevenlabs

        cold_open = _generate_audio_elevenlabs(cold_open_script)
        conversation = _generate_audio_elevenlabs(conversation_script)
        bitrate = "128k"
    else:
        raise ValueError(f"Unknown TTS_BACKEND: {TTS_BACKEND!r} (expected 'gemini' or 'elevenlabs')")

    final = _add_music(cold_open, conversation)

    output_path.parent.mkdir(parents=True, exist_ok=True)
    final.export(str(output_path), format="mp3", bitrate=bitrate)
    duration_seconds = len(final) // 1000
    log.info("Audio exported: %s (%d seconds)", output_path, duration_seconds)
    return output_path, duration_seconds
