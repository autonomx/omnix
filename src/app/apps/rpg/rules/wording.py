"""How the rules' lines word what the world names (the playtest: "Orik Stonewake offers A night's lodging")."""
from __future__ import annotations

import re

_ARTICLE = re.compile(r"^(A|An|The|Some)\b")


def in_sentence(label: str) -> str:
    """A label as it reads inside a sentence: an article the world capitalized for a list ("A night's lodging") is
    lowered; a name ("Healing Potion") is kept as written."""
    return _ARTICLE.sub(lambda match: match.group(1).lower(), label.strip(), count=1)


__all__ = ["in_sentence"]
