"""Ước lượng thời lượng phim từ Storyboard (trước bước audio)."""
from __future__ import annotations

from dataclasses import dataclass, field

from ..schema import Shot, Storyboard
from . import vocab


def count_words(text: str) -> int:
    return len(text.split())


def estimate_shot_seconds(shot: Shot, wps: float = vocab.WORDS_PER_SECOND) -> float:
    """Dùng shot.duration nếu bước audio đã điền; nếu không: max(min_duration, số từ / wps + 0.4)."""
    if shot.duration:
        return shot.duration
    speech = sum(ln.duration or count_words(ln.text) / wps for ln in shot.lines)
    return max(shot.min_duration, speech + vocab.SHOT_PADDING_S if speech else 0.0)


@dataclass
class StoryboardStats:
    shots: int
    characters: int
    locations: int
    words: int
    seconds: float
    shot_seconds: dict[str, float] = field(default_factory=dict)

    @property
    def minutes(self) -> float:
        return self.seconds / 60

    @property
    def avg_shot_seconds(self) -> float:
        return self.seconds / self.shots if self.shots else 0.0

    def summary(self) -> str:
        m, s = divmod(round(self.seconds), 60)
        return (f"{self.shots} shot · {self.characters} nhân vật · {self.locations} địa điểm · "
                f"{self.words} từ · ước tính {m}:{s:02d} (TB {self.avg_shot_seconds:.1f}s/shot)")


def storyboard_stats(sb: Storyboard, wps: float = vocab.WORDS_PER_SECOND) -> StoryboardStats:
    per = {shot.id: round(estimate_shot_seconds(shot, wps), 2) for shot in sb.shots}
    return StoryboardStats(
        shots=len(sb.shots),
        characters=len(sb.characters),
        locations=len(sb.locations),
        words=sum(count_words(ln.text) for s in sb.shots for ln in s.lines),
        seconds=round(sum(per.values()), 2),
        shot_seconds=per,
    )
