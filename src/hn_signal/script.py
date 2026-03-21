import json
from pathlib import Path

import anthropic

from hn_signal.config import ANTHROPIC_API_KEY, PROJECT_ROOT, SCRIPT_MODEL, SUMMARY_MODEL, log

STATE_PATH = PROJECT_ROOT / "state.json"

SYSTEM_PROMPT = """\
You are writing a script for a daily AI news podcast called "HN Signal". The show has two hosts:
- Alex: technical, precise, asks clarifying questions
- Sam: focused on implications and real-world impact, more conversational

Write a natural dialogue between Alex and Sam covering today's top AI stories from Hacker News.
Guidelines:
- Total script should take 6-8 minutes when read aloud (roughly 900-1100 words)
- Open with a brief 2-sentence cold open (no music cue needed in the script)
- Cover 4-6 of the most interesting stories; skip or briefly mention the rest
- Group related stories together naturally rather than going through them one by one
- Include at least one moment where Alex and Sam genuinely disagree or one pushes back
- Close with a single "story to watch" for tomorrow
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
        max_tokens=4096,
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
