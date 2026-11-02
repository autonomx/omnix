"""The RPG modules a turn executes, measured over the playthrough suite (RQ-0.7).

    python scripts/rpg_turn_path.py [--write] [pytest paths...]

Runs the playthrough suite (``src/tests/rpg/playthrough`` and the published-world golden by default) in this
process under coverage.py. A module of ``app.apps.rpg`` is on the turn path when one of its functions is
called while a state-changing request is handled: the turn route
(``turn_pipeline._execute_foreground_rpg_turn``, which the loadout's actions and the tactical move and attack take
too; a profile hook on the request's thread: work the request hands to another thread is not counted).
Coverage records which lines of each module ran anywhere in the suite.

With ``--write`` it stores the list as ``[rpg_turn_path] modules`` in resources/architecture/layers.toml and
writes ``docs/measurements/rpg-unexecuted-modules-<date>.json``: the RPG modules no scenario imports, and
those imported whose functions never run (input to RQ-2.10). PostgreSQL is required, as for the suite
(``OMNIX_DATABASE_URL`` and ``OMNIX_TEST_DATABASE_URL``). Without ``--write`` it prints a summary only.
"""
from __future__ import annotations

import argparse
import ast
import inspect
import json
import os
import re
import sys
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
RPG = ROOT / "src" / "app" / "apps" / "rpg"
LAYERS = ROOT / "resources" / "architecture" / "layers.toml"
DEFAULT_SUITE = ("src/tests/rpg/playthrough", "src/tests/characterization/test_rpg_published_world_golden.py")
# Where a state-changing request is handled: (module, attribute) wrapped to record the turn path.
TURN_ENTRY_POINTS = (
    ("app.apps.rpg.edge.api.turn_pipeline", "_execute_foreground_rpg_turn"),
)


def module_of(path: Path) -> str:
    relative = path.resolve().relative_to(ROOT / "src").with_suffix("")
    parts = list(relative.parts)
    if parts[-1] == "__init__":
        parts.pop()
    return ".".join(parts)


def rpg_sources() -> dict[str, Path]:
    return {module_of(path): path for path in sorted(RPG.rglob("*.py")) if "__pycache__" not in path.parts}


def function_body_lines(path: Path) -> set[int]:
    """Lines inside function and method bodies (what runs when the module's code is called, not imported)."""
    lines: set[int] = set()
    for node in ast.walk(ast.parse(path.read_text(encoding="utf-8"), filename=str(path))):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            for statement in node.body:
                lines.update(range(statement.lineno, (statement.end_lineno or statement.lineno) + 1))
    return lines


class TurnPathPlugin:
    """Records the RPG modules whose functions are called while a state-changing request is handled.

    The request runs on a worker thread; a profile hook set on that thread for the request's duration sees
    every Python function call (coverage.py keeps the line trace for the whole run).
    """

    def __init__(self) -> None:
        self.files: set[str] = set()
        self._rpg = str(RPG).casefold()

    def pytest_sessionstart(self, session) -> None:
        import importlib

        for module_name, attribute in TURN_ENTRY_POINTS:
            module = importlib.import_module(module_name)
            setattr(module, attribute, self._measured(getattr(module, attribute)))

    def _profile(self, frame, event, arg) -> None:
        # A function's code only: a module's top level (run by an import the turn makes) or a class body is no call
        # into the module, though the profile sees both as "call".
        if event == "call" and frame.f_code.co_flags & inspect.CO_OPTIMIZED:
            filename = frame.f_code.co_filename
            if filename not in self.files and filename.casefold().startswith(self._rpg):
                self.files.add(filename)

    def _measured(self, function):
        plugin = self

        def measured(*args, **kwargs):
            outer = sys.getprofile()
            sys.setprofile(plugin._profile)
            try:
                return function(*args, **kwargs)
            finally:
                sys.setprofile(outer)

        measured.__wrapped__ = function
        return measured


def measure(suite: list[str]) -> tuple[set[str], dict[str, set[int]]]:
    """(the RPG modules a turn calls into, the lines each RPG module ran anywhere in the suite)."""
    import coverage
    import pytest

    plugin = TurnPathPlugin()
    cov = coverage.Coverage(data_file=None, source=[str(RPG)], branch=False)
    cov.start()
    try:
        status = pytest.main([*suite, "-q", "-n", "0", "-p", "no:cacheprovider"], plugins=[plugin])
    finally:
        cov.stop()
    if status not in (0, 1):
        raise SystemExit(f"pytest did not run the suite (exit {status})")
    data = cov.get_data()
    sources = {str(path.resolve()).casefold(): name for name, path in rpg_sources().items()}
    anywhere = {
        sources[key]: set(data.lines(filename) or ())
        for filename in data.measured_files()
        if (key := str(Path(filename).resolve()).casefold()) in sources and data.lines(filename)
    }
    in_turn = {sources[key] for filename in plugin.files if (key := str(Path(filename).resolve()).casefold()) in sources}
    return in_turn, anywhere


def write_turn_path(modules: list[str], suite: list[str]) -> None:
    """Replace (or append) the [rpg_turn_path] section of layers.toml."""
    body = "\n".join(f'  "{name}",' for name in modules)
    section = (
        "# RQ-0.7: the app.apps.rpg modules a turn executes (a function of theirs called while the turn route, a\n"
        "# tactical move or attack, or a loadout action is handled), measured over the playthrough suite by\n"
        "# scripts/rpg_turn_path.py --write, and refreshed when a phase closes. Suite:\n"
        + "".join(f"#   {path}\n" for path in suite)
        + f"[rpg_turn_path]\nmodules = [\n{body}\n]\n"
    )
    text = LAYERS.read_text(encoding="utf-8")
    pattern = re.compile(r"(?:^#[^\n]*\n)*^\[rpg_turn_path\]\nmodules = \[\n(?:[^\]]*\n)?\]\n", re.MULTILINE)
    if pattern.search(text):
        text = pattern.sub(lambda _: section, text, count=1)
    else:
        text = text.rstrip("\n") + "\n\n" + section
    LAYERS.write_text(text, encoding="utf-8")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--write", action="store_true", help="update layers.toml and write the measurement")
    parser.add_argument("suite", nargs="*", default=list(DEFAULT_SUITE))
    args = parser.parse_args(argv)
    if not os.environ.get("OMNIX_TEST_DATABASE_URL"):
        print("OMNIX_TEST_DATABASE_URL is required: the playthrough suite runs on PostgreSQL", file=sys.stderr)
        return 2
    os.chdir(ROOT)
    sys.path.insert(0, str(ROOT / "src"))

    in_turn, anywhere = measure(args.suite)
    sources = rpg_sources()
    turn_path = sorted(in_turn)
    never_imported = sorted(name for name in sources if not anywhere.get(name))
    never_called = sorted(
        name for name in sources
        if name in anywhere and function_body_lines(sources[name])
        and not (anywhere[name] & function_body_lines(sources[name]))
    )
    print(f"{len(sources)} RPG modules: {len(turn_path)} on the turn path, {len(never_imported)} never imported, "
          f"{len(never_called)} imported with no function run")
    if args.write:
        write_turn_path(turn_path, args.suite)
        today = date.today().isoformat()
        out = ROOT / "docs" / "measurements" / f"rpg-unexecuted-modules-{today}.json"
        out.write_text(json.dumps({
            "date": today,
            "method": ("python scripts/rpg_turn_path.py --write: coverage.py over " + ", ".join(args.suite)
                       + "; a module is executed when any of its lines ran during the suite"),
            "rpg_modules": len(sources),
            "turn_path_modules": len(turn_path),
            "never_imported": never_imported,
            "imported_but_no_function_ran": never_called,
        }, indent=2) + "\n", encoding="utf-8")
        print(f"wrote [rpg_turn_path] to {LAYERS.relative_to(ROOT)} and {out.relative_to(ROOT)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
