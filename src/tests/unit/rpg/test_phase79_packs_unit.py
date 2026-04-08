"""Phase 7.9 — Adventure Packs / Reusable Modules — Unit Tests.

Covers:
- models: PackMetadata, PackManifest, PackContent, AdventurePack,
          PackValidationIssue, PackValidationResult roundtrips
- schema: normalize_pack_dict, build_empty_pack, namespace_content, collect_pack_ids
- validator: PackValidator duplicate/missing field detection
- merger: PackMerger conflict detection, deterministic merge
- loader: PackLoader seed payload shape
- registry: PackRegistry serialization/deserialization
- exporter: PackExporter output shape
- presenters: PackPresenter output stability
"""

import pytest

from app.rpg.packs.exporter import PackExporter
from app.rpg.packs.loader import PackLoader
from app.rpg.packs.merger import PackMergeConflictError, PackMerger
from app.rpg.packs.models import (
    AdventurePack,
    PackContent,
    PackManifest,
    PackMetadata,
    PackValidationIssue,
    PackValidationResult,
)
from app.rpg.packs.presenters import PackPresenter
from app.rpg.packs.registry import PackRegistry
from app.rpg.packs.schema import (
    build_empty_pack,
    collect_pack_ids,
    namespace_content,
    normalize_pack_dict,
)
from app.rpg.packs.validator import PackValidator

# ======================================================================
# Helper factories
# ======================================================================


def _make_pack(
    pack_id: str = "test_pack",
    title: str = "Test Pack",
    version: str = "1.0.0",
    **content_kwargs,
) -> AdventurePack:
    return AdventurePack(
        metadata=PackMetadata(pack_id=pack_id, title=title, version=version),
        manifest=PackManifest(
            manifest_id=f"{pack_id}_manifest",
            pack_id=pack_id,
            content_version=version,
        ),
        content=PackContent(**content_kwargs),
    )


# ======================================================================
# Model Roundtrip Tests
# ======================================================================


class TestPackMetadata:
    def test_roundtrip(self):
        meta = PackMetadata(
            pack_id="p1",
            title="Pack One",
            version="1.0.0",
            author="Alice",
            description="A test pack",
            tags=["fantasy", "starter"],
            requires_engine_version="7.9",
            metadata={"custom": "value"},
        )
        d = meta.to_dict()
        restored = PackMetadata.from_dict(d)
        assert restored.pack_id == "p1"
        assert restored.title == "Pack One"
        assert restored.version == "1.0.0"
        assert restored.author == "Alice"
        assert restored.tags == ["fantasy", "starter"]
        assert restored.metadata == {"custom": "value"}
        assert restored.to_dict() == d

    def test_defaults(self):
        meta = PackMetadata(pack_id="p", title="T", version="0")
        assert meta.author == ""
        assert meta.tags == []
        assert meta.metadata == {}


class TestPackManifest:
    def test_roundtrip(self):
        manifest = PackManifest(
            manifest_id="m1",
            pack_id="p1",
            content_version="1.0.0",
            dependencies=["base_pack"],
            conflicts=["enemy_pack"],
            namespaces=["ns1"],
            metadata={"k": "v"},
        )
        d = manifest.to_dict()
        restored = PackManifest.from_dict(d)
        assert restored.manifest_id == "m1"
        assert restored.dependencies == ["base_pack"]
        assert restored.conflicts == ["enemy_pack"]
        assert restored.to_dict() == d

    def test_defaults(self):
        m = PackManifest(manifest_id="m", pack_id="p", content_version="1")
        assert m.dependencies == []
        assert m.conflicts == []
        assert m.namespaces == []


class TestPackContent:
    def test_roundtrip(self):
        content = PackContent(
            factions=[{"faction_id": "f1", "name": "Order"}],
            locations=[{"location_id": "l1", "name": "Tavern"}],
            npcs=[{"npc_id": "n1", "name": "Bob"}],
        )
        d = content.to_dict()
        restored = PackContent.from_dict(d)
        assert len(restored.factions) == 1
        assert restored.factions[0]["faction_id"] == "f1"
        assert restored.to_dict() == d

    def test_defaults(self):
        c = PackContent()
        assert c.factions == []
        assert c.locations == []
        assert c.npcs == []
        assert c.threads == []
        assert c.arcs == []
        assert c.social_seeds == []
        assert c.metadata == {}


class TestAdventurePack:
    def test_roundtrip(self):
        pack = _make_pack(
            factions=[{"faction_id": "f1", "name": "Guild"}],
            npcs=[{"npc_id": "n1", "name": "Hero"}],
        )
        d = pack.to_dict()
        restored = AdventurePack.from_dict(d)
        assert restored.metadata.pack_id == "test_pack"
        assert len(restored.content.factions) == 1
        assert restored.to_dict() == d

    def test_from_dict_with_minimal_data(self):
        pack = AdventurePack.from_dict({})
        assert pack.metadata.pack_id == ""
        assert pack.content.factions == []


class TestPackValidationIssue:
    def test_roundtrip(self):
        issue = PackValidationIssue(
            path="metadata.pack_id",
            code="missing_pack_id",
            message="Pack ID is required",
            severity="error",
            metadata={"extra": True},
        )
        d = issue.to_dict()
        restored = PackValidationIssue.from_dict(d)
        assert restored.path == "metadata.pack_id"
        assert restored.code == "missing_pack_id"
        assert restored.to_dict() == d


class TestPackValidationResult:
    def test_empty_is_not_blocking(self):
        result = PackValidationResult()
        assert not result.is_blocking()

    def test_error_is_blocking(self):
        result = PackValidationResult(issues=[
            PackValidationIssue(path="x", code="y", message="z", severity="error"),
        ])
        assert result.is_blocking()

    def test_warning_is_not_blocking(self):
        result = PackValidationResult(issues=[
            PackValidationIssue(path="x", code="y", message="z", severity="warning"),
        ])
        assert not result.is_blocking()

    def test_roundtrip(self):
        result = PackValidationResult(issues=[
            PackValidationIssue(path="a", code="b", message="c"),
        ])
        d = result.to_dict()
        restored = PackValidationResult.from_dict(d)
        assert len(restored.issues) == 1
        assert restored.issues[0].path == "a"


# ======================================================================
# Schema Tests
# ======================================================================


class TestNormalizePackDict:
    def test_fills_missing_sections(self):
        result = normalize_pack_dict({})
        assert "metadata" in result
        assert "manifest" in result
        assert "content" in result
        assert isinstance(result["content"]["factions"], list)

    def test_strips_metadata_strings(self):
        result = normalize_pack_dict({
            "metadata": {"pack_id": "  p1  ", "title": "  T  "},
        })
        assert result["metadata"]["pack_id"] == "p1"
        assert result["metadata"]["title"] == "T"


class TestBuildEmptyPack:
    def test_creates_valid_pack(self):
        pack = build_empty_pack("starter", "Starter Pack", "1.0.0")
        assert pack.metadata.pack_id == "starter"
        assert pack.metadata.title == "Starter Pack"
        assert pack.manifest.pack_id == "starter"
        assert pack.content.factions == []

    def test_validator_passes(self):
        pack = build_empty_pack("s", "S", "1")
        result = PackValidator().validate(pack)
        assert not result.is_blocking()


class TestNamespaceContent:
    def test_prefixes_ids(self):
        pack = _make_pack(
            factions=[{"faction_id": "guild", "name": "G"}],
            npcs=[{"npc_id": "hero", "name": "H"}],
        )
        pack.manifest.namespaces = ["ns1"]
        nsed = namespace_content(pack)
        assert nsed.content.factions[0]["faction_id"] == "ns1:guild"
        assert nsed.content.npcs[0]["npc_id"] == "ns1:hero"

    def test_no_namespace_returns_same(self):
        pack = _make_pack(factions=[{"faction_id": "guild"}])
        result = namespace_content(pack)
        assert result.content.factions[0]["faction_id"] == "guild"

    def test_double_prefix_prevented(self):
        pack = _make_pack(factions=[{"faction_id": "ns1:guild"}])
        pack.manifest.namespaces = ["ns1"]
        nsed = namespace_content(pack)
        assert nsed.content.factions[0]["faction_id"] == "ns1:guild"


class TestCollectPackIds:
    def test_collects_all_types(self):
        pack = _make_pack(
            factions=[{"faction_id": "f1"}],
            locations=[{"location_id": "l1"}],
            npcs=[{"npc_id": "n1"}],
            threads=[{"thread_id": "t1"}],
            arcs=[{"arc_id": "a1"}],
        )
        ids = collect_pack_ids(pack)
        assert ids["factions"] == ["f1"]
        assert ids["locations"] == ["l1"]
        assert ids["npcs"] == ["n1"]
        assert ids["threads"] == ["t1"]
        assert ids["arcs"] == ["a1"]


# ======================================================================
# Validator Tests
# ======================================================================


class TestPackValidator:
    def test_valid_pack_passes(self):
        pack = _make_pack()
        result = PackValidator().validate(pack)
        assert not result.is_blocking()

    def test_missing_pack_id(self):
        pack = _make_pack(pack_id="")
        result = PackValidator().validate(pack)
        assert result.is_blocking()
        codes = [i.code for i in result.issues]
        assert "missing_pack_id" in codes

    def test_missing_title(self):
        pack = _make_pack(title="")
        result = PackValidator().validate(pack)
        assert result.is_blocking()
        codes = [i.code for i in result.issues]
        assert "missing_title" in codes

    def test_missing_version(self):
        pack = _make_pack(version="")
        result = PackValidator().validate(pack)
        assert result.is_blocking()
        codes = [i.code for i in result.issues]
        assert "missing_version" in codes

    def test_rejects_duplicate_ids(self):
        pack = _make_pack(
            factions=[
                {"faction_id": "f1", "name": "A"},
                {"faction_id": "f1", "name": "B"},
            ]
        )
        result = PackValidator().validate(pack)
        assert result.is_blocking()
        codes = [i.code for i in result.issues]
        assert "duplicate_id" in codes

    def test_rejects_duplicate_npc_ids(self):
        pack = _make_pack(
            npcs=[
                {"npc_id": "n1", "name": "A"},
                {"npc_id": "n1", "name": "B"},
            ]
        )
        result = PackValidator().validate(pack)
        assert result.is_blocking()

    def test_rejects_self_conflict(self):
        pack = _make_pack(pack_id="p1")
        pack.manifest.conflicts = ["p1"]
        result = PackValidator().validate(pack)
        assert result.is_blocking()
        codes = [i.code for i in result.issues]
        assert "self_conflict" in codes

    def test_rejects_self_dependency(self):
        pack = _make_pack(pack_id="p1")
        pack.manifest.dependencies = ["p1"]
        result = PackValidator().validate(pack)
        codes = [i.code for i in result.issues]
        assert "self_dependency" in codes

    def test_rejects_dependency_conflict_overlap(self):
        pack = _make_pack(pack_id="p1")
        pack.manifest.dependencies = ["other"]
        pack.manifest.conflicts = ["other"]
        result = PackValidator().validate(pack)
        assert result.is_blocking()
        codes = [i.code for i in result.issues]
        assert "dependency_conflict_overlap" in codes

    def test_rejects_malformed_content_item(self):
        pack = _make_pack()
        pack.content.factions = ["not_a_dict"]
        result = PackValidator().validate(pack)
        assert result.is_blocking()
        codes = [i.code for i in result.issues]
        assert "malformed_content_item" in codes

    def test_warns_on_empty_namespace(self):
        pack = _make_pack()
        pack.manifest.namespaces = [""]
        result = PackValidator().validate(pack)
        codes = [i.code for i in result.issues]
        assert "empty_namespace" in codes

    def test_warns_on_namespace_with_colon(self):
        pack = _make_pack()
        pack.manifest.namespaces = ["ns:bad"]
        result = PackValidator().validate(pack)
        codes = [i.code for i in result.issues]
        assert "invalid_namespace_char" in codes

    def test_pack_id_mismatch_between_metadata_and_manifest(self):
        pack = _make_pack(pack_id="p1")
        pack.manifest.pack_id = "p2"
        result = PackValidator().validate(pack)
        assert result.is_blocking()
        codes = [i.code for i in result.issues]
        assert "pack_id_mismatch" in codes

    def test_missing_manifest_id(self):
        pack = _make_pack()
        pack.manifest.manifest_id = ""
        result = PackValidator().validate(pack)
        assert result.is_blocking()
        codes = [i.code for i in result.issues]
        assert "missing_manifest_id" in codes


# ======================================================================
# Merger Tests
# ======================================================================


class TestPackMerger:
    def test_merge_empty_list(self):
        merged = PackMerger().merge([])
        assert merged.metadata.pack_id == "merged"
        assert merged.content.factions == []

    def test_merge_single_pack(self):
        pack = _make_pack(factions=[{"faction_id": "f1"}])
        merged = PackMerger().merge([pack])
        assert len(merged.content.factions) == 1
        assert merged.content.factions[0]["faction_id"] == "f1"

    def test_merge_two_compatible_packs(self):
        p1 = _make_pack(pack_id="a", factions=[{"faction_id": "f1"}])
        p2 = _make_pack(pack_id="b", factions=[{"faction_id": "f2"}])
        merged = PackMerger().merge([p1, p2])
        faction_ids = [f["faction_id"] for f in merged.content.factions]
        assert "f1" in faction_ids
        assert "f2" in faction_ids

    def test_merger_fails_on_conflicting_duplicate_ids(self):
        p1 = _make_pack(pack_id="a", factions=[{"faction_id": "f1", "name": "A"}])
        p2 = _make_pack(pack_id="b", factions=[{"faction_id": "f1", "name": "B"}])
        with pytest.raises(PackMergeConflictError):
            PackMerger().merge([p1, p2])

    def test_merger_fails_on_declared_conflicts(self):
        p1 = _make_pack(pack_id="a")
        p1.manifest.conflicts = ["b"]
        p2 = _make_pack(pack_id="b")
        with pytest.raises(PackMergeConflictError):
            PackMerger().merge([p1, p2])

    def test_merged_metadata_contains_source_packs(self):
        p1 = _make_pack(pack_id="a")
        p2 = _make_pack(pack_id="b")
        merged = PackMerger().merge([p1, p2])
        assert "a" in merged.metadata.metadata["source_packs"]
        assert "b" in merged.metadata.metadata["source_packs"]

    def test_merged_tags_are_unioned(self):
        p1 = _make_pack(pack_id="a")
        p1.metadata.tags = ["fantasy", "starter"]
        p2 = _make_pack(pack_id="b")
        p2.metadata.tags = ["starter", "advanced"]
        merged = PackMerger().merge([p1, p2])
        assert merged.metadata.tags == ["fantasy", "starter", "advanced"]

    def test_merge_concatenates_non_id_lists(self):
        p1 = _make_pack(pack_id="a", creator_facts=[{"key": "a"}])
        p2 = _make_pack(pack_id="b", creator_facts=[{"key": "b"}])
        merged = PackMerger().merge([p1, p2])
        assert len(merged.content.creator_facts) == 2

    def test_merge_dependencies_unioned(self):
        p1 = _make_pack(pack_id="a")
        p1.manifest.dependencies = ["base"]
        p2 = _make_pack(pack_id="b")
        p2.manifest.dependencies = ["base", "extra"]
        merged = PackMerger().merge([p1, p2])
        assert "base" in merged.manifest.dependencies
        assert "extra" in merged.manifest.dependencies


# ======================================================================
# Loader Tests
# ======================================================================


class TestPackLoader:
    def test_loader_returns_seed_payload_shape(self):
        pack = _make_pack(
            factions=[{"faction_id": "f1", "name": "G"}],
            npcs=[{"npc_id": "n1", "name": "H"}],
            arcs=[{"arc_id": "a1", "title": "Main"}],
            social_seeds=[{"type": "reputation"}],
        )
        payload = PackLoader().load(pack)
        assert "creator_seed" in payload
        assert "arc_seed" in payload
        assert "social_seed" in payload
        assert "memory_seed" in payload

    def test_creator_seed_contains_factions_and_npcs(self):
        pack = _make_pack(
            factions=[{"faction_id": "f1"}],
            npcs=[{"npc_id": "n1"}],
        )
        payload = PackLoader().load(pack)
        assert len(payload["creator_seed"]["factions"]) == 1
        assert len(payload["creator_seed"]["npcs"]) == 1

    def test_arc_seed_contains_arcs(self):
        pack = _make_pack(arcs=[{"arc_id": "a1"}])
        payload = PackLoader().load(pack)
        assert len(payload["arc_seed"]["arcs"]) == 1

    def test_social_seed_contains_seeds(self):
        pack = _make_pack(social_seeds=[{"type": "rumor"}])
        payload = PackLoader().load(pack)
        assert len(payload["social_seed"]["social_seeds"]) == 1

    def test_memory_seed_contains_locations(self):
        pack = _make_pack(locations=[{"location_id": "l1"}])
        payload = PackLoader().load(pack)
        assert len(payload["memory_seed"]["locations"]) == 1

    def test_load_many_merges(self):
        p1 = _make_pack(pack_id="a", factions=[{"faction_id": "f1"}])
        p2 = _make_pack(pack_id="b", factions=[{"faction_id": "f2"}])
        payload = PackLoader().load_many([p1, p2])
        assert len(payload["creator_seed"]["factions"]) == 2

    def test_load_many_empty(self):
        payload = PackLoader().load_many([])
        assert payload["creator_seed"] == {}

    def test_payload_has_pack_id(self):
        pack = _make_pack(pack_id="my_pack")
        payload = PackLoader().load(pack)
        assert payload["creator_seed"]["pack_id"] == "my_pack"


# ======================================================================
# Registry Tests
# ======================================================================


class TestPackRegistry:
    def test_register_and_get(self):
        registry = PackRegistry()
        pack = _make_pack(pack_id="p1")
        registry.register(pack)
        assert registry.get("p1") is pack

    def test_get_missing_returns_none(self):
        registry = PackRegistry()
        assert registry.get("missing") is None

    def test_remove(self):
        registry = PackRegistry()
        pack = _make_pack(pack_id="p1")
        registry.register(pack)
        registry.remove("p1")
        assert registry.get("p1") is None

    def test_list_packs_sorted(self):
        registry = PackRegistry()
        registry.register(_make_pack(pack_id="b"))
        registry.register(_make_pack(pack_id="a"))
        packs = registry.list_packs()
        assert packs[0].metadata.pack_id == "a"
        assert packs[1].metadata.pack_id == "b"

    def test_serialization_roundtrip(self):
        registry = PackRegistry()
        pack = _make_pack(
            pack_id="p1",
            factions=[{"faction_id": "f1", "name": "G"}],
        )
        registry.register(pack)
        data = registry.serialize_state()
        new_registry = PackRegistry()
        new_registry.deserialize_state(data)
        restored = new_registry.get("p1")
        assert restored is not None
        assert restored.metadata.pack_id == "p1"
        assert len(restored.content.factions) == 1

    def test_serialize_empty(self):
        registry = PackRegistry()
        data = registry.serialize_state()
        assert data == {"packs": {}}

    def test_remove_nonexistent_is_safe(self):
        registry = PackRegistry()
        registry.remove("nonexistent")  # should not raise


# ======================================================================
# Exporter Tests
# ======================================================================


class TestPackExporter:
    def test_export_minimal(self):
        pack = PackExporter().export_minimal("Title", "1.0", "p1")
        assert pack.metadata.pack_id == "p1"
        assert pack.metadata.title == "Title"
        assert pack.content.factions == []

    def test_export_from_creator_state_dict(self):
        state = {
            "facts": {"f1": {"key": "f1", "value": "test"}},
            "setup": {
                "factions": [{"faction_id": "f1", "name": "G"}],
                "locations": [{"location_id": "l1", "name": "T"}],
                "npc_seeds": [{"npc_id": "n1", "name": "H"}],
            },
        }
        pack = PackExporter().export_from_creator_state(
            creator_canon_state=state,
            title="Export",
            version="1.0",
            pack_id="exp1",
        )
        assert pack.metadata.pack_id == "exp1"
        assert len(pack.content.creator_facts) == 1
        assert len(pack.content.factions) == 1
        assert len(pack.content.locations) == 1
        assert len(pack.content.npcs) == 1

    def test_export_from_creator_state_none(self):
        pack = PackExporter().export_from_creator_state(
            creator_canon_state=None,
            title="Empty",
            version="1.0",
            pack_id="e1",
        )
        assert pack.metadata.pack_id == "e1"
        assert pack.content.factions == []

    def test_export_from_current_setup_dict(self):
        setup = {
            "title": "Adventure",
            "genre": "fantasy",
            "setting": "medieval",
            "premise": "A quest",
            "factions": [{"faction_id": "f1"}],
            "npc_seeds": [{"npc_id": "n1"}],
            "pacing": {"style": "balanced"},
        }
        pack = PackExporter().export_from_current_setup(
            setup=setup,
            title="Setup Export",
            version="1.0",
            pack_id="se1",
        )
        assert pack.metadata.pack_id == "se1"
        assert len(pack.content.factions) == 1
        assert len(pack.content.npcs) == 1
        assert len(pack.content.setup_templates) == 1
        assert len(pack.content.pacing_presets) == 1

    def test_exported_pack_validates(self):
        pack = PackExporter().export_minimal("V", "1.0", "v1")
        result = PackValidator().validate(pack)
        assert not result.is_blocking()


# ======================================================================
# Presenter Tests
# ======================================================================


class TestPackPresenter:
    def test_present_pack_list(self):
        packs = [_make_pack(pack_id="p1").to_dict(), _make_pack(pack_id="p2").to_dict()]
        result = PackPresenter().present_pack_list(packs)
        assert result["title"] == "Adventure Packs"
        assert result["count"] == 2
        assert result["items"][0]["pack_id"] == "p1"

    def test_present_pack(self):
        pack = _make_pack(
            pack_id="p1",
            factions=[{"faction_id": "f1"}],
            npcs=[{"npc_id": "n1"}, {"npc_id": "n2"}],
        )
        result = PackPresenter().present_pack(pack.to_dict())
        assert result["pack_id"] == "p1"
        assert result["content_summary"]["factions"] == 1
        assert result["content_summary"]["npcs"] == 2

    def test_present_validation_result(self):
        vr = PackValidationResult(issues=[
            PackValidationIssue(path="a", code="b", message="c"),
        ])
        result = PackPresenter().present_validation_result(vr.to_dict())
        assert result["title"] == "Pack Validation"
        assert result["issue_count"] == 1
        assert result["is_blocking"] is True

    def test_present_load_result(self):
        payload = {
            "creator_seed": {"factions": [1, 2], "npcs": [1]},
            "arc_seed": {"arcs": [1]},
            "social_seed": {},
            "memory_seed": {},
        }
        result = PackPresenter().present_load_result(payload)
        assert result["title"] == "Pack Load Result"
        assert result["section_count"] >= 1

    def test_present_empty_pack_list(self):
        result = PackPresenter().present_pack_list([])
        assert result["count"] == 0
        assert result["items"] == []
