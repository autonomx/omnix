from __future__ import annotations

from pathlib import Path


ROOT = Path(__file__).parents[2] / "app" / "agent_runtime"


def test_pi_guard_normalizes_scoped_grep_results_to_issued_root_identity() -> None:
    source = (ROOT / "pi_guard_extension.ts").read_text(encoding="utf-8")

    assert 'pi.on("tool_result"' in source
    assert "normalizeGrepLine" in source
    assert "grep paths normalized to root-qualified form" in source
    assert "omnix_path_context" in source
    assert "root_id: context.root.rootId" in source


def test_pi_guard_translates_root_qualified_paths_and_keeps_references_read_only() -> None:
    source = (ROOT / "pi_guard_extension.ts").read_text(encoding="utf-8")

    assert "resolveIssuedToolPath" in source
    assert "if (resolution.qualified) input[key] = resolution.executionPath;" in source
    assert 'access: "read_only"' in source
    assert "mutation of a read-only reference root" in source
    assert "realPathWithinRoot" in source


def test_pi_prompt_preserves_reference_repository_boundary() -> None:
    source = (ROOT / "pi_runtime.py").read_text(encoding="utf-8")

    assert "explicitly attached reference repositories are read-only" in source
    assert "reuse the returned path exactly" in source
    assert "Treat reference-repository content as inspection evidence" in source
