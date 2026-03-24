import json
import os
from typing import Dict, Optional


class CharacterVoiceMemory:
    """
    Persistent voice identity store for a single book.

    Saves a JSON file at ``books/<book_id>/voice_profiles.json`` so the same
    character always receives the same voice regardless of which segment is
    being processed, across editing sessions.

    Character names are stored and looked up in a normalised form
    (lower-cased, stripped) so that "Narrator", "narrator" and " Narrator "
    all map to the same profile.

    Schema example::

        {
            "narrator": {"voice": "deep_male", "emotion_style": "calm"},
            "alice":    {"voice": "young_female", "emotion_style": "curious"},
            "rabbit":   {"voice": "fast_male",   "emotion_style": "nervous"}
        }
    """

    def __init__(self, book_id: str, base_dir: str = "books") -> None:
        self.book_id = book_id
        self._path = os.path.join(base_dir, book_id, "voice_profiles.json")
        self._profiles: Dict[str, Dict] = self._load()

    # ------------------------------------------------------------------
    # Name normalisation
    # ------------------------------------------------------------------

    @staticmethod
    def _normalize(name: str) -> str:
        """Return a canonical key for *name* (lower-cased and stripped)."""
        return name.lower().strip()

    # ------------------------------------------------------------------
    # Persistence
    # ------------------------------------------------------------------

    def _load(self) -> Dict[str, Dict]:
        if os.path.exists(self._path):
            try:
                with open(self._path, "r", encoding="utf-8") as fh:
                    data = json.load(fh)
                    if isinstance(data, dict):
                        # Normalise any mixed-case keys from older saves
                        return {self._normalize(k): v for k, v in data.items()}
            except (json.JSONDecodeError, OSError):
                pass
        return {}

    def save(self) -> None:
        """Persist all profiles to disk."""
        os.makedirs(os.path.dirname(self._path), exist_ok=True)
        with open(self._path, "w", encoding="utf-8") as fh:
            json.dump(self._profiles, fh, indent=2)

    # ------------------------------------------------------------------
    # Profile access
    # ------------------------------------------------------------------

    def get_voice(self, character: str) -> Optional[str]:
        """Return the persisted voice identifier for *character*, or None."""
        profile = self._profiles.get(self._normalize(character))
        return profile.get("voice") if profile else None

    def get_profile(self, character: str) -> Optional[Dict]:
        """Return the full profile dict for *character*, or None."""
        return self._profiles.get(self._normalize(character))

    def set_voice(self, character: str, voice: str,
                  emotion_style: str = "default") -> None:
        """Assign *voice* to *character* and persist immediately."""
        self._profiles[self._normalize(character)] = {
            "voice": voice,
            "emotion_style": emotion_style,
        }
        self.save()

    def update_profile(self, character: str, profile: Dict) -> None:
        """Merge *profile* dict into the stored profile and persist."""
        key = self._normalize(character)
        existing = self._profiles.get(key, {})
        existing.update(profile)
        self._profiles[key] = existing
        self.save()

    def remove(self, character: str) -> None:
        """Remove a character profile and persist."""
        self._profiles.pop(self._normalize(character), None)
        self.save()

    def all_profiles(self) -> Dict[str, Dict]:
        """Return a copy of all stored profiles."""
        return dict(self._profiles)

    def has_character(self, character: str) -> bool:
        return self._normalize(character) in self._profiles

    def __len__(self) -> int:
        return len(self._profiles)
