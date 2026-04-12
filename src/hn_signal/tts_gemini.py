import io
import time
import wave

from pydub import AudioSegment

from hn_signal.config import (
    GEMINI_API_KEY,
    GEMINI_SAMPLE_RATE,
    HOST1,
    HOST2,
    log,
)

GEMINI_MODEL = "gemini-2.5-flash-preview-tts"


def _build_director_notes(host1: dict, host2: dict) -> str:
    """Build TTS director's notes from active host profiles."""
    h1 = host1["full_name"].split()[0]
    h2 = host2["full_name"].split()[0]
    return f"""\
DIRECTOR'S NOTES — read the entire transcript before performing.

SCENE: Two hosts across a small table in a warm studio. Morning light, coffee nearby. \
The energy is NPR meets a late-night tech conversation between old friends who genuinely \
enjoy arguing. You should hear the grin in the audio — the soft palate stays raised to \
keep the tone bright, sunny, and explicitly inviting.

VOICES:
{h1}: {host1["director_note"]}

{h2}: {host2["director_note"]}

PERFORMANCE RULES:
1. PACING: Keep it BRISK. Most turns are SHORT (1-2 sentences). Deliver at natural \
conversational speed — two friends who are excited about what they're discussing, not \
radio announcers. Gaps between turns should be MINIMAL — hosts jump in quickly. \
One-word reactions ("Right.", "Ha!", "Hmm.") are throwaway — quick, almost overlapping.
2. QUESTIONS: Pitch rises naturally. Answers come without long pauses — the host was \
already thinking while the other was talking.
3. INTERRUPTIONS: Lines ending with "—" are cut off. The interrupting host comes in \
with energy and SPEED — they couldn't wait.
4. DISCOVERY MOMENTS: Surprise reactions must sound GENUINE but quick — surprise is a \
reflex, not a dramatic beat.
5. ENERGY ARC: Start warm. Build momentum through the middle — the pace should \
ACCELERATE as hosts get excited. Wind down only at the very end.
6. LAUGHTER: Brief. Never hold a laugh.
7. MOMENTUM: Don't let energy drop between turns. This conversation has FORWARD MOTION.

REACTIONS ARE INVOLUNTARY: Surprise escapes before the speaker can stop it. \
Cognitive shifts happen in real time. Quick and reflexive, not performed.

Transcript:
"""


def _generate_audio_gemini(script: str) -> AudioSegment:
    """Generate dialogue audio using Gemini 2.5 Flash TTS with 2-speaker single-pass."""
    from google import genai
    from google.genai import types

    from hn_signal.audio import _parse_turns

    if not GEMINI_API_KEY:
        raise RuntimeError("GEMINI_API_KEY is required for TTS audio generation")

    turns = _parse_turns(script)
    if not turns:
        h1_name = HOST1["full_name"].split()[0]
        h2_name = HOST2["full_name"].split()[0]
        raise RuntimeError(
            "No valid %s:/%s: turns found in script" % (h1_name.upper(), h2_name.upper())
        )

    log.info("Generating audio for %d turns via Gemini TTS (single-pass)", len(turns))

    # Derive first names for speaker mapping
    h1_name = HOST1["full_name"].split()[0]
    h2_name = HOST2["full_name"].split()[0]

    # Reformat script with speaker names matching voice config
    formatted_lines = []
    for speaker, text in turns:
        name = h1_name if speaker == h1_name.upper() else h2_name
        formatted_lines.append(f"{name}: {text}")

    director_notes = _build_director_notes(HOST1, HOST2)
    dialogue_text = director_notes + "\n".join(formatted_lines)

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
                                    speaker=h1_name,
                                    voice_config=types.VoiceConfig(
                                        prebuilt_voice_config=types.PrebuiltVoiceConfig(
                                            voice_name=HOST1["voice"],
                                        )
                                    ),
                                ),
                                types.SpeakerVoiceConfig(
                                    speaker=h2_name,
                                    voice_config=types.VoiceConfig(
                                        prebuilt_voice_config=types.PrebuiltVoiceConfig(
                                            voice_name=HOST2["voice"],
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
