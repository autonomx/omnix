import json
import re
from typing import Dict, List, Optional

VALID_EMOTIONS = {"neutral", "happy", "sad", "angry", "fear", "panic", "whisper", "excited"}

_KEYWORD_EMOTIONS: List[tuple] = [
    ({"wonderful", "great", "laugh", "smile", "joy"}, "happy"),
    ({"amazing", "incredible", "exciting", "wow"}, "excited"),
    ({"sorry", "tears", "weep", "cry", "miss", "lost"}, "sad"),
    ({"angry", "furious", "rage", "hate", "never"}, "angry"),
    ({"whisper", "quietly", "softly", "hush"}, "whisper"),
    ({"help", "run", "danger", "attack", "flee"}, "fear"),
    ({"scream", "shout", "yell", "panic"}, "panic"),
]


def _keyword_emotion(text: str) -> str:
    tl = text.lower()
    for keywords, emotion in _KEYWORD_EMOTIONS:
        if any(k in tl for k in keywords):
            return emotion
    return "neutral"


class EmotionDetector:
    """Detects emotional tone for each line using LLM with keyword fallback."""

    EMOTION_PROMPT = """Detect the emotion for each line of dialogue below.

Valid emotions: neutral, happy, sad, angry, fear, panic, whisper, excited

Return a JSON array with one emotion string per line, in order.
Example: ["neutral","panic","happy"]

Lines:
{lines}
"""

    def __init__(self, llm_fn=None) -> None:
        """
        Args:
            llm_fn: Optional callable(prompt: str) -> str that calls the LLM.
                    If None, keyword-based fallback is used.
        """
        self._llm = llm_fn

    def detect_batch(self, lines: List[Dict]) -> List[str]:
        """Return a list of emotion strings parallel to *lines*."""
        if not lines:
            return []

        if self._llm:
            try:
                return self._llm_detect(lines)
            except Exception:
                pass

        return [_keyword_emotion(ln.get("text", "")) for ln in lines]

    def _llm_detect(self, lines: List[Dict]) -> List[str]:
        numbered = "\n".join(
            f"{i + 1}. [{ln.get('speaker', 'Narrator')}]: {ln.get('text', '')}"
            for i, ln in enumerate(lines)
        )
        prompt = self.EMOTION_PROMPT.format(lines=numbered)
        raw = self._llm(prompt)

        # Extract JSON array from the response
        match = re.search(r'\[.*?\]', raw, re.DOTALL)
        if match:
            emotions = json.loads(match.group())
            # Validate and clamp
            result = []
            for i, em in enumerate(emotions):
                em_clean = str(em).strip().lower()
                result.append(em_clean if em_clean in VALID_EMOTIONS else "neutral")
            # Pad if shorter than lines
            while len(result) < len(lines):
                result.append("neutral")
            return result[:len(lines)]

        return [_keyword_emotion(ln.get("text", "")) for ln in lines]
