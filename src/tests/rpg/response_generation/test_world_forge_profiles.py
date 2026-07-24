import pytest

from app.rpg.session.genesis.world_forge_profiles import (
    DomainDefinition,
    DomainTargetRange,
    FieldDefinition,
    GenreProfile,
    GenreProfileValidationError,
    LaunchRequirements,
)


def _valid_profile() -> GenreProfile:
    return GenreProfile(
        profile_id="post_apocalyptic",
        version=1,
        display_name="Post-apocalyptic",
        aliases=("wasteland",),
        domains=(
            DomainDefinition(
                domain_id="setting",
                title="Setting Rules",
                entity_kind="setting_rule",
                required_before_launch=True,
                semantic_roles=("starting_context",),
                fields=(FieldDefinition("name", "string", required=True),),
            ),
            DomainDefinition(
                domain_id="factions",
                title="Factions",
                entity_kind="faction",
                dependencies=("setting",),
                required_before_launch=True,
                semantic_roles=("initial_conflict",),
                fields=(
                    FieldDefinition("name", "string", required=True),
                    FieldDefinition(
                        "rival_ids",
                        "entity_ref_list",
                        allowed_target_domains=("factions",),
                    ),
                ),
                target_range=DomainTargetRange((2, 3), (4, 6), (7, 10)),
            ),
            DomainDefinition(
                domain_id="actors",
                title="Actors",
                entity_kind="actor",
                dependencies=("factions",),
                required_before_launch=True,
                semantic_roles=("initial_actors",),
                fields=(
                    FieldDefinition("name", "string", required=True),
                    FieldDefinition(
                        "faction_id",
                        "entity_ref",
                        allowed_target_domains=("factions",),
                    ),
                ),
            ),
        ),
        launch_requirements=LaunchRequirements(
            required_domain_ids=("setting", "factions", "actors"),
        ),
    )


def test_valid_profile_has_deterministic_hash() -> None:
    profile = _valid_profile().require_valid()
    assert profile.content_hash.startswith("sha256:")
    assert profile.content_hash == _valid_profile().content_hash
    assert profile.domain_map()["factions"].target_range.target("standard") == 5


def test_unknown_dependency_rejects_profile() -> None:
    profile = GenreProfile(
        profile_id="broken",
        version=1,
        display_name="Broken",
        domains=(
            DomainDefinition(
                domain_id="actors",
                title="Actors",
                entity_kind="actor",
                dependencies=("missing",),
                semantic_roles=("starting_context", "initial_actors", "initial_conflict"),
            ),
        ),
    )
    with pytest.raises(GenreProfileValidationError) as raised:
        profile.require_valid()
    assert any(issue.code == "unknown_domain_dependency" for issue in raised.value.issues)


def test_dependency_cycle_rejects_profile() -> None:
    profile = GenreProfile(
        profile_id="cycle",
        version=1,
        display_name="Cycle",
        domains=(
            DomainDefinition(
                "a",
                "A",
                "a",
                dependencies=("b",),
                semantic_roles=("starting_context", "initial_actors"),
            ),
            DomainDefinition(
                "b",
                "B",
                "b",
                dependencies=("a",),
                semantic_roles=("initial_conflict",),
            ),
        ),
    )
    assert any(issue.code == "domain_dependency_cycle" for issue in profile.validate())


def test_reference_targets_must_exist() -> None:
    profile = _valid_profile()
    actors = DomainDefinition(
        domain_id="actors",
        title="Actors",
        entity_kind="actor",
        dependencies=("factions",),
        semantic_roles=("initial_actors",),
        fields=(
            FieldDefinition(
                "ship_id",
                "entity_ref",
                allowed_target_domains=("ships",),
            ),
        ),
    )
    broken = GenreProfile(
        **{**profile.__dict__, "domains": (*profile.domains[:-1], actors)}
    )
    assert any(issue.code == "unknown_reference_target" for issue in broken.validate())


def test_launch_semantic_roles_are_required() -> None:
    profile = GenreProfile(
        profile_id="thin",
        version=1,
        display_name="Thin",
        domains=(DomainDefinition("setting", "Setting", "setting"),),
    )
    codes = {issue.code for issue in profile.validate()}
    assert "missing_launch_semantic_role" in codes
