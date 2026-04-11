from hn_signal.config import log
from hn_signal.models import Story
from hn_signal.sources import arstechnica, arxiv, hn, lab_blogs, venturebeat

SOURCES = [hn, arxiv, lab_blogs, venturebeat, arstechnica]


def collect_all_sources() -> list[Story]:
    all_stories = []
    for source in SOURCES:
        try:
            stories = source.collect()
            log.info("Source %s: %d stories", source.__name__, len(stories))
            all_stories.extend(stories)
        except Exception as e:
            log.warning("Source %s failed, skipping: %s", source.__name__, e)
    log.info("Total raw stories from all sources: %d", len(all_stories))
    return all_stories
