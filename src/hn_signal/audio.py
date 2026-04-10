import io
import re
import time
import wave
from pathlib import Path

from pydub import AudioSegment

from hn_signal.config import (
    ELEVENLABS_API_KEY,
    ELEVENLABS_VOICE_ID_DEAN,
    ELEVENLABS_VOICE_ID_KIT,
    GEMINI_API_KEY,
    GEMINI_VOICE_DEAN,
    GEMINI_VOICE_KIT,
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


# ---------------------------------------------------------------------------
# Gemini TTS backend (single-pass 2-speaker generation)
# ---------------------------------------------------------------------------

GEMINI_MODEL = "gemini-2.5-flash-preview-tts"
GEMINI_SAMPLE_RATE = 24_000

# Director's notes prepended to the dialogue for Gemini TTS voice styling
GEMINI_DIRECTOR_NOTES = """\
DIRECTOR'S NOTES — read the entire transcript before performing.

VOICES:
Kit: Clear, warm, measured. A designer who thinks before she speaks. Her default pace is \
moderate — she speeds up slightly when excited, slows down for emphasis. Her sharp lines \
("The demo was beautiful. The product is unusable.") should land with a beat of silence \
before them. Pitch drops on devastating observations. Laughs are quiet and genuine — an \
amused exhale, not a performance.

Dean: Warm, energetic, slightly faster default pace. A venture capitalist who's comfortable \
with conviction. Speeds up when pattern-matching ("Look — this is exactly what happened \
with—"). Slows down and drops pitch when naming specific numbers or making predictions. \
Laughs more openly than Kit. His "Look —" and "Here's the thing —" are verbal tics — \
deliver them quickly, not dramatically.

PERFORMANCE RULES:
1. PACING: Most turns are SHORT (1-2 sentences). Deliver them at conversational speed — \
not radio announcer speed. One-word reactions ("Right.", "Ha!", "Hmm.") should be quick \
and throwaway, not emphasized.
2. QUESTIONS: When a host asks a question, pitch should rise naturally. The other host's \
answer should sound like they're THINKING, not reciting — a slight pause, then the response.
3. INTERRUPTIONS: Lines that end with "—" are interrupted. Cut them off mid-word if \
possible. The interrupting host should come in with energy — they couldn't WAIT to respond.
4. DISCOVERY MOMENTS: When a host says "Wait, really?" or "I did not know that" — these \
must sound GENUINE. Slight pause before, pitch shift, real surprise in the voice.
5. ENERGY ARC: Start warm and relaxed. Build energy through the middle. The close should \
feel like winding down a real conversation — slightly slower, more reflective.
6. LAUGHTER: Brief and genuine. "Ha!" is one syllable. "Oh come on" is amused, not angry. \
Never hold a laugh — keep it short and move on.
7. SILENCE: Don't rush to fill every pause. A half-beat of silence before a sharp \
observation makes it land harder.

Transcript:
"""


def _generate_audio_gemini(script: str, output_path: Path) -> tuple[Path, int]:
    """Generate audio using Gemini 2.5 Flash TTS with 2-speaker single-pass."""
    from google import genai
    from google.genai import types

    if not GEMINI_API_KEY:
        raise RuntimeError("GEMINI_API_KEY is required when TTS_BACKEND=gemini")

    turns = _parse_turns(script)
    if not turns:
        raise RuntimeError("No valid KIT:/DEAN: turns found in script")

    log.info("Generating audio for %d turns via Gemini TTS (single-pass)", len(turns))

    # Reformat script with speaker names matching voice config
    formatted_lines = []
    for speaker, text in turns:
        name = "Kit" if speaker == "KIT" else "Dean"
        formatted_lines.append(f"{name}: {text}")
    dialogue_text = GEMINI_DIRECTOR_NOTES + "\n".join(formatted_lines)

    client = genai.Client(api_key=GEMINI_API_KEY)

    # Retry loop for rate limits
    for attempt in range(6):
        try:
            response = client.models.generate_content(
                model=GEMINI_MODEL,
                contents=dialogue_text,
                config=types.GenerateContentConfig(
                    response_modalities=["AUDIO"],
                    speech_config=types.SpeechConfig(
                        multi_speaker_voice_config=types.MultiSpeakerVoiceConfig(
                            speaker_voice_configs=[
                                types.SpeakerVoiceConfig(
                                    speaker="Kit",
                                    voice_config=types.VoiceConfig(
                                        prebuilt_voice_config=types.PrebuiltVoiceConfig(
                                            voice_name=GEMINI_VOICE_KIT,
                                        )
                                    ),
                                ),
                                types.SpeakerVoiceConfig(
                                    speaker="Dean",
                                    voice_config=types.VoiceConfig(
                                        prebuilt_voice_config=types.PrebuiltVoiceConfig(
                                            voice_name=GEMINI_VOICE_DEAN,
                                        )
                                    ),
                                ),
                            ]
                        )
                    ),
                ),
            )
            break
        except Exception as e:
            if ("429" in str(e) or "RESOURCE_EXHAUSTED" in str(e)) and attempt < 5:
                wait = 65
                log.warning("Rate limited, waiting %ds (attempt %d/6)", wait, attempt + 1)
                time.sleep(wait)
            else:
                raise

    audio_data = response.candidates[0].content.parts[0].inline_data.data
    duration_seconds = len(audio_data) // (GEMINI_SAMPLE_RATE * 2)

    # Save as WAV then export to MP3
    wav_tmp = output_path.with_suffix(".wav")
    with wave.open(str(wav_tmp), "wb") as wf:
        wf.setnchannels(1)
        wf.setsampwidth(2)
        wf.setframerate(GEMINI_SAMPLE_RATE)
        wf.writeframes(audio_data)

    segment = AudioSegment.from_wav(str(wav_tmp))
    output_path.parent.mkdir(parents=True, exist_ok=True)
    segment.export(str(output_path), format="mp3", bitrate="192k")
    wav_tmp.unlink()

    log.info("Audio exported: %s (%d seconds)", output_path, duration_seconds)
    return output_path, duration_seconds


# ---------------------------------------------------------------------------
# ElevenLabs TTS backend (per-turn generation, kept as fallback)
# ---------------------------------------------------------------------------

def _generate_audio_elevenlabs(script: str, output_path: Path) -> tuple[Path, int]:
    """Generate audio using ElevenLabs TTS with per-turn generation."""
    from elevenlabs import ElevenLabs, VoiceSettings

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

    duration_seconds = len(combined) // 1000
    output_path.parent.mkdir(parents=True, exist_ok=True)
    combined.export(str(output_path), format="mp3", bitrate="128k")
    log.info("Audio exported: %s (%d seconds)", output_path, duration_seconds)

    return output_path, duration_seconds


# ---------------------------------------------------------------------------
# Public API — routes to configured backend
# ---------------------------------------------------------------------------

def generate_audio(script: str, output_path: Path) -> tuple[Path, int]:
    if TTS_BACKEND == "gemini":
        return _generate_audio_gemini(script, output_path)
    elif TTS_BACKEND == "elevenlabs":
        return _generate_audio_elevenlabs(script, output_path)
    else:
        raise ValueError(f"Unknown TTS_BACKEND: {TTS_BACKEND!r} (expected 'gemini' or 'elevenlabs')")
