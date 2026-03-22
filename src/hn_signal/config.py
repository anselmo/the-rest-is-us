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
ELEVENLABS_VOICE_ID_NICK = _require("ELEVENLABS_VOICE_ID_NICK")
ELEVENLABS_VOICE_ID_MIA = _require("ELEVENLABS_VOICE_ID_MIA")
GITHUB_TOKEN = _require("GITHUB_TOKEN")
GITHUB_REPO = _require("GITHUB_REPO")
PODCAST_BASE_URL = _require("PODCAST_BASE_URL")

# Optional keys
TAVILY_API_KEY = os.getenv("TAVILY_API_KEY", "").strip() or None

# Podcast metadata
PODCAST_TITLE = os.getenv("PODCAST_TITLE", "HN Signal")
PODCAST_DESCRIPTION = os.getenv(
    "PODCAST_DESCRIPTION",
    "Daily AI stories from across the web, discussed in plain language.",
)
PODCAST_AUTHOR = os.getenv("PODCAST_AUTHOR", "HN Signal")

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
SUMMARY_MODEL = "claude-haiku-4-5-20251001"

# Logging
logging.basicConfig(
    format="%(asctime)s %(levelname)s %(message)s",
    level=logging.INFO,
)
log = logging.getLogger("hn-ai-podcast")
