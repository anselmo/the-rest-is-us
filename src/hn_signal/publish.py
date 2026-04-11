import xml.etree.ElementTree as ET
from datetime import datetime
from email.utils import format_datetime
from zoneinfo import ZoneInfo
from pathlib import Path

from hn_signal.config import (
    PODCAST_AUTHOR,
    PODCAST_BASE_URL,
    PODCAST_DESCRIPTION,
    PODCAST_TITLE,
    PROJECT_ROOT,
    PUBLISH_HOUR,
    PUBLISH_TIMEZONE,
    log,
)

FEED_PATH = PROJECT_ROOT / "feed.xml"
MAX_EPISODES = 30

ITUNES_NS = "http://www.itunes.com/dtds/podcast-1.0.dtd"
ET.register_namespace("itunes", ITUNES_NS)



def _create_feed() -> ET.Element:
    """Create a new RSS feed with channel metadata."""
    rss = ET.Element("rss", {"version": "2.0"})
    channel = ET.SubElement(rss, "channel")

    ET.SubElement(channel, "title").text = PODCAST_TITLE
    ET.SubElement(channel, "description").text = PODCAST_DESCRIPTION
    ET.SubElement(channel, "link").text = PODCAST_BASE_URL
    ET.SubElement(channel, "language").text = "en"
    ET.SubElement(channel, "{%s}author" % ITUNES_NS).text = PODCAST_AUTHOR
    ET.SubElement(channel, "{%s}explicit" % ITUNES_NS).text = "no"
    ET.SubElement(channel, "{%s}image" % ITUNES_NS, href=f"{PODCAST_BASE_URL}/assets/cover/cover-3000.png")

    category = ET.SubElement(channel, "{%s}category" % ITUNES_NS, text="Technology")
    ET.SubElement(category, "{%s}category" % ITUNES_NS, text="Tech News")

    return rss


def _load_feed() -> ET.Element:
    if FEED_PATH.exists():
        return ET.parse(FEED_PATH).getroot()
    return _create_feed()


def _add_episode(rss: ET.Element, date: str, mp3_url: str, mp3_size: int, duration_seconds: int, episode_number: int | None = None) -> None:
    channel = rss.find("channel")
    item = ET.Element("item")

    if episode_number:
        ET.SubElement(item, "title").text = f"{PODCAST_TITLE} — #{episode_number} — {date}"
    else:
        ET.SubElement(item, "title").text = f"{PODCAST_TITLE} — {date}"
    ET.SubElement(item, "enclosure", url=mp3_url, length=str(mp3_size), type="audio/mpeg")
    ET.SubElement(item, "{%s}duration" % ITUNES_NS).text = str(duration_seconds)

    tz = ZoneInfo(PUBLISH_TIMEZONE)
    pub_date = datetime.strptime(date, "%Y-%m-%d").replace(hour=PUBLISH_HOUR, tzinfo=tz)
    ET.SubElement(item, "pubDate").text = format_datetime(pub_date)
    ET.SubElement(item, "guid", isPermaLink="true").text = mp3_url

    # Insert after channel metadata, before existing items
    items = channel.findall("item")
    if items:
        idx = list(channel).index(items[0])
        channel.insert(idx, item)
    else:
        channel.append(item)

    # Trim to MAX_EPISODES
    all_items = channel.findall("item")
    for old_item in all_items[MAX_EPISODES:]:
        channel.remove(old_item)


def _save_feed(rss: ET.Element) -> None:
    ET.indent(rss, space="  ")
    tree = ET.ElementTree(rss)
    tree.write(str(FEED_PATH), encoding="unicode", xml_declaration=True)
    log.info("Feed saved to %s", FEED_PATH)


def _commit_and_push(mp3_path: Path | None = None) -> None:
    """Commit feed.xml, state.json, and optionally the MP3, then push."""
    import subprocess

    state_path = PROJECT_ROOT / "state.json"
    files_to_commit = [str(FEED_PATH)]
    if state_path.exists():
        files_to_commit.append(str(state_path))
    if mp3_path and mp3_path.exists():
        files_to_commit.append(str(mp3_path))

    try:
        subprocess.run(["git", "add"] + files_to_commit, check=True, capture_output=True)
        subprocess.run(
            ["git", "commit", "-m", "Update feed.xml and state.json"],
            check=True,
            capture_output=True,
        )
        subprocess.run(["git", "push"], check=True, capture_output=True)
        log.info("Committed and pushed feed.xml + state.json")
    except subprocess.CalledProcessError as e:
        raise RuntimeError(
            f"Git commit/push failed: {e.stderr.decode() if e.stderr else e}"
        ) from e


def publish_episode(mp3_path: Path, date: str, duration_seconds: int, episode_number: int | None = None) -> str:
    mp3_size = mp3_path.stat().st_size
    mp3_url = f"{PODCAST_BASE_URL}/episodes/{mp3_path.name}"

    rss = _load_feed()
    _add_episode(rss, date, mp3_url, mp3_size, duration_seconds, episode_number)
    _save_feed(rss)
    _commit_and_push(mp3_path)

    return mp3_url
