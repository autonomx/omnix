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
