"""TTS A/B Test: Generate 3 audio samples with stacked improvements.

Sample A: gemini-2.5-flash-preview-tts (current baseline)
Sample B: gemini-2.5-pro-preview-tts (model upgrade only)
Sample C: gemini-2.5-pro-preview-tts + inline markup tags + enhanced director's notes
"""

import io
import os
import sys
import time
import wave
from pathlib import Path

from dotenv import load_dotenv

PROJECT_ROOT = Path(__file__).resolve().parent.parent
load_dotenv(PROJECT_ROOT / ".env")

GEMINI_API_KEY = os.getenv("GEMINI_API_KEY", "").strip()
VOICE_KIT = os.getenv("GEMINI_VOICE_KIT", "Zephyr")
VOICE_DEAN = os.getenv("GEMINI_VOICE_DEAN", "Orus")
SAMPLE_RATE = 24_000

OUTPUT_DIR = PROJECT_ROOT / "episodes" / "tts-test"

# ---------------------------------------------------------------------------
# Director's notes — current (used in samples A & B)
# ---------------------------------------------------------------------------
CURRENT_DIRECTOR_NOTES = """\
DIRECTOR'S NOTES — read the entire transcript before performing.

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

# ---------------------------------------------------------------------------
# Director's notes — enhanced (used in sample C)
# ---------------------------------------------------------------------------
ENHANCED_DIRECTOR_NOTES = """\
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

ENERGY CONTRAST ON INTERRUPTIONS: When a host cuts in, they come in with noticeably \
higher energy than the previous speaker's last line. The contrast is what makes \
interruptions feel real. A flat-energy interruption just sounds like turn-taking.

REACTIONS MUST BE INVOLUNTARY: "Wait — seriously?" should sound like the words escaped \
before the speaker could stop them. "Oh. THAT's interesting." has a genuine cognitive \
shift — the speaker's mental model just updated in real time. These are not performed — \
they are reflexive.

PACING IS JAZZ, NOT METRONOME: Fast exchanges should accelerate slightly with each turn. \
Thoughtful observations should slow down. One-word reactions ("Go on.", "Both, probably.") \
are throwaway — quick, low-effort, almost muttered.

Transcript:
"""

# ---------------------------------------------------------------------------
# Dialogue — baseline (samples A & B)
# ---------------------------------------------------------------------------
DIALOGUE_BASELINE = """\
Kit: Good morning. April eleventh. OpenAI is teaching your finance team how to use ChatGPT, Linux has opinions about AI-written kernel code, and OpenAI quietly bought the CI tooling company nobody outside dev circles has heard of. Welcome to The Rest of Us.
Dean: Let's start with the one almost nobody noticed. Cirrus Labs is joining OpenAI — small announcement, April seventh, easy to scroll past.
Kit: I know Cirrus CI. Niche, but genuinely respected. What stopped you?
Dean: They were bootstrapped since 2017. No VC, no institutional money.
Kit: Wait — seriously?
Dean: The founder literally wrote "we never raised outside capital." Nine years. Profitable. No treadmill. OpenAI isn't buying a seed-stage team — they're buying a PROVEN operator.
Kit: Okay, but here's what I think you're missing. Cirrus isn't just CI tooling.
Dean: Go on.
Kit: The core primitive is ephemeral, clean-room execution environments. Spin up, run, tear down — no state bleeds through.
Dean: Oh. THAT's interesting.
Kit: If you're running autonomous coding agents — and that's exactly what OpenAI is building toward — you cannot have agents polluting each other's state. You need sandboxed execution at scale. That's what Cirrus built, over nine years of edge cases.
Dean: So this isn't a talent acquisition. This is agent infrastructure.
Kit: They needed someone who already solved the hard parts.
Dean: Could they not just build it themselves? What's the actual moat here?
Kit: Time is the moat. Reliable infra takes years of weird edge cases, not months of sprinting.
Dean: And the founder framed it as joining "in the spirit of Bell Labs," which is either genuinely aligned with what OpenAI is building—
Kit: Or the most graceful exit statement ever written.
Dean: Both, probably.
Kit: The real signal is OpenAI assembling the full stack for autonomous coding, piece by quiet piece. Cirrus is just the latest brick.
Dean: And the Linux kernel maintainers are watching all of this with extremely crossed arms."""

# ---------------------------------------------------------------------------
# Dialogue — with inline markup tags (sample C)
# ---------------------------------------------------------------------------
DIALOGUE_WITH_TAGS = """\
Kit: Good morning. [pause] April eleventh. OpenAI is teaching your finance team how to use ChatGPT, Linux has opinions about AI-written kernel code, and OpenAI quietly bought the CI tooling company nobody outside dev circles has heard of. Welcome to The Rest of Us.
Dean: [thoughtful] Let's start with the one almost nobody noticed. Cirrus Labs is joining OpenAI — small announcement, April seventh, easy to scroll past.
Kit: I know Cirrus CI. Niche, but genuinely respected. What stopped you?
Dean: They were bootstrapped since 2017. No VC, no institutional money.
Kit: [surprised] [short pause] Wait — seriously?
Dean: [excited] The founder literally wrote "we never raised outside capital." Nine years. Profitable. [pause] No treadmill. OpenAI isn't buying a seed-stage team — they're buying a PROVEN operator.
Kit: [speaking slowly] Okay, but here's what I think you're missing. Cirrus isn't just CI tooling.
Dean: Go on.
Kit: The core primitive is ephemeral, clean-room execution environments. Spin up, run, tear down — no state bleeds through.
Dean: [short pause] Oh. [surprised] THAT's interesting.
Kit: [speaking quickly] If you're running autonomous coding agents — and that's exactly what OpenAI is building toward — you cannot have agents polluting each other's state. You need sandboxed execution at scale. That's what Cirrus built, over nine years of edge cases.
Dean: [thoughtful] So this isn't a talent acquisition. This is agent infrastructure.
Kit: They needed someone who already solved the hard parts.
Dean: Could they not just build it themselves? What's the actual moat here?
Kit: Time is the moat. [pause] Reliable infra takes years of weird edge cases, not months of sprinting.
Dean: And the founder framed it as joining "in the spirit of Bell Labs," which is either genuinely aligned with what OpenAI is building—
Kit: [laughing] Or the most graceful exit statement ever written.
Dean: [amused] Both, probably.
Kit: [pause] The real signal is OpenAI assembling the full stack for autonomous coding, piece by quiet piece. Cirrus is just the latest brick.
Dean: And the Linux kernel maintainers are watching all of this with extremely crossed arms."""

# ---------------------------------------------------------------------------
# Sample configurations
# ---------------------------------------------------------------------------
SAMPLES = [
    {
        "name": "sample-a-flash-baseline",
        "label": "A (Flash baseline)",
        "model": "gemini-2.5-flash-preview-tts",
        "director_notes": CURRENT_DIRECTOR_NOTES,
        "dialogue": DIALOGUE_BASELINE,
    },
    {
        "name": "sample-b-pro-only",
        "label": "B (Pro model only)",
        "model": "gemini-2.5-pro-preview-tts",
        "director_notes": CURRENT_DIRECTOR_NOTES,
        "dialogue": DIALOGUE_BASELINE,
    },
    {
        "name": "sample-c-pro-markup-enhanced",
        "label": "C (Pro + markup + enhanced notes)",
        "model": "gemini-2.5-pro-preview-tts",
        "director_notes": ENHANCED_DIRECTOR_NOTES,
        "dialogue": DIALOGUE_WITH_TAGS,
    },
]


def generate_sample(sample: dict) -> Path:
    """Generate one TTS sample and save as WAV."""
    from google import genai
    from google.genai import types

    full_text = sample["director_notes"] + sample["dialogue"]
    byte_count = len(full_text.encode("utf-8"))
    print(f"  Text size: {byte_count:,} bytes (limit: 8,000)")

    client = genai.Client(api_key=GEMINI_API_KEY)

    for attempt in range(6):
        try:
            response = client.models.generate_content(
                model=sample["model"],
                contents=full_text,
                config=types.GenerateContentConfig(
                    response_modalities=["AUDIO"],
                    speech_config=types.SpeechConfig(
                        multi_speaker_voice_config=types.MultiSpeakerVoiceConfig(
                            speaker_voice_configs=[
                                types.SpeakerVoiceConfig(
                                    speaker="Kit",
                                    voice_config=types.VoiceConfig(
                                        prebuilt_voice_config=types.PrebuiltVoiceConfig(
                                            voice_name=VOICE_KIT,
                                        )
                                    ),
                                ),
                                types.SpeakerVoiceConfig(
                                    speaker="Dean",
                                    voice_config=types.VoiceConfig(
                                        prebuilt_voice_config=types.PrebuiltVoiceConfig(
                                            voice_name=VOICE_DEAN,
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
            err = str(e)
            if ("429" in err or "RESOURCE_EXHAUSTED" in err) and attempt < 5:
                wait = 65
                print(f"  Rate limited, waiting {wait}s (attempt {attempt + 1}/6)")
                time.sleep(wait)
            else:
                raise

    audio_data = response.candidates[0].content.parts[0].inline_data.data
    duration_seconds = len(audio_data) // (SAMPLE_RATE * 2)

    out_path = OUTPUT_DIR / f"{sample['name']}.wav"
    with wave.open(str(out_path), "wb") as wf:
        wf.setnchannels(1)
        wf.setsampwidth(2)
        wf.setframerate(SAMPLE_RATE)
        wf.writeframes(audio_data)

    print(f"  Saved: {out_path} ({duration_seconds}s)")
    return out_path


def main():
    if not GEMINI_API_KEY:
        print("ERROR: GEMINI_API_KEY not set in .env", file=sys.stderr)
        sys.exit(1)

    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    print(f"Output directory: {OUTPUT_DIR}\n")
    print(f"Voices: Kit={VOICE_KIT}, Dean={VOICE_DEAN}\n")

    results = []
    for sample in SAMPLES:
        print(f"Generating {sample['label']}...")
        print(f"  Model: {sample['model']}")
        try:
            path = generate_sample(sample)
            results.append((sample["label"], path, True))
        except Exception as e:
            print(f"  FAILED: {e}", file=sys.stderr)
            results.append((sample["label"], None, False))

        # Brief pause between samples to avoid burst rate limits
        if sample != SAMPLES[-1]:
            print("  Waiting 10s before next sample...\n")
            time.sleep(10)

    print("\n" + "=" * 60)
    print("RESULTS")
    print("=" * 60)
    for label, path, ok in results:
        status = f"OK  {path}" if ok else "FAILED"
        print(f"  {label}: {status}")

    failed = sum(1 for _, _, ok in results if not ok)
    if failed:
        print(f"\n{failed} sample(s) failed. Check errors above.")
        sys.exit(1)
    else:
        print(f"\nAll {len(results)} samples generated. Listen and fill out RUBRIC.md!")


if __name__ == "__main__":
    main()
