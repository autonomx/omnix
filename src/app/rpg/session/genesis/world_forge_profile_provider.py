"""Compatibility exports for the live genre-profile provider boundary."""
from __future__ import annotations

from app.rpg_world_forge_profile_provider import (
    GenreProfileProposalResponse,
    ProfileDomainResponse,
    ProfileFieldResponse,
    ProfileTargetRangeResponse,
    ProviderGenreProfileGenerator,
    build_genre_profile_generator_from_settings,
    profile_from_proposal,
)

__all__ = [
    "GenreProfileProposalResponse",
    "ProfileDomainResponse",
    "ProfileFieldResponse",
    "ProfileTargetRangeResponse",
    "ProviderGenreProfileGenerator",
    "build_genre_profile_generator_from_settings",
    "profile_from_proposal",
]
