import logging
import logging.handlers
import os
import sys
from pathlib import Path

from dotenv import load_dotenv

# Project root is two levels up from src/hn_signal/config.py
PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent

load_dotenv(PROJECT_ROOT / ".env")


def _require(key: str) -> str:
    value = os.getenv(key, "").strip()
    if not value:
        print(f"ERROR: Required environment variable {key} is not set", file=sys.stderr)
        raise SystemExit(1)
    return value


# Required keys
ANTHROPIC_API_KEY = _require("ANTHROPIC_API_KEY")
GITHUB_TOKEN = _require("GITHUB_TOKEN")
GITHUB_REPO = _require("GITHUB_REPO")
PODCAST_BASE_URL = _require("PODCAST_BASE_URL")

# Gemini TTS
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY", "").strip() or None
GEMINI_SAMPLE_RATE = 24_000

# Host profiles — all available hosts for the podcast
HOST_PROFILES = {
    "Kit": {
        "full_name": "Kit Palmer",
        "title": "The Maker",
        "voice": "Zephyr",
        "core_question": "What does this actually change about how something gets made, and for whom?",
        "persona": (
            "Comes from a tech, product, and design background. Has shipped things, sweated "
            "over interfaces, argued about roadmaps. Instinctively reaches for the user experience "
            "before the architecture, and the architecture before the press release. When a new "
            "model or tool drops, her first question isn't \"is it impressive?\" — it's \"what does "
            "this actually change about how something gets made, and for whom?\" Has a designer's "
            "sensitivity to the gap between what a thing claims to be and what it feels like to use. "
            "Measured in delivery. Occasionally devastating in a single quiet sentence."
        ),
        "voice_texture": (
            "Measured, clear delivery. Slightly longer sentences that build to a sharp point. Uses "
            "\"But —\" and \"The problem is —\" to pivot. Her sharpness comes through precision, not "
            "volume. Occasionally devastating in a single quiet sentence. Uses more \"Hmm.\" and "
            "\"I mean—\" and \"That's interesting because—\""
        ),
        "director_note": (
            "Clear, warm, measured. Speeds up when excited, slows down for emphasis. Sharp lines "
            "land with a beat of silence. Pitch drops on devastating observations. Laughs are "
            "quiet — an amused exhale, not a performance."
        ),
    },
    "Dean": {
        "full_name": "Dean Calloway",
        "title": "The Capital Allocator",
        "voice": "Orus",
        "core_question": "Who wins, who loses, and when does the money run out?",
        "persona": (
            "Comes from a venture background. Has sat across the table from hundreds of founders, "
            "written the cheques, and watched the gap between pitch and reality play out at close "
            "range. Thinks in market structure, defensibility, and timing. His frame on any "
            "announcement is: would I fund the team building on top of this, and at what valuation "
            "does that stop making sense? More willing to name numbers. Comfortable with uncertainty "
            "— he makes decisions without full information for a living. Warmer in register, but "
            "with a pattern-matching speed that occasionally reads as impatience."
        ),
        "voice_texture": (
            "Warmer, faster cadence. Short declarative sentences. Pattern-matches quickly. Uses "
            "specific numbers and timelines. Says \"Look —\" before a strong take. His energy is "
            "in his conviction and speed. Uses more \"Nah.\" and \"Here's what I'd say—\""
        ),
        "director_note": (
            "Warm, energetic, slightly faster default pace. Speeds up when pattern-matching. "
            "Slows down and drops pitch for numbers and predictions. Laughs more openly. "
            "\"Look —\" and \"Here's the thing —\" are verbal tics — deliver quickly, not dramatically."
        ),
    },
    "Luna": {
        "full_name": "Luna Ferreira",
        "title": "The Researcher",
        "voice": "Aoede",
        "core_question": "What does the evidence actually show?",
        "persona": (
            "An ML researcher who reads papers the way other people read the news. Thinks in "
            "experiments, ablations, and confidence intervals. When a new model drops, her first "
            "question is about the eval methodology, not the marketing claims. Unhurried — she "
            "thinks out loud, pauses to reformulate. Gets animated when methodology is elegant. "
            "Skeptical of hype, but genuinely excited by good science."
        ),
        "voice_texture": (
            "Breezy and relaxed. Unhurried pace — pauses to reformulate. Gets animated when "
            "methodology is elegant. Skeptical of hype. Uses \"Well —\" and \"The data suggests —\" "
            "and \"That's interesting, but —\""
        ),
        "director_note": (
            "Breezy, relaxed, natural. An ML researcher who thinks out loud. Unhurried default "
            "pace. Gets animated when methodology is elegant. Skeptical of hype but genuinely "
            "excited by good science."
        ),
    },
    "Wren": {
        "full_name": "Wren Adler",
        "title": "The Journalist",
        "voice": "Erinome",
        "core_question": "What aren't they saying in this announcement?",
        "persona": (
            "A tech journalist who follows the money and reads SEC filings for fun. Skeptical of "
            "press releases by default. Precise delivery — she asks pointed questions and notices "
            "what's missing from announcements. Gets sharper when something doesn't add up. Her "
            "frame on any story is accountability: who benefits, who's exposed, and what's the "
            "angle nobody's covering?"
        ),
        "voice_texture": (
            "Clear and articulate. Precise delivery — asks pointed questions. Gets sharper when "
            "something doesn't add up. Skeptical by default. Uses \"But here's the thing —\" and "
            "\"Follow the money —\" and \"What they're not saying is —\""
        ),
        "director_note": (
            "Clear, articulate, precise. A journalist who reads SEC filings for fun. Gets sharper "
            "when something doesn't add up. Pointed questions come naturally. Skeptical by default."
        ),
    },
    "Dax": {
        "full_name": "Dax Renard",
        "title": "The Founder",
        "voice": "Umbriel",
        "core_question": "I've been on the other side of this deal — here's what's really happening.",
        "persona": (
            "A serial founder who's raised rounds, sold companies, and watched the gap between "
            "pitch decks and reality from the inside. Conversational pace — he tells stories from "
            "lived experience. Gets more deliberate when sharing hard-won lessons. Empathizes with "
            "founders even when criticizing their moves. His frame is founder reality: what the "
            "press release doesn't capture about what it actually takes."
        ),
        "voice_texture": (
            "Easy-going and relaxed. Tells stories from the inside. Gets more deliberate when "
            "sharing hard-won lessons. Empathizes with founders. Uses \"Look, I've been there —\" "
            "and \"The thing nobody tells you —\" and \"Here's what actually happens —\""
        ),
        "director_note": (
            "Easy-going, relaxed, conversational. A serial founder who's been through acquisitions. "
            "Stories from the inside. Gets more deliberate for hard-won lessons. Empathizes with "
            "founders even when criticizing their moves."
        ),
    },
}

# Active hosts — override via env vars for special episodes
_host1_key = os.getenv("HOST1", "Kit").strip()
_host2_key = os.getenv("HOST2", "Dean").strip()

if _host1_key not in HOST_PROFILES:
    print(f"ERROR: HOST1='{_host1_key}' not found in HOST_PROFILES. Available: {', '.join(HOST_PROFILES)}", file=sys.stderr)
    raise SystemExit(1)
if _host2_key not in HOST_PROFILES:
    print(f"ERROR: HOST2='{_host2_key}' not found in HOST_PROFILES. Available: {', '.join(HOST_PROFILES)}", file=sys.stderr)
    raise SystemExit(1)

HOST1 = HOST_PROFILES[_host1_key]
HOST2 = HOST_PROFILES[_host2_key]

# Intro/outro music
INTRO_MUSIC_PATH = PROJECT_ROOT / "assets" / "intro.mp3"
OUTRO_MUSIC_PATH = PROJECT_ROOT / "assets" / "outro.mp3"
INTRO_CROSSFADE_MS = 2000    # crossfade duration from intro into dialogue
OUTRO_FADE_IN_MS = 3000      # how early outro music begins before dialogue ends
MUSIC_VOLUME_DB = -6          # volume reduction for music relative to dialogue

# Breaker clips (story separators)
BREAKER_DIR = PROJECT_ROOT / "assets"
BREAKER_PATTERN = "breaker-*.mp3"
BREAKER_CROSSFADE_MS = 1500
MAX_BREAKERS_PER_EPISODE = 5
BREAKER_VOLUME_DB = -3
SEGMENT_GAP_MS = 2500            # silence between story segments

# Optional keys
TAVILY_API_KEY = os.getenv("TAVILY_API_KEY", "").strip() or None

# Podcast metadata
PODCAST_TITLE = os.getenv("PODCAST_TITLE", "The Rest of Us")
PODCAST_DESCRIPTION = os.getenv(
    "PODCAST_DESCRIPTION",
    "AI tech news for the technically literate. Two hosts, sceptical optimism, no cheerleading.",
)
PODCAST_AUTHOR = os.getenv("PODCAST_AUTHOR", "The Rest of Us")

# Schedule / greeting
PUBLISH_HOUR = int(os.getenv("PUBLISH_HOUR", "7"))
PUBLISH_TIMEZONE = os.getenv("PUBLISH_TIMEZONE", "Europe/London").strip()


def time_of_day_label(hour: int) -> str:
    """Map hour (0-23) to greeting-friendly label."""
    if 5 <= hour < 12:
        return "morning"
    elif 12 <= hour < 18:
        return "afternoon"
    else:
        return "evening"


# AI keyword list for filtering HN stories
AI_KEYWORDS = [
    # Core terms
    "AI",
    "LLM",
    "GPT",
    "NLP",
    "AGI",
    "ASI",
    "GenAI",
    "generative AI",
    "artificial intelligence",
    "deep learning",
    "machine learning",
    "neural",
    "transformer",
    "diffusion",
    "multimodal",
    "embeddings",
    "inference",
    "fine-tun",
    "RAG",
    "prompt",
    "token",
    "hallucin",
    "reasoning model",
    "foundation model",
    "large language",
    "small language",
    "text-to-",
    "speech-to-",
    "image generation",
    "voice cloning",
    "synthetic data",
    # Agents & tools
    "agent",
    "agentic",
    "copilot",
    "chatbot",
    "chat bot",
    "AI coding",
    "code generation",
    "coding agent",
    "vibe coding",
    "MCP",
    "tool use",
    "function calling",
    "AI assistant",
    # Companies & products
    "OpenAI",
    "Anthropic",
    "Claude",
    "Gemini",
    "Mistral",
    "Llama",
    "Grok",
    "DeepSeek",
    "Perplexity",
    "Midjourney",
    "Stability AI",
    "Cohere",
    "Hugging Face",
    "HuggingFace",
    "Meta AI",
    "Google AI",
    "Microsoft AI",
    "Amazon Bedrock",
    "Azure AI",
    "Vertex AI",
    "ElevenLabs",
    "Runway",
    "Suno",
    "Cursor",
    "Windsurf",
    "Replit",
    "GitHub Copilot",
    "ChatGPT",
    "DALL-E",
    "Sora",
    "Whisper",
    "NVIDIA",
    "xAI",
    # Techniques & concepts
    "RLHF",
    "reinforcement learning",
    "computer vision",
    "object detection",
    "image recognition",
    "natural language",
    "speech recognition",
    "text to speech",
    "autonomous",
    "self-driving",
    "robotics",
    "neural network",
    "GPU",
    "TPU",
    "vector database",
    "semantic search",
    "knowledge graph",
    "AI safety",
    "alignment",
    "benchmark",
]

# Source RSS feeds
ARXIV_FEEDS = [
    "http://export.arxiv.org/rss/cs.AI",
    "http://export.arxiv.org/rss/cs.LG",
]

LAB_BLOG_FEEDS = {
    # "anthropic_blog": no public RSS feed — add scraper-based source later
    "huggingface_blog": "https://huggingface.co/blog/feed.xml",
}

VENTUREBEAT_AI_FEED = "https://venturebeat.com/category/ai/feed/"
ARSTECHNICA_AI_FEED = "https://arstechnica.com/ai/feed/"
TECHCRUNCH_AI_FEED = "https://techcrunch.com/category/artificial-intelligence/feed/"

# Ranking
MAX_FINAL_STORIES = 15

# Models
SCRIPT_MODEL = "claude-sonnet-4-6"
BEAT_SHEET_MODEL = "claude-sonnet-4-6"
SUMMARY_MODEL = "claude-haiku-4-5-20251001"

# Logging
_LOG_DIR = PROJECT_ROOT / "logs"
_LOG_DIR.mkdir(exist_ok=True)

_log_fmt = logging.Formatter("%(asctime)s %(levelname)s %(message)s")

# Console handler (existing behavior)
_console = logging.StreamHandler()
_console.setFormatter(_log_fmt)

# Rotating file handler: 5 MB per file, keep last 5 files (≈25 MB total)
_file = logging.handlers.RotatingFileHandler(
    _LOG_DIR / "pipeline.log",
    maxBytes=5 * 1024 * 1024,
    backupCount=5,
)
_file.setFormatter(_log_fmt)

log = logging.getLogger("hn-ai-podcast")
log.setLevel(logging.INFO)
log.addHandler(_console)
log.addHandler(_file)

# Fetch-failure log — dedicated file for reviewing broken sources
_fail_fmt = logging.Formatter("%(asctime)s | %(message)s")
_fail_file = logging.handlers.RotatingFileHandler(
    _LOG_DIR / "fetch-failures.log",
    maxBytes=2 * 1024 * 1024,
    backupCount=3,
)
_fail_file.setFormatter(_fail_fmt)
_fetch_fail_log = logging.getLogger("hn-ai-podcast.fetch-failures")
_fetch_fail_log.setLevel(logging.WARNING)
_fetch_fail_log.addHandler(_fail_file)
_fetch_fail_log.propagate = False  # don't duplicate into main pipeline.log


def log_fetch_failure(source: str, url: str, error: object) -> None:
    """Record a fetch failure to logs/fetch-failures.log."""
    _fetch_fail_log.warning("%s | %s | %s", source, url, error)
