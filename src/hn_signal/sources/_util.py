import re

import httpx
from bs4 import BeautifulSoup

from hn_signal.config import AI_KEYWORDS, log, log_fetch_failure

MAX_BODY_CHARS = 6000


def matches_keywords(text: str) -> bool:
    lower = text.lower()
    for kw in AI_KEYWORDS:
        kw_lower = kw.lower()
        if len(kw) <= 3:
            if re.search(r"\b" + re.escape(kw_lower) + r"\b", lower):
                return True
        else:
            if kw_lower in lower:
                return True
    return False


def extract_body(html: str) -> str:
    soup = BeautifulSoup(html, "html.parser")

    for tag in soup.find_all(["script", "style", "nav", "footer", "header"]):
        tag.decompose()

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


def fetch_article_body(url: str) -> str:
    if not url:
        return ""
    if re.search(r"\.(pdf|mp4|mp3|mov|avi)(\?|$)", url, re.IGNORECASE):
        return ""
    headers = {"User-Agent": "HNSignal/1.0 (podcast aggregator)"}
    try:
        resp = httpx.get(url, timeout=10, follow_redirects=True, headers=headers)
        resp.raise_for_status()
        content_type = resp.headers.get("content-type", "")
        if "text/html" not in content_type:
            return ""
        return extract_body(resp.text)
    except Exception as e:
        log.warning("Failed to fetch article %s: %s", url, e)
        log_fetch_failure("article_body", url, e)
        return ""
