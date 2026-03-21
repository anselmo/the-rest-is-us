# AGENTS.md

This file contains instructions for agentic coding agents working in this repository.

## Project Overview

HN Signal is an automated daily AI podcast pipeline. It scrapes top AI stories from Hacker News, generates a 3-person panel discussion script via Claude, renders audio via ElevenLabs TTS, and publishes as a GitHub Release with RSS feed.

**Python version:** >=3.11  
**Package manager:** uv  
**Key dependencies:** anthropic, elevenlabs, httpx, beautifulsoup4, pydub, tavily-python

---

## Build, Lint, and Test Commands

### Setup
```bash
uv sync                    # Install dependencies
brew install ffmpeg        # Required by pydub for audio export
```

### Running the Pipeline
```bash
uv run hn-signal                           # Run full pipeline (all 5 stages)
uv run python -m hn_signal.collect         # Test story collection only (free, no API costs)
uv run python -m hn_signal.collect --help  # Module-level execution
```

### Running Individual Stages (for testing)
```bash
uv run python -m hn_signal.collect    # Stage 1: Collect HN stories
uv run python -m hn_signal.enrich     # Stage 2: Enrich with Tavily
uv run python -m hn_signal.script     # Stage 3: Generate script
uv run python -m hn_signal.audio      # Stage 4: Generate audio
uv run python -m hn_signal.publish    # Stage 5: Publish to GitHub
```

### Linting and Formatting
This project does not currently have explicit linting/formatting tools configured. Run manually:
```bash
uv run ruff check src/          # Check with ruff (if installed)
uv run ruff format src/         # Format with ruff (if installed)
uv run mypy src/                # Type check with mypy (if installed)
```

---

## Code Style Guidelines

### General Principles
Follow SOLID principles. Keep functions small and focused (Single Responsibility). Prefer explicit over implicit (Zen of Python). Fail fast on invalid inputs.

### Imports

**Standard library first, third-party second, local third:**
```python
import logging
import os
import sys
from pathlib import Path

import httpx
from bs4 import BeautifulSoup

from hn_signal.config import PROJECT_ROOT, log
```

**Sort imports alphabetically within each group.**

**Avoid circular imports** — use late imports inside functions when needed (see `enrich.py` and `publish.py`).

### Type Annotations

Use type hints for all function signatures:
```python
def _fetch_article_body(url: str) -> str:
def collect_stories() -> list[dict]:
def generate_audio(script: str, output_path: Path) -> tuple[Path, int]:
```

Use `dict` for simple dicts, not `Dict[...]`. Prefer built-in types.

### Naming Conventions

| Element | Convention | Example |
|---------|-----------|---------|
| Modules | snake_case | `collect.py`, `audio.py` |
| Functions | snake_case | `collect_stories()`, `_fetch_article_body()` |
| Variables | snake_case | `story_ids`, `mp3_path` |
| Constants | UPPER_SNAKE_CASE | `MAX_STORIES`, `HN_TOP_STORIES` |
| Private functions | leading underscore | `_matches_keywords()` |
| Classes | PascalCase | (rarely used in this project) |
| Type variables | PascalCase | (rarely used) |

### File Structure

Each module should have:
1. Standard library imports
2. Third-party imports
3. Local imports
4. Module-level constants
5. Public functions
6. Private helper functions (prefixed with `_`)
7. `if __name__ == "__main__":` block at the end (if applicable)

### Docstrings

Use docstrings for public functions and complex logic:
```python
def _parse_turns(script: str) -> list[tuple[str, str]]:
    """Parse script into [(speaker, text), ...] turns."""
```

Keep docstrings concise. For simple helpers, a single line is sufficient.

### Error Handling

**Log and continue** for recoverable errors:
```python
except Exception as e:
    log.warning("Failed to fetch item %s: %s", story_id, e)
    continue
```

**Log and exit** for fatal errors:
```python
except Exception as e:
    log.error("Publish failed: %s", e)
    sys.exit(1)
```

**Use specific exception types** when possible (e.g., `httpx.HTTPStatusError`, `subprocess.CalledProcessError`).

### Logging

Use the module-level logger from `config.py`:
```python
from hn_signal.config import log

log.info("Collected %d AI stories", len(stories))
log.warning("Failed to fetch article %s: %s", url, e)
log.error("Only %d AI stories found, need at least 2", len(stories))
```

Use `%s` format strings (not f-strings) for log messages to avoid string interpolation when log level is above DEBUG.

### Path Handling

Use `pathlib.Path` for all file paths:
```python
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
FEED_PATH = PROJECT_ROOT / "feed.xml"
output_path.parent.mkdir(parents=True, exist_ok=True)
```

### Environment Variables

Use `_require()` helper for required env vars (raises `SystemExit` if missing):
```python
from hn_signal.config import _require

ANTHROPIC_API_KEY = _require("ANTHROPIC_API_KEY")
```

Use `os.getenv()` with defaults for optional vars:
```python
TAVILY_API_KEY = os.getenv("TAVILY_API_KEY", "").strip() or None
PODCAST_TITLE = os.getenv("PODCAST_TITLE", "HN Signal")
```

### API Clients

Initialize clients inside functions (not at module level) to avoid import-time side effects:
```python
def generate_script(stories: list[dict], history: dict) -> str:
    client = anthropic.Anthropic(api_key=ANTHROPIC_API_KEY)
    # ...
```

### Script Formatting

When generating podcast scripts, use this format:
```
ALEX: Dialogue here.
NICK: Response here.
MIA: Counterpoint here.
```

Each speaker prefix should be on its own line, followed by a colon and space.

### RSS/XML Generation

Use `xml.etree.ElementTree` with proper namespace handling:
```python
import xml.etree.ElementTree as ET

ITUNES_NS = "http://www.itunes.com/dtds/podcast-1.0.dtd"
ET.register_namespace("itunes", ITUNES_NS)
```

---

## Environment Setup

Required environment variables (see `.env.example`):
- `ANTHROPIC_API_KEY` — Claude API for script generation
- `ELEVENLABS_API_KEY` — TTS audio generation
- `ELEVENLABS_VOICE_ID_ALEX`, `ELEVENLABS_VOICE_ID_NICK`, `ELEVENLABS_VOICE_ID_MIA` — Voice IDs
- `GITHUB_TOKEN` — Creating releases and committing feed
- `GITHUB_REPO` — Repository for releases (format: `owner/repo`)
- `PODCAST_BASE_URL` — Base URL for podcast files

Optional:
- `TAVILY_API_KEY` — Web search enrichment (skipped without it)

---

## Output Files

- `episodes/YYYY-MM-DD.mp3` — Generated audio (versioned with `-v1`, `-v2` for multiple runs per day)
- `state.json` — Last 7 episode summaries (for continuity)
- `feed.xml` — Podcast RSS feed (max 30 episodes)

---

## Hosts

- **Alex Green** — Moderator: frames stories, directs conversation
- **Nick Salt** — Bold Analyst: conviction-driven takes and predictions
- **Mia Thorn** — Skeptical Pragmatist: reality-checks claims, tests business models
