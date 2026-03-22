import difflib
from datetime import date, datetime
from urllib.parse import urlparse, urlencode, parse_qs

from hn_signal.config import MAX_FINAL_STORIES, log
from hn_signal.sources import collect_all_sources


def _normalize_url(url: str) -> str:
    if not url:
        return ""
    parsed = urlparse(url)
    # Strip protocol, www prefix, trailing slash
    host = parsed.netloc.lower().removeprefix("www.")
    path = parsed.path.rstrip("/")
    # Strip utm and tracking query params
    params = parse_qs(parsed.query)
    clean_params = {k: v for k, v in params.items() if not k.startswith("utm_")}
    query = "&".join(f"{k}={v[0]}" for k, v in sorted(clean_params.items())) if clean_params else ""
    normalized = f"{host}{path}"
    if query:
        normalized += f"?{query}"
    return normalized


def _deduplicate(stories: list[dict]) -> list[dict]:
    # Group by normalized URL
    url_groups: dict[str, dict] = {}
    no_url: list[dict] = []

    for story in stories:
        norm = _normalize_url(story["url"])
        if not norm:
            no_url.append(story)
            continue
        if norm in url_groups:
            # Merge sources into existing story
            existing = url_groups[norm]
            existing["sources"].extend(story["sources"])
            # Keep the longer body
            if len(story.get("body", "")) > len(existing.get("body", "")):
                existing["body"] = story["body"]
        else:
            url_groups[norm] = story

    merged = list(url_groups.values())

    # Fuzzy title match for stories without URLs or with different URLs for the same content
    for orphan in no_url:
        matched = False
        for existing in merged:
            ratio = difflib.SequenceMatcher(
                None,
                orphan["title"].lower(),
                existing["title"].lower(),
            ).ratio()
            if ratio > 0.8:
                existing["sources"].extend(orphan["sources"])
                if len(orphan.get("body", "")) > len(existing.get("body", "")):
                    existing["body"] = orphan["body"]
                matched = True
                break
        if not matched:
            merged.append(orphan)

    # Also check fuzzy title match across URL-grouped stories (different URLs, same story)
    i = 0
    while i < len(merged):
        j = i + 1
        while j < len(merged):
            ratio = difflib.SequenceMatcher(
                None,
                merged[i]["title"].lower(),
                merged[j]["title"].lower(),
            ).ratio()
            if ratio > 0.8:
                merged[i]["sources"].extend(merged[j]["sources"])
                if len(merged[j].get("body", "")) > len(merged[i].get("body", "")):
                    merged[i]["body"] = merged[j]["body"]
                merged.pop(j)
            else:
                j += 1
        i += 1

    for story in merged:
        story["source_count"] = len(story["sources"])

    return merged


def _rank(stories: list[dict]) -> list[dict]:
    today = date.today()

    for story in stories:
        score = 0.0

        # Cross-source boost: +10 per source beyond the first
        score += (story["source_count"] - 1) * 10

        # HN score: normalized, capped at 5
        for src in story["sources"]:
            if src["name"] == "hackernews" and src["score"]:
                score += min(src["score"] / 100, 5.0)
                break

        # Recency bonus
        for src in story["sources"]:
            if src.get("published"):
                try:
                    pub_date = datetime.fromisoformat(src["published"]).date()
                    days_old = (today - pub_date).days
                    if days_old == 0:
                        score += 3.0
                    elif days_old == 1:
                        score += 1.0
                    break
                except (ValueError, TypeError):
                    pass

        # Body available bonus
        if story.get("body"):
            score += 2.0

        story["rank_score"] = score

    stories.sort(key=lambda s: s["rank_score"], reverse=True)
    return stories


def collect_stories() -> list[dict]:
    raw = collect_all_sources()
    deduped = _deduplicate(raw)
    ranked = _rank(deduped)

    top = ranked[:MAX_FINAL_STORIES]
    log.info(
        "Collected %d raw → %d deduped → top %d stories",
        len(raw),
        len(deduped),
        len(top),
    )
    return top


if __name__ == "__main__":
    results = collect_stories()
    for s in results:
        src_names = ", ".join(src["name"] for src in s["sources"])
        print(f"[rank={s['rank_score']:.1f} sources={s['source_count']}] {s['title']}")
        print(f"  Sources: {src_names}")
        print(f"  URL: {s['url']}")
        print(f"  Body: {s['body'][:200]}..." if s["body"] else "  Body: (none)")
        print()
