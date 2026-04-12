from __future__ import annotations

import dataclasses
from dataclasses import dataclass, field
from typing import Protocol


@dataclass
class StorySource:
    name: str
    score: int | None = None
    comments: int | None = None
    published: str | None = None


@dataclass
class Story:
    id: str
    title: str
    url: str
    body: str
    sources: list[StorySource] = field(default_factory=list)
    source_count: int = 1
    rank_score: float = 0.0
    enrichment: list[str] = field(default_factory=list)

    def to_dict(self) -> dict:
        return dataclasses.asdict(self)


@dataclass
class StoryTake:
    title: str
    host1_take: str = ""
    host2_take: str = ""
    agreed: bool = True


@dataclass
class EpisodeSummary:
    date: str
    episode_number: int = 0
    stories: list[StoryTake] = field(default_factory=list)
    predictions: list[str] = field(default_factory=list)
    key_themes: list[str] = field(default_factory=list)
    story_to_watch: str = ""
    title: str = ""

    def to_dict(self) -> dict:
        return dataclasses.asdict(self)

    @classmethod
    def from_dict(cls, data: dict) -> EpisodeSummary:
        stories_raw = data.get("stories", [])
        stories = [
            StoryTake(
                title=s.get("title", ""),
                # Backward compatibility: map old kit_take/dean_take to host1_take/host2_take
                host1_take=s.get("host1_take") or s.get("kit_take", ""),
                host2_take=s.get("host2_take") or s.get("dean_take", ""),
                agreed=s.get("agreed", True),
            )
            if isinstance(s, dict)
            else s
            for s in stories_raw
        ]
        return cls(
            date=data.get("date", ""),
            episode_number=data.get("episode_number", 0),
            stories=stories,
            predictions=data.get("predictions", []),
            key_themes=data.get("key_themes", []),
            story_to_watch=data.get("story_to_watch", ""),
            title=data.get("title", ""),
        )


@dataclass
class PipelineState:
    episode_count: int = 0
    episodes: list[EpisodeSummary] = field(default_factory=list)

    def to_dict(self) -> dict:
        return dataclasses.asdict(self)

    @classmethod
    def from_dict(cls, data: dict) -> PipelineState:
        episodes_raw = data.get("episodes", [])
        episodes = [
            EpisodeSummary.from_dict(ep) if isinstance(ep, dict) else ep
            for ep in episodes_raw
        ]
        return cls(
            episode_count=data.get("episode_count", 0),
            episodes=episodes,
        )


class SourceModule(Protocol):
    def collect(self) -> list[Story]: ...
