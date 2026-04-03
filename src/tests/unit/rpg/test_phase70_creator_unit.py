"""Comprehensive unit tests for Phase 7.0 Creator / GM layer."""

from __future__ import annotations

import sys
import types

# Mock Flask so we can import from app.rpg without Flask installed
_flask_mock = types.ModuleType("flask")
_flask_mock.Flask = type("Flask", (), {})
_flask_mock.Blueprint = type("Blueprint", (), {})
_flask_mock.request = None
_flask_mock.jsonify = lambda x: x
sys.modules.setdefault("flask", _flask_mock)

import pytest  # noqa: E402

from app.rpg.creator.schema import (  # noqa: E402
    AdventureSetup,
    ContentBalance,
    FactionSeed,
    LocationSeed,
    LoreConstraint,
    NPCSeed,
    PacingProfile,
    SafetyConstraint,
    ThemeConstraint,
)
from app.rpg.creator.canon import CreatorCanonFact, CreatorCanonState  # noqa: E402
from app.rpg.creator.gm_state import (  # noqa: E402
    CanonOverrideDirective,
    DangerDirective,
    GMDirective,
    GMDirectiveState,
    InjectEventDirective,
    PacingDirective,
    PinThreadDirective,
    RetconDirective,
    ToneDirective,
)
from app.rpg.creator.startup_pipeline import StartupGenerationPipeline  # noqa: E402
from app.rpg.creator.recap import RecapBuilder  # noqa: E402
from app.rpg.creator.commands import GMCommandProcessor  # noqa: E402
from app.rpg.coherence.models import CoherenceState, FactRecord  # noqa: E402


# ---------------------------------------------------------------------------
# Mock CoherenceCore used by pipeline, recap, and commands tests
# ---------------------------------------------------------------------------

class MockCoherenceCore:
    def __init__(self):
        self.facts = {}
        self.threads = {}
        self.anchors = []

    def insert_fact(self, fact):
        self.facts[fact.fact_id] = fact

    def upsert_fact(self, fact):
        self.facts[fact.fact_id] = fact

    def insert_thread(self, thread):
        self.threads[thread.thread_id] = thread

    def push_anchor(self, anchor):
        self.anchors.append(anchor)

    def get_scene_summary(self):
        return {"location": "test", "summary": "test scene"}

    def get_active_tensions(self):
        return ["tension1"]

    def get_unresolved_threads(self):
        return [{"thread_id": "t1", "title": "test"}]

    def get_recent_consequences(self, limit=10):
        return [{"consequence_id": "c1"}]

    def get_last_good_anchor(self):
        return None

    def get_state(self):
        state = CoherenceState()
        for fid, f in self.facts.items():
            state.stable_world_facts[fid] = f
        return state


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _minimal_setup(**overrides) -> AdventureSetup:
    """Return a valid AdventureSetup with sensible defaults."""
    defaults = dict(
        setup_id="s1",
        title="Test Adventure",
        genre="fantasy",
        setting="Dark Forest",
        premise="Heroes explore the unknown.",
    )
    defaults.update(overrides)
    return AdventureSetup(**defaults)


# ===================================================================
# 1. Schema tests
# ===================================================================

class TestLoreConstraint:
    def test_basic_creation(self):
        lc = LoreConstraint(name="Magic Law", description="No necromancy")
        assert lc.name == "Magic Law"
        assert lc.authority == "creator_canon"

    def test_roundtrip(self):
        lc = LoreConstraint(name="X", description="Y", authority="dm")
        assert LoreConstraint.from_dict(lc.to_dict()) == lc


class TestFactionSeed:
    def test_defaults(self):
        fs = FactionSeed(faction_id="f1", name="Guild", description="Thieves")
        assert fs.goals == []
        assert fs.relationships == {}
        assert fs.metadata == {}

    def test_roundtrip(self):
        fs = FactionSeed(
            faction_id="f1", name="G", description="D",
            goals=["steal"], relationships={"f2": "rival"}, metadata={"power": 5},
        )
        assert FactionSeed.from_dict(fs.to_dict()) == fs


class TestLocationSeed:
    def test_defaults(self):
        ls = LocationSeed(location_id="l1", name="Cave", description="Dark")
        assert ls.tags == []

    def test_roundtrip(self):
        ls = LocationSeed(location_id="l1", name="C", description="D", tags=["dark"])
        assert LocationSeed.from_dict(ls.to_dict()) == ls


class TestNPCSeed:
    def test_defaults(self):
        npc = NPCSeed(npc_id="n1", name="Bob", role="guard", description="A guard")
        assert npc.faction_id is None
        assert npc.must_survive is False

    def test_roundtrip(self):
        npc = NPCSeed(
            npc_id="n1", name="B", role="r", description="d",
            goals=["survive"], faction_id="f1", location_id="l1",
            must_survive=True, metadata={"level": 3},
        )
        assert NPCSeed.from_dict(npc.to_dict()) == npc


class TestThemeConstraint:
    def test_roundtrip(self):
        tc = ThemeConstraint(name="Hope", description="Prevails")
        assert ThemeConstraint.from_dict(tc.to_dict()) == tc


class TestPacingProfile:
    def test_defaults(self):
        pp = PacingProfile()
        assert pp.style == "balanced"
        assert pp.danger_level == "medium"

    def test_roundtrip(self):
        pp = PacingProfile(style="fast", combat_weight=0.5)
        assert PacingProfile.from_dict(pp.to_dict()) == pp


class TestSafetyConstraint:
    def test_defaults(self):
        sc = SafetyConstraint()
        assert sc.forbidden_themes == []

    def test_roundtrip(self):
        sc = SafetyConstraint(forbidden_themes=["gore"], soft_avoid_themes=["romance"])
        assert SafetyConstraint.from_dict(sc.to_dict()) == sc


class TestContentBalance:
    def test_defaults(self):
        cb = ContentBalance()
        assert cb.mystery == pytest.approx(0.2)

    def test_roundtrip(self):
        cb = ContentBalance(mystery=0.4, combat=0.1)
        assert ContentBalance.from_dict(cb.to_dict()) == cb


class TestAdventureSetup:
    def test_validate_pass(self):
        setup = _minimal_setup()
        setup.validate()  # should not raise

    @pytest.mark.parametrize("field", ["setup_id", "title", "genre", "setting", "premise"])
    def test_validate_missing_required(self, field):
        setup = _minimal_setup(**{field: ""})
        with pytest.raises(ValueError, match=f"AdventureSetup.{field} is required"):
            setup.validate()

    def test_validate_duplicate_locations(self):
        locs = [
            LocationSeed(location_id="dup", name="A", description="A"),
            LocationSeed(location_id="dup", name="B", description="B"),
        ]
        setup = _minimal_setup(locations=locs)
        with pytest.raises(ValueError, match="Duplicate location_id"):
            setup.validate()

    def test_validate_duplicate_factions(self):
        factions = [
            FactionSeed(faction_id="dup", name="A", description="A"),
            FactionSeed(faction_id="dup", name="B", description="B"),
        ]
        setup = _minimal_setup(factions=factions)
        with pytest.raises(ValueError, match="Duplicate faction_id"):
            setup.validate()

    def test_validate_duplicate_npcs(self):
        npcs = [
            NPCSeed(npc_id="dup", name="A", role="r", description="d"),
            NPCSeed(npc_id="dup", name="B", role="r", description="d"),
        ]
        setup = _minimal_setup(npc_seeds=npcs)
        with pytest.raises(ValueError, match="Duplicate npc_id"):
            setup.validate()

    def test_to_dict_none_optionals(self):
        setup = _minimal_setup()
        d = setup.to_dict()
        assert d["pacing"] is None
        assert d["safety"] is None
        assert d["content_balance"] is None

    def test_roundtrip_minimal(self):
        setup = _minimal_setup()
        rebuilt = AdventureSetup.from_dict(setup.to_dict())
        assert rebuilt.setup_id == setup.setup_id
        assert rebuilt.title == setup.title

    def test_roundtrip_full(self):
        setup = _minimal_setup(
            hard_rules=["No killing"],
            soft_tone_rules=["Be kind"],
            lore_constraints=[LoreConstraint(name="L", description="D")],
            factions=[FactionSeed(faction_id="f1", name="F", description="D")],
            locations=[LocationSeed(location_id="l1", name="L", description="D")],
            npc_seeds=[NPCSeed(npc_id="n1", name="N", role="R", description="D")],
            themes=[ThemeConstraint(name="T", description="D")],
            pacing=PacingProfile(style="slow"),
            safety=SafetyConstraint(forbidden_themes=["gore"]),
            content_balance=ContentBalance(mystery=0.5),
            forbidden_content=["x"],
            canon_notes=["note"],
            metadata={"key": "val"},
        )
        d = setup.to_dict()
        rebuilt = AdventureSetup.from_dict(d)
        assert rebuilt.to_dict() == d

    def test_from_dict_missing_optionals(self):
        """from_dict handles absent optional keys gracefully."""
        minimal = {
            "setup_id": "s1",
            "title": "T",
            "genre": "G",
            "setting": "S",
            "premise": "P",
        }
        setup = AdventureSetup.from_dict(minimal)
        assert setup.hard_rules == []
        assert setup.pacing is None

    def test_validate_empty_lists_ok(self):
        setup = _minimal_setup(
            locations=[], factions=[], npc_seeds=[],
        )
        setup.validate()  # no duplicates when lists are empty


# ===================================================================
# 2. Canon tests
# ===================================================================

class TestCreatorCanonFact:
    def test_defaults(self):
        f = CreatorCanonFact(fact_id="f1", subject="s", predicate="p", value="v")
        assert f.source == "creator"
        assert f.authority == "creator_canon"

    def test_roundtrip(self):
        f = CreatorCanonFact(
            fact_id="f1", subject="s", predicate="p", value=42,
            source="test", authority="test_auth", metadata={"k": "v"},
        )
        assert CreatorCanonFact.from_dict(f.to_dict()) == f


class TestCreatorCanonState:
    def _make_fact(self, fid="f1"):
        return CreatorCanonFact(fact_id=fid, subject="s", predicate="p", value="v")

    def test_add_and_get(self):
        state = CreatorCanonState()
        fact = self._make_fact()
        state.add_fact(fact)
        assert state.get_fact("f1") is fact

    def test_get_missing_returns_none(self):
        state = CreatorCanonState()
        assert state.get_fact("nope") is None

    def test_remove(self):
        state = CreatorCanonState()
        state.add_fact(self._make_fact())
        state.remove_fact("f1")
        assert state.get_fact("f1") is None

    def test_remove_nonexistent_ok(self):
        state = CreatorCanonState()
        state.remove_fact("nope")  # should not raise

    def test_list_facts(self):
        state = CreatorCanonState()
        state.add_fact(self._make_fact("a"))
        state.add_fact(self._make_fact("b"))
        assert len(state.list_facts()) == 2

    def test_serialize_deserialize_roundtrip(self):
        state = CreatorCanonState()
        state.add_fact(self._make_fact("a"))
        state.setup_id = "setup_1"
        state.metadata = {"x": 1}

        data = state.serialize_state()
        state2 = CreatorCanonState()
        state2.deserialize_state(data)

        assert state2.setup_id == "setup_1"
        assert state2.metadata == {"x": 1}
        assert state2.get_fact("a") is not None
        assert state2.get_fact("a").value == "v"

    def test_deserialize_empty(self):
        state = CreatorCanonState()
        state.deserialize_state({})
        assert state.facts == {}
        assert state.setup_id is None

    def test_apply_to_coherence(self):
        state = CreatorCanonState()
        state.add_fact(self._make_fact("f1"))
        mock = MockCoherenceCore()
        state.apply_to_coherence(mock)
        assert "f1" in mock.facts
        assert mock.facts["f1"].authority == "creator_canon"


# ===================================================================
# 3. GM state / directive tests
# ===================================================================

class TestGMDirective:
    def test_defaults(self):
        d = GMDirective(directive_id="d1", directive_type="test")
        assert d.scope == "global"
        assert d.enabled is True
        assert d.metadata == {}

    def test_roundtrip(self):
        d = GMDirective(directive_id="d1", directive_type="t", scope="scene", enabled=False)
        assert GMDirective.from_dict(d.to_dict()) == d


class TestInjectEventDirective:
    def test_fields(self):
        d = InjectEventDirective(
            directive_id="d1", directive_type="inject_event",
            event_type="spawn", payload={"npc": "bob"},
        )
        assert d.event_type == "spawn"
        assert d.payload == {"npc": "bob"}

    def test_to_dict_includes_subclass_fields(self):
        d = InjectEventDirective(
            directive_id="d1", directive_type="inject_event",
            event_type="spawn",
        )
        data = d.to_dict()
        assert "event_type" in data
        assert data["event_type"] == "spawn"


class TestPinThreadDirective:
    def test_fields(self):
        d = PinThreadDirective(
            directive_id="d1", directive_type="pin_thread", thread_id="t1",
        )
        assert d.thread_id == "t1"


class TestRetconDirective:
    def test_fields(self):
        d = RetconDirective(
            directive_id="d1", directive_type="retcon",
            subject="king", predicate="alive", value=False,
        )
        assert d.value is False


class TestCanonOverrideDirective:
    def test_fields(self):
        d = CanonOverrideDirective(
            directive_id="d1", directive_type="canon_override",
            fact_id="fact:1", value="new_val",
        )
        assert d.fact_id == "fact:1"


class TestPacingDirective:
    def test_default_style(self):
        d = PacingDirective(directive_id="d1", directive_type="pacing")
        assert d.style == "balanced"


class TestToneDirective:
    def test_default_tone(self):
        d = ToneDirective(directive_id="d1", directive_type="tone")
        assert d.tone == "neutral"


class TestDangerDirective:
    def test_default_level(self):
        d = DangerDirective(directive_id="d1", directive_type="danger")
        assert d.level == "medium"


class TestGMDirectiveState:
    def _state_with_directives(self):
        state = GMDirectiveState()
        state.add_directive(
            PacingDirective(directive_id="p1", directive_type="pacing", style="fast"),
        )
        state.add_directive(
            ToneDirective(directive_id="t1", directive_type="tone", tone="dark", scope="scene"),
        )
        state.add_directive(
            DangerDirective(directive_id="dg1", directive_type="danger", level="high", enabled=False),
        )
        return state

    def test_add_and_list(self):
        state = self._state_with_directives()
        assert len(state.list_directives()) == 3

    def test_remove(self):
        state = self._state_with_directives()
        state.remove_directive("p1")
        assert len(state.list_directives()) == 2

    def test_remove_nonexistent_ok(self):
        state = GMDirectiveState()
        state.remove_directive("nope")  # should not raise

    def test_get_active_excludes_disabled(self):
        state = self._state_with_directives()
        active = state.get_active_directives()
        assert all(d.enabled for d in active)
        assert len(active) == 2

    def test_clear_scene_scoped(self):
        state = self._state_with_directives()
        state.clear_scene_scoped_directives()
        remaining = state.list_directives()
        assert all(d.scope != "scene" for d in remaining)
        assert len(remaining) == 2  # p1 (global) and dg1 (global)

    def test_build_director_context(self):
        state = self._state_with_directives()
        ctx = state.build_director_context()
        assert len(ctx["active_directives"]) == 2
        assert "fast" in ctx["pacing"]
        assert "dark" in ctx["tone"]
        # dg1 is disabled so not in danger
        assert ctx["danger"] == []

    def test_build_director_context_pinned_threads(self):
        state = GMDirectiveState()
        state.add_directive(
            PinThreadDirective(directive_id="pin1", directive_type="pin_thread", thread_id="th1"),
        )
        ctx = state.build_director_context()
        assert "th1" in ctx["pinned_threads"]

    def test_serialize_deserialize_roundtrip(self):
        state = self._state_with_directives()
        data = state.serialize_state()
        state2 = GMDirectiveState()
        state2.deserialize_state(data)
        assert len(state2.list_directives()) == 3
        # Verify subtypes survived
        restored_pacing = [d for d in state2.list_directives() if isinstance(d, PacingDirective)]
        assert len(restored_pacing) == 1
        assert restored_pacing[0].style == "fast"

    def test_deserialize_empty(self):
        state = GMDirectiveState()
        state.deserialize_state({})
        assert state.list_directives() == []

    def test_apply_to_coherence_retcon(self):
        state = GMDirectiveState()
        state.add_directive(
            RetconDirective(
                directive_id="r1", directive_type="retcon",
                subject="king", predicate="alive", value=False,
            ),
        )
        mock = MockCoherenceCore()
        state.apply_to_coherence(mock)
        assert "gm_retcon:r1" in mock.facts

    def test_apply_to_coherence_canon_override(self):
        state = GMDirectiveState()
        state.add_directive(
            CanonOverrideDirective(
                directive_id="co1", directive_type="canon_override",
                fact_id="faction:f1", value="destroyed",
            ),
        )
        mock = MockCoherenceCore()
        state.apply_to_coherence(mock)
        assert "faction:f1" in mock.facts
        assert mock.facts["faction:f1"].value == "destroyed"

    def test_apply_to_coherence_skips_disabled(self):
        state = GMDirectiveState()
        state.add_directive(
            RetconDirective(
                directive_id="r1", directive_type="retcon",
                subject="s", predicate="p", value="v", enabled=False,
            ),
        )
        mock = MockCoherenceCore()
        state.apply_to_coherence(mock)
        assert len(mock.facts) == 0


# ===================================================================
# 4. StartupGenerationPipeline tests
# ===================================================================

class TestStartupGenerationPipeline:
    def _pipeline(self):
        return StartupGenerationPipeline(
            llm_gateway=None,
            coherence_core=MockCoherenceCore(),
        )

    def _full_setup(self):
        return _minimal_setup(
            hard_rules=["No flying"],
            locations=[LocationSeed(location_id="l1", name="Town", description="A town")],
            npc_seeds=[
                NPCSeed(npc_id="n1", name="Alice", role="hero", description="Brave"),
                NPCSeed(npc_id="n2", name="Bob", role="villain", description="Evil",
                         location_id="l1"),
            ],
            factions=[FactionSeed(faction_id="f1", name="Guild", description="Thieves")],
        )

    def test_generate_world_frame(self):
        p = self._pipeline()
        setup = self._full_setup()
        wf = p.generate_world_frame(setup)
        assert wf["setup_id"] == "s1"
        assert wf["genre"] == "fantasy"
        assert wf["hard_rules"] == ["No flying"]

    def test_generate_opening_situation_with_locations(self):
        p = self._pipeline()
        setup = self._full_setup()
        wf = p.generate_world_frame(setup)
        opening = p.generate_opening_situation(setup, wf)
        assert opening["location"] == "Town"
        assert "Alice" in opening["present_actors"]

    def test_generate_opening_situation_no_locations(self):
        p = self._pipeline()
        setup = _minimal_setup()
        wf = p.generate_world_frame(setup)
        opening = p.generate_opening_situation(setup, wf)
        assert opening["location"] == "Dark Forest"  # falls back to setting
        assert opening["present_actors"] == []

    def test_generate_opening_no_hard_rules_defaults(self):
        p = self._pipeline()
        setup = _minimal_setup()
        wf = p.generate_world_frame(setup)
        opening = p.generate_opening_situation(setup, wf)
        assert len(opening["active_tensions"]) >= 1

    def test_generate_seed_npcs(self):
        p = self._pipeline()
        setup = self._full_setup()
        wf = p.generate_world_frame(setup)
        npcs = p.generate_seed_npcs(setup, wf)
        assert len(npcs) == 2
        assert npcs[0]["npc_id"] == "n1"

    def test_generate_seed_factions(self):
        p = self._pipeline()
        setup = self._full_setup()
        wf = p.generate_world_frame(setup)
        factions = p.generate_seed_factions(setup, wf)
        assert len(factions) == 1

    def test_generate_seed_locations(self):
        p = self._pipeline()
        setup = self._full_setup()
        wf = p.generate_world_frame(setup)
        locs = p.generate_seed_locations(setup, wf)
        assert len(locs) == 1

    def test_generate_initial_threads(self):
        p = self._pipeline()
        setup = self._full_setup()
        wf = p.generate_world_frame(setup)
        opening = p.generate_opening_situation(setup, wf)
        threads = p.generate_initial_threads(setup, opening)
        assert len(threads) == 1
        assert threads[0]["status"] == "unresolved"
        assert threads[0]["priority"] == "high"

    def test_generate_full_pipeline(self):
        mock_cc = MockCoherenceCore()
        p = StartupGenerationPipeline(llm_gateway=None, coherence_core=mock_cc)
        setup = self._full_setup()
        result = p.generate(setup)

        assert "world_frame" in result
        assert "opening_situation" in result
        assert "seed_npcs" in result
        assert "initial_scene_anchor" in result

        # coherence was populated
        assert len(mock_cc.facts) > 0
        assert len(mock_cc.threads) > 0
        assert len(mock_cc.anchors) == 1

    def test_generate_materializes_creator_canon(self):
        mock_cc = MockCoherenceCore()
        p = StartupGenerationPipeline(llm_gateway=None, coherence_core=mock_cc)
        setup = self._full_setup()
        p.generate(setup)
        assert p.creator_canon_state.setup_id == "s1"
        facts = p.creator_canon_state.list_facts()
        predicates = {f.predicate for f in facts}
        assert {"genre", "setting", "premise"} <= predicates

    def test_generate_validates_setup(self):
        p = self._pipeline()
        bad_setup = _minimal_setup(setup_id="")
        with pytest.raises(ValueError):
            p.generate(bad_setup)

    def test_create_initial_scene_anchor(self):
        p = self._pipeline()
        setup = self._full_setup()
        wf = p.generate_world_frame(setup)
        opening = p.generate_opening_situation(setup, wf)
        threads = p.generate_initial_threads(setup, opening)
        generated = {
            "world_frame": wf,
            "opening_situation": opening,
            "initial_threads": threads,
        }
        anchor = p.create_initial_scene_anchor(generated)
        assert anchor["tick"] == 0
        assert anchor["location"] == "Town"

    def test_npc_location_fact_inserted(self):
        """NPC with location_id gets an extra location fact in coherence."""
        mock_cc = MockCoherenceCore()
        p = StartupGenerationPipeline(llm_gateway=None, coherence_core=mock_cc)
        setup = self._full_setup()
        p.generate(setup)
        assert "n2:location" in mock_cc.facts


# ===================================================================
# 5. RecapBuilder tests
# ===================================================================

class TestRecapBuilder:
    def _core_with_facts(self):
        """MockCoherenceCore pre-loaded with a faction and npc fact."""
        core = MockCoherenceCore()
        core.insert_fact(FactRecord(
            fact_id="faction:f1:exists", category="world",
            subject="f1", predicate="exists", value=True,
            metadata={"name": "Thieves Guild"},
        ))
        core.insert_fact(FactRecord(
            fact_id="npc:n1:name", category="world",
            subject="n1", predicate="name", value="Alice",
            metadata={"role": "hero"},
        ))
        return core

    def test_build_canon_summary_no_state(self):
        rb = RecapBuilder()
        result = rb.build_canon_summary(MockCoherenceCore())
        assert result["canon_facts"] == []
        assert "scene_summary" in result

    def test_build_canon_summary_with_state(self):
        rb = RecapBuilder()
        cs = CreatorCanonState()
        cs.add_fact(CreatorCanonFact(
            fact_id="f1", subject="s", predicate="p", value="v",
        ))
        result = rb.build_canon_summary(MockCoherenceCore(), creator_canon_state=cs)
        assert len(result["canon_facts"]) == 1

    def test_build_session_recap_no_gm_state(self):
        rb = RecapBuilder()
        result = rb.build_session_recap(MockCoherenceCore())
        assert result["gm_directives"] == {}
        assert "scene_summary" in result

    def test_build_session_recap_with_gm_state(self):
        rb = RecapBuilder()
        gm = GMDirectiveState()
        gm.add_directive(
            ToneDirective(directive_id="t1", directive_type="tone", tone="dark"),
        )
        result = rb.build_session_recap(MockCoherenceCore(), gm_state=gm)
        assert "dark" in result["gm_directives"]["tone"]

    def test_build_active_factions_summary(self):
        rb = RecapBuilder()
        core = self._core_with_facts()
        result = rb.build_active_factions_summary(core)
        assert len(result["factions"]) == 1
        assert result["factions"][0]["faction_id"] == "f1"

    def test_build_active_factions_empty(self):
        rb = RecapBuilder()
        result = rb.build_active_factions_summary(MockCoherenceCore())
        assert result["factions"] == []

    def test_build_npc_roster(self):
        rb = RecapBuilder()
        core = self._core_with_facts()
        result = rb.build_npc_roster(core)
        assert len(result["npcs"]) == 1
        assert result["npcs"][0]["name"] == "Alice"

    def test_build_npc_roster_empty(self):
        rb = RecapBuilder()
        result = rb.build_npc_roster(MockCoherenceCore())
        assert result["npcs"] == []

    def test_build_unresolved_threads_summary(self):
        rb = RecapBuilder()
        result = rb.build_unresolved_threads_summary(MockCoherenceCore())
        assert len(result["threads"]) == 1

    def test_build_world_tensions_summary(self):
        rb = RecapBuilder()
        result = rb.build_world_tensions_summary(MockCoherenceCore())
        assert "tension1" in result["active_tensions"]

    def test_build_player_impact_summary(self):
        rb = RecapBuilder()
        result = rb.build_player_impact_summary(MockCoherenceCore())
        assert len(result["recent_consequences"]) == 1


# ===================================================================
# 6. GMCommandProcessor tests
# ===================================================================

class TestGMCommandProcessorParse:
    def _proc(self):
        return GMCommandProcessor()

    def test_restate_canon(self):
        assert self._proc().parse_command("restate canon") == {"command": "restate_canon"}

    def test_restate_canon_case_insensitive(self):
        assert self._proc().parse_command("Restate Canon") == {"command": "restate_canon"}

    def test_unresolved_threads(self):
        r = self._proc().parse_command("what unresolved threads exist?")
        assert r["command"] == "list_unresolved_threads"

    def test_spawn_merchant(self):
        r = self._proc().parse_command("spawn a merchant")
        assert r["command"] == "spawn_merchant"

    def test_make_city_corrupt(self):
        r = self._proc().parse_command("make this city more corrupt")
        assert r["command"] == "make_city_more_corrupt"

    def test_introduce_hidden_faction(self):
        r = self._proc().parse_command("introduce a hidden faction")
        assert r["command"] == "introduce_hidden_faction"

    def test_keep_npc_alive(self):
        r = self._proc().parse_command("keep this npc alive")
        assert r["command"] == "keep_npc_alive"

    def test_turn_down_combat(self):
        r = self._proc().parse_command("turn down combat")
        assert r["command"] == "turn_down_combat"

    def test_switch_tone(self):
        r = self._proc().parse_command("switch tone gritty")
        assert r["command"] == "switch_tone"
        assert r["tone"] == "gritty"

    def test_switch_tone_trailing_space_is_unknown(self):
        """Input 'switch tone ' strips to 'switch tone' which does not
        start with 'switch tone ' (note trailing space), so it falls through."""
        r = self._proc().parse_command("switch tone ")
        assert r["command"] == "unknown"

    def test_switch_tone_extracts_value(self):
        """Input with extra spaces still extracts the tone value."""
        r = self._proc().parse_command("switch tone  x")
        assert r["command"] == "switch_tone"
        assert r["tone"] == "x"

    def test_unknown_command(self):
        r = self._proc().parse_command("do something weird")
        assert r["command"] == "unknown"
        assert r["raw"] == "do something weird"

    def test_empty_string(self):
        r = self._proc().parse_command("")
        assert r["command"] == "unknown"

    def test_none_input(self):
        r = self._proc().parse_command(None)
        assert r["command"] == "unknown"


class TestGMCommandProcessorApply:
    def _proc(self):
        return GMCommandProcessor()

    def _gm_state(self):
        return GMDirectiveState()

    def _core(self):
        return MockCoherenceCore()

    def test_apply_restate_canon(self):
        gm = self._gm_state()
        result = self._proc().apply_command(
            {"command": "restate_canon"}, gm, self._core(),
        )
        assert result["ok"] is True
        assert "canon" in result

    def test_apply_list_unresolved(self):
        result = self._proc().apply_command(
            {"command": "list_unresolved_threads"}, self._gm_state(), self._core(),
        )
        assert result["ok"] is True
        assert len(result["threads"]) >= 1

    def test_apply_spawn_merchant(self):
        gm = self._gm_state()
        result = self._proc().apply_command(
            {"command": "spawn_merchant"}, gm, self._core(),
        )
        assert result["ok"] is True
        assert len(gm.list_directives()) == 1
        d = gm.list_directives()[0]
        assert isinstance(d, InjectEventDirective)
        assert d.scope == "scene"

    def test_apply_make_city_corrupt(self):
        gm = self._gm_state()
        result = self._proc().apply_command(
            {"command": "make_city_more_corrupt"}, gm, self._core(),
        )
        assert result["ok"] is True

    def test_apply_introduce_hidden_faction(self):
        gm = self._gm_state()
        result = self._proc().apply_command(
            {"command": "introduce_hidden_faction"}, gm, self._core(),
        )
        assert result["ok"] is True
        d = gm.list_directives()[0]
        assert d.scope == "global"

    def test_apply_keep_npc_alive(self):
        gm = self._gm_state()
        result = self._proc().apply_command(
            {"command": "keep_npc_alive"}, gm, self._core(),
        )
        assert result["ok"] is True
        d = gm.list_directives()[0]
        assert isinstance(d, PinThreadDirective)

    def test_apply_turn_down_combat(self):
        gm = self._gm_state()
        result = self._proc().apply_command(
            {"command": "turn_down_combat"}, gm, self._core(),
        )
        assert result["ok"] is True
        d = gm.list_directives()[0]
        assert isinstance(d, DangerDirective)
        assert d.level == "low"

    def test_apply_switch_tone(self):
        gm = self._gm_state()
        result = self._proc().apply_command(
            {"command": "switch_tone", "tone": "lighthearted"}, gm, self._core(),
        )
        assert result["ok"] is True
        d = gm.list_directives()[0]
        assert isinstance(d, ToneDirective)
        assert d.tone == "lighthearted"

    def test_apply_unknown(self):
        result = self._proc().apply_command(
            {"command": "unknown"}, self._gm_state(), self._core(),
        )
        assert result["ok"] is False


# ===================================================================
# 7. Canon Override Directive tests (Phase 70 fixpass)
# ===================================================================

class TestCanonOverrideDirectiveFixpass:
    """Tests for the canon_override semantic fields fix."""

    def test_canon_override_directive_applies_real_subject_and_predicate(self):
        """CanonOverrideDirective should use explicit subject/predicate, not predicate='override'."""
        state = GMDirectiveState()
        state.add_directive(
            CanonOverrideDirective(
                directive_id="gm:override",
                directive_type="canon_override",
                fact_id="city:corruption",
                subject="city",
                predicate="corruption",
                value="high",
            )
        )

        mock = MockCoherenceCore()
        state.apply_to_coherence(mock)

        assert "city:corruption" in mock.facts
        assert mock.facts["city:corruption"].subject == "city"
        assert mock.facts["city:corruption"].predicate == "corruption"
        assert mock.facts["city:corruption"].value == "high"

    def test_canon_override_falls_back_to_fact_id_parsing(self):
        """When subject/predicate not provided, parse from fact_id with ':' separator."""
        state = GMDirectiveState()
        state.add_directive(
            CanonOverrideDirective(
                directive_id="gm:override",
                directive_type="canon_override",
                fact_id="faction:power",
                value=99,
            )
        )

        mock = MockCoherenceCore()
        state.apply_to_coherence(mock)

        assert "faction:power" in mock.facts
        assert mock.facts["faction:power"].subject == "faction"
        assert mock.facts["faction:power"].predicate == "power"

    def test_canon_override_single_fact_id_defaults_to_value(self):
        """When fact_id has no ':' and no explicit fields, predicate defaults to 'value'."""
        state = GMDirectiveState()
        state.add_directive(
            CanonOverrideDirective(
                directive_id="gm:override",
                directive_type="canon_override",
                fact_id="world_state",
                value="active",
            )
        )

        mock = MockCoherenceCore()
        state.apply_to_coherence(mock)

        assert "world_state" in mock.facts
        assert mock.facts["world_state"].subject == "world_state"
        assert mock.facts["world_state"].predicate == "value"

    def test_canon_override_metadata_includes_directive_type(self):
        """Canon override facts should include directive_type in metadata."""
        state = GMDirectiveState()
        state.add_directive(
            CanonOverrideDirective(
                directive_id="gm:override",
                directive_type="canon_override",
                fact_id="city:corruption",
                subject="city",
                predicate="corruption",
                value="high",
            )
        )

        mock = MockCoherenceCore()
        state.apply_to_coherence(mock)

        fact = mock.facts["city:corruption"]
        assert fact.metadata["directive_id"] == "gm:override"
        assert fact.metadata["directive_type"] == "canon_override"


# ===================================================================
# 8. Inject Event Directive tests (Phase 70 fixpass)
# ===================================================================

class TestInjectEventDirectiveFixpass:
    """Tests for inject-event directive being properly emitted."""

    def test_get_pending_injected_events_returns_active_events(self):
        """Active inject-event directives should be exposed as pending events."""
        state = GMDirectiveState()
        state.add_directive(
            InjectEventDirective(
                directive_id="gm:spawn",
                directive_type="inject_event",
                scope="scene",
                event_type="npc_spawned",
                payload={"npc_id": "merchant"},
            )
        )

        pending = state.get_pending_injected_events()
        assert pending == [
            {
                "directive_id": "gm:spawn",
                "scope": "scene",
                "event_type": "npc_spawned",
                "payload": {"npc_id": "merchant"},
            }
        ]


    def test_get_pending_injected_events_includes_directive_identity_and_scope(self):
        state = GMDirectiveState()
        state.add_directive(
            InjectEventDirective(
                directive_id="gm:event1",
                directive_type="inject_event",
                scope="global",
                event_type="quest_started",
                payload={"quest_id": "gm_q1", "title": "GM quest"},
            )
        )
        pending = state.get_pending_injected_events()
        assert len(pending) == 1
        assert pending[0]["directive_id"] == "gm:event1"
        assert pending[0]["scope"] == "global"
        assert pending[0]["event_type"] == "quest_started"
        assert pending[0]["payload"] == {"quest_id": "gm_q1", "title": "GM quest"}

    def test_get_pending_injected_events_excludes_disabled(self):
        """Disabled inject-event directives should not appear in pending events."""
        state = GMDirectiveState()
        d = InjectEventDirective(
            directive_id="gm:spawn",
            directive_type="inject_event",
            scope="scene",
            event_type="npc_spawned",
            payload={"npc_id": "merchant"},
            enabled=False,
        )
        state.add_directive(d)

        pending = state.get_pending_injected_events()
        assert pending == []

    def test_get_pending_injected_events_deep_copies_payload(self):
        """Payload should be deep-copied to prevent mutation."""
        state = GMDirectiveState()
        state.add_directive(
            InjectEventDirective(
                directive_id="gm:spawn",
                directive_type="inject_event",
                scope="scene",
                event_type="npc_spawned",
                payload={"npc": {"id": "merchant"}},
            )
        )

        pending = state.get_pending_injected_events()
        pending[0]["payload"]["npc"]["id"] = "CHANGED"

        second_call = state.get_pending_injected_events()
        assert second_call[0]["payload"]["npc"]["id"] == "merchant"

    def test_keep_npc_alive_uses_command_thread_id(self):
        """keep_npc_alive command should respect thread_id from command dict."""
        proc = GMCommandProcessor()
        gm = GMDirectiveState()
        result = proc.apply_command(
            {"command": "keep_npc_alive", "thread_id": "custom_thread"}, gm, MockCoherenceCore(),
        )
        assert result["ok"] is True
        directive = gm.list_directives()[0]
        assert directive.thread_id == "custom_thread"

    def test_keep_npc_alive_includes_placeholder_note(self):
        """keep_npc_alive should note this is a deterministic placeholder."""
        proc = GMCommandProcessor()
        gm = GMDirectiveState()
        proc.apply_command(
            {"command": "keep_npc_alive"}, gm, MockCoherenceCore(),
        )
        directive = gm.list_directives()[0]
        assert "note" in directive.metadata
        assert "deterministic placeholder" in directive.metadata["note"].lower()
