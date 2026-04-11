import dataclasses

from hn_signal.config import TAVILY_API_KEY, log
from hn_signal.models import Story


def enrich_stories(stories: list[Story]) -> list[Story]:
    if not TAVILY_API_KEY:
        log.info("TAVILY_API_KEY not set, skipping enrichment")
        return [dataclasses.replace(story, enrichment=[]) for story in stories]

    from tavily import TavilyClient

    client = TavilyClient(api_key=TAVILY_API_KEY)

    enriched = []
    for story in stories:
        query = f'"{story.title}" AI implications'
        try:
            result = client.search(query, max_results=2)
            snippets = []
            for r in result.get("results", [])[:2]:
                content = r.get("content", "")
                # Rough 300-token cap (~1200 chars)
                snippets.append(content[:1200])
            enriched.append(dataclasses.replace(story, enrichment=snippets))
            log.info("Enriched: %s (%d snippets)", story.title, len(snippets))
        except Exception as e:
            log.warning("Enrichment failed for '%s': %s", story.title, e)
            enriched.append(dataclasses.replace(story, enrichment=[]))

    return enriched
