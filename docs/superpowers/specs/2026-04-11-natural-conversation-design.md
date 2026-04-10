# Natural Conversation Pipeline Design

**Date:** 2026-04-11
**Goal:** Make podcast conversations sound natural — like NotebookLM — by fixing three problems: turns too long, no real discovery arc, flat TTS delivery.
**Approach:** Three-pass pipeline with beat sheet planning.

---

## Problem Analysis

The current two-pass pipeline (generate + refine) produces conversations where both hosts have all information upfront. "Discovery" moments are performative — the model writes them because the prompt says to, not because the conversation structure creates them. Turns default to 3-5 sentences because there's no structural constraint. TTS direction is generic.

## Architecture: Three-Pass Pipeline

```
Stories + History
       │
       ▼
┌──────────────────┐
│  Pass 0: Plan    │  Haiku — $0.001/episode
│  (Beat Sheet)    │  Plans structure, assigns asymmetric knowledge,
│                  │  maps energy arc, sets turn length targets
└────────┬─────────┘
         │ beat_sheet JSON
         ▼
┌──────────────────┐
│  Pass 1: Write   │  Sonnet — $0.02-0.04/episode
│  (Dialogue)      │  Generates dialogue following beat sheet,
│                  │  enforces turn length caps, writes discovery moments
└────────┬─────────┘
         │ draft script
         ▼
┌──────────────────┐
│  Pass 2: Polish  │  Sonnet — $0.01-0.03/episode
│  (TTS Delivery)  │  Tightens turns, optimizes prosody markers,
│                  │  kills blog-post phrasing, adds crosstalk
└────────┬─────────┘
         │ final script
         ▼
┌──────────────────┐
│  Gemini TTS      │  Enhanced director's notes
│  (Audio)         │  Per-host pacing, discovery moment delivery,
│                  │  interruption handling, energy arc
└──────────────────┘
```

No changes to main.py, collect.py, enrich.py, or publish.py.

---

## Pass 0: Beat Sheet

### Model
`claude-haiku-4-5-20251001` (same model used for summary extraction — cheap, fast, good at structured output).

### Output Schema

```json
{
  "episode_theme": "One-sentence thematic frame",
  "cold_open": {
    "hook": "Single most surprising fact or tension",
    "who_opens": "Kit | Dean",
    "energy": "curious | urgent | amused"
  },
  "segments": [
    {
      "story_index": 0,
      "story_title": "...",
      "segment_type": "deep_dive | quick_hit",
      "estimated_turns": 12,
      "lead_host": "Kit | Dean",
      "lead_reason": "Why this host leads",

      "asymmetric_knowledge": {
        "kit_knows": "Product/UX angle Kit uniquely brings",
        "dean_knows": "Market/capital angle Dean uniquely brings",
        "kit_doesnt_know": "What Kit will learn from Dean",
        "dean_doesnt_know": "What Dean will learn from Kit"
      },

      "discovery_beats": [
        {
          "revealer": "Kit | Dean",
          "reveals": "The specific insight being revealed",
          "expected_reaction": "surprise | pushback | builds_on_it | concedes",
          "reaction_note": "Why this surprises the other host"
        }
      ],

      "arc": [
        {
          "beat": "setup | reaction | develop | tension | reveal | resolve",
          "who": "Kit | Dean",
          "intent": "What this beat accomplishes",
          "turn_style": "rapid_fire | standard | one_word"
        }
      ],

      "energy_shape": "build | tension_release | slow_burn | peak_early",
      "bridge_to_next": "Thematic connection to next segment (null for last)"
    }
  ],
  "close": {
    "kit_takeaway": "Kit's takeaway direction",
    "dean_takeaway": "Dean's takeaway direction",
    "energy": "reflective | energized | provocative"
  }
}
```

### Key Design Decisions

- **`asymmetric_knowledge`** is the most important field. Forces the planner to split information between hosts, creating genuine discovery.
- **`arc`** beats have `turn_style` annotations that Pass 1 must honor. Most should be `rapid_fire` or `one_word`.
- **`estimated_turns`** gives Pass 1 a concrete length target. Deep dives: 10-18 turns. Quick hits: 4-6 turns.
- **`discovery_beats`** require at least 2 per deep_dive segment.

### Prompt Summary

The beat sheet prompt instructs Haiku to:
1. Select 2-3 stories for deep_dive, optionally 1-2 for quick_hit
2. Assign asymmetric knowledge based on host expertise (Kit: product/UX/technical; Dean: market/capital/competitive)
3. Plan discovery beats where information asymmetry pays off
4. Map energy shapes that vary across segments (not all "build")
5. Set turn style distribution biased toward rapid_fire and one_word
6. Output valid JSON only

Input: condensed story summaries (title, URL, source count, 500-char body preview, 300-char enrichment preview) + last 3 episode summaries for continuity.

---

## Pass 1: Dialogue Generation (Rewritten)

### What Changes from Current Prompt

**Removed sections** (now handled by beat sheet):
- CONVERSATION STRUCTURE — beat sheet defines segment order and flow
- DYNAMIC GUIDELINES — beat sheet plans specific tension/agreement moments
- Story selection logic — beat sheet already selected stories

**Added sections:**

#### FOLLOWING THE BEAT SHEET
- Follow segment order, host assignments, and discovery beats
- But write dialogue that sounds SPONTANEOUS
- Honor turn_style annotations strictly:
  - `rapid_fire` = 1 sentence max
  - `standard` = 2-3 sentences max
  - `one_word` = 1-5 words only
- Discovery moments must FEEL asymmetric — "Wait — seriously?" not "Oh interesting, and also..."

#### TURN LENGTH — NON-NEGOTIABLE RULES
- Default max: 2 sentences per turn
- Setup turns (first beat of segment): up to 3 sentences
- Rapid-fire: exactly 1 sentence
- One-word: 1-5 words only
- NO TURN may exceed 3 sentences under any circumstances

**Kept sections** (unchanged):
- Host personas (Kit and Dean descriptions)
- SHOW TONE
- WHAT THE HOSTS NEVER DO
- BOTH HOSTS ASK EACH OTHER QUESTIONS
- INTERRUPTIONS & INTERJECTIONS
- LAUGHTER & EMOTIONAL REACTIONS
- VOCAL FILLERS & THINKING ALOUD
- WRITE FOR SPEECH
- VOICE TEXTURE
- SOURCE ATTRIBUTION
- FORMAT

**Modified sections:**
- TEMPO: Target estimated_turns from beat sheet. Total script: 1200-1800 words (down from 1500-2200).

### User Message Format

```
BEAT SHEET (follow this structure):
{beat_sheet_json}

SOURCE STORIES (use these for facts and details):
{stories_json}
```

---

## Pass 2: TTS Delivery Refinement (Refocused)

### Shift in Purpose

Old focus: "Add 20VC-style energy" (structural + delivery)
New focus: "Optimize delivery for TTS" (delivery only — structure is handled)

### Key Rules

1. **Turn length enforcement** — Any turn >2 sentences: split or cut. Any >3: MUST be shortened.
2. **Prosody optimization** — Em dashes before reveals, ellipses for hesitation, caps on ONE stress word, vary sentence length
3. **Energy arc polish** — Warm opening, building middle, reflective close
4. **Crosstalk markers** — 3-5+ interruption fragments with genuinely incomplete sentences
5. **Anti-blog-post filter** — Kill: "It's worth noting", "At the end of the day", "It remains to be seen", "In terms of"

---

## TTS Direction (audio.py)

### Enhanced Gemini Director's Notes

Replace the current generic director's notes with more specific per-host instructions:

**Kit voice direction:**
- Clear, warm, measured default pace
- Speeds up slightly when excited, slows for emphasis
- Sharp lines land with a beat of silence before them
- Pitch drops on devastating observations
- Laughs are quiet — amused exhale, not performance

**Dean voice direction:**
- Warm, energetic, slightly faster default pace
- Speeds up when pattern-matching, slows and drops pitch for specific numbers
- Laughs more openly than Kit
- "Look —" and "Here's the thing —" are verbal tics — quick, not dramatic

**Performance rules:**
1. Short turns delivered at conversational speed, not radio speed
2. One-word reactions quick and throwaway, not emphasized
3. Questions get natural pitch rise; answers start with a thinking pause
4. Interruptions cut mid-word; the interrupter comes in with energy
5. Discovery moments ("Wait, really?") need genuine surprise — pause before, pitch shift
6. Energy builds through episode: warm start → conviction at end
7. Laughter brief and genuine — one syllable, then move on

---

## Files Modified

| File | Changes |
|------|---------|
| `src/hn_signal/config.py` | Add `BEAT_SHEET_MODEL` constant |
| `src/hn_signal/script.py` | Add beat sheet prompt + `generate_beat_sheet()` function; rewrite `SYSTEM_PROMPT` for beat-sheet-driven generation; refocus `REFINEMENT_PROMPT` on TTS delivery; update `generate_script()` to call Pass 0 first |
| `src/hn_signal/audio.py` | Replace `GEMINI_DIRECTOR_NOTES` with enhanced version |

No changes to: `main.py`, `collect.py`, `enrich.py`, `publish.py`, `sources/*`

---

## Cost Impact

| Pass | Model | Cost/Episode |
|------|-------|-------------|
| Beat Sheet (NEW) | Haiku | ~$0.001-0.002 |
| Dialogue | Sonnet | ~$0.02-0.04 |
| Refinement | Sonnet | ~$0.01-0.03 |
| Summary | Haiku | ~$0.001 |
| **Total** | | **~$0.03-0.07** |

Net increase: ~$0.001-0.002/episode for the beat sheet pass.

---

## Verification Plan

1. Run `uv run hn-signal` to execute full pipeline
2. Listen to generated episode and compare against previous episodes in `episodes/`
3. Check turn length distribution — most turns should be 1-2 sentences
4. Verify discovery moments sound genuine, not performative
5. Verify TTS delivery has varied energy, natural pacing, and genuine reactions
6. Check beat sheet JSON is well-formed (inspect debug artifact if saved)
7. Run `uv run python -m hn_signal.collect` first to validate story collection still works unchanged

---

## Risks and Mitigations

| Risk | Mitigation |
|------|-----------|
| Haiku outputs malformed JSON | Regex fallback to extract JSON; consider structured output via tool use if persistent |
| Beat sheet over-specifies, dialogue sounds mechanical | Prompt explicitly says "sound spontaneous despite following structure" |
| LLM still produces long turns despite caps | Pass 2 enforces turn length as first priority; could add programmatic post-processing |
| Beat sheet input token budget | Condensed story summaries (500-char body, 300-char enrichment) keep input small |
