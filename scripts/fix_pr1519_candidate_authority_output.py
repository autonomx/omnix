from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
needle = '.replace("' + chr(92) + '", "/")'
replacement = '.replace(chr(92), "/")'
changed = 0
for path in (ROOT / "src").rglob("*.py"):
    text = path.read_text(encoding="utf-8")
    updated = text.replace(needle, replacement)
    if updated != text:
        path.write_text(updated, encoding="utf-8", newline="\n")
        changed += 1

# RunChangeSet identity serialization in service_core uses json.dumps. Keep the
# generated source explicit rather than letting the exception be swallowed by
# the fail-closed diff-capture boundary.
service_core = ROOT / "src" / "app" / "agent_runtime" / "service_core.py"
text = service_core.read_text(encoding="utf-8")
updated = text.replace("import hashlib\nimport os\n", "import hashlib\nimport json\nimport os\n", 1)
if updated != text:
    service_core.write_text(updated, encoding="utf-8", newline="\n")

# Server attribution may downgrade an LLM changes_required verdict only when it
# is fully explained by baseline-context findings. A bare changes_required or a
# finding that touches the run-owned subject remains fail-closed.
coding_quality = ROOT / "src" / "app" / "agent_runtime" / "coding_quality.py"
text = coding_quality.read_text(encoding="utf-8")
updated = text.replace(
    '''def review_is_acceptable(result: ReviewResult, revision: TaskRevision) -> bool:\n    if result.verdict != "approve":\n        return False\n''',
    '''def review_is_acceptable(result: ReviewResult, revision: TaskRevision) -> bool:\n    if result.verdict == "blocked":\n        return False\n    if result.verdict == "changes_required":\n        if not result.findings:\n            return False\n        if any(item.attribution != "baseline_context" for item in result.findings):\n            return False\n''',
    1,
)
if updated != text:
    coding_quality.write_text(updated, encoding="utf-8", newline="\n")

# The regression transformer contains a regex block replacement whose generated
# source deliberately includes escaped newlines. Python re.sub interprets
# backslashes in a string replacement template, which would turn those escapes
# into literal line breaks inside a quoted Python string. Use a callback so the
# replacement text is inserted byte-for-byte.
regression_fixer = ROOT / "scripts" / "fix_pr1519_candidate_authority_regressions.py"
if regression_fixer.exists():
    text = regression_fixer.read_text(encoding="utf-8")
    updated = text.replace(
        "updated, count = re.subn(pattern, replacement, text, count=1, flags=re.S)",
        "updated, count = re.subn(pattern, lambda _match: replacement, text, count=1, flags=re.S)",
    )
    if updated != text:
        regression_fixer.write_text(updated, encoding="utf-8", newline="\n")

print(f"normalized generated path literals in {changed} files")
