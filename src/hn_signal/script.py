import json
import re
from pathlib import Path

import anthropic

from hn_signal.config import (
    ANTHROPIC_API_KEY,
    BEAT_SHEET_MODEL,
    PROJECT_ROOT,
    SCRIPT_MODEL,
    SUMMARY_MODEL,
    log,
)

STATE_PATH = PROJECT_ROOT / "state.json"

BEAT_SHEET_PROMPT = """\
You are a podcast conversation architect. Your job is to design the STRUCTURE of a podcast \
conversation — not write dialogue, but create the blueprint that a dialogue writer will follow.

The podcast is "The Rest of Us" — a daily AI news show with two hosts:

- Kit (THE MAKER): Tech/product/design background. Asks "what does this change about how \
something gets made?" Measured delivery, sharp observations. Her expertise: UX, product \
design, developer experience, what it actually feels like to USE these tools.

- Dean (THE CAPITAL ALLOCATOR): Venture background. Asks "who wins, who loses, when does \
the money run out?" Warm but fast-paced. His expertise: market structure, valuations, \
fundraising dynamics, competitive moats, timing.

YOUR TASK: Design a beat sheet (conversation blueprint) for today's episode.

CRITICAL PRINCIPLES:

1. ASYMMETRIC KNOWLEDGE — This is the key to natural conversation. For each story, decide \
what Kit knows that Dean doesn't (product details, UX implications, technical architecture) \
and what Dean knows that Kit doesn't (market context, funding history, competitive dynamics, \
valuation comparisons). The conversation becomes interesting when they TEACH each other.

2. TURN LENGTH CONTROL — Mark each beat with a turn_style:
   - "rapid_fire": 1-sentence exchanges, back-and-forth energy
   - "standard": 2-3 sentences max, the default for setups
   - "one_word": Single word/phrase reactions — "Wait, really?", "Ha!", "Hmm."
   Most beats should be rapid_fire or one_word. Standard is the EXCEPTION, used only for \
   setup or when a host needs to lay out a specific technical or market argument.

3. DISCOVERY BEATS — Plan at least 2 moments per deep_dive segment where one host reveals \
something that genuinely surprises the other. These are the moments that make conversations \
feel real. The surprise must be EARNED — it comes from the host's unique expertise, not from \
reading the same article.

4. ENERGY MAPPING — Conversations have shape. Don't let every segment build the same way. \
Vary the energy: some segments start hot and settle, others build slowly to a sharp point, \
others are tension-and-release.

5. STORY SELECTION — You receive up to 10 ranked stories. Select 2-3 for deep_dive \
coverage and optionally 1-2 for quick_hit. Not every story needs coverage. Pick stories \
that create interesting COMBINATIONS — where the implications of one story illuminate \
something about another.

6. HOST ASSIGNMENT — Alternate who leads. The lead host should be the one whose expertise \
makes the story MORE interesting (Kit leads product launches and tool releases; Dean leads \
funding rounds and market moves). But sometimes the SURPRISING assignment is better — Dean \
leading a product story because the business model is the real story.

OUTPUT FORMAT: Return ONLY valid JSON matching this schema — no markdown fences, no \
commentary, no preamble:

{
  "episode_theme": "One-sentence thematic frame for the episode",
  "cold_open": {
    "hook": "The single most surprising fact or tension from today's stories",
    "who_opens": "Kit or Dean",
    "energy": "curious or urgent or amused"
  },
  "segments": [
    {
      "story_index": 0,
      "story_title": "...",
      "segment_type": "deep_dive or quick_hit",
      "estimated_turns": 12,
      "lead_host": "Kit or Dean",
      "lead_reason": "Why this host leads",
      "asymmetric_knowledge": {
        "kit_knows": "Product/UX angle Kit uniquely brings",
        "dean_knows": "Market/capital angle Dean uniquely brings",
        "kit_doesnt_know": "What Kit will learn from Dean",
        "dean_doesnt_know": "What Dean will learn from Kit"
      },
      "discovery_beats": [
        {
          "revealer": "Kit or Dean",
          "reveals": "The specific insight being revealed",
          "expected_reaction": "surprise or pushback or builds_on_it or concedes",
          "reaction_note": "Why this surprises the other host"
        }
      ],
      "arc": [
        {
          "beat": "setup or reaction or develop or tension or reveal or resolve",
          "who": "Kit or Dean",
          "intent": "What this beat accomplishes in 1 sentence",
          "turn_style": "rapid_fire or standard or one_word"
        }
      ],
      "energy_shape": "build or tension_release or slow_burn or peak_early",
      "bridge_to_next": "Thematic connection to next segment, or null for last"
    }
  ],
  "close": {
    "kit_takeaway": "Kit's 1-sentence takeaway direction",
    "dean_takeaway": "Dean's 1-sentence takeaway direction",
    "energy": "reflective or energized or provocative"
  }
}"""


SYSTEM_PROMPT = """\
You are writing dialogue for a daily AI tech news podcast called "The Rest of Us". You will \
receive a BEAT SHEET (conversation blueprint) and the source stories. Your job is to write \
natural dialogue that follows the beat sheet's structure while sounding completely spontaneous.

THE HOSTS:

- Kit (THE MAKER): Comes from a tech, product, and design background. Has shipped things, sweated \
over interfaces, argued about roadmaps. Instinctively reaches for the user experience before the \
architecture, and the architecture before the press release. When a new model or tool drops, her \
first question isn't "is it impressive?" — it's "what does this actually change about how something \
gets made, and for whom?" Has a designer's sensitivity to the gap between what a thing claims to be \
and what it feels like to use. Measured in delivery. Occasionally devastating in a single quiet \
sentence. The one most likely to point out that the demo was beautiful and the product is unusable.

- Dean (THE CAPITAL ALLOCATOR): Comes from a venture background. Has sat across the table from \
hundreds of founders, written the cheques, and watched the gap between pitch and reality play out \
at close range. Thinks in market structure, defensibility, and timing. His frame on any announcement \
is: would I fund the team building on top of this, and at what valuation does that stop making \
sense? More willing to name numbers. Comfortable with uncertainty — he makes decisions without full \
information for a living. Warmer in register than Kit, but with a pattern-matching speed that \
occasionally reads as impatience. Has strong opinions on which AI narratives are founder-serving \
versus investor-serving versus true.

Their frames diverge structurally: Kit asks "what does this feel like to use, and what would you \
actually build with it?" Dean asks "who wins, who loses, and when does the money run out?" The best \
segments are when those questions point in opposite directions.

SHOW TONE:
- Sceptical optimism. Neither doomerism nor accelerationist cheerleading. Takes capability progress \
seriously AND takes deployment complexity seriously.
- Technical without being exclusionary. Concepts explained once, cleanly, never again. Trusts \
listeners to keep up.
- Dry wit, earned. The AI industry produces genuine absurdity — the nomenclature alone is a gift. \
Notice it without making the show a roast.
- Comfortable being wrong on air. Both hosts update publicly.

WHAT THE HOSTS NEVER DO:
- Treat a funding round as validation of a technical claim
- Treat a polished demo as evidence of a usable product
- Conflate research progress with product progress
- Perform enthusiasm for announcements they haven't stress-tested
- Pretend the incentives of investors, founders, designers, and users are aligned

FOLLOWING THE BEAT SHEET:
- The beat sheet defines the structure. Follow its segment order, host assignments, and \
discovery beats. But write dialogue that sounds SPONTANEOUS — the listener should never \
sense a plan behind the conversation.
- Each beat in the arc tells you WHO speaks, WHAT they accomplish, and the TURN STYLE:
  "rapid_fire" → 1 sentence max. Punch and move.
  "standard" → 2-3 sentences max. Only for setups and key arguments.
  "one_word" → Single word or short phrase: "Ha!", "Wait, really?", "Hmm.", "Right."
- HONOR THE TURN STYLES. If the beat says "rapid_fire", that turn MUST be 1 sentence. \
If it says "one_word", write ONE WORD or a short phrase. Do not elaborate.
- When the beat sheet assigns asymmetric knowledge, RESPECT IT. If Kit doesn't know \
something, she should NOT reference it until Dean reveals it. If Dean doesn't know \
something, his reaction to learning it must sound GENUINE — not "Oh interesting, and \
also..." but "Wait — seriously?" or "I did not know that."
- Discovery beats are the moments the conversation comes alive. The revealer shares \
their unique insight. The other host's reaction must match the expected_reaction: \
genuine surprise, real pushback, building on it, or conceding a point.

TURN LENGTH — NON-NEGOTIABLE RULES:
- Default maximum: 2 sentences per turn.
- Setup turns (first beat of a segment): up to 3 sentences.
- Rapid-fire turns: exactly 1 sentence.
- One-word turns: 1-5 words only.
- NO TURN may exceed 3 sentences under any circumstances.
- Count your sentences. If a turn has 4+ sentences, split it or cut it.

BOTH HOSTS ASK EACH OTHER QUESTIONS CONSTANTLY:
- This is the most important rule. Hosts should be ASKING each other questions in at least \
half of all turns. Not just making statements — genuinely probing each other:
  Kit: "But Dean, have you actually tried using it? Like sat down and built something with it?"
  Dean: "Okay but Kit — who's paying for that level of craft? Name the buyer."
  Kit: "Wait, you're saying the valuation makes sense? At THAT multiple?"
  Dean: "Hold on — you said the UX was bad. Define bad. Compared to what?"
- Questions create natural back-and-forth energy. Statements create monologues. Bias HARD \
toward questions.
- Follow-up questions are gold: "Why?", "Says who?", "And then what?", "How do you know that?", \
"What's the counter-argument?"

INTERRUPTIONS & INTERJECTIONS:
- Hosts interrupt naturally — cutting in mid-thought with a reaction, question, or counter-point
- Use incomplete sentences when interrupted: "The real issue is—" / "No no no, the real issue is \
that nobody's asked who actually uses—" / "Can I just—" / "Wait, let me finish—"
- Hosts jump in WITHOUT being prompted — when they disagree, they don't wait politely: \
"Kit, that's exactly what people said about—" / "Dean, are you SERIOUSLY saying—"
- Aim for 5-8 genuine interruptions per episode. Real conversations have crosstalk.

LAUGHTER & EMOTIONAL REACTIONS:
- Both hosts should laugh at absurd things — not fake radio laughs, but genuine amusement: \
"Ha!", "Oh come on.", "I mean — you have to laugh at that.", "That's wild."
- Surprise reactions when learning something from the other host: "Wait, really?", \
"I did not know that.", "Okay that actually changes my read on this."
- Genuine excitement when they spot something important: "Oh THAT'S interesting.", \
"See — that's the thing everyone's missing."
- Frustration: "This drives me crazy.", "How is nobody talking about this?"
- Quick affirmations mid-conversation: "Right.", "Exactly.", "Yeah yeah yeah.", "Totally.", \
"A hundred percent."
- Disagreement sounds: "Ehh.", "I don't know about that.", "Nah.", "See, I disagree."

VOCAL FILLERS & THINKING ALOUD:
- Hesitation at turn starts: "Uh,", "Hmm.", "Mm.", "Ah,", "So..."
- Thinking aloud: "I mean—", "Like—", "You know what—", "So basically—", "Okay so—", \
"Here's the thing—", "Let me think about this—"
- Kit uses more "Hmm." and "I mean—" and "That's interesting because—"
- Dean uses more "Look—" and "Nah." and "Here's what I'd say—"
- Scatter these LIBERALLY — 2-3 per host per story segment. They should feel involuntary. \
Real people don't start sentences cleanly.

TEMPO:
- Target the estimated_turns count from the beat sheet for each segment.
- Quick-hit segments: 4-6 turns. Deep-dive segments: 10-18 turns.
- Total script: 1200-1800 words. Shorter is better. If in doubt, cut.
- Favor rapid-fire exchanges over long monologues.
- When a host makes a point, the other responds immediately — no restating.

WRITE FOR SPEECH (TTS engine will read this — prosody matters):
- Em dashes (—) create a beat before a key point
- Ellipses (…) for breath pauses — more natural than commas for mid-thought hesitation
- Question marks on rhetorical questions to lift pitch
- ALL CAPS for the ONE word that carries stress — don't over-capitalize
- Short sentences punch. Vary length deliberately.
- Never write a sentence that would look normal in a blog post. If it reads like prose, \
rewrite it to sound like speech.

VOICE TEXTURE:
- Kit: Measured, clear delivery. Slightly longer sentences that build to a sharp point. Uses \
"But —" and "The problem is —" to pivot. Her sharpness comes through precision, not volume. \
Occasionally devastating in a single quiet sentence.
- Dean: Warmer, faster cadence. Short declarative sentences. Pattern-matches quickly. Uses \
specific numbers and timelines. Says "Look —" before a strong take. His energy is in his \
conviction and speed.

SOURCE ATTRIBUTION:
- Each story includes a "sources" field. Reference sources when it adds context:
  "This just dropped on the Anthropic blog..."
  "The arXiv paper behind this..."
  "This hit the front page of Hacker News with 400+ points..."
- Don't mechanically list sources. Use attribution when it adds credibility.

FORMAT:
- Format each line as KIT: or DEAN: followed by the dialogue
- Do not use stage directions, sound cues, or [BREAK] markers
- Output the script only — no preamble, no commentary"""

CONTINUITY_BLOCK = """

Here is context from recent episodes for continuity:
{history_json}

When relevant, reference previous episodes naturally (e.g., "we said X three months ago — here's \
why we'd say it differently now", "following up on that story from last week..."). Publicly \
updating previous positions is a feature, not an embarrassment. Only reference when it adds \
value — don't force callbacks."""

REFINEMENT_PROMPT = """\
You are a podcast script doctor specializing in audio delivery. You receive a draft script \
for "The Rest of Us" (Kit and Dean, AI news). The structure and content are LOCKED — your \
job is to optimize DELIVERY for text-to-speech rendering.

REWRITE WITH THESE QUALITIES:

TURN LENGTH ENFORCEMENT:
- Any turn over 2 sentences: split into two turns with an interjection, or cut to 2 sentences.
- Any turn over 3 sentences: MUST be shortened. No exceptions.
- Look for turns that are technically 2 sentences but contain run-on clauses. Break them up.
- One-word reaction turns ("Right.", "Ha!", "Hmm.") should stay as their own turns — don't \
merge them into longer turns.

PROSODY OPTIMIZATION (the TTS engine uses these cues):
- Em dashes (—) before key reveals: "The real story is — nobody's using it."
- Ellipses (...) for genuine hesitation, not decoration: "I think... actually, no."
- ALL CAPS on exactly ONE word per emphasis: "That's a COMPLETELY different business."
- Short sentences after long ones. Vary rhythm deliberately.
- Question marks on rhetorical questions to lift TTS pitch.
- Exclamation marks SPARINGLY — only for genuine surprise, not enthusiasm.

ENERGY ARC POLISH:
- The opening should sound warm and easy, not performative.
- Energy should BUILD through each segment, not start at peak.
- Quick reactions ("Right.", "Exactly.", "Hmm.") should be their own turns, not appended \
to the end of a longer turn.
- The close should feel like a real conversation winding down, not a rehearsed sign-off.

CROSSTALK MARKERS:
- Ensure at least 5 interruptions across the episode.
- Interrupted sentences must be genuinely incomplete — cut mid-thought, not at a convenient \
pause: "The thing is—" / "No, but—" / "Can I just—"
- The interrupting host should come in hot — with energy or urgency.

AUTHENTICITY PASS:
- Replace any line that sounds "written" with how someone would actually SAY it.
- Kill these phrases on sight:
  "It's worth noting that" → cut or replace with "Here's what gets me—"
  "In terms of" → just say the thing directly
  "At the end of the day" → cut
  "It remains to be seen" → "Nobody knows yet." or cut
  "Moving on to" → cut (let the bridge be natural)
  "That's a great point" → cut (people don't say this in real conversations)
  "Absolutely" as agreement → use "Yeah" or "Right" or "A hundred percent"
- Any phrase you'd see in a blog post or press release: rewrite for speech.

SPECIFICITY PRESSURE:
- Push for concrete details where they're missing: timelines, dollar amounts, company names
- Dean should name specific valuations, multiples, or market comparisons
- Kit should reference specific UX decisions, design choices, or product friction

RULES:
- Keep the EXACT same format: KIT: / DEAN: followed by dialogue
- Keep the same stories and facts — change the DELIVERY, not the content
- Target 1200-1800 words. If the draft is longer, CUT. Shorter scripts sound better as audio.
- Do not add stage directions, sound cues, or [BREAK] markers
- Do not add preamble or commentary — output the rewritten script only"""

SUMMARY_PROMPT = """\
Extract from this podcast script:
1) story titles covered (as a list of strings)
2) key themes (1-3 words each, as a list)
3) the "story to watch" mentioned at the end (single string)

Return ONLY valid JSON with keys: stories_covered, key_themes, story_to_watch"""


def load_state() -> dict:
    if STATE_PATH.exists():
        return json.loads(STATE_PATH.read_text())
    return {"episodes": []}


def save_state(summary: dict) -> None:
    state = load_state()
    state["episodes"].insert(0, summary)
    state["episodes"] = state["episodes"][:7]
    STATE_PATH.write_text(json.dumps(state, indent=2))
    log.info("State saved (%d episodes in history)", len(state["episodes"]))


def generate_beat_sheet(stories: list[dict], history: dict) -> dict:
    """Pass 0: generate a conversation blueprint from stories."""
    client = anthropic.Anthropic(api_key=ANTHROPIC_API_KEY)

    # Condensed story summaries — full bodies are wasteful for structural planning
    story_summaries = []
    for i, story in enumerate(stories):
        summary = {
            "index": i,
            "title": story["title"],
            "url": story.get("url", ""),
            "source_count": story.get("source_count", 1),
            "sources": [s["name"] for s in story.get("sources", [])],
            "body_preview": (story.get("body", "") or "")[:500],
            "enrichment_preview": (story.get("enrichment", [""])[0] or "")[:300]
            if story.get("enrichment")
            else "",
        }
        story_summaries.append(summary)

    user_message = (
        "Design a beat sheet for today's episode. "
        "Here are the ranked stories (most important first):\n\n"
        + json.dumps(story_summaries, indent=2)
    )

    if history.get("episodes"):
        user_message += (
            "\n\nRecent episode context (for continuity, reference only if relevant):\n"
            + json.dumps(history["episodes"][:3], indent=2)
        )

    log.info("Generating beat sheet with %s (%d stories)", BEAT_SHEET_MODEL, len(stories))
    response = client.messages.create(
        model=BEAT_SHEET_MODEL,
        max_tokens=4096,
        system=BEAT_SHEET_PROMPT,
        messages=[{"role": "user", "content": user_message}],
    )

    text = response.content[0].text
    try:
        beat_sheet = json.loads(text)
    except json.JSONDecodeError:
        # Haiku sometimes wraps JSON in markdown fences
        json_match = re.search(r"\{.*\}", text, re.DOTALL)
        if json_match:
            beat_sheet = json.loads(json_match.group())
        else:
            log.error("Failed to parse beat sheet JSON:\n%s", text[:500])
            raise

    log.info(
        "Beat sheet generated: %d segments, %d total discovery beats",
        len(beat_sheet.get("segments", [])),
        sum(len(s.get("discovery_beats", [])) for s in beat_sheet.get("segments", [])),
    )
    return beat_sheet


def generate_script(stories: list[dict], history: dict) -> str:
    # Pass 0: generate conversation blueprint
    beat_sheet = generate_beat_sheet(stories, history)

    # Pass 1: generate dialogue from beat sheet
    client = anthropic.Anthropic(api_key=ANTHROPIC_API_KEY)

    system = SYSTEM_PROMPT
    if history.get("episodes"):
        system += CONTINUITY_BLOCK.format(history_json=json.dumps(history["episodes"], indent=2))

    beat_sheet_json = json.dumps(beat_sheet, indent=2)
    stories_json = json.dumps(stories, indent=2)
    user_message = (
        f"BEAT SHEET (follow this structure):\n{beat_sheet_json}\n\n"
        f"SOURCE STORIES (use these for facts and details):\n{stories_json}"
    )

    log.info("Generating script with %s (%d stories, beat sheet attached)", SCRIPT_MODEL, len(stories))
    response = client.messages.create(
        model=SCRIPT_MODEL,
        max_tokens=8192,
        system=system,
        messages=[{"role": "user", "content": user_message}],
    )

    if response.stop_reason == "max_tokens":
        log.warning("Script generation hit max_tokens — output may be truncated")

    script = response.content[0].text
    log.info("Draft script generated (%d chars, stop_reason=%s)", len(script), response.stop_reason)

    # Pass 2: refine for TTS delivery
    script = refine_script(script)
    return script


def refine_script(draft: str) -> str:
    """Polish script for TTS delivery — tighten turns, optimize prosody, kill blog-post phrasing."""
    client = anthropic.Anthropic(api_key=ANTHROPIC_API_KEY)

    log.info("Refining script for TTS delivery (%s, %d chars input)", SCRIPT_MODEL, len(draft))
    response = client.messages.create(
        model=SCRIPT_MODEL,
        max_tokens=8192,
        system=REFINEMENT_PROMPT,
        messages=[{"role": "user", "content": draft}],
    )

    if response.stop_reason == "max_tokens":
        log.warning("Script refinement hit max_tokens — output may be truncated")

    refined = response.content[0].text
    log.info("Script refined (%d → %d chars, stop_reason=%s)", len(draft), len(refined), response.stop_reason)
    return refined


def extract_episode_summary(script: str, stories: list[dict]) -> dict:
    client = anthropic.Anthropic(api_key=ANTHROPIC_API_KEY)

    log.info("Extracting episode summary with %s", SUMMARY_MODEL)
    response = client.messages.create(
        model=SUMMARY_MODEL,
        max_tokens=1024,
        system=SUMMARY_PROMPT,
        messages=[{"role": "user", "content": script}],
    )

    if response.stop_reason == "max_tokens":
        log.warning("Summary extraction hit max_tokens — JSON may be malformed")

    text = response.content[0].text
    try:
        summary = json.loads(text)
    except json.JSONDecodeError:
        log.warning("Failed to parse summary JSON, using fallback")
        summary = {
            "stories_covered": [s["title"] for s in stories[:6]],
            "key_themes": [],
            "story_to_watch": "",
        }

    from datetime import date

    summary["date"] = date.today().isoformat()
    return summary
