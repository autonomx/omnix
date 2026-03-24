from dataclasses import dataclass, field
from typing import List, Optional


@dataclass
class DirectedLine:
    """A single narration line with full directing metadata."""
    speaker: str
    text: str
    emotion: str = "neutral"
    pace: str = "normal"
    pause_before: float = 0.0
    pause_after: float = 0.2
    emphasis: Optional[List[str]] = None
    sfx: Optional[str] = None
    voice: Optional[str] = None

    def to_dict(self) -> dict:
        return {
            "speaker": self.speaker,
            "text": self.text,
            "emotion": self.emotion,
            "pace": self.pace,
            "pause_before": self.pause_before,
            "pause_after": self.pause_after,
            "emphasis": self.emphasis or [],
            "sfx": self.sfx,
            "voice": self.voice,
        }


@dataclass
class SceneBlock:
    """A scene grouping of directed lines."""
    scene_id: int
    script: List[DirectedLine] = field(default_factory=list)

    def to_dict(self) -> dict:
        return {
            "scene": self.scene_id,
            "script": [line.to_dict() for line in self.script],
        }


@dataclass
class DirectedScript:
    """Full directed audiobook script."""
    title: str = ""
    characters: List[dict] = field(default_factory=list)
    scenes: List[SceneBlock] = field(default_factory=list)

    def to_dict(self) -> dict:
        return {
            "title": self.title,
            "characters": self.characters,
            "segments": [scene.to_dict() for scene in self.scenes],
        }
