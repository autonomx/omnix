import hashlib
from typing import Dict, List, Optional

from audiobook.voice.character_voice_memory import CharacterVoiceMemory
from audiobook.voice.character_normalizer import CharacterNormalizer

_DEFAULT_VOICE_MAP: Dict[str, str] = {
    "narrator": "deep_male",
    "queen": "royal_female",
    "king": "deep_male",
    "alice": "young_female",
    "rabbit": "fast_male",
    "witch": "old_female",
    "wizard": "old_male",
    "child": "young_female",
    "boy": "young_male",
    "girl": "young_female",
}


class VoiceAssignment:
    """Maps characters to TTS voice identifiers with persistent memory.

    Lookup order for any character:
    1. ``CharacterVoiceMemory`` (persisted across sessions / segments).
    2. Keyword heuristics (narrator → deep_male, etc.).
    3. Deterministic hash over the available voices list.
    4. Fallback literal ``"neutral_voice"``.

    New assignments are saved to memory immediately so they remain
    consistent for the rest of the book.
    """

    def __init__(
        self,
        available_voices: Optional[List[str]] = None,
        memory: Optional[CharacterVoiceMemory] = None,
        normalizer: Optional[CharacterNormalizer] = None,
    ) -> None:
        self._available = available_voices or []
        self._memory = memory
        self._normalizer = normalizer or CharacterNormalizer()

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def assign(self, characters: List[str]) -> Dict[str, str]:
        """Return a mapping of character name → voice identifier."""
        return {char: self.get_voice(char) for char in characters}

    def get_voice(self, character: str) -> str:
        """Return the voice for *character*, persisting a new assignment if needed."""
        canonical = self._normalizer.normalize(character)

        # 1. Check persistent memory
        if self._memory is not None:
            voice = self._memory.get_voice(canonical)
            if voice:
                return voice

        # 2. Derive a new voice
        voice = self._derive_voice(canonical)

        # 3. Persist so the same character always gets this voice
        if self._memory is not None:
            self._memory.set_voice(canonical, voice)

        return voice

    def override_voice(self, character: str, voice: str,
                       emotion_style: str = "default") -> None:
        """Manually assign *voice* to *character* and persist."""
        canonical = self._normalizer.normalize(character)
        if self._memory is not None:
            self._memory.set_voice(canonical, voice, emotion_style)

    # ------------------------------------------------------------------
    # Internals
    # ------------------------------------------------------------------

    def _derive_voice(self, character: str) -> str:
        lower = character.lower().strip()

        # Keyword heuristics
        for keyword, voice in _DEFAULT_VOICE_MAP.items():
            if keyword in lower:
                return voice

        # Hash-deterministic selection from real available voices
        if self._available:
            idx = int(hashlib.md5(lower.encode()).hexdigest(), 16) % len(self._available)
            return self._available[idx]

        return "neutral_voice"
