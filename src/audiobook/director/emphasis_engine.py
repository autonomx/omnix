import re
from typing import Dict, List


class EmphasisEngine:
    """Detects words that should receive vocal emphasis."""

    KEYWORDS: List[str] = [
        "never", "always", "late", "stop", "run", "danger",
        "help", "now", "suddenly", "immediately", "must",
        "only", "alone", "dead", "alive", "free", "trapped",
    ]

    def detect(self, line: Dict) -> List[str]:
        """Return a list of emphasis words found in the line's text."""
        text = line.get("text", "").lower()
        found: List[str] = []
        for word in self.KEYWORDS:
            # Match whole word
            if re.search(r'\b' + re.escape(word) + r'\b', text):
                found.append(word)
        return found
