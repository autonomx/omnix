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

# The regression transformer contains a regex block replacement whose generated
# source deliberately includes escaped newlines. Python re.sub interprets
# backslashes in a string replacement template, which would turn those escapes
# into literal line breaks inside a quoted Python string. Use a callback so the
# replacement text is inserted byte-for-byte. Also keep reviewer verdict
# semantics fail-closed unless a changes_required verdict is fully explained by
# findings that Omnix deterministically attributes to baseline-only context.
regression_fixer = ROOT / "scripts" / "fix_pr1519_candidate_authority_regressions.py"
if regression_fixer.exists():
    text = regression_fixer.read_text(encoding="utf-8")
    updated = text.replace(
        "updated, count = re.subn(pattern, replacement, text, count=1, flags=re.S)",
        "updated, count = re.subn(pattern, lambda _match: replacement, text, count=1, flags=re.S)",
    )
    updated = updated.replace(
        '''    ''' + "'''" + '''def review_is_acceptable(result: ReviewResult, revision: TaskRevision) -> bool:\n    if result.verdict == "blocked":\n        return False\n''' + "'''" + ''',\n''',
        '''    ''' + "'''" + '''def review_is_acceptable(result: ReviewResult, revision: TaskRevision) -> bool:\n    if result.verdict == "blocked":\n        return False\n    if result.verdict == "changes_required":\n        if not result.findings:\n            return False\n        if any(item.attribution != "baseline_context" for item in result.findings):\n            return False\n''' + "'''" + ''',\n''',
    )
    if updated != text:
        regression_fixer.write_text(updated, encoding="utf-8", newline="\n")

print(f"normalized generated path literals in {changed} files")
