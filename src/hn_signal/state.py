import json
import re

from hn_signal.config import PROJECT_ROOT, log
from hn_signal.models import EpisodeSummary, PipelineState

STATE_PATH = PROJECT_ROOT / "state.json"


def load_state() -> PipelineState:
    if STATE_PATH.exists():
        return PipelineState.from_dict(json.loads(STATE_PATH.read_text()))
    return PipelineState()


def next_episode_number() -> int:
    state = load_state()
    return state.episode_count + 1


def save_state(summary: EpisodeSummary) -> None:
    state = load_state()
    state.episode_count += 1
    summary.episode_number = state.episode_count
    state.episodes.insert(0, summary)
    state.episodes = state.episodes[:30]
    STATE_PATH.write_text(json.dumps(state.to_dict(), indent=2))
    log.info("State saved (episode #%d, %d in history)", state.episode_count, len(state.episodes))


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
