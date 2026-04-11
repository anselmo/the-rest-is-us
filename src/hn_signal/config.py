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

# TTS backend: "gemini" (default) or "elevenlabs"
TTS_BACKEND = os.getenv("TTS_BACKEND", "gemini").strip()

# Gemini TTS (required when TTS_BACKEND=gemini)
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY", "").strip() or None
GEMINI_VOICE_KIT = os.getenv("GEMINI_VOICE_KIT", "Zephyr")      # bright, clear, energetic
GEMINI_VOICE_DEAN = os.getenv("GEMINI_VOICE_DEAN", "Orus")      # firm, decisive, commanding — clearly male
GEMINI_SAMPLE_RATE = 24_000

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
MAX_BREAKERS_PER_EPISODE = 3
BREAKER_VOLUME_DB = -3

# ElevenLabs (required when TTS_BACKEND=elevenlabs)
ELEVENLABS_API_KEY = os.getenv("ELEVENLABS_API_KEY", "").strip() or None
ELEVENLABS_VOICE_ID_KIT = os.getenv("ELEVENLABS_VOICE_ID_KIT", "").strip() or None
ELEVENLABS_VOICE_ID_DEAN = os.getenv("ELEVENLABS_VOICE_ID_DEAN", "").strip() or None

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
    "openai_blog": "https://openai.com/blog/rss.xml",
    "google_ai_blog": "https://blog.google/technology/ai/rss/",
    "huggingface_blog": "https://huggingface.co/blog/feed.xml",
}

VENTUREBEAT_AI_FEED = "https://venturebeat.com/category/ai/feed/"
ARSTECHNICA_AI_FEED = "https://arstechnica.com/ai/feed/"

# Ranking
MAX_FINAL_STORIES = 10

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
