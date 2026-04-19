"""Parse KIT:/DEAN: scripts into (speaker, text) turns.

Duplicates the logic in src/hn_signal/audio.py:_parse_turns() to avoid importing
the main package (which requires API-key env vars at import time).
"""
from __future__ import annotations

import re


def parse_turns(script: str, host1: str, host2: str) -> list[tuple[str, str]]:
    """Returns list of (speaker_name, dialogue_text) tuples."""
    h1 = host1.upper()
    h2 = host2.upper()
    pattern = re.compile(rf"^({h1}|{h2}):\s*", re.MULTILINE)
    matches = list(pattern.finditer(script))
    if not matches:
        return []
    turns = []
    for i, match in enumerate(matches):
        speaker = match.group(1)
        start = match.end()
        end = matches[i + 1].start() if i + 1 < len(matches) else len(script)
        text = script[start:end].strip()
        # Strip [BREAK] markers and TTS tags
        text = re.sub(r"^\[BREAK\]$", "", text, flags=re.MULTILINE).strip()
        text = re.sub(r"\[[a-z ]+\]", "", text)
        if text:
            turns.append((speaker, text))
    return turns
