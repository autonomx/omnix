"""Mechanical source chunks for tests.rpg.autoplay_llm_campaign.

N117.4 keeps the public script path stable while moving the large historical
implementation into bounded source fragments. The loader in
``autoplay_llm_campaign.py`` concatenates and compiles these fragments as one
module so split boundaries do not change Python semantics.
"""

from __future__ import annotations

CHUNK_COUNT = 30
MAX_CHUNK_LINES = 925

__all__ = ["CHUNK_COUNT", "MAX_CHUNK_LINES"]
