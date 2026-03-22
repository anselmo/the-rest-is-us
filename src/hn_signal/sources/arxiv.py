from hn_signal.config import ARXIV_FEEDS, log
from hn_signal.sources._rss import fetch_rss_stories


def collect() -> list[dict]:
    all_stories = []
    for feed_url in ARXIV_FEEDS:
        stories = fetch_rss_stories(
            feed_url,
            source_name="arxiv",
            needs_keyword_filter=False,
            fetch_body=False,  # use RSS abstract as body
        )
        all_stories.extend(stories)

    log.info("arXiv: %d papers collected", len(all_stories))
    return all_stories


if __name__ == "__main__":
    results = collect()
    for s in results:
        print(f"[arXiv] {s['title']}")
        print(f"  URL: {s['url']}")
        print(f"  Body: {s['body'][:200]}..." if s["body"] else "  Body: (none)")
        print()
