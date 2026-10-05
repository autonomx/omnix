"""Check RPG source and test files against the 1,200-line file budget.

Default target areas:
  - src/app/apps/rpg
  - src/tests/unit/rpg

The script prints files whose line count is greater than the configured limit and
exits with status 1 when any oversized files are found. This makes it suitable
for local audits and CI gates.
"""
from __future__ import annotations

import argparse
import json
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Iterable, Sequence

# The repository-wide architecture metrics also track all files over 1,200 lines
# and all functions over 150 lines. This focused gate keeps the RPG line budget
# aligned with that global policy while existing oversize files shrink.
DEFAULT_LIMIT = 1200
DEFAULT_PATHS = (
    Path("src/app/apps/rpg"),
    Path("src/tests/unit/rpg"),
)
DEFAULT_EXTENSIONS = (
    ".py",
    ".ts",
    ".tsx",
    ".js",
    ".jsx",
    ".json",
    ".html",
    ".css",
    ".md",
)
IGNORED_DIR_NAMES = {
    "__pycache__",
    ".mypy_cache",
    ".pytest_cache",
    ".ruff_cache",
    "node_modules",
}

# Existing RPG files above the shared budget may only shrink; new files receive
# no exception. The repository-wide architecture metrics track this debt too.
LINE_DEBT_LIMITS = {
    "src/app/apps/rpg/ai/grounding_validator.py": 1017,
    "src/app/apps/rpg/presentation/dialogue_quality.py": 1251,
    "src/app/apps/rpg/response_generation/production_pipeline.py": 1182,
    "src/app/apps/rpg/session/genesis/campaign_lore_store.py": 1093,
    "src/app/apps/rpg/session/genesis/runtime_lore_materialization.py": 1049,
    "src/app/apps/rpg/worlds/world_images.py": 1126,
    # Single-pass generation landed as one safety-coherent cutover. Keep this
    # ceiling tight so follow-up extraction can only reduce the coordinator.
    "src/app/apps/rpg/worlds/generation_coordinator.py": 1259,
}


@dataclass(frozen=True)
class FileLineResult:
    path: str
    lines: int
    limit: int
    over_by: int


@dataclass(frozen=True)
class FileLineDebt:
    path: str
    lines: int
    debt_limit: int
    over_by: int


def _repo_root() -> Path:
    return Path(__file__).resolve().parents[1]


def _relative_to_root(path: Path, root: Path) -> str:
    try:
        return path.relative_to(root).as_posix()
    except ValueError:
        return path.as_posix()


def _iter_files(paths: Sequence[Path], *, extensions: set[str], root: Path) -> Iterable[Path]:
    for path in paths:
        resolved = path if path.is_absolute() else root / path
        if not resolved.exists():
            continue
        if resolved.is_file():
            if resolved.suffix in extensions:
                yield resolved
            continue
        for child in sorted(resolved.rglob("*")):
            if any(part in IGNORED_DIR_NAMES for part in child.parts):
                continue
            if child.is_file() and child.suffix in extensions:
                yield child


def _count_lines(path: Path) -> int:
    with path.open("r", encoding="utf-8", errors="replace") as handle:
        return sum(1 for _ in handle)


def find_oversized_files(
    paths: Sequence[Path],
    *,
    limit: int = DEFAULT_LIMIT,
    extensions: Sequence[str] = DEFAULT_EXTENSIONS,
    root: Path | None = None,
) -> list[FileLineResult]:
    root = root or _repo_root()
    normalized_extensions = {ext if ext.startswith(".") else f".{ext}" for ext in extensions}
    results = []
    seen: set[Path] = set()
    for path in _iter_files(paths, extensions=normalized_extensions, root=root):
        resolved = path.resolve()
        if resolved in seen:
            continue
        seen.add(resolved)
        line_count = _count_lines(resolved)
        relative_path = _relative_to_root(resolved, root)
        debt_limit = LINE_DEBT_LIMITS.get(relative_path)
        allowed_limit = debt_limit or limit
        if line_count > allowed_limit:
            results.append(
                FileLineResult(
                    path=relative_path,
                    lines=line_count,
                    limit=allowed_limit,
                    over_by=line_count - allowed_limit,
                )
            )
        elif line_count > limit and debt_limit is None:
            results.append(
                FileLineResult(
                    path=relative_path,
                    lines=line_count,
                    limit=limit,
                    over_by=line_count - limit,
                )
            )
    return sorted(results, key=lambda item: (-item.lines, item.path))


def find_line_debt(
    paths: Sequence[Path],
    *,
    limit: int = DEFAULT_LIMIT,
    extensions: Sequence[str] = DEFAULT_EXTENSIONS,
    root: Path | None = None,
) -> list[FileLineDebt]:
    root = root or _repo_root()
    normalized_extensions = {ext if ext.startswith(".") else f".{ext}" for ext in extensions}
    debts = []
    seen: set[Path] = set()
    for path in _iter_files(paths, extensions=normalized_extensions, root=root):
        resolved = path.resolve()
        if resolved in seen:
            continue
        seen.add(resolved)
        relative_path = _relative_to_root(resolved, root)
        debt_limit = LINE_DEBT_LIMITS.get(relative_path)
        if debt_limit is None:
            continue
        line_count = _count_lines(resolved)
        if line_count > limit:
            debts.append(
                FileLineDebt(
                    path=relative_path,
                    lines=line_count,
                    debt_limit=debt_limit,
                    over_by=line_count - limit,
                )
            )
    return sorted(debts, key=lambda item: (-item.lines, item.path))


def build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Check the RPG 1,200-line file budget.")
    parser.add_argument(
        "paths",
        nargs="*",
        type=Path,
        default=list(DEFAULT_PATHS),
        help="Paths to scan. Defaults to src/app/apps/rpg and src/tests/unit/rpg.",
    )
    parser.add_argument("--limit", type=int, default=DEFAULT_LIMIT, help="Maximum allowed line count. Defaults to 1200.")
    parser.add_argument(
        "--extension",
        action="append",
        default=[],
        help="File extension to include. Can be repeated. Defaults to common source/test extensions.",
    )
    parser.add_argument("--json", action="store_true", help="Print machine-readable JSON output.")
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = build_arg_parser().parse_args(argv)
    extensions = tuple(args.extension) if args.extension else DEFAULT_EXTENSIONS
    oversized = find_oversized_files(
        list(args.paths),
        limit=args.limit,
        extensions=extensions,
    )
    debt = find_line_debt(
        list(args.paths),
        limit=args.limit,
        extensions=extensions,
    )
    if args.json:
        print(json.dumps([asdict(item) for item in oversized], indent=2, sort_keys=True))
    elif oversized:
        print(f"RPG file line audit failed: {len(oversized)} file(s) exceed configured limits.")
        for item in oversized:
            print(f"{item.lines:5d} lines  +{item.over_by:4d}  {item.path}  limit={item.limit}")
    else:
        print("RPG file line audit passed: no files exceed configured limits.")
        if debt:
            print(f"Tracked RPG line debt remains: {len(debt)} file(s) above {args.limit} lines.")
            for item in debt:
                print(f"{item.lines:5d} lines  +{item.over_by:4d}  {item.path}  debt_limit={item.debt_limit}")
    return 1 if oversized else 0


if __name__ == "__main__":
    raise SystemExit(main())
