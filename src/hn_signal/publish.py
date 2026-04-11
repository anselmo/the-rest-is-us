import xml.etree.ElementTree as ET
from datetime import datetime, timezone
from email.utils import format_datetime
from zoneinfo import ZoneInfo
from pathlib import Path

import httpx

from hn_signal.config import (
    GITHUB_REPO,
    GITHUB_TOKEN,
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


def _github_headers() -> dict:
    return {
        "Authorization": f"Bearer {GITHUB_TOKEN}",
        "Accept": "application/vnd.github+json",
        "X-GitHub-Api-Version": "2022-11-28",
    }


def _github_base_url() -> str:
    parts = GITHUB_REPO.split("/")
    if len(parts) != 2:
        raise ValueError(f"GITHUB_REPO must be 'owner/repo', got: {GITHUB_REPO!r}")
    owner, repo = parts
    return f"https://api.github.com/repos/{owner}/{repo}"


def _upload_to_github(mp3_path: Path, tag: str) -> str:
    """Create (or reuse) a GitHub Release and upload the MP3. Returns the download URL."""
    base = _github_base_url()

    # Check if release already exists (idempotent re-runs)
    existing = httpx.get(f"{base}/releases/tags/{tag}", headers=_github_headers(), timeout=30)
    if existing.status_code == 200:
        release = existing.json()
        log.info("Reusing existing GitHub release: %s", tag)
        # Check if asset already uploaded
        for asset in release.get("assets", []):
            if asset["name"] == mp3_path.name:
                log.info("MP3 asset already uploaded: %s", asset["browser_download_url"])
                return asset["browser_download_url"]
    else:
        # Create release
        log.info("Creating GitHub release: %s", tag)
        resp = httpx.post(
            f"{base}/releases",
            headers=_github_headers(),
            json={"tag_name": tag, "name": tag, "body": f"Episode {tag}"},
            timeout=30,
        )
        resp.raise_for_status()
        release = resp.json()

    upload_url = release["upload_url"].replace("{?name,label}", "")

    # Upload asset (streaming)
    log.info("Uploading MP3 asset (%d bytes)", mp3_path.stat().st_size)
    with open(mp3_path, "rb") as f:
        resp = httpx.post(
            upload_url,
            params={"name": mp3_path.name},
            headers={
                **_github_headers(),
                "Content-Type": "application/octet-stream",
            },
            content=f,
            timeout=120,
        )
    resp.raise_for_status()
    download_url = resp.json()["browser_download_url"]
    log.info("Upload complete: %s", download_url)
    return download_url


def _create_feed() -> ET.Element:
    """Create a new RSS feed with channel metadata."""
    rss = ET.Element("rss", {
        "version": "2.0",
        "xmlns:itunes": ITUNES_NS,
    })
    channel = ET.SubElement(rss, "channel")

    ET.SubElement(channel, "title").text = PODCAST_TITLE
    ET.SubElement(channel, "description").text = PODCAST_DESCRIPTION
    ET.SubElement(channel, "link").text = PODCAST_BASE_URL
    ET.SubElement(channel, "language").text = "en"
    ET.SubElement(channel, "{%s}author" % ITUNES_NS).text = PODCAST_AUTHOR
    ET.SubElement(channel, "{%s}explicit" % ITUNES_NS).text = "no"
    ET.SubElement(channel, "{%s}image" % ITUNES_NS, href=f"{PODCAST_BASE_URL}/cover.jpg")

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


def _commit_and_push() -> None:
    """Commit feed.xml and state.json, then push."""
    import subprocess

    state_path = PROJECT_ROOT / "state.json"
    files_to_commit = [str(FEED_PATH)]
    if state_path.exists():
        files_to_commit.append(str(state_path))

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
    tag = f"episode-{date}"
    mp3_url = _upload_to_github(mp3_path, tag)
    mp3_size = mp3_path.stat().st_size

    rss = _load_feed()
    _add_episode(rss, date, mp3_url, mp3_size, duration_seconds, episode_number)
    _save_feed(rss)
    _commit_and_push()

    return mp3_url
