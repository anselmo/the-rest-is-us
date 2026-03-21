import io
import re
from pathlib import Path

from elevenlabs import ElevenLabs
from pydub import AudioSegment

from hn_signal.config import (
    ELEVENLABS_API_KEY,
    ELEVENLABS_VOICE_ID_ALEX,
    ELEVENLABS_VOICE_ID_SAM,
    log,
)

MAX_TURNS = 30
TURN_PATTERN = re.compile(r"^(ALEX|SAM):\s*", re.MULTILINE)


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


def generate_audio(script: str, output_path: Path) -> tuple[Path, int]:
    turns = _parse_turns(script)
    if not turns:
        raise RuntimeError("No valid ALEX:/SAM: turns found in script")

    if len(turns) > MAX_TURNS:
        log.warning("Script has %d turns, truncating to %d", len(turns), MAX_TURNS)
        turns = turns[:MAX_TURNS]

    log.info("Generating audio for %d turns", len(turns))

    client = ElevenLabs(api_key=ELEVENLABS_API_KEY)
    voice_map = {
        "ALEX": ELEVENLABS_VOICE_ID_ALEX,
        "SAM": ELEVENLABS_VOICE_ID_SAM,
    }

    segments: list[AudioSegment] = []
    for i, (speaker, text) in enumerate(turns):
        try:
            audio_iter = client.text_to_speech.convert(
                voice_id=voice_map[speaker],
                text=text,
                model_id="eleven_multilingual_v2",
                output_format="mp3_44100_128",
            )
            # Collect all chunks from the iterator
            audio_bytes = b"".join(audio_iter)
            segment = AudioSegment.from_mp3(io.BytesIO(audio_bytes))
            segments.append(segment)
            log.info("Turn %d/%d (%s): %d chars → %.1fs", i + 1, len(turns), speaker, len(text), len(segment) / 1000)
        except Exception as e:
            log.warning("Turn %d/%d (%s) failed, skipping: %s", i + 1, len(turns), speaker, e)

    if not segments:
        raise RuntimeError("All TTS turns failed, no audio generated")

    combined = segments[0]
    for seg in segments[1:]:
        combined += seg

    duration_seconds = len(combined) // 1000

    output_path.parent.mkdir(parents=True, exist_ok=True)
    combined.export(str(output_path), format="mp3", bitrate="128k")
    log.info("Audio exported: %s (%d seconds)", output_path, duration_seconds)

    return output_path, duration_seconds
