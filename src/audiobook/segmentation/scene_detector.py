import re
from typing import List, Dict


class SceneDetector:
    """Detects scene boundaries within segmented text."""

    SCENE_BREAK_PATTERN = re.compile(
        r'(?:^\s*[\*\-]{3,}\s*$|^\s*#{1,3}\s+\w|chapter\s+\w+)',
        re.IGNORECASE | re.MULTILINE,
    )

    def detect(self, segments: List[str]) -> List[Dict]:
        """Group segments into scenes by detecting scene-break markers.

        Returns a list of scene dicts:
            {"scene_id": int, "segments": [str, ...]}
        """
        scenes: List[Dict] = []
        current_scene_segs: List[str] = []
        scene_id = 1

        for seg in segments:
            if self.SCENE_BREAK_PATTERN.search(seg) and current_scene_segs:
                scenes.append({"scene_id": scene_id, "segments": current_scene_segs})
                scene_id += 1
                current_scene_segs = [seg]
            else:
                current_scene_segs.append(seg)

        if current_scene_segs:
            scenes.append({"scene_id": scene_id, "segments": current_scene_segs})

        return scenes if scenes else [{"scene_id": 1, "segments": segments}]
