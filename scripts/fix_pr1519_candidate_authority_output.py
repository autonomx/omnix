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
print(f"normalized generated path literals in {changed} files")
