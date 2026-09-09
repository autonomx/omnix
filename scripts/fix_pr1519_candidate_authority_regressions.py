from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def read(path: str) -> str:
    return (ROOT / path).read_text(encoding="utf-8")


def write(path: str, content: str) -> None:
    (ROOT / path).write_text(content, encoding="utf-8", newline="\n")


def replace_once(path: str, old: str, new: str) -> None:
    text = read(path)
    if old not in text:
        if new in text:
            return
        raise RuntimeError(f"missing regression-fix anchor in {path}: {old[:120]!r}")
    write(path, text.replace(old, new, 1))


# The public pi_runtime wrapper already exposes omnix_plan only for mutating
# coding-quality runs. Do not widen that authority in the stable core merely
# because RunChangeSet adds another extension tool.
replace_once(
    "src/app/agent_runtime/pi_runtime_core.py",
    '''    if "workspace.run_change_set" in spec.capabilities:\n        tools.add("omnix_change_set")\n    if spec.profile == "coding":\n        tools.add("omnix_plan")\n''',
    '''    if "workspace.run_change_set" in spec.capabilities:\n        tools.add("omnix_change_set")\n''',
)

# Existing quality fixtures manually construct a coding RunSpec rather than
# resolving the profile. Keep the fixture authority aligned with the now-issued
# read-only RunChangeSet capability used by independent review.
replace_once(
    "src/tests/agent_runtime/test_coding_quality_phases_20_31.py",
    '''            "workspace.git_diff",\n            "workspace.edit",\n''',
    '''            "workspace.git_diff",\n            "workspace.run_change_set",\n            "workspace.edit",\n''',
)
replace_once(
    "src/tests/agent_runtime/test_coding_quality_phases_20_31.py",
    '''        "workspace.git_diff",\n    }\n''',
    '''        "workspace.git_diff",\n        "workspace.run_change_set",\n    }\n''',
)

# The old blob-store regression asserted the retired workspace.diff name and a
# fake WorkspaceAuthority surface that predates canonical tracked/untracked
# RunChangeSet capture. Preserve the intent: the authoritative patch is durable
# in the blob store, not a machine-local temp file.
replace_once(
    "src/tests/agent_runtime/test_acceptance_authority.py",
    '''        def git_diff(self, paths=None) -> str:\n            assert paths == ["a.txt"]\n            return "diff --git a/a.txt b/a.txt\\n+changed\\n"\n''',
    '''        def git_status_entries(self):\n            return {"a.txt": " M"}\n\n        def git_head(self):\n            return "abc123"\n\n        def git_tracked_diff(self, paths=None) -> str:\n            assert paths == ["a.txt"]\n            return "diff --git a/a.txt b/a.txt\\n+changed\\n"\n\n        def git_diff(self, paths=None) -> str:\n            assert paths == ["a.txt"]\n            return "diff --git a/a.txt b/a.txt\\n+changed\\n"\n''',
)
replace_once(
    "src/tests/agent_runtime/test_acceptance_authority.py",
    '''    assert service.blob_store.storage_key.endswith("/workspace.diff")\n''',
    '''    assert service.blob_store.storage_key.endswith("/run-owned.patch")\n''',
)

# Provenance tests now inspect the canonical diff artifact rather than the
# retired workspace.diff alias. The assertions about run-owned paths and
# baseline conflicts remain unchanged.
path = "src/tests/agent_runtime/test_service_workspace_provenance.py"
text = read(path)
text = text.replace('item.name == "workspace.diff"', 'item.name == "run-change-set.patch"')
write(path, text)

print("candidate authority regression fixes applied")
