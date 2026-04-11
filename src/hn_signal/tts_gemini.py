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

SCENE: Two hosts across a small table in a warm studio. Morning light, coffee nearby. \
The energy is NPR meets a late-night tech conversation between old friends who genuinely \
enjoy arguing. You should hear the grin in the audio — the soft palate stays raised to \
keep the tone bright, sunny, and explicitly inviting.

VOICES:
Kit: Clear, warm, measured. A designer who thinks before she speaks. Her default pace is \
moderate — she speeds up slightly when excited, slows down for emphasis. Her sharp lines \
should land with a beat of silence before them. Pitch drops on devastating observations. \
Laughs are quiet and genuine — an amused exhale, not a performance.

Dean: Warm, energetic, slightly faster default pace. A venture capitalist who's comfortable \
with conviction. Speeds up when pattern-matching. Slows down and drops pitch when naming \
specific numbers or making predictions. Laughs more openly than Kit. His "Look —" and \
"Here's the thing —" are verbal tics — deliver them quickly, not dramatically.

PERFORMANCE RULES:
1. PACING: Keep it BRISK. Most turns are SHORT (1-2 sentences). Deliver at natural \
conversational speed — two friends who are excited about what they're discussing, not \
radio announcers. Gaps between turns should be MINIMAL — hosts jump in quickly. \
One-word reactions ("Right.", "Ha!", "Hmm.") are throwaway — quick, almost overlapping.
2. QUESTIONS: Pitch rises naturally. Answers come without long pauses — the host was \
already thinking while the other was talking.
3. INTERRUPTIONS: Lines ending with "—" are cut off. The interrupting host comes in \
with energy and SPEED — they couldn't wait.
4. DISCOVERY MOMENTS: "Wait, really?" must sound GENUINE but quick — surprise is a \
reflex, not a dramatic beat.
5. ENERGY ARC: Start warm. Build momentum through the middle — the pace should \
ACCELERATE as hosts get excited. Wind down only at the very end.
6. LAUGHTER: Brief. "Ha!" is one syllable. Never hold a laugh.
7. MOMENTUM: Don't let energy drop between turns. This conversation has FORWARD MOTION.

REACTIONS ARE INVOLUNTARY: "Wait — seriously?" escapes before the speaker can stop it. \
"Oh. THAT's interesting." is a real-time cognitive shift. Quick and reflexive, not performed.

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
