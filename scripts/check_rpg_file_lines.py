"""Check RPG source and test files for excessive line counts.

Default target areas:
  - src/app/rpg
  - src/tests/rpg

The script prints files whose line count is greater than the configured limit and
exits with status 1 when any oversized files are found. This makes it suitable
for local audits and CI gates.
"""
from __future__ import annotations

import argparse
import json
import sys
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Iterable, Sequence

DEFAULT_LIMIT = 1000
DEFAULT_PATHS = (
    Path("src/app/rpg"),
    Path("src/tests/rpg"),
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


@dataclass(frozen=True)
class FileLineResult:
    path: str
    lines: int
    limit: int
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
        if line_count > limit:
            results.append(
                FileLineResult(
                    path=_relative_to_root(resolved, root),
                    lines=line_count,
                    limit=limit,
                    over_by=line_count - limit,
                )
            )
    return sorted(results, key=lambda item: (-item.lines, item.path))


def build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Check RPG source/test files for files over a line-count limit.")
    parser.add_argument(
        "paths",
        nargs="*",
        type=Path,
        default=list(DEFAULT_PATHS),
        help="Paths to scan. Defaults to src/app/rpg and src/tests/rpg.",
    )
    parser.add_argument("--limit", type=int, default=DEFAULT_LIMIT, help="Maximum allowed line count. Defaults to 1000.")
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
    if args.json:
        print(json.dumps([asdict(item) for item in oversized], indent=2, sort_keys=True))
    elif oversized:
        print(f"RPG file line audit failed: {len(oversized)} file(s) exceed {args.limit} lines.")
        for item in oversized:
            print(f"{item.lines:5d} lines  +{item.over_by:4d}  {item.path}")
    else:
        print(f"RPG file line audit passed: no files exceed {args.limit} lines.")
    return 1 if oversized else 0


if __name__ == "__main__":
    raise SystemExit(main())
