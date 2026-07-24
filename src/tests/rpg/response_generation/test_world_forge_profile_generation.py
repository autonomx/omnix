from app.rpg.session.genesis.world_forge_profile_binding import (
    bind_world_genre_profile_metadata,
    genre_profile_from_payload,
    resolve_bound_world_genre_profile,
)
from app.rpg.session.genesis.world_forge_profile_generation import (
    GenreProfileRegistry,
    HeuristicWorldLocalProfileGenerator,
    normalize_genre_key,
    resolve_or_generate_genre_profile,
)


def test_known_genre_resolves_registry_profile() -> None:
    resolution = resolve_or_generate_genre_profile(
        genre="Fallout style",
        description="A retro-futuristic nuclear wasteland.",
    )
    assert resolution.generated is False
    assert resolution.profile.profile_id == "post_apocalyptic"
    assert "ruins" in resolution.profile.domain_map()
    assert "spells" not in resolution.profile.domain_map()


def test_known_aliases_resolve_same_profile_hash() -> None:
    first = resolve_or_generate_genre_profile(genre="wasteland")
    second = resolve_or_generate_genre_profile(genre="post apocalypse")
    assert first.profile.content_hash == second.profile.content_hash


def test_unknown_genre_generates_valid_world_local_profile() -> None:
    resolution = resolve_or_generate_genre_profile(
        genre="Victorian underwater biopunk romantic tragedy",
        description="Sentient architecture grows around a drowned imperial court.",
        campaign_mode="political_mystery",
        registry=GenreProfileRegistry(),
    )
    assert resolution.generated is True
    assert resolution.source == "generated_world_local"
    assert resolution.profile.scope == "world_local"
    assert resolution.profile.validate() == ()
    assert "genre_elements" in resolution.profile.domain_map()
    assert resolution.profile.provenance["campaign_mode"] == "political_mystery"


def test_unknown_profile_is_not_automatically_registered() -> None:
    registry = GenreProfileRegistry()
    resolution = resolve_or_generate_genre_profile(
        genre="dream courtroom horror",
        registry=registry,
    )
    assert resolution.generated is True
    assert registry.resolve("dream courtroom horror") is None


def test_genre_normalization_avoids_duplicate_wording_profiles() -> None:
    assert normalize_genre_key("Cyber-Punk Noir") == "cyber_punk_noir"
    assert normalize_genre_key("  Cyber punk  noir ") == "cyber_punk_noir"


def test_heuristic_generator_records_world_specific_guidance() -> None:
    profile = HeuristicWorldLocalProfileGenerator().generate_profile(
        genre="clockwork pastoral",
        description="Villages migrate on mechanical roots.",
        campaign_mode="travelling_sandbox",
    )
    guidance = profile.domain_map()["genre_elements"].generation_guidance
    assert guidance["requested_genre"] == "clockwork pastoral"
    assert "mechanical roots" in guidance["description"]


def test_world_metadata_pins_and_restores_exact_cyberpunk_profile() -> None:
    metadata = bind_world_genre_profile_metadata(
        {"campaign_mode": "persistent_living_world"},
        genre="cyberpunk",
        description="A corporate neon sprawl.",
    )
    payload = metadata["resolved_genre_profile"]
    restored = genre_profile_from_payload(payload)
    resolution = resolve_bound_world_genre_profile(
        {
            "genre": "cyberpunk",
            "description": "This description can change later.",
            "metadata": metadata,
        }
    )

    assert restored.content_hash == metadata["resolved_profile_hash"]
    assert resolution.source == "world_metadata_binding"
    assert resolution.profile.content_hash == restored.content_hash
    assert {"networks", "augmentations"}.issubset(
        resolution.profile.domain_map()
    )
    assert "spells" not in resolution.profile.domain_map()
