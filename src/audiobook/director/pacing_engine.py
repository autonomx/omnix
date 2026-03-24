from typing import Dict


class PacingEngine:
    """Determines narration pace and pause timing for each script line."""

    LONG_LINE_THRESHOLD = 200

    def decide(self, line: Dict, scene_mood: str = "calm") -> str:
        """Return a pace string: 'fast', 'slow', or 'normal'."""
        text = line.get("text", "")

        if "!" in text:
            return "fast"

        if scene_mood == "suspense":
            return "slow"

        if len(text) > self.LONG_LINE_THRESHOLD:
            return "slow"

        # Dialogue lines are normal pace; narration can be slow
        if line.get("speaker", "").lower() == "narrator" and len(text) > 80:
            return "slow"

        return "normal"

    def pause(self, line: Dict) -> float:
        """Return pause duration (seconds) after the line."""
        text = line.get("text", "").rstrip()

        if text.endswith("?"):
            return 0.5

        if text.endswith("!"):
            return 0.3

        if text.endswith("..."):
            return 0.6

        return 0.2
