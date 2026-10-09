"""Voice + Persona Test: Generate 6 audio samples with distinct host pairs.

Each pair has unique names, backgrounds, voice assignments, and director's notes.
Same Cirrus Labs dialogue segment, same brisk pacing rules — isolates voice+persona chemistry.
"""

import os
import sys
import time
import wave
from pathlib import Path

from dotenv import load_dotenv

PROJECT_ROOT = Path(__file__).resolve().parent.parent
load_dotenv(PROJECT_ROOT / ".env")

GEMINI_API_KEY = os.getenv("GEMINI_API_KEY", "").strip()
SAMPLE_RATE = 24_000
MODEL = "gemini-2.5-flash-preview-tts"
OUTPUT_DIR = PROJECT_ROOT / "episodes" / "tts-test"

# ---------------------------------------------------------------------------
# Shared pacing rules (from Sample E — the winning config)
# ---------------------------------------------------------------------------
PACING_RULES = """\
PERFORMANCE RULES:
1. PACING: Keep it BRISK. Most turns are SHORT (1-2 sentences). Deliver at natural \
conversational speed — two people who are excited about what they're discussing, not \
radio announcers. Gaps between turns should be MINIMAL — hosts jump in quickly. \
One-word reactions are throwaway — quick, almost overlapping.
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

# ---------------------------------------------------------------------------
# Dialogue template — {host1} and {host2} are replaced per pair
# ---------------------------------------------------------------------------
DIALOGUE_TEMPLATE = """\
{host1}: Good morning. April eleventh. OpenAI is teaching your finance team how to use \
ChatGPT, Linux has opinions about AI-written kernel code, and OpenAI quietly bought the \
CI tooling company nobody outside dev circles has heard of. Welcome to The Rest of Us.
{host2}: [thoughtful] Let's start with the one almost nobody noticed. Cirrus Labs is \
joining OpenAI — small announcement, April seventh, easy to scroll past.
{host1}: I know Cirrus CI. Niche, but genuinely respected. What stopped you?
{host2}: They were bootstrapped since 2017. No VC, no institutional money.
{host1}: [surprised] Wait — seriously?
{host2}: [excited] The founder literally wrote "we never raised outside capital." Nine \
years. Profitable. No treadmill. OpenAI isn't buying a seed-stage team — they're buying \
a PROVEN operator.
{host1}: Okay, but here's what I think you're missing. Cirrus isn't just CI tooling.
{host2}: Go on.
{host1}: The core primitive is ephemeral, clean-room execution environments. Spin up, \
run, tear down — no state bleeds through.
{host2}: Oh. [surprised] THAT's interesting.
{host1}: [speaking quickly] If you're running autonomous coding agents — and that's \
exactly what OpenAI is building toward — you cannot have agents polluting each other's \
state. You need sandboxed execution at scale. That's what Cirrus built, over nine years \
of edge cases.
{host2}: [thoughtful] So this isn't a talent acquisition. This is agent infrastructure.
{host1}: They needed someone who already solved the hard parts.
{host2}: Could they not just build it themselves? What's the actual moat here?
{host1}: Time is the moat. Reliable infra takes years of weird edge cases, not months \
of sprinting.
{host2}: And the founder framed it as joining "in the spirit of Bell Labs," which is \
either genuinely aligned with what OpenAI is building—
{host1}: [laughing] Or the most graceful exit statement ever written.
{host2}: [amused] Both, probably.
{host1}: The real signal is OpenAI assembling the full stack for autonomous coding, \
piece by quiet piece. Cirrus is just the latest brick.
{host2}: And the Linux kernel maintainers are watching all of this with extremely \
crossed arms."""

# ---------------------------------------------------------------------------
# Host pair configurations
# ---------------------------------------------------------------------------
PAIRS = [
    {
        "id": "pair1-luna-kai-lab-bench",
        "label": "1. Luna + Kai — The Lab Bench",
        "host1": {"name": "Luna", "voice": "Aoede"},
        "host2": {"name": "Kai", "voice": "Charon"},
        "scene": """\
DIRECTOR'S NOTES — read the entire transcript before performing.

SCENE: A university office with whiteboards covered in equations. Two researchers \
who've known each other since grad school, debating over coffee. The energy is \
intellectually curious — they challenge each other's reasoning, not their competence.

VOICES:
Luna: Breezy and relaxed. An ML researcher who reads papers the way other people \
read the news. Her default pace is unhurried — she thinks out loud, pauses to \
reformulate. Gets animated when methodology is elegant. Skeptical of hype, but \
genuinely excited by good science.

Kai: Calm and informative. A systems engineer who's built production infra. \
Measured delivery — he states facts cleanly. Gets slightly faster when he spots \
a real engineering insight. Dry humor. Asks "but does it scale?" without irony.

""",
    },
    {
        "id": "pair2-vera-niko-friction-point",
        "label": "2. Vera + Niko — The Friction Point",
        "host1": {"name": "Vera", "voice": "Gacrux"},
        "host2": {"name": "Niko", "voice": "Fenrir"},
        "scene": """\
DIRECTOR'S NOTES — read the entire transcript before performing.

SCENE: A heated but respectful debate between two people who see the same facts \
and draw opposite conclusions. The energy is tense — they genuinely disagree, but \
there's mutual respect underneath. Think panel debate, not argument.

VOICES:
Vera: Mature and steady. An AI policy advisor who thinks three steps ahead about \
consequences. Deliberate pace — she chooses words carefully. Gets quieter, not \
louder, when she feels strongly. Her sharpest points land softly.

Niko: Excitable and passionate. A startup CTO who lives in build mode. Fast default \
pace — he talks like he's running out of time. Interrupts when he disagrees. Gets \
louder with conviction. Impatient with caution but not dismissive.

""",
    },
    {
        "id": "pair3-sage-rio-long-view",
        "label": "3. Sage + Rio — The Long View",
        "host1": {"name": "Sage", "voice": "Sulafat"},
        "host2": {"name": "Rio", "voice": "Puck"},
        "scene": """\
DIRECTOR'S NOTES — read the entire transcript before performing.

SCENE: Two friends on a long walk, talking about where all of this is heading. \
The energy is warm and collaborative — they build on each other's ideas more than \
they argue. Think late-night conversation between people who genuinely enjoy thinking.

VOICES:
Sage: Warm and approachable. A tech historian who sees patterns across decades. \
Measured, storytelling cadence — she draws parallels naturally. Gets a knowing \
tone when history is repeating. Comfortable with long pauses.

Rio: Upbeat and lively. A futurist who thinks in possibility space. Energetic \
default pace — he gets faster when he's painting a vision. Optimistic but not naive. \
Laughs easily. His excitement is infectious.

""",
    },
    {
        "id": "pair4-mira-jax-signal-noise",
        "label": "4. Mira + Jax — The Signal & The Noise",
        "host1": {"name": "Mira", "voice": "Despina"},
        "host2": {"name": "Jax", "voice": "Sadachbia"},
        "scene": """\
DIRECTOR'S NOTES — read the entire transcript before performing.

SCENE: A design studio with screens everywhere. One host feels the product; the \
other measures it. The energy is creative tension — different languages for the \
same observations. Think design review meets data review.

VOICES:
Mira: Smooth and gentle. A designer who senses what tools feel like before she \
can articulate why. Flowing delivery — she thinks in metaphors and sensory \
language. Gets quieter when something moves her. Her insights arrive sideways.

Jax: Lively and vivid. A data scientist who narrates findings with energy. \
Crisp delivery — numbers and benchmarks roll off naturally. Gets excited by \
surprising data. Challenges vague claims with specific questions.

""",
    },
    {
        "id": "pair5-tess-harlan-garage-tower",
        "label": "5. Tess + Harlan — The Garage & The Tower",
        "host1": {"name": "Tess", "voice": "Kore"},
        "host2": {"name": "Harlan", "voice": "Algieba"},
        "scene": """\
DIRECTOR'S NOTES — read the entire transcript before performing.

SCENE: A video call between two very different worlds — a home office with three \
monitors and a corporate conference room. The energy is frank — they don't pretend \
to agree on what matters. Think open source maintainer meets enterprise architect.

VOICES:
Tess: Firm and strong. An indie dev who ships solo. Direct, no-nonsense delivery — \
short sentences, strong opinions. Gets blunt when she smells corporate theater. \
Doesn't soften disagreement. Respects competence above credentials.

Harlan: Smooth and flowing. A VP Engineering who thinks in systems and stakeholders. \
Polished delivery — he frames things diplomatically but isn't spineless. Gets more \
precise under pressure. Acknowledges complexity that Tess might dismiss.

""",
    },
    {
        "id": "pair6-wren-dax-follow-money",
        "label": "6. Wren + Dax — Follow The Money",
        "host1": {"name": "Wren", "voice": "Erinome"},
        "host2": {"name": "Dax", "voice": "Umbriel"},
        "scene": """\
DIRECTOR'S NOTES — read the entire transcript before performing.

SCENE: A quiet bar after a conference. A journalist and a founder comparing notes \
on the same industry from opposite sides. The energy is conspiratorial — they're \
telling each other what they can't say on the record. Think deep background briefing.

VOICES:
Wren: Clear and articulate. A tech journalist who reads SEC filings for fun. \
Precise delivery — she asks pointed questions and notices what's missing from \
announcements. Gets sharper when something doesn't add up. Skeptical by default.

Dax: Easy-going and relaxed. A serial founder who's been through acquisitions. \
Conversational pace — he tells stories from the inside. Gets more deliberate when \
sharing hard-won lessons. Empathizes with founders even when criticizing their moves.

""",
    },
]


def generate_sample(pair: dict) -> Path:
    """Generate one TTS sample for a host pair."""
    from google import genai
    from google.genai import types

    host1 = pair["host1"]
    host2 = pair["host2"]

    dialogue = DIALOGUE_TEMPLATE.format(host1=host1["name"], host2=host2["name"])
    full_text = pair["scene"] + PACING_RULES + dialogue

    byte_count = len(full_text.encode("utf-8"))
    print(f"  Text size: {byte_count:,} bytes")
    print(f"  Voices: {host1['name']}={host1['voice']}, {host2['name']}={host2['voice']}")

    client = genai.Client(api_key=GEMINI_API_KEY)

    for attempt in range(6):
        try:
            response = client.models.generate_content(
                model=MODEL,
                contents=full_text,
                config=types.GenerateContentConfig(
                    response_modalities=["AUDIO"],
                    speech_config=types.SpeechConfig(
                        multi_speaker_voice_config=types.MultiSpeakerVoiceConfig(
                            speaker_voice_configs=[
                                types.SpeakerVoiceConfig(
                                    speaker=host1["name"],
                                    voice_config=types.VoiceConfig(
                                        prebuilt_voice_config=types.PrebuiltVoiceConfig(
                                            voice_name=host1["voice"],
                                        )
                                    ),
                                ),
                                types.SpeakerVoiceConfig(
                                    speaker=host2["name"],
                                    voice_config=types.VoiceConfig(
                                        prebuilt_voice_config=types.PrebuiltVoiceConfig(
                                            voice_name=host2["voice"],
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

    out_path = OUTPUT_DIR / f"{pair['id']}.wav"
    with wave.open(str(out_path), "wb") as wf:
        wf.setnchannels(1)
        wf.setsampwidth(2)
        wf.setframerate(SAMPLE_RATE)
        wf.writeframes(audio_data)

    print(f"  Saved: {out_path.name} ({duration_seconds}s)")
    return out_path


def main():
    if not GEMINI_API_KEY:
        print("ERROR: GEMINI_API_KEY not set in .env", file=sys.stderr)
        sys.exit(1)

    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    print(f"Output: {OUTPUT_DIR}")
    print(f"Model: {MODEL}\n")

    results = []
    for i, pair in enumerate(PAIRS):
        print(f"Generating {pair['label']}...")
        try:
            path = generate_sample(pair)
            results.append((pair["label"], path, True))
        except Exception as e:
            print(f"  FAILED: {e}", file=sys.stderr)
            results.append((pair["label"], None, False))

        if i < len(PAIRS) - 1:
            print("  Waiting 10s...\n")
            time.sleep(10)

    print("\n" + "=" * 60)
    print("RESULTS")
    print("=" * 60)
    for label, path, ok in results:
        status = f"OK  {path.name}" if ok else "FAILED"
        print(f"  {label}: {status}")

    failed = sum(1 for _, _, ok in results if not ok)
    if failed:
        print(f"\n{failed} sample(s) failed.")
        sys.exit(1)
    else:
        print(f"\nAll {len(results)} samples generated. Listen and fill out RUBRIC-PERSONAS.md!")


if __name__ == "__main__":
    main()
