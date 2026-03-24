from typing import Dict, List, Optional, Tuple

_SFX_RULES: List[Tuple[str, str]] = [
    ("door open", "door_open"),
    ("door closed", "door_close"),
    ("door slam", "door_slam"),
    ("thunder", "thunder"),
    ("lightning", "lightning"),
    ("footstep", "footsteps"),
    ("rain", "rain"),
    ("wind", "wind"),
    ("fire", "fire_crackle"),
    ("horse", "horse_gallop"),
    ("sword", "sword_clash"),
    ("arrow", "arrow_whoosh"),
    ("crowd", "crowd_murmur"),
    ("bell", "bell_toll"),
    ("music", "ambient_music"),
    ("forest", "forest_ambience"),
    ("ocean", "ocean_waves"),
    ("storm", "rain"),
    ("battle", "battle_music"),
]


class SFXEngine:
    """Maps descriptive text cues to sound-effect identifiers."""

    def detect(self, line: Dict) -> Optional[str]:
        """Return an SFX identifier if the line text contains a known cue."""
        text = line.get("text", "").lower()
        for phrase, sfx_id in _SFX_RULES:
            if phrase in text:
                return sfx_id
        return None
