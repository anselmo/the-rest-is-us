# The Rest of Us

Automated daily AI podcast pipeline. Aggregates top AI stories from multiple sources (Hacker News, arXiv, lab blogs, tech journalism), cross-references and ranks them, generates a 2-host dialogue script via Claude, renders audio via Gemini TTS, and publishes as a GitHub Release with RSS feed.

## Quick Start

```bash
# Install dependencies
uv sync
brew install ffmpeg          # required by pydub for audio export

# Run full pipeline (all 5 stages)
uv run hn-signal

# Or use Make targets (run `make help` for all targets)
make run              # full pipeline
make collect          # stage 1 only
make check-env        # verify .env is set up

# Test story collection only (free, no API costs)
uv run python -m hn_signal.collect

# Test individual sources
uv run python -m hn_signal.sources.hn
uv run python -m hn_signal.sources.arxiv
uv run python -m hn_signal.sources.lab_blogs
uv run python -m hn_signal.sources.venturebeat
uv run python -m hn_signal.sources.arstechnica
```

## Pipeline Stages

| Stage | Module | What it does | API used |
|-------|--------|-------------|----------|
| 1. Collect | `collect.py` | Aggregate stories from all sources, deduplicate, rank by cross-source appearance + score | Multiple (see Sources) |
| 2. Enrich | `enrich.py` | Add web search context per story | Tavily (optional) |
| 3. Script | `script.py` | 3-pass pipeline: beat sheet → dialogue → TTS refinement, then summary extraction | Claude Sonnet (×3) + Haiku |
| 4. Audio | `audio.py` | Parse turns, add intro/outro music, export MP3 | Gemini TTS |
| 5. Publish | `publish.py` | Create GitHub Release, upload MP3, update RSS, commit & push | GitHub API |

## Module Architecture

All modules live in `src/hn_signal/`. The refactored structure:

| Module | Role |
|--------|------|
| `main.py` | Orchestrator — coordinates all 5 stages |
| `config.py` | All env vars, constants, keyword lists, voice settings |
| `models.py` | Typed dataclasses: `Story`, `StorySource`, `EpisodeSummary`, `PipelineState` |
| `prompts.py` | All LLM prompt templates: beat sheet, dialogue system, refinement, summary |
| `script.py` | 3-pass script generation (uses prompts.py for templates, state.py for history) |
| `state.py` | `state.json` load/save, episode numbering, date/number-to-words helpers |
| `audio.py` | Turn parsing, cold-open detection, music layering |
| `tts_gemini.py` | Gemini 2.5 Flash TTS backend (single-pass 2-speaker with director's notes) |
| `collect.py` | Story aggregation, deduplication (URL + fuzzy title), ranking |
| `enrich.py` | Optional Tavily web search enrichment |
| `publish.py` | GitHub Release upload, RSS feed generation, git commit & push |
| `sources/` | Pluggable story sources (see Sources section) |

## Sources

Pluggable source architecture in `src/hn_signal/sources/`. Each source module exports a `collect() -> list[dict]` function.

| Source | Module | Type | Keyword filter? |
|--------|--------|------|-----------------|
| Hacker News | `sources/hn.py` | API | Yes |
| arXiv cs.AI/cs.LG | `sources/arxiv.py` | RSS | No (inherently AI) |
| Lab blogs (OpenAI, Google AI, HuggingFace) | `sources/lab_blogs.py` | RSS | No (inherently AI) |
| VentureBeat AI | `sources/venturebeat.py` | RSS | Yes |
| Ars Technica AI | `sources/arstechnica.py` | RSS | Yes |

Shared helpers: `sources/_rss.py` (RSS parsing), `sources/_util.py` (keyword matching, body extraction).

### Adding a new source

1. Create `sources/new_source.py` with a `collect() -> list[dict]` function
2. Return stories in unified format: `{id, title, url, body, sources: [{name, score, comments, published}], source_count, rank_score}`
3. Add module to `SOURCES` list in `sources/__init__.py`

### Story ranking

Stories are deduplicated by URL (normalized) and fuzzy title matching, then ranked:
- Cross-source appearance: +10 per additional source
- HN score: normalized, capped at +5
- Recency: +3 today, +1 yesterday
- Body available: +2

## Environment Variables

Configured in `.env` (see `.env.example`):

**Required:** `ANTHROPIC_API_KEY`, `GITHUB_TOKEN`, `GITHUB_REPO`, `PODCAST_BASE_URL`

**Optional:** `TAVILY_API_KEY` (enrichment skipped without it), `GEMINI_API_KEY`, `PODCAST_TITLE`, `PODCAST_DESCRIPTION`, `PODCAST_AUTHOR`, `GEMINI_VOICE_KIT`, `GEMINI_VOICE_DEAN`, `PUBLISH_HOUR` (default: `7`), `PUBLISH_TIMEZONE` (default: `Europe/London`)

## Key Constants

- AI keyword filter list: `config.py:AI_KEYWORDS`
- RSS feed URLs: `config.py:ARXIV_FEEDS`, `LAB_BLOG_FEEDS`, `VENTUREBEAT_AI_FEED`, `ARSTECHNICA_AI_FEED`
- Max final stories after ranking: `config.py:MAX_FINAL_STORIES` (15)
- Script model: `claude-sonnet-4-6` (max 12,288 tokens for dialogue/refinement, 8,192 for beat sheet)
- Beat sheet model: `claude-sonnet-4-6`
- Summary model: `claude-haiku-4-5-20251001`
- TTS: Gemini 2.5 Flash TTS (24kHz, single-pass 2-speaker)
- Gemini voices: Kit → Zephyr (bright, clear, energetic), Dean → Orus (firm, decisive, commanding)
- Max 30 RSS episodes
- Publish schedule: `PUBLISH_HOUR` (default: 7), `PUBLISH_TIMEZONE` (default: Europe/London)
- Time-of-day greeting derived from `PUBLISH_HOUR` via `config.time_of_day_label()`

## Hosts

- **Kit** — The Maker: tech/product/design background, asks "what does this change about how something gets made?", measured delivery
- **Dean** — The Capital Allocator: venture background, asks "who wins, who loses, when does the money run out?", warm but fast-paced

## Output

- `episodes/YYYY-MM-DD-vN.mp3` — generated audio (versioned for multiple runs per day)
- `episodes/YYYY-MM-DD-vN-script.txt` — corresponding dialogue script
- `state.json` — last 30 episode summaries (for continuity)
- `feed.xml` — podcast RSS feed
- `logs/pipeline.log` — rotating Python log (5 MB × 5 backups), written by all pipeline runs
- `logs/YYYY-MM-DD.log` — daily shell-level log (created by `run-daily.sh` for scheduled runs)
- `logs/launchd-stdout.log` / `logs/launchd-stderr.log` — launchd capture

## Scheduling

Daily automated runs via macOS launchd. The pipeline starts at 6:35am London time so episodes are ready by 7am.

```bash
make install-schedule    # install & load the launchd job
make uninstall-schedule  # remove it
launchctl list com.therestofus.podcast  # check job status
```

- **Wrapper script**: `scripts/run-daily.sh` — runs `make run`, retries once after 10 minutes on failure, sends macOS notifications (Glass on success, Basso on failure)
- **Logs**: `logs/YYYY-MM-DD.log` (pipeline output), `logs/launchd-stdout.log` / `logs/launchd-stderr.log` (launchd output)
- **Timezone**: `StartCalendarInterval` uses system local time — assumes machine is set to Europe/London
- **Sleep handling**: launchd runs missed jobs on wake, so the episode will still generate if the machine was asleep at 6:35am

## Distribution via GitHub Pages

The podcast RSS feed is served via GitHub Pages from `feed.xml` in the repo root.

### Setup (one-time, manual):
1. Make the repo public: GitHub > Settings > General > Danger Zone > Change visibility
2. Enable Pages: GitHub > Settings > Pages > Source: Deploy from branch `main` / `/ (root)`
3. Set `PODCAST_BASE_URL` in `.env` to `https://<owner>.github.io/<repo>`
4. Subscribe in Apple Podcasts: Library > Add a Show by URL > `https://<owner>.github.io/<repo>/feed.xml`

## Code Style

### Imports

Standard library first, third-party second, local third. Alphabetical within each group.

```python
import logging
import os
from pathlib import Path

import httpx
from bs4 import BeautifulSoup

from hn_signal.config import PROJECT_ROOT, log
```

Avoid circular imports — use late imports inside functions when needed (see `enrich.py` and `publish.py`).

### Types and naming

- Type hints on all function signatures; use built-in types (`dict`, `list`, not `Dict`, `List`)
- Functions/variables: `snake_case`; constants: `UPPER_SNAKE_CASE`; private helpers: `_leading_underscore`
- Classes: `PascalCase` (rarely used)

### Logging

Use the shared logger from `config.py` with `%s` format strings (not f-strings) to avoid interpolation when the log level is above DEBUG:

```python
from hn_signal.config import log

log.info("Collected %d AI stories", len(stories))
log.warning("Failed to fetch article %s: %s", url, e)
```

### Error handling

- **Recoverable**: `log.warning(...)` + `continue`
- **Fatal**: `log.error(...)` + `sys.exit(1)`
- Prefer specific exception types (`httpx.HTTPStatusError`, `subprocess.CalledProcessError`)

### API clients

Initialize inside functions, not at module level, to avoid import-time side effects:

```python
def generate_script(stories, history):
    client = anthropic.Anthropic(api_key=ANTHROPIC_API_KEY)
```

### Paths and env vars

- Use `pathlib.Path` for all file paths
- Use `_require()` for required env vars (raises `SystemExit`), `os.getenv()` with defaults for optional ones

### Script format

Dialogue scripts use `KIT:` / `DEAN:` turn prefixes, one per line:

```
KIT: Dialogue here.
DEAN: Response here.
```

## Gotchas

- `ffmpeg` must be installed at runtime (pydub needs it for audio export), not just at install time
- `config.py` loads `.env` at **module import time** — the `.env` file must exist before importing any `hn_signal` module
- Script generation uses `max_tokens=8192`; if the model hits this limit, the dialogue is silently truncated (logged as a warning)
- No automated tests exist — validate changes by running individual stages (`make collect`, etc.)
- `.env.example` comments may lag behind `config.py` defaults (e.g., voice names) — trust `config.py` as source of truth
