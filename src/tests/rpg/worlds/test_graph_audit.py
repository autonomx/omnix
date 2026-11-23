"""A world graph audit's error lists its issues' fields, and the registry names each audit with its report and gate."""
from __future__ import annotations

from dataclasses import dataclass
from types import SimpleNamespace

from app.apps.rpg.genesis.worlds import generation_compilation
from app.apps.rpg.genesis.worlds.generation_conflict_portfolio import ConflictPortfolioCompilationError
from app.apps.rpg.genesis.worlds.generation_named_claims import ObjectiveNamedClaimCompilationError
from app.apps.rpg.genesis.worlds.generation_starter_region import StarterRegionCompilationError
from app.apps.rpg.genesis.worlds.graph_audit import GraphAudit, GraphAuditError


@dataclass(frozen=True)
class _Issue:
    code: str
    path: str
    anchor: str = ""
    count: int = 0
    entity_ratio: float = 0.0
    claim: object = None

    def as_dict(self) -> dict[str, str]:
        return {"code": self.code, "path": self.path}


def test_the_message_is_the_code_then_each_issue_s_fields() -> None:
    error = StarterRegionCompilationError([_Issue("gap", "a.b"), _Issue("loop", "c")])
    assert str(error) == "starter_region_integrity_failed:gap:a.b;loop:c"
    assert error.as_dict() == {"ok": False, "code": "starter_region_integrity_failed",
                               "issues": [{"code": "gap", "path": "a.b"}, {"code": "loop", "path": "c"}]}
    assert isinstance(error, ValueError) and error.issues == (_Issue("gap", "a.b"), _Issue("loop", "c"))


def test_a_field_can_be_an_attribute_path_or_carry_a_format() -> None:
    ratio = ConflictPortfolioCompilationError([_Issue("dominant", "", anchor="war", count=3, entity_ratio=2 / 3)])
    assert str(ratio) == "conflict_portfolio_integrity_failed:dominant:war:3:0.6667"
    claim = SimpleNamespace(subject_id="npc_1", predicate="rules", mentioned_name="Ash")
    named = ObjectiveNamedClaimCompilationError([_Issue("unresolved", "", claim=claim)])
    assert str(named) == "objective_named_claim_integrity_failed:unresolved:npc_1:rules:Ash"


def test_every_registered_audit_is_a_graph_audit_with_a_unique_name() -> None:
    audits = generation_compilation._graph_audits()
    assert all(isinstance(audit, GraphAudit) for audit in audits)
    names = [name for name, _report, _require in audits]
    assert len(names) == len(set(names)) == 26


def test_each_audit_module_s_error_is_a_graph_audit_error() -> None:
    import importlib
    import inspect
    from pathlib import Path

    folder = Path(generation_compilation.__file__).parent
    errors = []
    for path in sorted(folder.glob("generation_*.py")):
        module = importlib.import_module(f"app.apps.rpg.genesis.worlds.{path.stem}")
        errors += [value for name, value in vars(module).items()
                   if name.endswith("CompilationError") and inspect.isclass(value) and value.__module__ == module.__name__]
    shells = [error.__name__ for error in errors if not issubclass(error, GraphAuditError)]
    # The duplicate-canon gate lists its duplicates, not issues, and keeps its own message.
    assert shells == ["DuplicateCanonCompilationError"]
