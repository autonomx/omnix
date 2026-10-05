"""Rewrite module paths after a pure ``git mv`` (ADR-0016, PA-5).

    python scripts/rewrite_imports.py --map app.old.pkg=app.new.pkg [--map ...] [--check]

Idempotent. In tracked Python files it rewrites, from AST positions:

- ``import`` and ``from ... import`` statements (absolute ones; relative imports
  move with their package);
- string literals that are a mapped module path or start with one followed by
  ``.`` or ``:`` (``import_module`` targets, ``monkeypatch`` strings, catalog
  entries such as ``"app.pkg.feature:FEATURE"``).

In other tracked text files (docs, workflows, configuration, scripts) it
rewrites the dotted path and its ``src/`` file path (``src/app/old/pkg``).
``--check`` lists what would change and exits 1 if anything would.
"""
from __future__ import annotations

import argparse
import ast
import re
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
TEXT_SUFFIXES = {".md", ".toml", ".yml", ".yaml", ".json", ".bat", ".cmd", ".ps1", ".sh", ".txt", ".ini", ".cfg",
                 ".ts", ".tsx", ".mjs", ".js", ".html", ".sql", ".dockerfile"}
TEXT_NAMES = {"Dockerfile", "Makefile", ".gitignore", ".dockerignore", "CODEOWNERS"}
# Records of the past (roadmaps, progress, decisions, changelog) and generated measurements: never rewritten.
EXCLUDED = ("docs/measurements/", "docs/roadmap/", "docs/ENTERPRISE_ARCHITECTURE_", "docs/PLATFORM_ARCHITECTURE_ROADMAP_",
            "CHANGELOG.md", "resources/architecture/metrics-baseline.json",
            "resources/architecture/runtime-metrics.json", "resources/architecture/lint-baseline.json")


def _mapped(name: str, mapping: list[tuple[str, str]]) -> str | None:
    for old, new in mapping:
        if name == old:
            return new
        for separator in (".", ":"):
            if name.startswith(old + separator):
                return new + name[len(old):]
    return None


def _line_offsets(source: str) -> list[int]:
    # Lines as the parser counts them: split on "\n" only (a "\r" stays at the end of its line).
    offsets, total = [0], 0
    for line in source.split("\n"):
        total += len(line.encode("utf-8")) + 1
        offsets.append(total)
    return offsets


def rewrite_python(source: str, mapping: list[tuple[str, str]]) -> str:
    """The source with mapped module paths rewritten at their AST positions."""
    try:
        tree = ast.parse(source)
    except SyntaxError:
        return source
    raw = source.encode("utf-8")
    offsets = _line_offsets(source)
    edits: list[tuple[int, int, bytes]] = []

    def span(node: ast.AST) -> tuple[int, int]:
        return (offsets[node.lineno - 1] + node.col_offset, offsets[node.end_lineno - 1] + node.end_col_offset)

    def replace_name(start: int, end: int, old_name: str) -> None:
        segment = raw[start:end]
        new_name = _mapped(old_name, mapping)
        if new_name is None:
            return
        index = segment.find(old_name.encode("utf-8"))
        if index >= 0:
            edits.append((start + index, start + index + len(old_name.encode("utf-8")), new_name.encode("utf-8")))

    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom) and node.level == 0 and node.module:
            start, end = span(node)
            head_end = raw.find(b" import", start, end)
            replace_name(start, head_end if head_end > 0 else end, node.module)
        elif isinstance(node, ast.Import):
            for alias in node.names:
                start, end = span(alias)
                replace_name(start, end, alias.name)
        elif isinstance(node, ast.Constant) and isinstance(node.value, str) and "\n" in node.value:
            # Docstrings and other prose: dotted and src/ paths, as in a text file.
            start, end = span(node)
            segment = raw[start:end].decode("utf-8")
            updated = rewrite_text(segment, mapping)
            if updated != segment:
                edits.append((start, end, updated.encode("utf-8")))
        elif isinstance(node, ast.Constant) and isinstance(node.value, str):
            new_value = _mapped(node.value, mapping)
            if new_value is not None:
                start, end = span(node)
                segment = raw[start:end]
                index = segment.find(node.value.encode("utf-8"))
                if index >= 0:
                    edits.append((start + index, start + index + len(node.value.encode("utf-8")), new_value.encode("utf-8")))
    for start, end, value in sorted(set(edits), reverse=True):
        raw = raw[:start] + value + raw[end:]
    return raw.decode("utf-8")


def rewrite_text(text: str, mapping: list[tuple[str, str]]) -> str:
    for old, new in mapping:
        text = re.sub(rf"(?<![\w.]){re.escape(old)}(?=[.:\s'\"`)\],/]|$)", new, text, flags=re.M)
        old_path, new_path = "src/" + old.replace(".", "/"), "src/" + new.replace(".", "/")
        text = re.sub(rf"(?<![\w/]){re.escape(old_path)}\.py\b", new_path + ".py", text)
        text = re.sub(rf"(?<![\w/]){re.escape(old_path)}(?=[/\s'\"`)\],:]|$)", new_path, text, flags=re.M)
        text = text.replace(old_path.replace("/", "\\") + "\\", new_path.replace("/", "\\") + "\\")
    return text


def tracked_files() -> list[Path]:
    names = subprocess.run(["git", "ls-files", "-z"], cwd=ROOT, capture_output=True, check=True).stdout.decode().split("\0")
    return [ROOT / name for name in names if name]


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--map", action="append", required=True, metavar="OLD=NEW")
    parser.add_argument("--check", action="store_true")
    args = parser.parse_args(argv)
    mapping = [tuple(item.split("=", 1)) for item in args.map]
    if any(len(pair) != 2 or not pair[0] or not pair[1] for pair in mapping):
        parser.error("--map takes OLD=NEW")
    mapping.sort(key=lambda pair: -len(pair[0]))  # the most specific prefix first
    changed = []
    for path in tracked_files():
        if not path.is_file() or path.relative_to(ROOT).as_posix().startswith(EXCLUDED):
            continue
        is_python = path.suffix == ".py"
        if not is_python and path.suffix.lower() not in TEXT_SUFFIXES and path.name not in TEXT_NAMES:
            continue
        try:
            source = path.read_bytes().decode("utf-8")  # line endings kept as they are
        except (UnicodeDecodeError, OSError):
            continue
        if not any(old in source or "src/" + old.replace(".", "/") in source for old, _ in mapping):
            continue
        updated = rewrite_python(source, mapping) if is_python else rewrite_text(source, mapping)
        if updated != source:
            changed.append(path.relative_to(ROOT).as_posix())
            if not args.check:
                path.write_bytes(updated.encode("utf-8"))
    for name in changed:
        print(("would rewrite " if args.check else "rewrote ") + name)
    return 1 if args.check and changed else 0


if __name__ == "__main__":
    raise SystemExit(main())
