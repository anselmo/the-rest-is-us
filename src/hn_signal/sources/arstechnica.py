from hn_signal.config import ARSTECHNICA_AI_FEED
from hn_signal.models import Story
from hn_signal.sources._rss import fetch_rss_stories


def collect() -> list[Story]:
    return fetch_rss_stories(
        ARSTECHNICA_AI_FEED,
        source_name="arstechnica",
        needs_keyword_filter=True,
    )


if __name__ == "__main__":
    results = collect()
    for s in results:
        print(f"[Ars Technica] {s.title}")
        print(f"  URL: {s.url}")
        print()
