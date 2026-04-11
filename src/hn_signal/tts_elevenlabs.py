import io

from pydub import AudioSegment

from hn_signal.config import (
    ELEVENLABS_API_KEY,
    ELEVENLABS_VOICE_ID_DEAN,
    ELEVENLABS_VOICE_ID_KIT,
    log,
)


def _generate_audio_elevenlabs(script: str) -> AudioSegment:
    """Generate dialogue audio using ElevenLabs TTS with per-turn generation."""
    from elevenlabs import ElevenLabs, VoiceSettings

    from hn_signal.audio import _parse_turns

    if not ELEVENLABS_API_KEY:
        raise RuntimeError("ELEVENLABS_API_KEY is required when TTS_BACKEND=elevenlabs")
    if not ELEVENLABS_VOICE_ID_KIT or not ELEVENLABS_VOICE_ID_DEAN:
        raise RuntimeError("ELEVENLABS_VOICE_ID_KIT and ELEVENLABS_VOICE_ID_DEAN are required")

    turns = _parse_turns(script)
    if not turns:
        raise RuntimeError("No valid KIT:/DEAN: turns found in script")

    log.info("Generating audio for %d turns via ElevenLabs", len(turns))

    voice_settings = {
        "KIT": VoiceSettings(stability=0.40, similarity_boost=0.75, style=0.45, use_speaker_boost=True),
        "DEAN": VoiceSettings(stability=0.35, similarity_boost=0.75, style=0.50, use_speaker_boost=True),
    }
    voice_map = {
        "KIT": ELEVENLABS_VOICE_ID_KIT,
        "DEAN": ELEVENLABS_VOICE_ID_DEAN,
    }

    client = ElevenLabs(api_key=ELEVENLABS_API_KEY)
    segments: list[AudioSegment] = []

    for i, (speaker, text) in enumerate(turns):
        try:
            audio_iter = client.text_to_speech.convert(
                voice_id=voice_map[speaker],
                text=text,
                model_id="eleven_multilingual_v2",
                output_format="mp3_44100_128",
                voice_settings=voice_settings[speaker],
            )
            audio_bytes = b"".join(audio_iter)
            segment = AudioSegment.from_mp3(io.BytesIO(audio_bytes))
            segments.append(segment)
            log.info("Turn %d/%d (%s): %d chars → %.1fs", i + 1, len(turns), speaker, len(text), len(segment) / 1000)
        except Exception as e:
            log.warning("Turn %d/%d (%s) failed, skipping: %s", i + 1, len(turns), speaker, e)

    if not segments:
        raise RuntimeError("All TTS turns failed, no audio generated")

    # Concatenate with natural pauses
    combined = segments[0]
    for idx, seg in enumerate(segments[1:], start=1):
        prev_speaker, prev_text = turns[idx - 1]
        curr_speaker, curr_text = turns[idx]

        if curr_speaker == prev_speaker:
            gap_ms = 100
        elif len(curr_text) < 30:
            gap_ms = 0
        elif len(curr_text) < 80:
            gap_ms = 80
        else:
            gap_ms = 200

        combined += AudioSegment.silent(duration=gap_ms) + seg

    log.info("ElevenLabs TTS generated: %d seconds", len(combined) // 1000)
    return combined
