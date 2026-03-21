import io
import re
from pathlib import Path

from elevenlabs import ElevenLabs, VoiceSettings
from pydub import AudioSegment

from hn_signal.config import (
    ELEVENLABS_API_KEY,
    ELEVENLABS_VOICE_ID_ALEX,
    ELEVENLABS_VOICE_ID_MIA,
    ELEVENLABS_VOICE_ID_NICK,
    log,
)

TURN_PATTERN = re.compile(r"^(ALEX|NICK|MIA):\s*", re.MULTILINE)

# Per-speaker voice settings for expressiveness
VOICE_SETTINGS = {
    "ALEX": VoiceSettings(stability=0.40, similarity_boost=0.75, style=0.45, use_speaker_boost=True),
    "NICK": VoiceSettings(stability=0.30, similarity_boost=0.70, style=0.60, use_speaker_boost=True),
    "MIA": VoiceSettings(stability=0.35, similarity_boost=0.75, style=0.50, use_speaker_boost=True),
}


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
        raise RuntimeError("No valid ALEX:/NICK:/MIA: turns found in script")

    log.info("Generating audio for %d turns", len(turns))

    client = ElevenLabs(api_key=ELEVENLABS_API_KEY)
    voice_map = {
        "ALEX": ELEVENLABS_VOICE_ID_ALEX,
        "NICK": ELEVENLABS_VOICE_ID_NICK,
        "MIA": ELEVENLABS_VOICE_ID_MIA,
    }

    segments: list[AudioSegment] = []
    for i, (speaker, text) in enumerate(turns):
        try:
            audio_iter = client.text_to_speech.convert(
                voice_id=voice_map[speaker],
                text=text,
                model_id="eleven_multilingual_v2",
                output_format="mp3_44100_128",
                voice_settings=VOICE_SETTINGS[speaker],
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

    # Concatenate with natural pauses between turns
    combined = segments[0]
    for idx, seg in enumerate(segments[1:], start=1):
        prev_speaker, prev_text = turns[idx - 1]
        curr_speaker, curr_text = turns[idx]

        if curr_speaker == prev_speaker:
            gap_ms = 150
        elif len(curr_text) < 30:
            # Quick interjection — near-immediate, feels like an interruption
            gap_ms = 50
        elif len(curr_text) < 80:
            gap_ms = 150
        elif prev_speaker == "ALEX" and len(prev_text) > 150:
            # After a longer ALEX setup, give a beat before panelist responds
            gap_ms = 500
        else:
            gap_ms = 350

        combined += AudioSegment.silent(duration=gap_ms) + seg

    duration_seconds = len(combined) // 1000

    output_path.parent.mkdir(parents=True, exist_ok=True)
    combined.export(str(output_path), format="mp3", bitrate="128k")
    log.info("Audio exported: %s (%d seconds)", output_path, duration_seconds)

    return output_path, duration_seconds
