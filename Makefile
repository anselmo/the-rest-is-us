.DEFAULT_GOAL := help

# ── Full pipeline ────────────────────────────────────────────────────
.PHONY: run
run: ## Run the full end-to-end pipeline (collect → enrich → script → audio → publish)
	uv run hn-signal

# ── Individual stages ────────────────────────────────────────────────
.PHONY: collect
collect: ## Stage 1 — Aggregate stories from all sources (free, no API costs)
	uv run python -m hn_signal.collect

.PHONY: enrich
enrich: ## Stage 2 — Enrich stories with web search context (requires TAVILY_API_KEY)
	uv run python -c "from hn_signal.collect import collect_stories; from hn_signal.enrich import enrich_stories; stories = enrich_stories(collect_stories()); print(f'{len(stories)} stories enriched')"

.PHONY: script
script: ## Stage 3 — Generate dialogue script from collected stories (requires ANTHROPIC_API_KEY)
	uv run python -c "\
	from hn_signal.collect import collect_stories; \
	from hn_signal.enrich import enrich_stories; \
	from hn_signal.script import generate_script, load_state; \
	stories = enrich_stories(collect_stories()); \
	script = generate_script(stories, load_state()); \
	print(script)"

.PHONY: audio
audio: ## Stage 4 — Re-generate audio from latest saved script (or SCRIPT=path/to/script.txt)
	@SCRIPT_FILE=$${SCRIPT:-$$(ls -t episodes/*-script.txt 2>/dev/null | head -1)}; \
	if [ -z "$$SCRIPT_FILE" ]; then echo "✗ No script found. Run 'make run' first or pass SCRIPT=path/to/file.txt"; exit 1; fi; \
	echo "Using script: $$SCRIPT_FILE"; \
	uv run python -c "\
	from pathlib import Path; \
	from datetime import date; \
	from hn_signal.audio import generate_audio; \
	from hn_signal.config import PROJECT_ROOT; \
	script = Path('$$SCRIPT_FILE').read_text(); \
	d = date.today().isoformat(); \
	out = PROJECT_ROOT / 'episodes'; \
	v = 1; \
	exec('while (out / f\"{d}-v{v}.mp3\").exists(): v += 1'); \
	p, dur = generate_audio(script, out / f'{d}-v{v}.mp3'); \
	print(f'Audio: {p} ({dur}s)')"

# ── Individual sources ───────────────────────────────────────────────
.PHONY: source-hn
source-hn: ## Fetch stories from Hacker News only
	uv run python -m hn_signal.sources.hn

.PHONY: source-arxiv
source-arxiv: ## Fetch stories from arXiv only
	uv run python -m hn_signal.sources.arxiv

.PHONY: source-labs
source-labs: ## Fetch stories from lab blogs (OpenAI, Google AI, HuggingFace)
	uv run python -m hn_signal.sources.lab_blogs

.PHONY: source-venturebeat
source-venturebeat: ## Fetch stories from VentureBeat AI
	uv run python -m hn_signal.sources.venturebeat

.PHONY: source-arstechnica
source-arstechnica: ## Fetch stories from Ars Technica AI
	uv run python -m hn_signal.sources.arstechnica

# ── Setup & maintenance ─────────────────────────────────────────────
.PHONY: install
install: ## Install all dependencies
	uv sync
	@command -v ffmpeg >/dev/null 2>&1 || echo "⚠  ffmpeg not found — install with: brew install ffmpeg"

.PHONY: check-env
check-env: ## Verify required environment variables are set
	@echo "Checking required environment variables..."
	@test -f .env || (echo "✗ .env file not found (copy from .env.example)" && exit 1)
	@. ./.env 2>/dev/null; \
	ok=true; \
	for var in ANTHROPIC_API_KEY GEMINI_API_KEY GITHUB_TOKEN GITHUB_REPO PODCAST_BASE_URL; do \
		eval val=\$$var; \
		if [ -z "$$val" ]; then echo "✗ $$var is not set"; ok=false; else echo "✓ $$var"; fi; \
	done; \
	for var in TAVILY_API_KEY; do \
		eval val=\$$var; \
		if [ -z "$$val" ]; then echo "○ $$var (optional, enrichment will be skipped)"; else echo "✓ $$var"; fi; \
	done; \
	$$ok || exit 1

.PHONY: clean
clean: ## Remove generated episodes and cached state
	rm -rf episodes/*.mp3
	@echo "Cleaned episodes/"

# ── Scheduling ──────────────────────────────────────────────────────
PLIST_SRC := com.therestofus.podcast.plist
PLIST_DST := $(HOME)/Library/LaunchAgents/com.therestofus.podcast.plist

.PHONY: install-schedule
install-schedule: ## Install daily 6:35am launchd job (episode ready by 7am)
	@cp $(PLIST_SRC) $(PLIST_DST)
	@chmod 644 $(PLIST_DST)
	@launchctl bootout gui/$$(id -u) $(PLIST_DST) 2>/dev/null || true
	@launchctl bootstrap gui/$$(id -u) $(PLIST_DST)
	@echo "Installed and loaded $(PLIST_DST)"

.PHONY: uninstall-schedule
uninstall-schedule: ## Remove daily launchd job
	@launchctl bootout gui/$$(id -u) $(PLIST_DST) 2>/dev/null || true
	@rm -f $(PLIST_DST)
	@echo "Unloaded and removed $(PLIST_DST)"

# ── Help ─────────────────────────────────────────────────────────────
.PHONY: help
help: ## Show this help message
	@grep -E '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) | \
		awk 'BEGIN {FS = ":.*?## "}; {printf "  \033[36m%-20s\033[0m %s\n", $$1, $$2}'
