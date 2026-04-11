from hn_signal.config import LAB_BLOG_FEEDS, log
from hn_signal.models import Story
from hn_signal.sources._rss import fetch_rss_stories


def collect() -> list[Story]:
    all_stories = []
    for source_name, feed_url in LAB_BLOG_FEEDS.items():
        try:
            stories = fetch_rss_stories(
                feed_url,
                source_name=source_name,
                needs_keyword_filter=False,
            )
            all_stories.extend(stories)
        except Exception as e:
            log.warning("Lab blog %s failed: %s", source_name, e)

    log.info("Lab blogs: %d posts collected", len(all_stories))
    return all_stories


if __name__ == "__main__":
    results = collect()
    for s in results:
        src = s.sources[0].name
        print(f"[{src}] {s.title}")
        print(f"  URL: {s.url}")
        print(f"  Body: {s.body[:200]}..." if s.body else "  Body: (none)")
        print()
