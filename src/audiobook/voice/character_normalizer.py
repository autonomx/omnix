import re
from typing import Dict, List, Optional


class CharacterNormalizer:
    """
    Maps character name aliases to a canonical form so that "Mr. Darcy",
    "Darcy", and "Fitzwilliam Darcy" are all treated as the same character.

    Usage::

        normalizer = CharacterNormalizer()
        # Seed with explicit aliases if known
        normalizer.add_alias("Mr. Darcy", "Darcy")
        normalizer.add_alias("Fitzwilliam Darcy", "Darcy")

        name = normalizer.normalize("Mr. Darcy")  # → "Darcy"

    The normalizer also applies a set of automatic heuristics:

    * Strips honorifics (Mr., Mrs., Dr., …) and compares the remainder.
    * Treats "FirstName LastName" and "FirstName" as the same character when
      "FirstName" already exists in the seen-name registry.
    """

    _HONORIFICS = re.compile(
        r'^\s*(mr\.?|mrs\.?|ms\.?|miss|dr\.?|prof\.?|sir|lady|lord'
        r'|captain|cap\.?|sergeant|sgt\.?|officer|detective)\s+',
        re.IGNORECASE,
    )

    def __init__(self, aliases: Optional[Dict[str, str]] = None) -> None:
        # explicit alias map: raw_name → canonical_name
        self._aliases: Dict[str, str] = {}
        # tracks all canonical names seen so far
        self._canonical_names: List[str] = []

        if aliases:
            for raw, canonical in aliases.items():
                self.add_alias(raw, canonical)

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def add_alias(self, raw: str, canonical: str) -> None:
        """Register an explicit alias."""
        self._aliases[raw.strip()] = canonical.strip()
        if canonical not in self._canonical_names:
            self._canonical_names.append(canonical)

    def normalize(self, name: str) -> str:
        """
        Return the canonical form of *name*.

        Lookup order:
        1. Explicit alias map.
        2. Strip honorifics and retry alias map.
        3. First-name match against already-seen canonical names.
        4. Return the stripped name as the canonical form (and remember it).
        """
        name = name.strip()
        if not name:
            return name

        # 1. Explicit alias
        if name in self._aliases:
            return self._aliases[name]

        # 2. Strip honorifics and check again
        stripped = self._HONORIFICS.sub("", name).strip()
        if stripped != name and stripped in self._aliases:
            self._aliases[name] = self._aliases[stripped]
            return self._aliases[stripped]

        # 3. First-name heuristic: if "FirstName LastName", check if "FirstName" known
        parts = stripped.split()
        if len(parts) > 1:
            first = parts[0]
            for canonical in self._canonical_names:
                if canonical.split()[0].lower() == first.lower():
                    self._aliases[name] = canonical
                    return canonical

        # 4. Register as new canonical
        canonical = stripped if stripped else name
        if canonical not in self._canonical_names:
            self._canonical_names.append(canonical)
        self._aliases[name] = canonical
        return canonical

    def normalize_segment(self, segment: Dict) -> Dict:
        """Return a copy of *segment* with the speaker name normalised."""
        result = dict(segment)
        result["speaker"] = self.normalize(segment.get("speaker", ""))
        return result

    def normalize_script(self, script: List[Dict]) -> List[Dict]:
        """Normalize all speaker names in a flat script list."""
        return [self.normalize_segment(line) for line in script]
