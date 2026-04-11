import sys
from datetime import date

from hn_signal.config import PROJECT_ROOT, log

EPISODES_DIR = PROJECT_ROOT / "episodes"


def main() -> None:
    from hn_signal.collect import collect_stories
    from hn_signal.enrich import enrich_stories
    from hn_signal.script import extract_episode_summary, generate_script, load_state, next_episode_number, save_state
    from hn_signal.audio import generate_audio
    from hn_signal.publish import publish_episode

    today = date.today().isoformat()
    log.info("=== HN Signal pipeline starting for %s ===", today)

    # Stage 1: Collect
    stories = collect_stories()
    if len(stories) < 2:
        log.error("Only %d AI stories found, need at least 2. Aborting.", len(stories))
        sys.exit(1)

    # Stage 2: Enrich
    stories = enrich_stories(stories)

    # Stage 3: Script
    history = load_state()
    episode_number = next_episode_number()
    log.info("Generating episode #%d", episode_number)
    script = generate_script(stories, history)
    summary = extract_episode_summary(script, stories)

    # Stage 4: Audio — versioned filename (v1, v2, ...) for multiple runs per day
    version = 1
    while (EPISODES_DIR / f"{today}-v{version}.mp3").exists():
        version += 1

    # Save script for re-generation (make audio)
    script_path = EPISODES_DIR / f"{today}-v{version}-script.txt"
    EPISODES_DIR.mkdir(parents=True, exist_ok=True)
    script_path.write_text(script)
    log.info("Script saved: %s", script_path)

    mp3_path = EPISODES_DIR / f"{today}-v{version}.mp3"
    mp3_path, duration = generate_audio(script, mp3_path)

    # Stage 5: Publish
    try:
        url = publish_episode(mp3_path, today, duration, episode_number)
    except Exception as e:
        log.error("Publish failed: %s", e)
        log.error("Local MP3 preserved at: %s", mp3_path)
        sys.exit(1)

    # Only save state after successful publish
    save_state(summary)
    log.info("=== Published: %s ===", url)


if __name__ == "__main__":
    main()
