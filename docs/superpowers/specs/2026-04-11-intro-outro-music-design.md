# Intro/Outro Music Support

## Context

The Rest of Us podcast currently outputs pure dialogue — no sonic branding. Adding a short intro sting and an outro music bed gives the show a recognizable identity and a polished feel, without competing with the conversational tone that defines it.

Reference vibe: **M83 "Midnight City"** — dreamy synth textures, atmospheric but driving. The music should frame the conversation, not dominate it.

## Audio Flow

```
[intro.mp3 plays solo ~5-8s] ──crossfade──▶ [TTS dialogue] ──outro fades in under last lines──▶ [outro.mp3 tail ~5-8s]
```

- **Intro**: Music plays solo, then crossfades into the dialogue's cold open (Kit's first line fades in as music fades out over ~2s)
- **Outro**: Music fades in under the final lines of dialogue (~3s before dialogue ends), then continues solo for its remaining duration after voices stop

## File Structure

```
assets/
  intro.mp3    # User-provided intro music sting (~8-15 sec)
  outro.mp3    # User-provided outro music (~10-20 sec)
```

Static files committed to the repo. Same music every episode — swap files to rebrand.

## Config Constants

Add to `src/hn_signal/config.py`:

```python
# Intro/outro music
INTRO_MUSIC_PATH = PROJECT_ROOT / "assets" / "intro.mp3"
OUTRO_MUSIC_PATH = PROJECT_ROOT / "assets" / "outro.mp3"
INTRO_CROSSFADE_MS = 2000    # crossfade duration from intro into dialogue
OUTRO_FADE_IN_MS = 3000      # how early outro music begins before dialogue ends
MUSIC_VOLUME_DB = -6          # volume reduction for music relative to dialogue
```

No new environment variables — these are code constants, not per-deployment config.

## Implementation

### Refactor: Backend functions return AudioSegment

Currently both `_generate_audio_gemini()` and `_generate_audio_elevenlabs()` handle their own MP3 export. Refactor so they return an `AudioSegment` instead, and move the export to `generate_audio()`. This creates a single point where music can be added before export.

**`_generate_audio_gemini()`** (`audio.py:85`):
- Remove lines 161-162 (MP3 export) and line 163 (wav cleanup)
- Return `(segment, duration_seconds)` where `segment` is the `AudioSegment` from line 160
- Keep wav file cleanup (unlink) in this function

**`_generate_audio_elevenlabs()`** (`audio.py:173`):
- Remove lines 237-238 (MP3 export)
- Return `(combined, duration_seconds)` where `combined` is the concatenated `AudioSegment`

Both backends change signature: `-> tuple[AudioSegment, int]`

### New function: `_add_music(dialogue: AudioSegment) -> AudioSegment`

Located in `audio.py`. Logic:

1. **Check for files**: If `INTRO_MUSIC_PATH` or `OUTRO_MUSIC_PATH` don't exist, log a warning and return `dialogue` unchanged. Pipeline never breaks due to missing music.

2. **Intro** (if file exists):
   - Load `intro.mp3` as `AudioSegment`
   - Reduce volume by `MUSIC_VOLUME_DB` dB
   - Use `intro.append(dialogue, crossfade=INTRO_CROSSFADE_MS)` to crossfade intro into dialogue
   - This means the intro plays, then the last `INTRO_CROSSFADE_MS` of the intro overlaps with the first `INTRO_CROSSFADE_MS` of the dialogue, with the intro fading out and dialogue fading in

3. **Outro** (if file exists):
   - Load `outro.mp3` as `AudioSegment`
   - Reduce volume by `MUSIC_VOLUME_DB` dB
   - Apply `fade_in(OUTRO_FADE_IN_MS)` to the outro
   - Calculate overlay position: `pos = len(current_audio) - OUTRO_FADE_IN_MS`
   - Pad current audio with silence to fit the full outro: `current_audio += AudioSegment.silent(duration=len(outro) - OUTRO_FADE_IN_MS)`
   - Overlay: `current_audio = current_audio.overlay(outro, position=pos)`
   - Result: outro fades in under the last lines, then continues solo after voices end

4. Return the final `AudioSegment`

### Modified: `generate_audio()`

Updated flow (`audio.py:248`):

```python
def generate_audio(script: str, output_path: Path) -> tuple[Path, int]:
    # 1. Generate dialogue audio via backend
    if TTS_BACKEND == "gemini":
        dialogue, duration = _generate_audio_gemini(script, output_path)
    elif TTS_BACKEND == "elevenlabs":
        dialogue, duration = _generate_audio_elevenlabs(script, output_path)
    else:
        raise ValueError(...)

    # 2. Add intro/outro music
    final = _add_music(dialogue)

    # 3. Export to MP3
    bitrate = "192k" if TTS_BACKEND == "gemini" else "128k"
    output_path.parent.mkdir(parents=True, exist_ok=True)
    final.export(str(output_path), format="mp3", bitrate=bitrate)

    # 4. Recalculate duration (music changes total length)
    duration = len(final) // 1000
    log.info("Audio exported: %s (%d seconds)", output_path, duration)
    return output_path, duration
```

### New imports in `audio.py`

Add to the config import block:

```python
from hn_signal.config import (
    ...
    INTRO_MUSIC_PATH,
    OUTRO_MUSIC_PATH,
    INTRO_CROSSFADE_MS,
    OUTRO_FADE_IN_MS,
    MUSIC_VOLUME_DB,
)
```

## Graceful Degradation

- **No music files**: Pipeline produces dialogue-only output (current behavior). Warning logged.
- **Only intro, no outro** (or vice versa): Applies whichever is present, skips the missing one.
- **Music shorter than crossfade**: `pydub.append()` handles this — crossfade is clamped to the shorter segment's length.

## Files Modified

| File | Change |
|------|--------|
| `src/hn_signal/config.py` | Add 5 music constants |
| `src/hn_signal/audio.py` | Refactor backends to return `AudioSegment`, add `_add_music()`, update `generate_audio()` |
| `assets/intro.mp3` | New file (user-provided) |
| `assets/outro.mp3` | New file (user-provided) |

## Verification

1. **Without music files**: Run `uv run hn-signal` — pipeline should work identically to current behavior, with a log warning about missing music files
2. **With music files**: Place test MP3s in `assets/`, run pipeline — verify intro crossfades into dialogue and outro fades in under sign-off
3. **Spot-check**: Open output MP3 in Audacity or similar — visually confirm the waveform shows music → crossfade → dialogue → outro overlay → outro tail
4. **Duration**: Verify reported duration includes music (should be ~15-25s longer than dialogue-only)
