"""Comprehensive unit tests for Phase 7.1 Creator Setup UX + Live GM Controls."""

from __future__ import annotations

from dataclasses import asdict

# ---------------------------------------------------------------------------
# Imports under test
# ---------------------------------------------------------------------------
from app.rpg.creator.defaults import (
    apply_adventure_defaults,
    build_setup_template,
    default_content_balance,
    default_pacing_profile,
    default_safety_constraint,
    list_setup_templates,
)
from app.rpg.creator.validation import (
    ValidationIssue,
    ValidationResult,
    validate_adventure_setup_payload,
    validate_setup_balances,
    validate_setup_cross_references,
    validate_setup_ids,
    validate_setup_required_fields,
)
from app.rpg.creator.presenters import CreatorStatePresenter
from app.rpg.creator.schema import (
    AdventureSetup,
    ContentBalance,
    PacingProfile,
    SafetyConstraint,
)
from app.rpg.creator.gm_state import (
    DangerDirective,
    GMDirectiveState,
    PinThreadDirective,
    RevealDirective,
    TargetFactionDirective,
    TargetLocationDirective,
    TargetNPCDirective,
    ToneDirective,
    DIRECTIVE_TYPES,
)
from app.rpg.creator.commands import GMCommandProcessor


# ===================================================================
# helpers
# ===================================================================

def _minimal_setup_data(**overrides) -> dict:
    """Return a minimal valid adventure-setup dict."""
    base = {
        "setup_id": "test_setup",
        "title": "Test Adventure",
        "genre": "fantasy",
        "setting": "A test world",
        "premise": "Testing the system",
    }
    base.update(overrides)
    return base


def _minimal_setup(**overrides) -> AdventureSetup:
    """Return a minimal valid AdventureSetup dataclass."""
    return AdventureSetup.from_dict(_minimal_setup_data(**overrides))


# ===================================================================
# defaults.py tests
# ===================================================================

class TestDefaultPacingProfile:
    def test_returns_pacing_profile(self):
        p = default_pacing_profile()
        assert isinstance(p, PacingProfile)

    def test_default_values(self):
        p = default_pacing_profile()
        assert p.style == "balanced"
        assert p.danger_level == "medium"

    def test_roundtrip(self):
        p = default_pacing_profile()
        d = p.to_dict()
        p2 = PacingProfile.from_dict(d)
        assert p == p2


class TestDefaultSafetyConstraint:
    def test_returns_safety_constraint(self):
        s = default_safety_constraint()
        assert isinstance(s, SafetyConstraint)

    def test_empty_by_default(self):
        s = default_safety_constraint()
        assert s.forbidden_themes == []
        assert s.soft_avoid_themes == []


class TestDefaultContentBalance:
    def test_returns_content_balance(self):
        c = default_content_balance()
        assert isinstance(c, ContentBalance)

    def test_sums_to_one(self):
        c = default_content_balance()
        total = c.mystery + c.combat + c.politics + c.exploration + c.social
        assert abs(total - 1.0) < 0.001


class TestApplyAdventureDefaults:
    def test_fills_missing_pacing(self):
        data = _minimal_setup_data()
        result = apply_adventure_defaults(data)
        assert result["pacing"] is not None
        assert result["pacing"]["style"] == "balanced"

    def test_fills_missing_safety(self):
        data = _minimal_setup_data()
        result = apply_adventure_defaults(data)
        assert result["safety"] is not None

    def test_fills_missing_content_balance(self):
        data = _minimal_setup_data()
        result = apply_adventure_defaults(data)
        assert result["content_balance"] is not None

    def test_does_not_overwrite_existing_pacing(self):
        data = _minimal_setup_data(pacing={"style": "fast", "danger_level": "high",
                                            "mystery_weight": 0.1, "combat_weight": 0.5,
                                            "politics_weight": 0.1, "social_weight": 0.3})
        result = apply_adventure_defaults(data)
        assert result["pacing"]["style"] == "fast"

    def test_fills_empty_lists(self):
        data = _minimal_setup_data()
        result = apply_adventure_defaults(data)
        assert result["hard_rules"] == []
        assert result["factions"] == []
        assert result["npc_seeds"] == []
        assert result["starting_npc_ids"] == []

    def test_preserves_existing_values(self):
        data = _minimal_setup_data(hard_rules=["rule1"])
        result = apply_adventure_defaults(data)
        assert result["hard_rules"] == ["rule1"]


class TestBuildSetupTemplate:
    def test_known_template(self):
        tpl = build_setup_template("fantasy_adventure")
        assert tpl["genre"] == "fantasy"

    def test_unknown_template_raises(self):
        try:
            build_setup_template("nonexistent")
            assert False, "Should have raised ValueError"
        except ValueError as e:
            assert "nonexistent" in str(e)

    def test_all_templates_valid(self):
        for info in list_setup_templates():
            tpl = build_setup_template(info["name"])
            assert "genre" in tpl
            assert "setting" in tpl
            assert "premise" in tpl

    def test_template_returns_copy(self):
        t1 = build_setup_template("fantasy_adventure")
        t2 = build_setup_template("fantasy_adventure")
        t1["genre"] = "modified"
        assert t2["genre"] == "fantasy"


class TestListSetupTemplates:
    def test_returns_list(self):
        templates = list_setup_templates()
        assert isinstance(templates, list)
        assert len(templates) >= 5

    def test_template_shape(self):
        for t in list_setup_templates():
            assert "name" in t
            assert "genre" in t
            assert "mood" in t

    def test_expected_templates_present(self):
        names = {t["name"] for t in list_setup_templates()}
        assert "fantasy_adventure" in names
        assert "political_intrigue" in names
        assert "mystery_noir" in names
        assert "grimdark_survival" in names
        assert "cyberpunk_heist" in names


# ===================================================================
# validation.py tests
# ===================================================================

class TestValidationIssue:
    def test_to_dict(self):
        issue = ValidationIssue(path="title", code="required", message="missing")
        d = issue.to_dict()
        assert d["path"] == "title"
        assert d["code"] == "required"
        assert d["severity"] == "error"

    def test_from_dict(self):
        d = {"path": "x", "code": "y", "message": "z", "severity": "warning"}
        issue = ValidationIssue.from_dict(d)
        assert issue.severity == "warning"

    def test_from_dict_default_severity(self):
        d = {"path": "x", "code": "y", "message": "z"}
        issue = ValidationIssue.from_dict(d)
        assert issue.severity == "error"


class TestValidationResult:
    def test_valid_result(self):
        result = ValidationResult(valid=True, issues=[])
        assert result.valid
        assert result.to_dict()["valid"] is True

    def test_invalid_result(self):
        result = ValidationResult(
            valid=False,
            issues=[ValidationIssue(path="x", code="y", message="z")],
        )
        assert not result.valid
        d = result.to_dict()
        assert len(d["issues"]) == 1

    def test_roundtrip(self):
        result = ValidationResult(
            valid=False,
            issues=[ValidationIssue(path="a", code="b", message="c", severity="warning")],
        )
        d = result.to_dict()
        r2 = ValidationResult.from_dict(d)
        assert r2.valid == result.valid
        assert len(r2.issues) == 1
        assert r2.issues[0].path == "a"


class TestValidateSetupRequiredFields:
    def test_all_present(self):
        issues = validate_setup_required_fields(_minimal_setup_data())
        assert issues == []

    def test_missing_setup_id(self):
        data = _minimal_setup_data(setup_id="")
        issues = validate_setup_required_fields(data)
        assert any(i.path == "setup_id" for i in issues)

    def test_missing_title(self):
        data = _minimal_setup_data(title="")
        issues = validate_setup_required_fields(data)
        assert any(i.path == "title" for i in issues)

    def test_whitespace_only_fails(self):
        data = _minimal_setup_data(genre="   ")
        issues = validate_setup_required_fields(data)
        assert any(i.path == "genre" for i in issues)


class TestValidateSetupIds:
    def test_no_seeds_ok(self):
        issues = validate_setup_ids(_minimal_setup_data())
        assert issues == []

    def test_duplicate_npc_id(self):
        data = _minimal_setup_data(npc_seeds=[
            {"npc_id": "a", "name": "A", "role": "r", "description": "d"},
            {"npc_id": "a", "name": "B", "role": "r", "description": "d"},
        ])
        issues = validate_setup_ids(data)
        assert any(i.code == "duplicate_id" for i in issues)

    def test_duplicate_faction_id(self):
        data = _minimal_setup_data(factions=[
            {"faction_id": "f1", "name": "F1", "description": "d"},
            {"faction_id": "f1", "name": "F2", "description": "d"},
        ])
        issues = validate_setup_ids(data)
        assert any(i.code == "duplicate_id" for i in issues)

    def test_duplicate_location_id(self):
        data = _minimal_setup_data(locations=[
            {"location_id": "l1", "name": "L1", "description": "d"},
            {"location_id": "l1", "name": "L2", "description": "d"},
        ])
        issues = validate_setup_ids(data)
        assert any(i.code == "duplicate_id" for i in issues)

    def test_missing_npc_id(self):
        data = _minimal_setup_data(npc_seeds=[
            {"npc_id": "", "name": "A", "role": "r", "description": "d"},
        ])
        issues = validate_setup_ids(data)
        assert any(i.code == "missing_id" for i in issues)


class TestValidateSetupBalances:
    def test_valid_balance(self):
        data = _minimal_setup_data(content_balance={
            "mystery": 0.2, "combat": 0.2, "politics": 0.2,
            "exploration": 0.2, "social": 0.2,
        })
        issues = validate_setup_balances(data)
        assert issues == []

    def test_no_balance_ok(self):
        issues = validate_setup_balances(_minimal_setup_data())
        assert issues == []

    def test_out_of_range_warning(self):
        data = _minimal_setup_data(content_balance={"mystery": 1.5})
        issues = validate_setup_balances(data)
        assert any(i.code == "out_of_range" for i in issues)

    def test_bad_sum_warning(self):
        data = _minimal_setup_data(content_balance={
            "mystery": 0.5, "combat": 0.5, "politics": 0.5,
            "exploration": 0.5, "social": 0.5,
        })
        issues = validate_setup_balances(data)
        assert any(i.code == "balance_sum" for i in issues)


class TestValidateSetupCrossReferences:
    def test_no_refs_ok(self):
        issues = validate_setup_cross_references(_minimal_setup_data())
        assert issues == []

    def test_dangling_faction_ref(self):
        data = _minimal_setup_data(npc_seeds=[
            {"npc_id": "n1", "name": "N", "role": "r", "description": "d", "faction_id": "nonexistent"},
        ])
        issues = validate_setup_cross_references(data)
        assert any(i.code == "dangling_ref" and "faction" in i.message for i in issues)

    def test_dangling_location_ref(self):
        data = _minimal_setup_data(npc_seeds=[
            {"npc_id": "n1", "name": "N", "role": "r", "description": "d", "location_id": "nonexistent"},
        ])
        issues = validate_setup_cross_references(data)
        assert any(i.code == "dangling_ref" and "location" in i.message for i in issues)

    def test_dangling_starting_npc_ids(self):
        data = _minimal_setup_data(starting_npc_ids=["missing_npc"])
        issues = validate_setup_cross_references(data)
        assert any(i.code == "dangling_ref" and "starting_npc_ids" in i.path for i in issues)

    def test_dangling_starting_location_id(self):
        data = _minimal_setup_data(starting_location_id="missing_loc")
        issues = validate_setup_cross_references(data)
        assert any(i.code == "dangling_ref" and "starting_location_id" in i.path for i in issues)

    def test_valid_refs_ok(self):
        data = _minimal_setup_data(
            factions=[{"faction_id": "f1", "name": "F1", "description": "d"}],
            locations=[{"location_id": "l1", "name": "L1", "description": "d"}],
            npc_seeds=[{"npc_id": "n1", "name": "N", "role": "r", "description": "d",
                        "faction_id": "f1", "location_id": "l1"}],
            starting_location_id="l1",
            starting_npc_ids=["n1"],
        )
        issues = validate_setup_cross_references(data)
        assert issues == []


class TestValidateAdventureSetupPayload:
    def test_valid_payload(self):
        result = validate_adventure_setup_payload(_minimal_setup_data())
        assert result.valid

    def test_missing_required_returns_invalid(self):
        data = _minimal_setup_data(setup_id="")
        result = validate_adventure_setup_payload(data)
        assert not result.valid

    def test_warnings_only_still_valid(self):
        data = _minimal_setup_data(starting_location_id="missing_loc")
        result = validate_adventure_setup_payload(data)
        assert result.valid  # only warnings, no errors
        assert len(result.issues) > 0


# ===================================================================
# schema.py new methods tests
# ===================================================================

class TestAdventureSetupNewFields:
    def test_difficulty_style_default_none(self):
        setup = _minimal_setup()
        assert setup.difficulty_style is None

    def test_mood_default_none(self):
        setup = _minimal_setup()
        assert setup.mood is None

    def test_starting_location_id_default_none(self):
        setup = _minimal_setup()
        assert setup.starting_location_id is None

    def test_starting_npc_ids_default_empty(self):
        setup = _minimal_setup()
        assert setup.starting_npc_ids == []

    def test_new_fields_roundtrip(self):
        setup = _minimal_setup(
            difficulty_style="hard",
            mood="dark",
            starting_location_id="loc1",
            starting_npc_ids=["n1", "n2"],
        )
        d = setup.to_dict()
        s2 = AdventureSetup.from_dict(d)
        assert s2.difficulty_style == "hard"
        assert s2.mood == "dark"
        assert s2.starting_location_id == "loc1"
        assert s2.starting_npc_ids == ["n1", "n2"]


class TestAdventureSetupWithDefaults:
    def test_fills_pacing(self):
        setup = _minimal_setup()
        assert setup.pacing is None
        setup2 = setup.with_defaults()
        assert setup2.pacing is not None
        assert setup2.pacing.style == "balanced"

    def test_fills_safety(self):
        setup = _minimal_setup()
        setup2 = setup.with_defaults()
        assert setup2.safety is not None

    def test_fills_content_balance(self):
        setup = _minimal_setup()
        setup2 = setup.with_defaults()
        assert setup2.content_balance is not None

    def test_does_not_overwrite_existing(self):
        setup = _minimal_setup()
        setup.pacing = PacingProfile(style="fast")
        setup2 = setup.with_defaults()
        assert setup2.pacing.style == "fast"

    def test_returns_copy(self):
        setup = _minimal_setup()
        setup2 = setup.with_defaults()
        assert setup is not setup2
        setup2.title = "modified"
        assert setup.title != "modified"


class TestAdventureSetupNormalize:
    def test_trims_strings(self):
        setup = _minimal_setup(title="  Test  ", genre="  Fantasy  ")
        normalized = setup.normalize()
        assert normalized.title == "Test"
        assert normalized.genre == "fantasy"

    def test_lowercases_genre(self):
        setup = _minimal_setup(genre="FANTASY")
        normalized = setup.normalize()
        assert normalized.genre == "fantasy"

    def test_lowercases_difficulty_style(self):
        setup = _minimal_setup(difficulty_style="HARD")
        normalized = setup.normalize()
        assert normalized.difficulty_style == "hard"

    def test_lowercases_mood(self):
        setup = _minimal_setup(mood="DARK")
        normalized = setup.normalize()
        assert normalized.mood == "dark"

    def test_strips_starting_npc_ids(self):
        setup = _minimal_setup(starting_npc_ids=["  n1  ", "", "  n2  "])
        normalized = setup.normalize()
        assert normalized.starting_npc_ids == ["n1", "n2"]

    def test_filters_empty_rules(self):
        setup = _minimal_setup(hard_rules=["rule1", "", "rule2"])
        normalized = setup.normalize()
        assert normalized.hard_rules == ["rule1", "rule2"]

    def test_returns_copy(self):
        setup = _minimal_setup()
        normalized = setup.normalize()
        assert setup is not normalized


class TestAdventureSetupValidateForUI:
    def test_valid_setup_returns_valid(self):
        setup = _minimal_setup()
        result = setup.validate_for_ui()
        assert result["valid"] is True

    def test_invalid_setup_returns_issues(self):
        setup = AdventureSetup(
            setup_id="", title="", genre="", setting="", premise="",
        )
        result = setup.validate_for_ui()
        assert result["valid"] is False
        assert len(result["issues"]) > 0


# ===================================================================
# gm_state.py new directive types tests
# ===================================================================

class TestNewDirectiveFields:
    def test_pin_thread_priority(self):
        d = PinThreadDirective(
            directive_id="t1", directive_type="pin_thread",
            thread_id="th1", priority="low",
        )
        assert d.priority == "low"

    def test_pin_thread_default_priority(self):
        d = PinThreadDirective(directive_id="t1", directive_type="pin_thread")
        assert d.priority == "high"

    def test_tone_directive_target_scope(self):
        d = ToneDirective(
            directive_id="t1", directive_type="tone",
            tone="dark", target_scope="global",
        )
        assert d.target_scope == "global"

    def test_tone_directive_default_scope(self):
        d = ToneDirective(directive_id="t1", directive_type="tone")
        assert d.target_scope == "scene"

    def test_danger_directive_target_scope(self):
        d = DangerDirective(
            directive_id="t1", directive_type="danger",
            level="high", target_scope="global",
        )
        assert d.target_scope == "global"

    def test_danger_directive_default_scope(self):
        d = DangerDirective(directive_id="t1", directive_type="danger")
        assert d.target_scope == "scene"


class TestTargetNPCDirective:
    def test_basic(self):
        d = TargetNPCDirective(
            directive_id="tn1", directive_type="target_npc",
            npc_id="npc_01", instruction="betray the party",
        )
        assert d.npc_id == "npc_01"
        assert d.instruction == "betray the party"

    def test_in_directive_types(self):
        assert "target_npc" in DIRECTIVE_TYPES

    def test_serializable(self):
        d = TargetNPCDirective(
            directive_id="tn1", directive_type="target_npc",
            npc_id="npc_01", instruction="betray",
        )
        data = asdict(d)
        assert data["npc_id"] == "npc_01"


class TestTargetFactionDirective:
    def test_basic(self):
        d = TargetFactionDirective(
            directive_id="tf1", directive_type="target_faction",
            faction_id="faction_01", instruction="declare war",
        )
        assert d.faction_id == "faction_01"

    def test_in_directive_types(self):
        assert "target_faction" in DIRECTIVE_TYPES


class TestTargetLocationDirective:
    def test_basic(self):
        d = TargetLocationDirective(
            directive_id="tl1", directive_type="target_location",
            location_id="loc_01", instruction="burn it",
        )
        assert d.location_id == "loc_01"

    def test_in_directive_types(self):
        assert "target_location" in DIRECTIVE_TYPES


class TestRevealDirective:
    def test_basic(self):
        d = RevealDirective(
            directive_id="r1", directive_type="reveal",
            reveal_type="secret", target_id="npc_spy",
        )
        assert d.reveal_type == "secret"
        assert d.timing == "soon"

    def test_custom_timing(self):
        d = RevealDirective(
            directive_id="r1", directive_type="reveal",
            reveal_type="identity", target_id="npc_01", timing="next_scene",
        )
        assert d.timing == "next_scene"

    def test_in_directive_types(self):
        assert "reveal" in DIRECTIVE_TYPES


class TestGMDirectiveStateFindMethods:
    def test_find_for_npc(self):
        state = GMDirectiveState()
        state.add_directive(TargetNPCDirective(
            directive_id="tn1", directive_type="target_npc",
            npc_id="npc_01", instruction="betray",
        ))
        state.add_directive(TargetNPCDirective(
            directive_id="tn2", directive_type="target_npc",
            npc_id="npc_02", instruction="flee",
        ))
        found = state.find_directives_for_npc("npc_01")
        assert len(found) == 1
        assert found[0].directive_id == "tn1"

    def test_find_for_npc_includes_reveal(self):
        state = GMDirectiveState()
        state.add_directive(RevealDirective(
            directive_id="r1", directive_type="reveal",
            reveal_type="secret", target_id="npc_01",
        ))
        found = state.find_directives_for_npc("npc_01")
        assert len(found) == 1

    def test_find_for_faction(self):
        state = GMDirectiveState()
        state.add_directive(TargetFactionDirective(
            directive_id="tf1", directive_type="target_faction",
            faction_id="f1", instruction="attack",
        ))
        found = state.find_directives_for_faction("f1")
        assert len(found) == 1

    def test_find_for_location(self):
        state = GMDirectiveState()
        state.add_directive(TargetLocationDirective(
            directive_id="tl1", directive_type="target_location",
            location_id="l1", instruction="siege",
        ))
        found = state.find_directives_for_location("l1")
        assert len(found) == 1

    def test_find_empty_for_unmatched(self):
        state = GMDirectiveState()
        state.add_directive(TargetNPCDirective(
            directive_id="tn1", directive_type="target_npc",
            npc_id="npc_01", instruction="x",
        ))
        assert state.find_directives_for_npc("npc_99") == []
        assert state.find_directives_for_faction("f99") == []
        assert state.find_directives_for_location("l99") == []

    def test_find_excludes_disabled(self):
        state = GMDirectiveState()
        state.add_directive(TargetNPCDirective(
            directive_id="tn1", directive_type="target_npc",
            npc_id="npc_01", instruction="x", enabled=False,
        ))
        assert state.find_directives_for_npc("npc_01") == []


class TestGMDirectiveStateBuildUISummary:
    def test_empty_state(self):
        state = GMDirectiveState()
        summary = state.build_ui_summary()
        assert summary["total_directives"] == 0
        assert summary["active_directives"] == 0
        assert summary["by_type"] == {}

    def test_groups_by_type(self):
        state = GMDirectiveState()
        state.add_directive(ToneDirective(
            directive_id="t1", directive_type="tone", tone="dark",
        ))
        state.add_directive(DangerDirective(
            directive_id="d1", directive_type="danger", level="high",
        ))
        state.add_directive(ToneDirective(
            directive_id="t2", directive_type="tone", tone="humorous",
        ))
        summary = state.build_ui_summary()
        assert summary["total_directives"] == 3
        assert summary["active_directives"] == 3
        assert len(summary["by_type"]["tone"]) == 2
        assert len(summary["by_type"]["danger"]) == 1


class TestDirectiveTypesSerializeDeserialize:
    def test_new_types_serialize_deserialize(self):
        state = GMDirectiveState()
        state.add_directive(TargetNPCDirective(
            directive_id="tn1", directive_type="target_npc",
            npc_id="npc_01", instruction="betray",
        ))
        state.add_directive(RevealDirective(
            directive_id="r1", directive_type="reveal",
            reveal_type="secret", target_id="npc_01",
        ))
        data = state.serialize_state()
        state2 = GMDirectiveState()
        state2.deserialize_state(data)
        assert len(state2.directives) == 2
        assert isinstance(state2.directives["tn1"], TargetNPCDirective)
        assert isinstance(state2.directives["r1"], RevealDirective)


# ===================================================================
# commands.py expanded parse tests
# ===================================================================

class TestGMCommandProcessorParsing:
    def setup_method(self):
        self.proc = GMCommandProcessor()

    def test_pin_thread(self):
        cmd = self.proc.parse_command("pin thread main_quest")
        assert cmd["command"] == "pin_thread"
        assert cmd["thread_id"] == "main_quest"

    def test_keep_npc_alive(self):
        cmd = self.proc.parse_command("keep npc gandalf alive")
        assert cmd["command"] == "keep_npc_alive"
        assert cmd["npc_id"] == "gandalf"

    def test_target_npc(self):
        cmd = self.proc.parse_command("target npc bandit_01 ambush the party")
        assert cmd["command"] == "target_npc"
        assert cmd["npc_id"] == "bandit_01"
        assert cmd["instruction"] == "ambush the party"

    def test_target_faction(self):
        cmd = self.proc.parse_command("target faction guild_01 begin trade embargo")
        assert cmd["command"] == "target_faction"
        assert cmd["faction_id"] == "guild_01"

    def test_target_location(self):
        cmd = self.proc.parse_command("target location tavern increase tension")
        assert cmd["command"] == "target_location"
        assert cmd["location_id"] == "tavern"

    def test_reveal_with_timing(self):
        cmd = self.proc.parse_command("reveal secret npc_spy timing next_scene")
        assert cmd["command"] == "reveal"
        assert cmd["reveal_type"] == "secret"
        assert cmd["target_id"] == "npc_spy"
        assert cmd["timing"] == "next_scene"

    def test_reveal_default_timing(self):
        cmd = self.proc.parse_command("reveal identity npc_01")
        assert cmd["command"] == "reveal"
        assert cmd["timing"] == "soon"

    def test_set_danger(self):
        cmd = self.proc.parse_command("set danger high")
        assert cmd["command"] == "set_danger"
        assert cmd["level"] == "high"

    def test_set_tone(self):
        cmd = self.proc.parse_command("set tone ominous and foreboding")
        assert cmd["command"] == "switch_tone"
        assert cmd["tone"] == "ominous and foreboding"

    def test_legacy_restate_canon(self):
        cmd = self.proc.parse_command("restate canon")
        assert cmd["command"] == "restate_canon"

    def test_legacy_switch_tone(self):
        cmd = self.proc.parse_command("switch tone darker")
        assert cmd["command"] == "switch_tone"
        assert cmd["tone"] == "darker"

    def test_unknown_command(self):
        cmd = self.proc.parse_command("do something random")
        assert cmd["command"] == "unknown"


class TestGMCommandProcessorApply:
    def setup_method(self):
        self.proc = GMCommandProcessor()
        self.gm_state = GMDirectiveState()

    def _mock_coherence(self):
        class MockCoherence:
            def get_scene_summary(self):
                return "scene"
            def get_unresolved_threads(self):
                return []
        return MockCoherence()

    def test_apply_pin_thread(self):
        cmd = {"command": "pin_thread", "thread_id": "quest1"}
        result = self.proc.apply_command(cmd, self.gm_state, self._mock_coherence())
        assert result["ok"]
        assert "gm:pin_thread:quest1" in self.gm_state.directives

    def test_apply_target_npc(self):
        cmd = {"command": "target_npc", "npc_id": "npc_01", "instruction": "flee"}
        result = self.proc.apply_command(cmd, self.gm_state, self._mock_coherence())
        assert result["ok"]
        d = self.gm_state.directives["gm:target_npc:npc_01"]
        assert isinstance(d, TargetNPCDirective)
        assert d.instruction == "flee"

    def test_apply_target_faction(self):
        cmd = {"command": "target_faction", "faction_id": "f1", "instruction": "attack"}
        result = self.proc.apply_command(cmd, self.gm_state, self._mock_coherence())
        assert result["ok"]
        assert isinstance(self.gm_state.directives["gm:target_faction:f1"], TargetFactionDirective)

    def test_apply_target_location(self):
        cmd = {"command": "target_location", "location_id": "l1", "instruction": "siege"}
        result = self.proc.apply_command(cmd, self.gm_state, self._mock_coherence())
        assert result["ok"]
        assert isinstance(self.gm_state.directives["gm:target_location:l1"], TargetLocationDirective)

    def test_apply_reveal(self):
        cmd = {"command": "reveal", "reveal_type": "secret", "target_id": "npc_01", "timing": "soon"}
        result = self.proc.apply_command(cmd, self.gm_state, self._mock_coherence())
        assert result["ok"]
        assert isinstance(self.gm_state.directives["gm:reveal:npc_01"], RevealDirective)

    def test_apply_set_danger(self):
        cmd = {"command": "set_danger", "level": "extreme"}
        result = self.proc.apply_command(cmd, self.gm_state, self._mock_coherence())
        assert result["ok"]
        d = self.gm_state.directives["gm:danger_extreme"]
        assert isinstance(d, DangerDirective)
        assert d.level == "extreme"

    def test_apply_unknown_returns_not_ok(self):
        cmd = {"command": "unknown"}
        result = self.proc.apply_command(cmd, self.gm_state, self._mock_coherence())
        assert not result["ok"]


# ===================================================================
# presenters.py tests
# ===================================================================

class _MockCoherenceState:
    def __init__(self):
        self.stable_world_facts = {}


class _MockCoherenceCore:
    def __init__(self):
        self._state = _MockCoherenceState()

    def get_scene_summary(self):
        return "A dark forest clearing."

    def get_unresolved_threads(self):
        return [{"thread_id": "t1", "title": "Mystery"}]

    def get_state(self):
        return self._state


class _MockFact:
    def __init__(self, fact_id, subject, predicate, value, metadata=None):
        self.fact_id = fact_id
        self.subject = subject
        self.predicate = predicate
        self.value = value
        self.metadata = metadata or {}


class TestCreatorStatePresenter:
    def setup_method(self):
        self.presenter = CreatorStatePresenter()
        self.coherence = _MockCoherenceCore()

    def test_present_setup_summary(self):
        setup = _minimal_setup(difficulty_style="hard", mood="dark")
        result = self.presenter.present_setup_summary(setup)
        assert result["setup_id"] == "test_setup"
        assert result["difficulty_style"] == "hard"
        assert result["mood"] == "dark"
        assert "faction_count" in result
        assert "npc_count" in result

    def test_present_canon_summary(self):
        from app.rpg.creator.canon import CreatorCanonFact, CreatorCanonState
        cs = CreatorCanonState()
        cs.add_fact(CreatorCanonFact(
            fact_id="f1", subject="world", predicate="genre", value="fantasy",
        ))
        result = self.presenter.present_canon_summary(cs, self.coherence)
        assert len(result["canon_facts"]) == 1
        assert result["canon_facts"][0]["fact_id"] == "f1"
        assert result["scene_summary"] == "A dark forest clearing."

    def test_present_canon_summary_none_state(self):
        result = self.presenter.present_canon_summary(None, self.coherence)
        assert result["canon_facts"] == []

    def test_present_gm_dashboard(self):
        gm = GMDirectiveState()
        gm.add_directive(ToneDirective(directive_id="t1", directive_type="tone", tone="dark"))
        result = self.presenter.present_gm_dashboard(gm, self.coherence)
        assert result["active_directive_count"] == 1
        assert "dark" in result["tone"]
        assert result["scene_summary"] == "A dark forest clearing."

    def test_present_thread_panel(self):
        result = self.presenter.present_thread_panel(self.coherence)
        assert result["total"] == 1
        assert result["unresolved_threads"][0]["thread_id"] == "t1"

    def test_present_npc_panel(self):
        self.coherence._state.stable_world_facts["npc:hero:name"] = _MockFact(
            "npc:hero:name", "hero", "name", "Hero", {"role": "protagonist"},
        )
        result = self.presenter.present_npc_panel(self.coherence)
        assert result["total"] == 1
        assert result["npcs"][0]["name"] == "Hero"

    def test_present_faction_panel(self):
        self.coherence._state.stable_world_facts["faction:guild:exists"] = _MockFact(
            "faction:guild:exists", "guild", "exists", True, {"name": "Thieves Guild"},
        )
        result = self.presenter.present_faction_panel(self.coherence)
        assert result["total"] == 1

    def test_present_location_panel(self):
        self.coherence._state.stable_world_facts["location:tavern:name"] = _MockFact(
            "location:tavern:name", "tavern", "name", "The Rusty Nail", {},
        )
        result = self.presenter.present_location_panel(self.coherence)
        assert result["total"] == 1
        assert result["locations"][0]["name"] == "The Rusty Nail"

    def test_present_recap_panel(self):
        recap = {
            "scene_summary": "summary",
            "recent_consequences": ["c1"],
            "active_tensions": ["t1"],
            "unresolved_threads": [{"id": "th1"}],
            "gm_directives": {"tone": ["dark"]},
        }
        result = self.presenter.present_recap_panel(recap)
        assert result["scene_summary"] == "summary"
        assert result["recent_consequences"] == ["c1"]

    def test_present_recap_panel_missing_fields(self):
        result = self.presenter.present_recap_panel({})
        assert result["scene_summary"] == ""
        assert result["recent_consequences"] == []
        assert result["active_tensions"] == []
        assert result["unresolved_threads"] == []
        assert result["gm_directives"] == {}


# ===================================================================
# Integration-style tests
# ===================================================================

class TestEndToEndTemplateFlow:
    """Test building a setup from a template through to validation."""

    def test_template_to_validated_setup(self):
        tpl = build_setup_template("fantasy_adventure")
        tpl["setup_id"] = "game_001"
        tpl["title"] = "Dragon's Wake"
        tpl = apply_adventure_defaults(tpl)
        result = validate_adventure_setup_payload(tpl)
        assert result.valid

    def test_template_normalize_roundtrip(self):
        tpl = build_setup_template("cyberpunk_heist")
        tpl["setup_id"] = "cp_001"
        tpl["title"] = "Neon Shadows"
        tpl = apply_adventure_defaults(tpl)
        setup = AdventureSetup.from_dict(tpl)
        setup = setup.normalize().with_defaults()
        d = setup.to_dict()
        setup2 = AdventureSetup.from_dict(d)
        assert setup2.genre == "cyberpunk"
        assert setup2.pacing is not None

    def test_all_templates_produce_valid_setups(self):
        for info in list_setup_templates():
            tpl = build_setup_template(info["name"])
            tpl["setup_id"] = f"test_{info['name']}"
            tpl["title"] = f"Test {info['name']}"
            tpl = apply_adventure_defaults(tpl)
            result = validate_adventure_setup_payload(tpl)
            assert result.valid, f"Template '{info['name']}' produced invalid setup: {result.to_dict()}"


class TestGMCommandFullFlow:
    """Test parsing a command text all the way through to directive state."""

    def setup_method(self):
        self.proc = GMCommandProcessor()
        self.gm_state = GMDirectiveState()

    class MockCoherence:
        def get_scene_summary(self):
            return "scene"
        def get_unresolved_threads(self):
            return []

    def test_parse_and_apply_target_npc(self):
        cmd = self.proc.parse_command("target npc guard_01 become suspicious")
        result = self.proc.apply_command(cmd, self.gm_state, self.MockCoherence())
        assert result["ok"]
        found = self.gm_state.find_directives_for_npc("guard_01")
        assert len(found) == 1
        assert found[0].instruction == "become suspicious"

    def test_parse_and_apply_reveal(self):
        cmd = self.proc.parse_command("reveal identity spy_npc timing next_scene")
        result = self.proc.apply_command(cmd, self.gm_state, self.MockCoherence())
        assert result["ok"]
        found = self.gm_state.find_directives_for_npc("spy_npc")
        assert len(found) == 1

    def test_ui_summary_after_multiple_commands(self):
        for text in [
            "target npc guard_01 patrol",
            "set danger high",
            "set tone ominous",
        ]:
            cmd = self.proc.parse_command(text)
            self.proc.apply_command(cmd, self.gm_state, self.MockCoherence())
        summary = self.gm_state.build_ui_summary()
        assert summary["active_directives"] == 3
        assert "target_npc" in summary["by_type"]
        assert "danger" in summary["by_type"]
        assert "tone" in summary["by_type"]
