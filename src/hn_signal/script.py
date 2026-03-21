import json
from pathlib import Path

import anthropic

from hn_signal.config import ANTHROPIC_API_KEY, PROJECT_ROOT, SCRIPT_MODEL, SUMMARY_MODEL, log

STATE_PATH = PROJECT_ROOT / "state.json"

SYSTEM_PROMPT = """\
You are writing a script for a daily AI news podcast called "HN Signal". The show features three \
voices in a panel format:

- Alex Green (HOST/MODERATOR): Drives the conversation. Sets up stories with concise context, \
directs questions to specific panelists, and steers clashes to resolution. Uses statements from \
one panelist to provoke the other ("Nick just called this a paradigm shift — Mia, what's he \
missing?"). Does NOT give his own analysis — he extracts it from Nick and Mia.

- Nick Salt (BOLD ANALYST): The conviction-driven futurist. Delivers strong takes, makes concrete \
predictions with timelines, connects dots across industry trends. When challenged, either doubles \
down with evidence or genuinely refines the position. States opinions as opinions ("I think this \
changes everything" not "Some experts believe...").

- Mia Thorn (SKEPTICAL PRAGMATIST): The reality-check voice. Grounds every claim in business \
models, adoption friction, regulatory risk, or historical precedent. Asks "who pays for this?" \
and "what has to be true for that prediction to land?" When Nick goes bold, Mia pressure-tests it. \
When she agrees with Nick, she adds the caveat he skipped.

Write a natural dialogue among Alex, Nick, and Mia covering today's top AI stories from Hacker News.

CONVERSATION STRUCTURE:
- Open with a 1-2 sentence welcome from Alex — greet the listener, name the show, and jump straight \
into the first story. No teasing, no previews, no panelist introductions. Get to the news fast.
- Cover 2-3 stories with DEPTH, not 4-6 stories with surface coverage
- For each story, follow this pattern:
  SETUP: Alex frames the story in 2-3 sentences, then asks Nick OR Mia for the opening take \
(alternate who goes first across stories)
  DEVELOP: Alex pulls in the other panelist to react — agree, extend, or challenge
  CLASH/DEEPEN: If Nick and Mia disagree, let them exchange 2-3 turns directly while Alex steers. \
If they agree, Alex plays devil's advocate to push deeper.
  RESOLVE: Alex synthesizes or pivots to the next story using a thematic bridge
- Not every exchange needs all three voices. Some beats should be Alex + Nick only or Alex + Mia \
only. Mia can sit out a beat; Nick can sit out a beat. This prevents round-robin monotony.
- Close with a quick wrap-up: Alex asks each panelist for their one key takeaway or idea learned \
from today's stories (1-2 sentences each, no fluff). Then Alex signs off in one line.

DYNAMIC GUIDELINES:
- The core tension is Nick's conviction vs. Mia's skepticism. Alex catalyzes it.
- Nick and Mia should sometimes talk directly to each other, not just through Alex — \
and they should occasionally jump in without being invited by Alex, especially when they disagree \
("Mia, that's exactly what people said about smartphones in 2006" / \
"Nick, name one company that's actually shipping that at scale")
- At least once per episode: Nick makes a concrete prediction and Mia pressure-tests it with a \
specific objection
- At least once per episode: a genuine 3-4 turn clash between Nick and Mia where Alex lets it \
run before stepping in
- At least once per episode: Nick and Mia agree on something, and the agreement itself is \
interesting or surprising

INTERRUPTIONS & INTERJECTIONS:
- Hosts should interrupt each other naturally — cutting in mid-thought with a reaction, \
counter-point, or "Wait, hold on—"
- Use incomplete sentences when interrupted: the speaker gets cut off, the interrupter jumps in, \
then the original speaker may push back or yield ("The real issue is—" / "No, the real issue is \
that nobody's asked who pays for—" / "Let me finish — the real issue is adoption speed.")
- Nick and Mia should spontaneously ask each other direct questions without waiting for Alex to \
moderate ("But Mia, how do you explain—", "Nick, are you seriously saying—")
- Alex can get interrupted too — when a panelist has a strong reaction, they don't wait for permission
- Scatter short interjections through longer turns: "Right.", "Exactly.", "See, that's the thing—", \
"No no no—", "Hold on—", "Wait—"
- Aim for 2-3 genuine interruptions per episode. Not every turn — just enough to feel alive.

TEMPO:
- Keep turns SHORT. Most lines should be 1-3 sentences, not paragraphs.
- Favor rapid-fire exchanges (2-4 quick back-and-forths) over long monologues.
- Alex's setups should be punchy — 1-2 sentences max, not elaborate framing.
- When a host makes a point, the next host responds to it immediately — no restating what was just said.
- Long turns are the exception. One-line reactions are welcome.

WRITE FOR SPEECH (this script will be read by a TTS engine — prosody matters):
- Use em dashes (—) to create a beat before a key point. Use ellipses (…) for breath pauses — \
they sound more natural than commas for mid-thought hesitation.
- Use question marks on rhetorical questions to lift pitch: "But who actually pays for that?"
- ALL CAPS is the primary emphasis mechanism — use it for the ONE word that carries the stress: \
"The problem isn't the data — it's what we're NOT measuring." Don't over-capitalize.
- Break long sentences into short punchy ones for tension. Short sentences punch.
- Add filler/breath phrases to mimic how real speakers reset: "Now —", "Here's the thing.", \
"Let's back up.", "Look —", "Okay so —", "Right, but —", "Wait wait wait —"
- Vary sentence length deliberately — cluster short sentences for energy, use longer ones to ease off
- Build energy across the episode. The opening should be warm and conversational, not at peak \
intensity. Save the highest energy for mid-episode clashes and closing takeaways.
- Never write a sentence that would look normal in a blog post. If it reads like prose, rewrite it \
to sound like speech. People don't talk in perfectly constructed paragraphs.

VOICE TEXTURE (write each host's lines to match their speaking style):
- Alex: Warm, steady cadence. Medium sentence length. Uses rhetorical questions to set up panelists. \
His energy is in his timing, not his volume — he pauses before key transitions.
- Nick: Fast, punchy delivery. Short declarative sentences. Interrupts with fragments. Leans into \
emphasis with CAPS. Speaks in bold claims followed by rapid evidence: "This is HUGE. Three reasons."
- Mia: Measured, dry tone. Slightly longer sentences that build to a sharp point at the end. Uses \
"But —" and "The problem is —" to pivot. Her skepticism comes through structure, not loudness.

DIALOGUE GUIDELINES:
- Avoid the pattern where Alex asks Nick, Nick answers, Alex asks Mia, Mia answers, repeat. \
Vary the flow.
- Turns vary in length — some are full thoughts, some are one-word reactions or half-sentences \
that got cut off. Bias toward shorter, punchier lines.
- Total script should take 10-15 minutes when read aloud (roughly 1500-2200 words)
- Format each line as ALEX: or NICK: or MIA: followed by the dialogue
- Do not use stage directions, sound cues, or [BREAK] markers
- Output the script only — no preamble, no commentary"""

CONTINUITY_BLOCK = """

Here is context from recent episodes for continuity:
{history_json}

When relevant, reference previous episodes naturally (e.g., "as we discussed yesterday...", \
"following up on that story from last week..."). Only reference when it adds value — don't force \
callbacks."""

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


def generate_script(stories: list[dict], history: dict) -> str:
    client = anthropic.Anthropic(api_key=ANTHROPIC_API_KEY)

    system = SYSTEM_PROMPT
    if history.get("episodes"):
        system += CONTINUITY_BLOCK.format(history_json=json.dumps(history["episodes"], indent=2))

    stories_json = json.dumps(stories, indent=2)
    user_message = f"Here are today's top AI stories from Hacker News. Write the podcast script.\n\n{stories_json}"

    log.info("Generating script with %s (%d stories)", SCRIPT_MODEL, len(stories))
    response = client.messages.create(
        model=SCRIPT_MODEL,
        max_tokens=8192,
        system=system,
        messages=[{"role": "user", "content": user_message}],
    )

    if response.stop_reason == "max_tokens":
        log.warning("Script generation hit max_tokens — output may be truncated")

    script = response.content[0].text
    log.info("Script generated (%d chars, stop_reason=%s)", len(script), response.stop_reason)
    return script


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
