import json
import re
from typing import List, Dict, Optional, Callable

_CHARACTER_PROMPT = """Extract all character names that appear in this story text.

Return ONLY a JSON object in this exact format:
{{"characters": ["Name1", "Name2", "Name3"]}}

Rules:
- Include all named characters and the Narrator if present.
- Do not include pronouns or generic terms like "the man".
- If no named characters exist, return {{"characters": ["Narrator"]}}.

Text:
{text}
"""


class CharacterExtractor:
    """Extracts character names from a structured script or raw text."""

    def __init__(self, llm_fn: Optional[Callable[[str], str]] = None) -> None:
        self._llm = llm_fn

    def extract(self, segments: List[Dict]) -> List[Dict]:
        """Return a deduplicated list of character dicts from script segments.

        Each dict has: {"id": str, "name": str}
        """
        seen: set = set()
        characters: List[Dict] = []

        for seg in segments:
            speaker = seg.get("speaker", "")
            if not speaker:
                continue
            key = speaker.lower().strip()
            if key not in seen:
                seen.add(key)
                characters.append({
                    "id": re.sub(r'\W+', '_', key),
                    "name": speaker.strip(),
                })

        return characters

    def extract_from_text(self, text: str) -> List[str]:
        """Return a flat list of character names extracted from raw *text*.

        Uses the LLM when available, falling back to a regex heuristic.
        """
        if self._llm:
            try:
                return self._llm_extract(text)
            except Exception:
                pass
        return self._regex_extract(text)

    # ------------------------------------------------------------------
    # Internals
    # ------------------------------------------------------------------

    def _llm_extract(self, text: str) -> List[str]:
        # Use only a reasonable sample to keep the prompt short
        sample = text[:3000]
        prompt = _CHARACTER_PROMPT.format(text=sample)
        raw = self._llm(prompt)  # type: ignore[misc]

        match = re.search(r'\{.*\}', raw, re.DOTALL)
        if match:
            data = json.loads(match.group())
            names = data.get("characters", [])
            if isinstance(names, list):
                return [str(n).strip() for n in names if n]

        return []

    def _regex_extract(self, text: str) -> List[str]:
        """Heuristic fallback: collect capitalised words that follow speech verbs."""
        verbs = r'(?:said|asked|replied|whispered|shouted|murmured|answered|thought)'
        pattern = re.compile(
            r'([A-Z][A-Za-z\'\-]+)\s+' + verbs, re.MULTILINE
        )
        names = list({m.group(1) for m in pattern.finditer(text)})

        # Also pick up "Name:" format
        colon_pattern = re.compile(r'^([A-Z][A-Za-z\'\-]+)\s*:', re.MULTILINE)
        names += list({m.group(1) for m in colon_pattern.finditer(text)})

        return list(dict.fromkeys(names))  # deduplicate, preserve order
