import re

import httpx
from bs4 import BeautifulSoup

from hn_signal.config import AI_KEYWORDS, log

HN_TOP_STORIES = "https://hacker-news.firebaseio.com/v0/topstories.json"
HN_ITEM = "https://hacker-news.firebaseio.com/v0/item/{}.json"
MAX_STORIES = 25
MAX_BODY_CHARS = 6000


def _matches_keywords(title: str) -> bool:
    lower = title.lower()
    for kw in AI_KEYWORDS:
        kw_lower = kw.lower()
        # Use word boundary for short keywords (<=3 chars) to avoid false positives
        # e.g. "AI" shouldn't match "aircraft" or "airplane"
        if len(kw) <= 3:
            if re.search(r"\b" + re.escape(kw_lower) + r"\b", lower):
                return True
        else:
            if kw_lower in lower:
                return True
    return False


def _extract_body(html: str) -> str:
    soup = BeautifulSoup(html, "html.parser")

    for tag in soup.find_all(["script", "style", "nav", "footer", "header"]):
        tag.decompose()

    # Try <article>, then <main>, then longest <div>
    for selector in ["article", "main"]:
        el = soup.find(selector)
        if el:
            text = el.get_text(separator="\n", strip=True)
            if len(text) > 100:
                return text[:MAX_BODY_CHARS]

    divs = soup.find_all("div")
    if divs:
        longest = max(divs, key=lambda d: len(d.get_text()))
        text = longest.get_text(separator="\n", strip=True)
        if len(text) > 100:
            return text[:MAX_BODY_CHARS]

    return soup.get_text(separator="\n", strip=True)[:MAX_BODY_CHARS]


def _fetch_article_body(url: str) -> str:
    if not url:
        return ""
    # Skip PDFs, videos, and other non-HTML
    if re.search(r"\.(pdf|mp4|mp3|mov|avi)(\?|$)", url, re.IGNORECASE):
        return ""
    try:
        resp = httpx.get(url, timeout=10, follow_redirects=True)
        resp.raise_for_status()
        content_type = resp.headers.get("content-type", "")
        if "text/html" not in content_type:
            return ""
        return _extract_body(resp.text)
    except Exception as e:
        log.warning("Failed to fetch article %s: %s", url, e)
        return ""


def collect_stories() -> list[dict]:
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
            continue

        title = item.get("title", "")
        if not _matches_keywords(title):
            continue

        url = item.get("url", "")
        body = _fetch_article_body(url)

        stories.append(
            {
                "id": item["id"],
                "title": title,
                "url": url,
                "score": item.get("score", 0),
                "comments": item.get("descendants", 0),
                "body": body,
            }
        )
        log.info("Collected: %s (score=%d)", title, item.get("score", 0))

    log.info("Collected %d AI stories", len(stories))
    return stories


if __name__ == "__main__":
    results = collect_stories()
    for s in results:
        print(f"[{s['score']}] {s['title']}")
        print(f"  URL: {s['url']}")
        print(f"  Body: {s['body'][:200]}..." if s["body"] else "  Body: (none)")
        print()
