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
| 1. Collect | `src/hn_signal/collect.py` | Aggregate stories from all sources, deduplicate, rank by cross-source appearance + score | Multiple (see Sources) |
| 2. Enrich | `src/hn_signal/enrich.py` | Add web search context per story | Tavily (optional) |
| 3. Script | `src/hn_signal/script.py` | 3-pass pipeline: beat sheet → dialogue → TTS refinement, then summary extraction | Claude Sonnet (×3) + Haiku |
| 4. Audio | `src/hn_signal/audio.py` | TTS via Gemini (single-pass 2-speaker) or ElevenLabs fallback | Gemini TTS / ElevenLabs |
| 5. Publish | `src/hn_signal/publish.py` | Create GitHub Release, upload MP3, update RSS, commit & push | GitHub API |

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

**Optional:** `TAVILY_API_KEY` (enrichment skipped without it), `TTS_BACKEND` (default: `gemini`), `GEMINI_API_KEY` (required when `TTS_BACKEND=gemini`), `PODCAST_TITLE`, `PODCAST_DESCRIPTION`, `PODCAST_AUTHOR`, `GEMINI_VOICE_KIT`, `GEMINI_VOICE_DEAN`

**ElevenLabs fallback:** Set `TTS_BACKEND=elevenlabs` and provide `ELEVENLABS_API_KEY`, `ELEVENLABS_VOICE_ID_KIT`, `ELEVENLABS_VOICE_ID_DEAN`

## Key Constants

- AI keyword filter list: `config.py:AI_KEYWORDS`
- RSS feed URLs: `config.py:ARXIV_FEEDS`, `LAB_BLOG_FEEDS`, `VENTUREBEAT_AI_FEED`, `ARSTECHNICA_AI_FEED`
- Max final stories after ranking: `config.py:MAX_FINAL_STORIES` (10)
- Script model: `claude-sonnet-4-6` (max 8,192 tokens) — used for beat sheet, dialogue, and TTS refinement passes
- Beat sheet model: `claude-sonnet-4-6`
- Summary model: `claude-haiku-4-5-20251001`
- TTS: Gemini 2.5 Flash TTS (24kHz, single-pass 2-speaker), fallback ElevenLabs
- Gemini voices: Kit → Zephyr (bright, clear, energetic), Dean → Orus (firm, decisive, commanding)
- Max 30 RSS episodes

## Hosts

- **Kit** — The Maker: tech/product/design background, asks "what does this change about how something gets made?", measured delivery
- **Dean** — The Capital Allocator: venture background, asks "who wins, who loses, when does the money run out?", warm but fast-paced

## Output

- `episodes/YYYY-MM-DD.mp3` — generated audio
- `state.json` — last 7 episode summaries (for continuity)
- `feed.xml` — podcast RSS feed

## Gotchas

- `ffmpeg` must be installed at runtime (pydub needs it for audio export), not just at install time
- `config.py` loads `.env` at **module import time** — the `.env` file must exist before importing any `hn_signal` module
- Script generation uses `max_tokens=8192`; if the model hits this limit, the dialogue is silently truncated (logged as a warning)
- No automated tests exist — validate changes by running individual stages (`make collect`, etc.)
- `.env.example` comments may lag behind `config.py` defaults (e.g., voice names) — trust `config.py` as source of truth
