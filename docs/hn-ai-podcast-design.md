# HN AI Podcast — Design Spec

## Context

Build a fully automated daily podcast that surfaces AI stories from Hacker News, enriches them with web context, generates a two-host conversational script via Claude, renders audio via ElevenLabs, and publishes via GitHub Releases + Pages RSS. Episodes maintain continuity by referencing prior episodes.

## Architecture

Simple sequential pipeline: `collect → enrich → script → audio → publish`. Runs once daily via cron. No async, no task queue — each stage is a pure function.

## Project Structure

```
hn-ai-podcast/
├── pyproject.toml       # uv + dependencies
├── main.py              # Orchestrator
├── collect.py           # HN API + article fetching
├── enrich.py            # Tavily web search
├── script.py            # Claude API script generation
├── audio.py             # ElevenLabs TTS + pydub concatenation
├── publish.py           # GitHub Releases + Pages RSS
├── config.py            # Env vars, constants, keyword list
├── state.json           # Episode history (last 7 episodes)
├── feed.xml             # RSS feed (committed, served via GH Pages)
├── episodes/            # Local MP3 output (gitignored)
├── logs/                # Run logs (gitignored)
├── .env                 # API keys (gitignored)
└── .gitignore
```

## Dependencies

```
anthropic
elevenlabs
httpx
beautifulsoup4
pydub
tavily-python
python-dotenv
```

## Environment Variables

```
ANTHROPIC_API_KEY=         # Required — Claude API
ELEVENLABS_API_KEY=        # Required — TTS
ELEVENLABS_VOICE_ID_ALEX=  # Required — pre-created voice
ELEVENLABS_VOICE_ID_SAM=   # Required — pre-created voice
TAVILY_API_KEY=            # Optional — enrichment skipped without it
GITHUB_TOKEN=              # Required — release creation
GITHUB_REPO=owner/repo     # Required — releases + pages
PODCAST_BASE_URL=          # Required — e.g. https://owner.github.io/hn-ai-podcast
PODCAST_TITLE=HN Signal
PODCAST_DESCRIPTION=Daily AI stories from Hacker News, discussed in plain language.
PODCAST_AUTHOR=HN Signal
```

## Stage 1: collect.py

**Function:** `collect_stories() -> list[dict]`

- Fetch top 25 story IDs from `https://hacker-news.firebaseio.com/v0/topstories.json`
- For each ID, fetch `/v0/item/{id}.json`
- Filter: case-insensitive substring match on title against keyword list:
  `AI, LLM, GPT, Claude, Gemini, OpenAI, Anthropic, model, neural, transformer, inference, fine-tun, RAG, agent, multimodal, diffusion, embeddings, Mistral, Llama, Grok, deep learning, machine learning`
- For qualifying stories, fetch article URL via `httpx` (10s timeout) + `BeautifulSoup`:
  - Extract text from first `<article>`, then `<main>`, then longest `<div>` by character count
  - Strip nav/footer/ads/script/style tags
  - Truncate to ~6000 chars (~1500 tokens)
  - On failure (timeout, PDF, video, non-200): body = `""` (title + score + comments still present)
- Return: `[{"id": int, "title": str, "url": str, "score": int, "comments": int, "body": str}]`

## Stage 2: enrich.py

**Function:** `enrich_stories(stories: list[dict]) -> list[dict]`

- For each story, call Tavily API: `"{title}" site:news.ycombinator.com OR AI implications`
- Extract top 2 result snippets, max 300 tokens each
- Add `enrichment: list[str]` to each story
- If `TAVILY_API_KEY` missing or call fails: `enrichment: []`, no error

## Stage 3: script.py

**Functions:**
- `generate_script(stories: list[dict], history: dict) -> str`
- `extract_episode_summary(script: str, stories: list[dict]) -> dict`

### Script generation
- Single Claude API call, model `claude-sonnet-4-5`
- System prompt with additional continuity block:
  ```
  Here is context from recent episodes for continuity:
  {history_json}

  When relevant, reference previous episodes naturally (e.g., "as we discussed
  yesterday...", "following up on that story from last week..."). Only reference
  when it adds value — don't force callbacks.
  ```
- User message: enriched story list as JSON
- Output: raw script as `ALEX: ... \n SAM: ...` lines

### Summary extraction
- Second Claude API call (using `claude-haiku-4-5` to minimize cost) with the generated script as input
- Prompt: "Extract from this podcast script: 1) story titles covered, 2) key themes (1-3 words each), 3) the 'story to watch' mentioned at the end. Return JSON."
- Returns: `{"stories_covered": [...], "key_themes": [...], "story_to_watch": "..."}`
- Updates `state.json`

## Stage 4: audio.py

**Function:** `generate_audio(script: str, output_path: Path) -> tuple[Path, int]`

Returns `(mp3_path, duration_seconds)`.

- Parse script: split on `^ALEX:` / `^SAM:` line prefixes (regex `r'^(ALEX|SAM):\s*'`)
- If no valid turns found (malformed output), abort with error
- Cap at 30 turns (log warning if truncated)
- For each turn: ElevenLabs SDK `generate()` with appropriate voice ID, model `eleven_multilingual_v2`
- On single turn failure: skip, log warning, continue
- Concatenate all segments with `pydub`
- Calculate duration: `len(combined_audio)` in milliseconds, convert to seconds for RSS
- Export: MP3 44.1kHz 128kbps to `episodes/YYYY-MM-DD.mp3`
- Return: `(output_path, duration_seconds)`

## Stage 5: publish.py

**Function:** `publish_episode(mp3_path: Path, date: str, duration_seconds: int) -> str`

### MP3 upload
- Create GitHub Release tagged `episode-YYYY-MM-DD`
- Attach MP3 as release asset
- Uses `httpx` + GitHub Releases API (`POST /repos/{owner}/{repo}/releases` then upload asset)
- MP3 download URL: extract `browser_download_url` from the asset upload response

### RSS update
- Read `feed.xml` from repo (create if first episode)
- Prepend new `<item>`:
  - `<title>`: HN Signal — YYYY-MM-DD
  - `<enclosure>`: MP3 URL from release asset, length in bytes, type="audio/mpeg"
  - `<itunes:duration>`: seconds (from pydub)
  - `<pubDate>`: RFC 2822
  - `<guid>`: MP3 URL
- Trim to 30 episodes
- Channel-level tags: `itunes:author`, `itunes:category` (Technology), `itunes:image`, `language` (en), `itunes:explicit` (no)
- Commit `feed.xml` + `state.json` to repo (triggers GH Pages rebuild)

## state.json

```json
{
  "episodes": [
    {
      "date": "2026-03-21",
      "stories_covered": ["Story title 1", "Story title 2"],
      "key_themes": ["NVIDIA", "open-source models"],
      "story_to_watch": "OpenAI reasoning model release"
    }
  ]
}
```

Last 7 entries retained. Older entries dropped on each run.
On first run (no `state.json` exists): `load_state()` returns `{"episodes": []}` — no continuity context sent to Claude.

## Orchestrator: main.py

```python
def main():
    stories = collect_stories()
    if len(stories) < 3:
        log.error("Only %d AI stories found, aborting", len(stories))
        sys.exit(1)

    stories = enrich_stories(stories)
    history = load_state()
    script = generate_script(stories, history)
    save_state(extract_episode_summary(script, stories))

    mp3_path, duration = generate_audio(script, episode_path(today))
    url = publish_episode(mp3_path, today, duration)
    log.info("Published: %s", url)
```

- Abort if < 3 stories
- If publish fails: local MP3 preserved in episodes/, exit non-zero
- Logging: Python `logging` module with timestamp prefix

## Error Handling

| Stage | Failure mode | Behavior |
|-------|-------------|----------|
| collect | HN API down | Abort (no stories) |
| collect | Article fetch fails | Fall back to title+score+comments |
| enrich | Tavily unavailable | Skip enrichment, continue |
| script | Claude API error | Abort (can't generate episode) |
| audio | Single turn TTS fails | Skip turn, continue |
| audio | pydub/ffmpeg missing | Abort with clear error |
| publish | GitHub API fails | Preserve local MP3, exit non-zero |

## Verification

1. **Unit test each stage** with mock data — confirm data shapes match interfaces
2. **Dry run** with real HN API but mocked Claude/ElevenLabs — verify collect + enrich work
3. **Full pipeline test** — run `python main.py` with real API keys, verify:
   - MP3 created in episodes/
   - GitHub Release created with MP3 asset
   - feed.xml updated with new entry
   - state.json updated with episode summary
4. **RSS validation** — paste feed URL into castfeedvalidator.com to verify Apple Podcasts compliance
5. **Continuity test** — run twice, verify second episode's script references first

## One-Time Manual Steps

1. Create ElevenLabs voices for Alex and Sam → copy IDs to .env
2. Create podcast cover art (3000x3000px JPG) → upload to repo root or GH Pages
3. Enable GitHub Pages on the repo (source: main branch or gh-pages)
4. Submit RSS feed URL to podcastsconnect.apple.com after first episode
5. Set up cron: `0 6 * * * cd /path/to/hn-ai-podcast && python main.py >> logs/run.log 2>&1`
