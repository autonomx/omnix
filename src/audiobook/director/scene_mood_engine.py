import re
from typing import Callable, Dict, List, Optional

VALID_MOODS = {"calm", "suspense", "action", "romantic", "comedic"}

_KEYWORD_MOODS = [
    ({"run", "chase", "battle", "attack", "fight", "explod"}, "action"),
    ({"shadow", "creak", "dark", "fear", "whisper", "silent", "alone"}, "suspense"),
    ({"love", "heart", "kiss", "embrace", "tender", "dear"}, "romantic"),
    ({"laugh", "joke", "funny", "silly", "chuckle", "grin"}, "comedic"),
]

MOOD_PROMPT = """Detect the overall mood of this scene.

Return ONLY one of these words: calm, suspense, action, romantic, comedic

Text:
{text}
"""


def _keyword_mood(text: str) -> str:
    tl = text.lower()
    for keywords, mood in _KEYWORD_MOODS:
        if any(k in tl for k in keywords):
            return mood
    return "calm"


class SceneMoodEngine:
    """Detects the emotional/dramatic mood of a scene."""

    def __init__(self, llm_fn: Optional[Callable[[str], str]] = None) -> None:
        self._llm = llm_fn

    def detect(self, script: List[Dict]) -> str:
        """Return a mood string for the given list of script lines."""
        sample_text = "\n".join(ln.get("text", "") for ln in script[:5])

        if self._llm:
            try:
                prompt = MOOD_PROMPT.format(text=sample_text)
                result = self._llm(prompt).strip().lower()
                # Extract first valid mood word
                for word in result.split():
                    clean = re.sub(r'\W', '', word)
                    if clean in VALID_MOODS:
                        return clean
            except Exception:
                pass

        return _keyword_mood(sample_text)
