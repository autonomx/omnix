from __future__ import annotations

from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SEARCH_ROOTS = (
    ROOT / "src" / "app",
    ROOT / "src" / "tests",
    ROOT / "tests",
    ROOT / "scripts",
)

# Longest/specialized names first so broad replacements cannot partially alter
# a more specific identifier.
REPLACEMENTS = (
    ("OwnerAwareSQLiteMemoryRepository", "OwnerAwareInMemoryMemoryRepository"),
    ("BaseSQLiteChatSessionStore", "BaseInMemoryChatSessionStore"),
    ("SQLiteConversationSummaryRepository", "InMemoryConversationSummaryRepository"),
    ("SQLiteProviderModelRefreshStore", "InMemoryProviderModelRefreshStore"),
    ("SQLiteModelResidencyStore", "InMemoryModelResidencyStore"),
    ("SQLiteHistorySearchService", "InMemoryHistorySearchService"),
    ("SQLiteChatSessionStore", "InMemoryChatSessionStore"),
    ("SQLiteMemoryRepository", "InMemoryMemoryRepository"),
    ("SQLiteChatRepository", "InMemoryChatRepository"),
    ("SQLiteJobStore", "InMemoryJobStore"),
)

NEW_NAMES = tuple(new for _, new in REPLACEMENTS)


def _clean_lines(text: str) -> str:
    lines = text.splitlines()
    cleaned: list[str] = []
    seen_symbol_entries: set[str] = set()
    self_assignments = {f"{name} = {name}" for name in NEW_NAMES}
    symbol_entries = {
        f"{name}," for name in NEW_NAMES
    } | {
        f'"{name}",' for name in NEW_NAMES
    } | {
        f"'{name}'," for name in NEW_NAMES
    }

    for line in lines:
        stripped = line.strip()
        if stripped in self_assignments:
            continue
        if stripped in symbol_entries:
            if stripped in seen_symbol_entries:
                continue
            seen_symbol_entries.add(stripped)
        cleaned.append(line)
    return "\n".join(cleaned) + ("\n" if text.endswith("\n") else "")


def main() -> int:
    changed: list[str] = []
    for root in SEARCH_ROOTS:
        if not root.exists():
            continue
        for path in sorted(root.rglob("*.py")):
            original = path.read_text(encoding="utf-8")
            updated = original
            for old, new in REPLACEMENTS:
                updated = updated.replace(old, new)
            updated = _clean_lines(updated)
            if updated == original:
                continue
            path.write_text(updated, encoding="utf-8")
            changed.append(path.relative_to(ROOT).as_posix())

    print(f"updated {len(changed)} files")
    for path in changed:
        print(path)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
