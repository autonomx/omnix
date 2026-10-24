"""Measure the RPG production scorecard's static metrics (RQ-0.1).

The RPG production roadmap (docs/RPG_PRODUCTION_ROADMAP_2026-10-23.md, §2)
grades the turn's architecture, content-in-code, intent and determinism areas
by counts this script computes from tracked source only. It never imports
Omnix. Every pattern is stated here and copied into the report, so a later
count is comparable with this one.

Scope. "RPG code" is every tracked, non-test ``.py`` file under
``src/app/apps/rpg`` (migrations are SQL and not counted). "Turn path" is the
module list in ``[rpg_turn_path]`` of ``resources/architecture/layers.toml``
(``modules = [...]``, dotted module names or ``src/`` paths), recorded by
RQ-0.7; until that table exists the turn-path counts are reported as
unavailable. "RPG web code" is every tracked ``.ts``/``.tsx`` file under
``web/src/features/rpg`` except ``api/generated.ts`` and ``*.test.*`` /
``*.spec.*`` files.

Patterns (Python is parsed with ``ast`` unless a regex is named):

- ``state_string_key_reads``: a read of a literal string key from a state
  section, where the receiver is a name or attribute called
  ``simulation_state`` or ``runtime_state``: ``<receiver>["key"]`` in load
  context, or ``<receiver>.get("key", ...)``. Reported as occurrences and
  distinct keys, per section.
- ``save_call_sites``: a call whose callee name (bare or attribute) is
  ``save_session`` or ``save_runtime_session``. Definitions are not calls.
  Reported as call sites and modules.
- ``dict_str_any``: regex ``\\b(?:dict|Dict)\\[\\s*str\\s*,\\s*Any\\s*\\]``
  over the source text (annotations in strings count too). Both spellings
  count, so ``Dict`` -> ``dict`` is not a change; each is also reported.
- ``deepcopy_calls``: a call whose callee name is ``deepcopy``
  (``deepcopy(...)`` or ``copy.deepcopy(...)``).
- ``broad_excepts``: an ``except`` clause whose type is ``Exception`` or a
  tuple containing ``Exception``, and bare ``except:``.
- ``world_specific_names``: regex, case-insensitive, with letters and digits
  (not ``_``) as the word boundary, so ``npc:Bran``, ``npc_bran`` and
  ``demo_glimmerdeep_pass`` match and ``Brandon`` does not:
  ``Rusty Flagon``/``rusty_flagon``, ``Bran``, ``Elara``, ``Aldric``,
  ``Mira``, ``old_mill``/``old mill``, ``Glimmerdeep``. Scope: the
  ``rules``, ``world``, ``session`` and ``narration`` contexts, excluding
  fixture modules (a file name containing ``fixture``). The whole package is
  reported alongside, for reference.
- ``word_list_constants``: a module-level assignment to a name ending in
  ``WORDS``, ``KEYWORDS``, ``VERBS``, ``TERMS``, ``MARKERS`` or ``PHRASES``
  (any case of a leading underscore), by context.
- ``nondeterminism``: a call to a ``random`` module function (the global,
  unseeded generator), ``random.Random()`` without a seed, ``uuid4``,
  ``time.time``, or ``datetime.now``/``datetime.utcnow`` (on ``datetime`` or
  ``datetime.datetime``). Calls are resolved through the module's imports, so
  ``from uuid import uuid4`` counts. ``time.perf_counter``/``monotonic`` are
  durations, not clock reads, and are not counted.
- ``contract_bypass_imports``: an import (at any scope) from one RPG context
  into a module of another context that is not that context's ``contracts``
  module or package. Contexts come from ``[rpg_contexts]`` with AL017's
  longest-entry match. Counted as distinct (importing module, imported module)
  pairs.
- ``python_files_over_1200_lines``: RPG Python files with more than 1,200
  lines (``str.splitlines``).
- ``web_files_over_600_lines``: RPG web files with more than 600 lines.

The shrink-only metrics are also ratchets in ``scripts/architecture_metrics.py``
(``RATCHETS`` below); its baseline (``resources/architecture/metrics-baseline.json``)
holds today's values.
"""

from __future__ import annotations

import argparse
import ast
from collections import Counter
from datetime import date
import hashlib
import json
from pathlib import Path, PurePosixPath
import re
import subprocess
import sys
from typing import Any, Iterable

sys.path.insert(0, str(Path(__file__).resolve().parent))

from architecture_analysis import (  # noqa: E402
    import_aliases, import_target, is_test, load_layers, module_name, qualified_name, tracked_sources,
)

ROOT = Path(__file__).resolve().parents[1]
SCHEMA_VERSION = 1
RPG_ROOT = "src/app/apps/rpg/"
RPG_PACKAGE = "app.apps.rpg"
WEB_ROOT = "web/src/features/rpg/"
STATE_SECTIONS = ("simulation_state", "runtime_state")
SAVE_CALLS = frozenset({"save_session", "save_runtime_session"})
DICT_STR_ANY = re.compile(r"\b(?:dict|Dict)\[\s*str\s*,\s*Any\s*\]")
WORD_LIST_NAME = re.compile(r"(?:WORDS|KEYWORDS|VERBS|TERMS|MARKERS|PHRASES)$")
NAME_CONTEXTS = ("rules", "world", "session", "narration")
_EDGE = r"(?<![A-Za-z0-9]){}(?![A-Za-z0-9])"
WORLD_NAMES: dict[str, re.Pattern[str]] = {
    "Rusty Flagon": re.compile(_EDGE.format(r"rusty[ _]flagon"), re.IGNORECASE),
    "Bran": re.compile(_EDGE.format("bran"), re.IGNORECASE),
    "Elara": re.compile(_EDGE.format("elara"), re.IGNORECASE),
    "Aldric": re.compile(_EDGE.format("aldric"), re.IGNORECASE),
    "Mira": re.compile(_EDGE.format("mira"), re.IGNORECASE),
    "old_mill": re.compile(_EDGE.format(r"old[ _]mill"), re.IGNORECASE),
    "Glimmerdeep": re.compile(_EDGE.format("glimmerdeep"), re.IGNORECASE),
}
CLOCK_CALLS = frozenset({
    "time.time", "datetime.now", "datetime.utcnow", "datetime.datetime.now", "datetime.datetime.utcnow",
})
PYTHON_LINE_LIMIT = 1200
WEB_LINE_LIMIT = 600
# Metric name in architecture_metrics -> (scorecard key, target). Each may only shrink.
RATCHETS: dict[str, tuple[str, int | str]] = {
    "rpg_state_string_key_reads": ("state_string_key_reads", "0 in the turn path"),
    "rpg_save_call_sites": ("save_call_sites", "the commit step and listed exemptions"),
    "rpg_dict_str_any": ("dict_str_any", "ratchet"),
    "rpg_deepcopy_calls": ("deepcopy_calls", "ratchet"),
    "rpg_broad_excepts": ("broad_excepts", "ratchet"),
    "rpg_world_specific_names": ("world_specific_names", 0),
    "rpg_word_list_constants": ("word_list_constants", 0),
    "rpg_nondeterminism_calls": ("nondeterminism", "0 reachable from the turn path"),
    "rpg_contract_bypass_imports": ("contract_bypass_imports", "ratchet"),
    "rpg_python_files_over_1200_lines": ("python_files_over_1200_lines", 0),
    "rpg_web_files_over_600_lines": ("web_files_over_600_lines", 0),
}


def rpg_python(sources: dict[str, str]) -> dict[str, str]:
    return {path: source for path, source in sources.items()
            if path.startswith(RPG_ROOT) and path.endswith(".py") and not is_test(path)}


def rpg_web(sources: dict[str, str]) -> dict[str, str]:
    return {path: source for path, source in sources.items()
            if path.startswith(WEB_ROOT) and path.endswith((".ts", ".tsx"))
            and not re.search(r"\.(?:test|spec)\.tsx?$", path) and not path.endswith("/api/generated.ts")}


def line_count(source: str) -> int:
    return len(source.splitlines())


def _parse(sources: dict[str, str]) -> dict[str, ast.Module]:
    trees = {}
    for path, source in sources.items():
        try:
            trees[path] = ast.parse(source, filename=path)
        except SyntaxError:
            continue
    return trees


class ContextMap:
    """AL017's mapping from an RPG module to its context (longest entry wins)."""

    def __init__(self, config: dict) -> None:
        contexts = config.get("rpg_contexts", {})
        self.order = list(contexts.get("order", []))
        self.entries = {entry: name for name in self.order for entry in contexts.get(name, [])}

    def entry_of(self, module: str) -> str | None:
        prefix = RPG_PACKAGE.split(".")
        parts = module.split(".")
        if parts[: len(prefix)] != prefix or len(parts) <= len(prefix):
            return None
        relative = parts[len(prefix):]
        for size in range(len(relative), 1, -1):
            candidate = ".".join(relative[:size])
            if candidate in self.entries:
                return candidate
        return relative[0]

    def context_of(self, module: str) -> str | None:
        entry = self.entry_of(module)
        return self.entries.get(entry) if entry is not None else None


def _receiver(node: ast.AST) -> str | None:
    if isinstance(node, ast.Name):
        return node.id
    if isinstance(node, ast.Attribute):
        return node.attr
    return None


def _string(node: ast.AST | None) -> str | None:
    return node.value if isinstance(node, ast.Constant) and isinstance(node.value, str) else None


def _callee(node: ast.Call) -> str | None:
    return _receiver(node.func)


def state_reads(tree: ast.AST) -> Iterable[tuple[str, str, int]]:
    """(section, key, line) for each literal string-key read of a state section."""
    for node in ast.walk(tree):
        if isinstance(node, ast.Subscript) and isinstance(node.ctx, ast.Load):
            section, key = _receiver(node.value), _string(node.slice)
        elif (isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute) and node.func.attr == "get"
              and node.args):
            section, key = _receiver(node.func.value), _string(node.args[0])
        else:
            continue
        if section in STATE_SECTIONS and key is not None:
            yield section, key, node.lineno


def save_calls(tree: ast.AST) -> Iterable[int]:
    for node in ast.walk(tree):
        if isinstance(node, ast.Call) and _callee(node) in SAVE_CALLS:
            yield node.lineno


def deepcopy_calls(tree: ast.AST) -> int:
    return sum(isinstance(node, ast.Call) and _callee(node) == "deepcopy" for node in ast.walk(tree))


def broad_excepts(tree: ast.AST) -> int:
    def broad(kind: ast.AST | None) -> bool:
        if kind is None:
            return True
        if isinstance(kind, ast.Tuple):
            return any(broad(item) for item in kind.elts)
        return _receiver(kind) == "Exception"
    return sum(isinstance(node, ast.ExceptHandler) and broad(node.type) for node in ast.walk(tree))


def word_list_constants(tree: ast.Module) -> list[str]:
    names = []
    for node in tree.body:
        targets = node.targets if isinstance(node, ast.Assign) else [node.target] if isinstance(node, ast.AnnAssign) else []
        for target in targets:
            if isinstance(target, ast.Name) and WORD_LIST_NAME.search(target.id.lstrip("_")) and target.id.upper() == target.id:
                names.append(target.id)
    return names


def nondeterministic_calls(tree: ast.AST, path: str) -> Iterable[tuple[str, int]]:
    aliases = import_aliases(tree, path)
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        # Only names bound by an import: a parameter called ``random`` is not the module.
        if (qualified_name(node.func) or "").split(".")[0] not in aliases:
            continue
        name = qualified_name(node.func, aliases) or ""
        if name == "random.Random":
            if not node.args and not any(item.arg in {"x", "seed"} for item in node.keywords):
                yield "random.Random()", node.lineno
        elif name == "random.SystemRandom" or name.startswith("random.") and name.count(".") == 1:
            yield name, node.lineno
        elif name in {"uuid.uuid4", "uuid4"}:
            yield "uuid.uuid4", node.lineno
        elif name in CLOCK_CALLS:
            yield name.removeprefix("datetime.") if name.startswith("datetime.datetime.") else name, node.lineno


def imported_targets(tree: ast.AST, path: str, modules: set[str]) -> set[str]:
    """Every module an import statement names, at any scope, preferring submodules."""
    targets: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            targets.update(item.name for item in node.names)
        elif isinstance(node, ast.ImportFrom):
            base = import_target(node, path)
            for item in node.names:
                candidate = f"{base}.{item.name}"
                targets.add(candidate if candidate in modules else base)
    return targets


def _is_contract(module: str, context: str) -> bool:
    parts = module.split(".")
    prefix = RPG_PACKAGE.split(".") + [context, "contracts"]
    return parts[: len(prefix)] == prefix


def turn_path_modules(config: dict) -> set[str] | None:
    table = config.get("rpg_turn_path")
    if not isinstance(table, dict):
        return None
    entries = table.get("modules", [])
    return {module_name(entry) if entry.endswith(".py") or "/" in entry else entry for entry in entries}


def _sorted_counts(counter: Counter) -> dict[str, int]:
    return dict(sorted(counter.items()))


def measure(sources: dict[str, str], config: dict) -> dict[str, Any]:
    python = rpg_python(sources)
    web = rpg_web(sources)
    trees = _parse(python)
    contexts = ContextMap(config)
    modules = {module_name(path) for path in trees}
    turn_path = turn_path_modules(config)

    def context(path: str) -> str:
        return contexts.context_of(module_name(path)) or "<none>"

    # State reads.
    reads: dict[str, list[tuple[str, str, int]]] = {}
    for path, tree in trees.items():
        reads[path] = list(state_reads(tree))

    def read_summary(paths: Iterable[str]) -> dict[str, Any]:
        summary: dict[str, Any] = {}
        total = 0
        for section in STATE_SECTIONS:
            keys = Counter(key for path in paths for found, key, _ in reads[path] if found == section)
            summary[section] = {"occurrences": sum(keys.values()), "distinct_keys": len(keys), "keys": _sorted_counts(keys)}
            total += sum(keys.values())
        summary["occurrences"] = total
        summary["distinct_keys"] = sum(summary[section]["distinct_keys"] for section in STATE_SECTIONS)
        return summary

    state = read_summary(trees)
    in_turn_path = sorted(path for path in trees if turn_path is not None and module_name(path) in turn_path)
    state["turn_path"] = read_summary(in_turn_path) if turn_path is not None else "unavailable: no [rpg_turn_path] in layers.toml"

    # Saves.
    save_sites = sorted(f"{path}:{line}" for path, tree in trees.items() for line in save_calls(tree))
    save_modules = sorted({site.rsplit(":", 1)[0] for site in save_sites})

    # Counts by context.
    dict_any = Counter({path: len(DICT_STR_ANY.findall(source)) for path, source in python.items()})
    copies = Counter({path: deepcopy_calls(tree) for path, tree in trees.items()})
    excepts = Counter({path: broad_excepts(tree) for path, tree in trees.items()})

    def by_context(counter: Counter) -> dict[str, int]:
        result: Counter = Counter()
        for path, count in counter.items():
            if count:
                result[context(path)] += count
        return _sorted_counts(result)

    # World-specific names.
    def name_hits(paths: Iterable[str]) -> dict[str, Any]:
        per_name: dict[str, dict[str, int]] = {}
        files: set[str] = set()
        total = 0
        for name, pattern in WORLD_NAMES.items():
            hits = Counter()
            for path in paths:
                count = len(pattern.findall(python[path]))
                if count:
                    hits[path] = count
            per_name[name] = {"hits": sum(hits.values()), "files": len(hits)}
            files.update(hits)
            total += sum(hits.values())
        return {"hits": total, "files": len(files), "by_name": per_name, "file_list": sorted(files)}

    gated_paths = [path for path in python if context(path) in NAME_CONTEXTS
                   and "fixture" not in PurePosixPath(path).name]
    names = name_hits(gated_paths)
    package_names = name_hits(list(python))
    package_names.pop("file_list")

    # Word lists.
    word_lists = {path: word_list_constants(tree) for path, tree in trees.items()}
    word_list_sites = sorted(f"{path}:{name}" for path, found in word_lists.items() for name in found)
    word_by_context = Counter(context(site.rsplit(":", 1)[0]) for site in word_list_sites)
    turn_path_contexts = {"session", "rules", "world", "narration"}

    # Nondeterminism.
    nondeterminism = sorted(f"{path}:{line}:{name}" for path, tree in trees.items()
                            for name, line in nondeterministic_calls(tree, path))
    nondeterminism_kinds = Counter(site.rsplit(":", 1)[1] for site in nondeterminism)
    nondeterminism_turn_path = (
        [site for site in nondeterminism if module_name(site.split(":", 1)[0]) in turn_path]
        if turn_path is not None else None
    )

    # Cross-context imports that bypass a contracts module.
    bypass: set[str] = set()
    for path, tree in trees.items():
        source_module = module_name(path)
        source_context = contexts.context_of(source_module)
        if source_context is None:
            continue
        for target in imported_targets(tree, path, modules):
            target_context = contexts.context_of(target)
            if target_context is None or target_context == source_context or _is_contract(target, target_context):
                continue
            bypass.add(f"{source_module}->{target}")
    bypass_pairs = Counter()
    for pair in bypass:
        source, target = pair.split("->")
        bypass_pairs[f"{contexts.context_of(source)}->{contexts.context_of(target)}"] += 1

    # File sizes.
    big_python = sorted((path, line_count(source)) for path, source in python.items() if line_count(source) > PYTHON_LINE_LIMIT)
    big_web = sorted((path, line_count(source)) for path, source in web.items() if line_count(source) > WEB_LINE_LIMIT)

    metrics: dict[str, Any] = {
        "state_string_key_reads": state,
        "save_call_sites": {"call_sites": len(save_sites), "modules": len(save_modules), "sites": save_sites},
        "dict_str_any": {"occurrences": sum(dict_any.values()), "by_context": by_context(dict_any),
                         "by_spelling": _sorted_counts(Counter(match.split("[", 1)[0] for source in python.values()
                                                               for match in DICT_STR_ANY.findall(source)))},
        "deepcopy_calls": {"occurrences": sum(copies.values()), "by_context": by_context(copies)},
        "broad_excepts": {"occurrences": sum(excepts.values()), "by_context": by_context(excepts)},
        "world_specific_names": {**names, "scope": "rules, world, session, narration; fixture modules excluded",
                                 "whole_package": package_names},
        "word_list_constants": {
            "constants": len(word_list_sites), "by_context": _sorted_counts(word_by_context),
            "in_session_rules_world_narration": sum(count for name, count in word_by_context.items() if name in turn_path_contexts),
            "sites": word_list_sites,
        },
        "nondeterminism": {
            "calls": len(nondeterminism), "by_kind": _sorted_counts(nondeterminism_kinds), "sites": nondeterminism,
            "turn_path": (len(nondeterminism_turn_path) if nondeterminism_turn_path is not None
                          else "unavailable: no [rpg_turn_path] in layers.toml"),
        },
        "contract_bypass_imports": {"pairs": len(bypass), "by_context_pair": _sorted_counts(bypass_pairs)},
        "python_files_over_1200_lines": {"files": len(big_python), "list": [f"{path}:{lines}" for path, lines in big_python]},
        "web_files_over_600_lines": {"files": len(big_web), "list": [f"{path}:{lines}" for path, lines in big_web]},
    }
    return {
        "schema_version": SCHEMA_VERSION,
        "scope": {
            "rpg_python_files": len(python), "rpg_python_lines": sum(line_count(source) for source in python.values()),
            "rpg_web_files": len(web), "turn_path_modules": len(turn_path) if turn_path is not None else None,
        },
        "metrics": metrics,
        "ratchets": ratchet_values_from(metrics),
        "patterns": _patterns(),
    }


def ratchet_values_from(metrics: dict[str, Any]) -> dict[str, int]:
    headline = {
        "state_string_key_reads": lambda item: item["occurrences"],
        "save_call_sites": lambda item: item["call_sites"],
        "dict_str_any": lambda item: item["occurrences"],
        "deepcopy_calls": lambda item: item["occurrences"],
        "broad_excepts": lambda item: item["occurrences"],
        "world_specific_names": lambda item: item["hits"],
        "word_list_constants": lambda item: item["constants"],
        "nondeterminism": lambda item: item["calls"],
        "contract_bypass_imports": lambda item: item["pairs"],
        "python_files_over_1200_lines": lambda item: item["files"],
        "web_files_over_600_lines": lambda item: item["files"],
    }
    return {name: headline[key](metrics[key]) for name, (key, _) in RATCHETS.items()}


def ratchet_metrics(sources: dict[str, str], config: dict) -> tuple[dict[str, int], dict[str, Any]]:
    """The ratchet values and a compact evidence summary, for architecture_metrics."""
    report = measure(sources, config)
    metrics = report["metrics"]
    evidence = {
        "save_call_sites": metrics["save_call_sites"]["sites"],
        "world_specific_name_files": metrics["world_specific_names"]["file_list"],
        "word_list_constants": metrics["word_list_constants"]["sites"],
        "nondeterminism": metrics["nondeterminism"]["sites"],
        "python_files_over_1200_lines": metrics["python_files_over_1200_lines"]["list"],
        "web_files_over_600_lines": metrics["web_files_over_600_lines"]["list"],
        "contract_bypass_by_context_pair": metrics["contract_bypass_imports"]["by_context_pair"],
    }
    return report["ratchets"], evidence


def _patterns() -> dict[str, str]:
    """The exact patterns, from the module docstring, one entry per metric."""
    patterns: dict[str, str] = {}
    current = None
    for line in (__doc__ or "").splitlines():
        match = re.match(r"- ``(\w+)``: (.*)", line)
        if match:
            current = match.group(1)
            patterns[current] = match.group(2)
        elif current and line.startswith("  ") and line.strip():
            patterns[current] += " " + line.strip()
        else:
            current = None
    return patterns


def _revision(root: Path) -> str | None:
    result = subprocess.run(["git", "rev-parse", "--short=10", "HEAD"], cwd=root, capture_output=True, text=True)
    return result.stdout.strip() or None if result.returncode == 0 else None


def _digest(sources: dict[str, str]) -> str:
    digest = hashlib.sha256()
    for path, source in sorted(sources.items()):
        digest.update(path.encode("utf-8") + b"\0" + source.replace("\r\n", "\n").encode("utf-8") + b"\0")
    return digest.hexdigest()


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n", 1)[0])
    parser.add_argument("--root", type=Path, default=ROOT)
    parser.add_argument("--date", default=date.today().isoformat())
    parser.add_argument("--output", type=Path, help="default: docs/measurements/rpg-scorecard-<date>.json")
    parser.add_argument("--stdout", action="store_true", help="print the report instead of writing it")
    args = parser.parse_args(argv)
    root = args.root.resolve()
    all_sources = tracked_sources(root)
    sources = {path: source for path, source in all_sources.items() if path.startswith((RPG_ROOT, WEB_ROOT))}
    config = load_layers(root / "resources/architecture/layers.toml")
    report = measure(sources, config)
    report = {"measured_on": args.date, "revision": _revision(root), "source_digest": _digest(sources), **report}
    output = json.dumps(report, indent=2, sort_keys=True) + "\n"
    if args.stdout:
        sys.stdout.write(output)
        return 0
    path = args.output or Path("docs/measurements") / f"rpg-scorecard-{args.date}.json"
    path = path if path.is_absolute() else root / path
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(output, encoding="utf-8", newline="\n")
    print(json.dumps(report["ratchets"], indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
