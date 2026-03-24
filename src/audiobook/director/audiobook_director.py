from typing import List, Dict, Optional, Callable

from audiobook.constants import NARRATOR
from audiobook.director.pacing_engine import PacingEngine
from audiobook.director.emphasis_engine import EmphasisEngine
from audiobook.director.scene_mood_engine import SceneMoodEngine
from audiobook.director.sfx_engine import SFXEngine
from audiobook.ai.emotion_detector import EmotionDetector


class AudiobookDirector:
    """
    Sits between the AI structuring service and the TTS engine.

    Takes a list of raw script lines and produces fully directed lines with:
      - pacing decisions
      - pause timings
      - emphasis words
      - optional SFX cues
      - emotion tags
      - scene mood context
    """

    def __init__(self, llm_fn: Optional[Callable[[str], str]] = None) -> None:
        self.pacing = PacingEngine()
        self.emphasis = EmphasisEngine()
        self.scene = SceneMoodEngine(llm_fn=llm_fn)
        self.sfx = SFXEngine()
        self.emotion = EmotionDetector(llm_fn=llm_fn)

    def direct(self, script: List[Dict]) -> List[Dict]:
        """
        Direct a flat list of script lines.

        Args:
            script: List of dicts with at least {"speaker": str, "text": str}.

        Returns:
            List of fully directed dicts.
        """
        if not script:
            return []

        scene_mood = self.scene.detect(script)
        emotions = self.emotion.detect_batch(script)

        directed: List[Dict] = []
        for i, line in enumerate(script):
            emotion = emotions[i] if i < len(emotions) else "neutral"
            # Preserve pre-existing emotion from AI structuring if present
            emotion = line.get("emotion") or emotion

            pace = self.pacing.decide(line, scene_mood)
            emphasis = self.emphasis.detect(line)
            sfx = self.sfx.detect(line)
            pause_after = self.pacing.pause(line)

            directed.append({
                "speaker": line.get("speaker", NARRATOR),
                "text": line.get("text", ""),
                "emotion": emotion,
                "pace": pace,
                "pause_before": line.get("pause_before", 0.0),
                "pause_after": pause_after,
                "emphasis": emphasis,
                "sfx": sfx,
                "voice": line.get("voice"),
            })

        return directed

    def direct_scene(self, scene: Dict) -> Dict:
        """Direct a single scene dict (with 'script' key)."""
        directed_lines = self.direct(scene.get("script", []))
        return {
            "scene": scene.get("scene", 1),
            "script": directed_lines,
        }

    def direct_full_script(self, structured: Dict) -> Dict:
        """Direct a full structured script produced by AIStructuringService."""
        directed_segments = [
            self.direct_scene(seg)
            for seg in structured.get("segments", [])
        ]
        return {
            "title": structured.get("title", ""),
            "characters": structured.get("characters", []),
            "segments": directed_segments,
        }
