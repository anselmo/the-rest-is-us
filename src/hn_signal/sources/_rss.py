from datetime import datetime

import feedparser

from hn_signal.config import log, log_fetch_failure
from hn_signal.models import Story, StorySource
from hn_signal.sources._util import fetch_article_body, matches_keywords


def fetch_rss_stories(
    feed_url: str,
    source_name: str,
    needs_keyword_filter: bool = True,
    max_items: int = 25,
    fetch_body: bool = True,
) -> list[Story]:
    log.info("Fetching RSS feed: %s", feed_url)
    feed = feedparser.parse(feed_url)

    if feed.bozo and not feed.entries:
        log.warning("RSS feed error for %s: %s", feed_url, feed.bozo_exception)
        log_fetch_failure(source_name, feed_url, feed.bozo_exception)
        return []

    stories = []
    for entry in feed.entries[:max_items]:
        title = entry.get("title", "").strip()
        if not title:
            continue

        link = entry.get("link", "")
        summary = entry.get("summary", "")

        if needs_keyword_filter and not matches_keywords(f"{title} {summary}"):
            continue

        published = None
        if entry.get("published_parsed"):
            try:
                published = datetime(*entry.published_parsed[:6]).isoformat()
            except Exception:
                pass

        body = ""
        if fetch_body:
            body = fetch_article_body(link)
        if not body and summary:
            # Fall back to RSS summary as body (stripped of HTML)
            from bs4 import BeautifulSoup

            body = BeautifulSoup(summary, "html.parser").get_text(strip=True)[:6000]

        stories.append(
            Story(
                id=entry.get("id", link),
                title=title,
                url=link,
                body=body,
                sources=[StorySource(name=source_name, published=published)],
                source_count=1,
                rank_score=0.0,
            )
        )

    log.info("RSS %s: %d stories collected", source_name, len(stories))
    return stories
