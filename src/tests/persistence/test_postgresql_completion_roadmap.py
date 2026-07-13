from __future__ import annotations

from pathlib import Path


_REPOSITORY_ROOT = Path(__file__).resolve().parents[3]
_ROADMAP = _REPOSITORY_ROOT / "docs" / "CENTRALIZED_POSTGRESQL_COMPLETION_FIXES_ROADMAP.md"


def test_completion_roadmap_declares_all_corrective_phases() -> None:
    text = _ROADMAP.read_text(encoding="utf-8")

    for phase in range(9):
        assert f"C{phase} —" in text


def test_completion_roadmap_keeps_release_gates_and_exact_head_policy() -> None:
    text = _ROADMAP.read_text(encoding="utf-8")

    assert "Gate A — Ready to activate PostgreSQL authority" in text
    assert "Gate B — Ready to reopen writes" in text
    assert "Gate C — Centralization complete" in text
    assert "exact-head" in text
    assert "Failures are patched on the same branch before the next phase starts" in text


def test_completion_roadmap_links_authoritative_operational_documents() -> None:
    text = _ROADMAP.read_text(encoding="utf-8")

    expected_paths = {
        "docs/CENTRALIZED_POSTGRESQL_ARCHITECTURE_ROADMAP.md",
        "docs/architecture/ADR-0001-centralized-postgresql-authority.md",
        "docs/architecture/PERSISTENCE_INVENTORY.md",
        "docs/architecture/LOCAL_POSTGRESQL_OPERATIONS.md",
        "docs/architecture/POSTGRESQL_CUTOVER_RUNBOOK.md",
        "docs/architecture/POSTGRESQL_RUNTIME_RETIREMENT.md",
    }

    for path in expected_paths:
        assert path in text
