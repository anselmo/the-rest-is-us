import sys
from datetime import date, datetime

from hn_signal.config import PROJECT_ROOT, log

EPISODES_DIR = PROJECT_ROOT / "episodes"


def main() -> None:
    from hn_signal.collect import collect_stories
    from hn_signal.enrich import enrich_stories
    from hn_signal.script import extract_episode_summary, generate_script, load_state, save_state
    from hn_signal.audio import generate_audio
    from hn_signal.publish import publish_episode

    skip_publish = "--no-publish" in sys.argv

    today = date.today().isoformat()
    now = datetime.now()
    episode_tag = f"{today}-{now.hour:02d}{now.minute:02d}"
    log.info("=== HN Signal pipeline starting for %s ===", episode_tag)

    # Stage 1: Collect
    stories = collect_stories()
    if len(stories) < 2:
        log.error("Only %d AI stories found, need at least 2. Aborting.", len(stories))
        sys.exit(1)

    # Stage 2: Enrich
    stories = enrich_stories(stories)

    # Stage 3: Script
    history = load_state()
    script = generate_script(stories, history)
    summary = extract_episode_summary(script, stories)

    # Stage 4: Audio
    EPISODES_DIR.mkdir(parents=True, exist_ok=True)

    script_path = EPISODES_DIR / f"{episode_tag}-script.txt"
    script_path.write_text(script)
    log.info("Script saved: %s", script_path)

    mp3_path = EPISODES_DIR / f"{episode_tag}.mp3"
    mp3_path, duration = generate_audio(script, mp3_path)

    if skip_publish:
        log.info("=== Skipping publish (--no-publish) ===")
        log.info("MP3: %s (%ds)", mp3_path, duration)
        return

    # Stage 5: Publish
    try:
        url = publish_episode(mp3_path, today, duration, title=summary.title)
    except Exception as e:
        log.error("Publish failed: %s", e)
        log.error("Local MP3 preserved at: %s", mp3_path)
        sys.exit(1)

    # Only save state after successful publish
    save_state(summary)
    log.info("=== Published: %s ===", url)


if __name__ == "__main__":
    main()
