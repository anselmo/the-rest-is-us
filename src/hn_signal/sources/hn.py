import httpx

from hn_signal.config import log, log_fetch_failure
from hn_signal.models import Story, StorySource
from hn_signal.sources._util import fetch_article_body, matches_keywords

HN_TOP_STORIES = "https://hacker-news.firebaseio.com/v0/topstories.json"
HN_ITEM = "https://hacker-news.firebaseio.com/v0/item/{}.json"
MAX_STORIES = 25


def collect() -> list[Story]:
    log.info("Fetching top %d HN stories", MAX_STORIES)

    resp = httpx.get(HN_TOP_STORIES, timeout=10)
    resp.raise_for_status()
    story_ids = resp.json()[:MAX_STORIES]

    stories = []
    for story_id in story_ids:
        try:
            item_resp = httpx.get(HN_ITEM.format(story_id), timeout=10)
            item_resp.raise_for_status()
            item = item_resp.json()
        except Exception as e:
            log.warning("Failed to fetch item %s: %s", story_id, e)
            log_fetch_failure("hackernews", HN_ITEM.format(story_id), e)
            continue

        title = item.get("title", "")
        if not matches_keywords(title):
            continue

        url = item.get("url", "")
        body = fetch_article_body(url)

        stories.append(
            Story(
                id=str(item["id"]),
                title=title,
                url=url,
                body=body,
                sources=[
                    StorySource(
                        name="hackernews",
                        score=item.get("score", 0),
                        comments=item.get("descendants", 0),
                    )
                ],
                source_count=1,
                rank_score=0.0,
            )
        )
        log.info("HN: %s (score=%d)", title, item.get("score", 0))

    log.info("HN: %d AI stories collected", len(stories))
    return stories


if __name__ == "__main__":
    results = collect()
    for s in results:
        score = s.sources[0].score
        print(f"[{score}] {s.title}")
        print(f"  URL: {s.url}")
        print(f"  Body: {s.body[:200]}..." if s.body else "  Body: (none)")
        print()
