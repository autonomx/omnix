"""Agent runtime SQL lives in repository modules (WP-8.2)."""
from __future__ import annotations

import ast
from pathlib import Path

RUNTIME = Path(__file__).parents[2] / "app" / "agent_runtime"

# Modules that own SQL. Services, routers and supervisors call these; they
# never hand a statement to a connection themselves.
REPOSITORY_MODULES = {
    "coding_quality_repository.py",
    "planning_repository.py",
    "repository.py",
    "resource_grants.py",
    "run_repository_approvals.py",
    "run_repository_capabilities.py",
    "run_repository_commands.py",
    "run_repository_events.py",
    "run_repository_queries.py",
    "run_repository_revisions.py",
    "run_repository_usage.py",
    "run_slots.py",
    "task_graph_repository.py",
    "workflow_repository.py",
}


def _issues_sql(path: Path) -> bool:
    tree = ast.parse(path.read_text(encoding="utf-8"))
    return any(
        isinstance(node, ast.Call)
        and isinstance(node.func, ast.Attribute)
        and node.func.attr in {"execute", "executemany"}
        and node.args
        and isinstance(node.args[0], (ast.Constant, ast.JoinedStr))
        for node in ast.walk(tree)
    )


def test_only_repository_modules_issue_sql() -> None:
    issuing = {
        path.relative_to(RUNTIME).as_posix()
        for path in RUNTIME.rglob("*.py")
        if _issues_sql(path)
    }

    assert issuing - REPOSITORY_MODULES == set()
