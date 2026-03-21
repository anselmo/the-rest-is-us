# HN Signal

Automated daily AI podcast pipeline. Scrapes top AI stories from Hacker News, generates a 3-person panel discussion script via Claude, renders audio via ElevenLabs TTS, and publishes as a GitHub Release with RSS feed.

## Quick Start

```bash
# Install dependencies
uv sync
brew install ffmpeg          # required by pydub for audio export

# Run full pipeline (all 5 stages)
uv run hn-signal

# Test story collection only (free, no API costs)
uv run python -m hn_signal.collect
```

## Pipeline Stages

| Stage | Module | What it does | API used |
|-------|--------|-------------|----------|
| 1. Collect | `src/hn_signal/collect.py` | Fetch top 25 HN stories, filter by AI keywords, extract article bodies | HN API (free) |
| 2. Enrich | `src/hn_signal/enrich.py` | Add web search context per story | Tavily (optional) |
| 3. Script | `src/hn_signal/script.py` | Generate 3-host panel discussion + episode summary | Claude Sonnet 4.5 + Haiku 4.5 |
| 4. Audio | `src/hn_signal/audio.py` | TTS for each dialogue turn, concatenate into MP3 | ElevenLabs |
| 5. Publish | `src/hn_signal/publish.py` | Create GitHub Release, upload MP3, update RSS, commit & push | GitHub API |

## Environment Variables

Configured in `.env` (see `.env.example`):

**Required:** `ANTHROPIC_API_KEY`, `ELEVENLABS_API_KEY`, `ELEVENLABS_VOICE_ID_ALEX`, `ELEVENLABS_VOICE_ID_NICK`, `ELEVENLABS_VOICE_ID_MIA`, `GITHUB_TOKEN`, `GITHUB_REPO`, `PODCAST_BASE_URL`

**Optional:** `TAVILY_API_KEY` (enrichment skipped without it), `PODCAST_TITLE`, `PODCAST_DESCRIPTION`, `PODCAST_AUTHOR`

## Key Constants

- AI keyword filter list: `config.py:AI_KEYWORDS`
- Script model: `claude-sonnet-4-5-20250514` (max 6,144 tokens)
- Summary model: `claude-haiku-4-5-20241022`
- TTS model: `eleven_multilingual_v2`, format `mp3_44100_128`
- Max 30 dialogue turns, max 30 RSS episodes

## Hosts

- **Alex Green** — Moderator: frames stories, directs conversation
- **Nick Salt** — Bold Analyst: conviction-driven takes and predictions
- **Mia Thorn** — Skeptical Pragmatist: reality-checks claims, tests business models

## Output

- `episodes/YYYY-MM-DD.mp3` — generated audio
- `state.json` — last 7 episode summaries (for continuity)
- `feed.xml` — podcast RSS feed
