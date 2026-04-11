from hn_signal.config import VENTUREBEAT_AI_FEED
from hn_signal.models import Story
from hn_signal.sources._rss import fetch_rss_stories


def collect() -> list[Story]:
    return fetch_rss_stories(
        VENTUREBEAT_AI_FEED,
        source_name="venturebeat",
        needs_keyword_filter=True,
    )


if __name__ == "__main__":
    results = collect()
    for s in results:
        print(f"[VentureBeat] {s.title}")
        print(f"  URL: {s.url}")
        print()
