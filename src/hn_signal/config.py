import logging
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
ELEVENLABS_API_KEY = _require("ELEVENLABS_API_KEY")
ELEVENLABS_VOICE_ID_ALEX = _require("ELEVENLABS_VOICE_ID_ALEX")
ELEVENLABS_VOICE_ID_SAM = _require("ELEVENLABS_VOICE_ID_SAM")
GITHUB_TOKEN = _require("GITHUB_TOKEN")
GITHUB_REPO = _require("GITHUB_REPO")
PODCAST_BASE_URL = _require("PODCAST_BASE_URL")

# Optional keys
TAVILY_API_KEY = os.getenv("TAVILY_API_KEY", "").strip() or None

# Podcast metadata
PODCAST_TITLE = os.getenv("PODCAST_TITLE", "HN Signal")
PODCAST_DESCRIPTION = os.getenv(
    "PODCAST_DESCRIPTION",
    "Daily AI stories from Hacker News, discussed in plain language.",
)
PODCAST_AUTHOR = os.getenv("PODCAST_AUTHOR", "HN Signal")

# AI keyword list for filtering HN stories
AI_KEYWORDS = [
    "AI",
    "LLM",
    "GPT",
    "Claude",
    "Gemini",
    "OpenAI",
    "Anthropic",
    "model",
    "neural",
    "transformer",
    "inference",
    "fine-tun",
    "RAG",
    "agent",
    "multimodal",
    "diffusion",
    "embeddings",
    "Mistral",
    "Llama",
    "Grok",
    "deep learning",
    "machine learning",
]

# Models
SCRIPT_MODEL = "claude-sonnet-4-5-20250514"
SUMMARY_MODEL = "claude-haiku-4-5-20241022"

# Logging
logging.basicConfig(
    format="%(asctime)s %(levelname)s %(message)s",
    level=logging.INFO,
)
log = logging.getLogger("hn-ai-podcast")
