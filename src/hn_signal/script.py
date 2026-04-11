import json

import anthropic

from hn_signal.config import (
    ANTHROPIC_API_KEY,
    BEAT_SHEET_MODEL,
    PUBLISH_HOUR,
    SCRIPT_MODEL,
    SUMMARY_MODEL,
    log,
    time_of_day_label,
)
from hn_signal.models import EpisodeSummary, PipelineState, Story, StoryTake
from hn_signal.prompts import (
    BEAT_SHEET_PROMPT,
    CONTINUITY_BLOCK,
    REFINEMENT_PROMPT,
    SUMMARY_PROMPT,
    SYSTEM_PROMPT,
)
from hn_signal.state import (
    _format_date_spoken,
    _parse_json_response,
    load_state,
    save_state,
)


def generate_beat_sheet(stories: list[Story], history: PipelineState, date_spoken: str, time_of_day: str = "") -> dict:
    """Pass 0: generate a conversation blueprint from stories."""
    client = anthropic.Anthropic(api_key=ANTHROPIC_API_KEY)

    # Condensed story summaries — full bodies are wasteful for structural planning
    story_summaries = []
    for i, story in enumerate(stories):
        summary = {
            "index": i,
            "title": story.title,
            "url": story.url,
            "source_count": story.source_count,
            "sources": [s.name for s in story.sources],
            "body_preview": (story.body or "")[:500],
            "enrichment_preview": (story.enrichment[0] or "")[:300]
            if story.enrichment
            else "",
        }
        story_summaries.append(summary)

    user_message = (
        f"Design a beat sheet for today's episode, airing {date_spoken}."
    )
    if time_of_day:
        user_message += f" This is a {time_of_day} episode."
    user_message += (
        "\n\nHere are the ranked stories (most important first):\n\n"
        + json.dumps(story_summaries, indent=2)
    )

    if history.episodes:
        user_message += (
            "\n\nRecent episode context (for continuity, reference only if relevant):\n"
            + json.dumps([ep.to_dict() for ep in history.episodes[:3]], indent=2)
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


def generate_script(stories: list[Story], history: PipelineState) -> str:
    from datetime import date

    today = date.today().isoformat()
    date_spoken = _format_date_spoken(today)
    time_of_day = time_of_day_label(PUBLISH_HOUR)

    # Pass 0: generate conversation blueprint
    beat_sheet = generate_beat_sheet(stories, history, date_spoken, time_of_day)

    # Pass 1: generate dialogue from beat sheet
    client = anthropic.Anthropic(api_key=ANTHROPIC_API_KEY)

    system = SYSTEM_PROMPT
    if history.episodes:
        system += CONTINUITY_BLOCK.format(
            history_json=json.dumps([ep.to_dict() for ep in history.episodes], indent=2)
        )

    beat_sheet_json = json.dumps(beat_sheet, indent=2)
    stories_json = json.dumps([s.to_dict() for s in stories], indent=2)
    user_message = (
        f"EPISODE INFO: {date_spoken}."
        f" Time of day: {time_of_day}.\n\n"
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


def extract_episode_summary(script: str, stories: list[Story]) -> EpisodeSummary:
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
    parsed = _parse_json_response(text)

    from datetime import date

    today = date.today().isoformat()

    if parsed is None:
        log.warning("Failed to parse summary JSON, using fallback")
        return EpisodeSummary(
            date=today,
            stories=[StoryTake(title=s.title) for s in stories[:3]],
        )

    parsed["date"] = today
    return EpisodeSummary.from_dict(parsed)


# Re-export state functions for backward compatibility
from hn_signal.state import load_state, save_state  # noqa: F401
