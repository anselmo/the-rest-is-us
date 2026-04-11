import io
import time
import wave

from pydub import AudioSegment

from hn_signal.config import (
    GEMINI_API_KEY,
    GEMINI_SAMPLE_RATE,
    GEMINI_VOICE_DEAN,
    GEMINI_VOICE_KIT,
    log,
)

GEMINI_MODEL = "gemini-2.5-flash-preview-tts"

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


def _generate_audio_gemini(script: str) -> AudioSegment:
    """Generate dialogue audio using Gemini 2.5 Flash TTS with 2-speaker single-pass."""
    from google import genai
    from google.genai import types

    from hn_signal.audio import _parse_turns

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

    # Convert raw PCM to AudioSegment via temporary WAV
    wav_buf = io.BytesIO()
    with wave.open(wav_buf, "wb") as wf:
        wf.setnchannels(1)
        wf.setsampwidth(2)
        wf.setframerate(GEMINI_SAMPLE_RATE)
        wf.writeframes(audio_data)
    wav_buf.seek(0)
    segment = AudioSegment.from_wav(wav_buf)

    log.info("Gemini TTS generated: %d seconds", duration_seconds)
    return segment
