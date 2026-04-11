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
from hn_signal.prompts import (
    BEAT_SHEET_PROMPT,
    CONTINUITY_BLOCK,
    REFINEMENT_PROMPT,
    SUMMARY_PROMPT,
    SYSTEM_PROMPT,
)

STATE_PATH = PROJECT_ROOT / "state.json"


def load_state() -> dict:
    if STATE_PATH.exists():
        return json.loads(STATE_PATH.read_text())
    return {"episode_count": 0, "episodes": []}


def next_episode_number() -> int:
    state = load_state()
    return state.get("episode_count", 0) + 1


def save_state(summary: dict) -> None:
    state = load_state()
    state["episode_count"] = state.get("episode_count", 0) + 1
    summary["episode_number"] = state["episode_count"]
    state["episodes"].insert(0, summary)
    state["episodes"] = state["episodes"][:30]
    STATE_PATH.write_text(json.dumps(state, indent=2))
    log.info("State saved (episode #%d, %d in history)", state["episode_count"], len(state["episodes"]))


_ORDINALS = {
    1: "first", 2: "second", 3: "third", 4: "fourth", 5: "fifth",
    6: "sixth", 7: "seventh", 8: "eighth", 9: "ninth", 10: "tenth",
    11: "eleventh", 12: "twelfth", 13: "thirteenth", 14: "fourteenth",
    15: "fifteenth", 16: "sixteenth", 17: "seventeenth", 18: "eighteenth",
    19: "nineteenth", 20: "twentieth", 21: "twenty-first", 22: "twenty-second",
    23: "twenty-third", 24: "twenty-fourth", 25: "twenty-fifth",
    26: "twenty-sixth", 27: "twenty-seventh", 28: "twenty-eighth",
    29: "twenty-ninth", 30: "thirtieth", 31: "thirty-first",
}


def _format_date_spoken(iso_date: str) -> str:
    """Format '2026-04-11' as 'April eleventh' for natural TTS."""
    from datetime import date as _date

    d = _date.fromisoformat(iso_date)
    month_name = d.strftime("%B")
    ordinal = _ORDINALS.get(d.day, f"{d.day}th")
    return f"{month_name} {ordinal}"


def _number_to_words(n: int) -> str:
    """Convert an integer to spoken English for TTS (e.g. 47 → 'forty-seven')."""
    if n <= 0:
        return str(n)
    ones = ["", "one", "two", "three", "four", "five", "six", "seven", "eight", "nine",
            "ten", "eleven", "twelve", "thirteen", "fourteen", "fifteen", "sixteen",
            "seventeen", "eighteen", "nineteen"]
    tens = ["", "", "twenty", "thirty", "forty", "fifty", "sixty", "seventy", "eighty", "ninety"]

    if n < 20:
        return ones[n]
    if n < 100:
        return tens[n // 10] + ("-" + ones[n % 10] if n % 10 else "")
    if n < 1000:
        remainder = n % 100
        rest = _number_to_words(remainder) if remainder else ""
        return ones[n // 100] + " hundred" + (" " + rest if rest else "")
    return str(n)


def _parse_json_response(text: str) -> dict | None:
    """Best-effort JSON extraction from an LLM response."""
    # 1. Try raw text directly
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        pass

    # 2. Strip markdown code fences
    cleaned = re.sub(r"```(?:json)?\s*", "", text).strip().rstrip("`")
    try:
        return json.loads(cleaned)
    except json.JSONDecodeError:
        pass

    # 3. Find the first complete JSON object using raw_decode
    brace = cleaned.find("{")
    if brace != -1:
        try:
            obj, _ = json.JSONDecoder().raw_decode(cleaned, brace)
            if isinstance(obj, dict):
                return obj
        except json.JSONDecodeError:
            pass

    return None


def generate_beat_sheet(stories: list[dict], history: dict, episode_number: int, date_spoken: str) -> dict:
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

    ep_word = _number_to_words(episode_number)
    user_message = (
        f"Design a beat sheet for today's episode. "
        f"This is Episode {episode_number} (say \"episode {ep_word}\"), "
        f"airing {date_spoken}.\n\n"
        f"Here are the ranked stories (most important first):\n\n"
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
        max_tokens=8192,
        system=BEAT_SHEET_PROMPT,
        messages=[{"role": "user", "content": user_message}],
    )

    if response.stop_reason == "max_tokens":
        log.warning("Beat sheet hit max_tokens — JSON likely truncated, retrying")
        # Retry with instruction to be more concise
        retry_msg = user_message + "\n\nIMPORTANT: Keep the JSON compact — use short strings, fewer arc beats (3-5 per segment). Previous attempt was truncated."
        response = client.messages.create(
            model=BEAT_SHEET_MODEL,
            max_tokens=8192,
            system=BEAT_SHEET_PROMPT,
            messages=[{"role": "user", "content": retry_msg}],
        )

    text = response.content[0].text
    beat_sheet = _parse_json_response(text)
    if beat_sheet is None:
        log.error("Failed to parse beat sheet JSON:\n%s", text[:500])
        raise ValueError("Beat sheet generation returned unparseable JSON")

    log.info(
        "Beat sheet generated: %d segments, %d total discovery beats",
        len(beat_sheet.get("segments", [])),
        sum(len(s.get("discovery_beats", [])) for s in beat_sheet.get("segments", [])),
    )
    return beat_sheet


def generate_script(stories: list[dict], history: dict) -> str:
    from datetime import date

    episode_number = next_episode_number()
    today = date.today().isoformat()
    date_spoken = _format_date_spoken(today)
    ep_word = _number_to_words(episode_number)

    # Pass 0: generate conversation blueprint
    beat_sheet = generate_beat_sheet(stories, history, episode_number, date_spoken)

    # Pass 1: generate dialogue from beat sheet
    client = anthropic.Anthropic(api_key=ANTHROPIC_API_KEY)

    system = SYSTEM_PROMPT
    if history.get("episodes"):
        system += CONTINUITY_BLOCK.format(history_json=json.dumps(history["episodes"], indent=2))

    beat_sheet_json = json.dumps(beat_sheet, indent=2)
    stories_json = json.dumps(stories, indent=2)
    user_message = (
        f"EPISODE INFO: Episode {episode_number} (say \"episode {ep_word}\"), {date_spoken}.\n\n"
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
        max_tokens=2048,
        system=SUMMARY_PROMPT,
        messages=[{"role": "user", "content": script}],
    )

    if response.stop_reason == "max_tokens":
        log.warning("Summary extraction hit max_tokens — JSON may be malformed")

    text = response.content[0].text
    summary = _parse_json_response(text)
    if summary is None:
        log.warning("Failed to parse summary JSON, using fallback")
        summary = {
            "stories": [{"title": s["title"], "kit_take": "", "dean_take": "", "agreed": True} for s in stories[:3]],
            "predictions": [],
            "key_themes": [],
            "story_to_watch": "",
        }

    from datetime import date

    summary["date"] = date.today().isoformat()
    return summary
