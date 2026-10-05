"""Check tracked architecture boundaries against a strictly shrinking baseline."""

from __future__ import annotations

import argparse
from collections import Counter
import hashlib
import json
import os
from pathlib import Path, PurePosixPath
import re
import subprocess
import sys
import tempfile

from architecture_analysis import (
    AnalysisError, SourceAnalysis, Violation, is_production, load_layers, tracked_sources,
)

ROOT = Path(__file__).resolve().parents[1]
RULES = tuple(f"AL{number:03}" for number in range(1, 17))
MIGRATIONS = "src/app/persistence/migrations/"
RETIRED_MIGRATIONS = "src/app/persistence/retired/"
REGISTRY = "resources/architecture/migration-checksums.json"
SCOPE = "tracked_nonvendor_production_python_and_migrations"


def checksum(source: str) -> str:
    return hashlib.sha256(source.replace("\r\n", "\n").encode("utf-8")).hexdigest()


def is_schema_migration(path: str, files: set[str] | dict[str, str]) -> bool:
    """One of the three places schema migrations live (PA-2.3): the kernel folder,
    a migrations/ folder next to a feature.py, or a retired module's tombstone."""
    posix = PurePosixPath(path)
    if not path.endswith(".sql") or posix.parent.name != "migrations":
        return False
    if path.startswith(MIGRATIONS) and len(posix.parts) == 5:
        return True
    if path.startswith(RETIRED_MIGRATIONS) and len(posix.parts) == 7:
        return True
    return path.startswith("src/app/") and str(posix.parent.parent / "feature.py") in files


def migration_sources(sources: dict[str, str]) -> dict[str, str]:
    return {path: source for path, source in sources.items() if is_schema_migration(path, sources)}


def stray_migration_violations(sources: dict[str, str]) -> list[Violation]:
    """A .sql file in any other migrations/ folder would silently become schema."""
    return [Violation("AL014", path, "stray_schema_migration", 1)
            for path in sorted(sources)
            if path.startswith("src/") and path.endswith(".sql") and "migrations" in PurePosixPath(path).parts
            and not is_schema_migration(path, sources)]


def registry_checksums(registry: dict) -> dict[str, str]:
    if not isinstance(registry, dict) or registry.get("schema_version") != 1:
        raise AnalysisError("migration checksum registry schema is invalid")
    entries = registry.get("checksums")
    if not isinstance(entries, dict) or not entries:
        raise AnalysisError("migration checksum registry is empty or invalid")
    for path, digest in entries.items():
        if (not isinstance(path, str) or not path.startswith("src/app/")
                or PurePosixPath(path).parent.name != "migrations"
                or ".." in PurePosixPath(path).parts or not path.endswith(".sql")
                or not isinstance(digest, str) or not re.fullmatch(r"[0-9a-f]{64}", digest)):
            raise AnalysisError("migration checksum registry entry is invalid")
    return entries


def reference_migrations(root: Path, reference: str) -> dict[str, str] | None:
    result = subprocess.run(["git", "rev-parse", "--verify", f"{reference}^{{commit}}"],
                            cwd=root, capture_output=True)
    if result.returncode:
        return None
    revision = result.stdout.decode("ascii").strip()
    names = subprocess.run(["git", "ls-tree", "-r", "--name-only", "-z", revision, "--", "src/app"],
                           cwd=root, capture_output=True, check=True)
    listed = set(names.stdout.decode("utf-8").split("\0"))
    entries = {}
    for path in sorted(listed):
        if is_schema_migration(path, listed):
            contents = subprocess.run(["git", "show", f"{revision}:{path}"], cwd=root,
                                      capture_output=True, check=True).stdout.decode("utf-8-sig")
            entries[path] = checksum(contents)
    return entries


def migration_violations(sources: dict[str, str], protected: dict[str, str]) -> list[Violation]:
    # A migration's identity is its version (file stem) and checksum, not its
    # path: moving it into its owner's migrations/ folder is not a change (PA-2.3).
    current = migration_sources(sources)
    by_stem = {PurePosixPath(path).stem: path for path in current}
    protected_stems = {PurePosixPath(path).stem: digest for path, digest in protected.items()}
    violations = stray_migration_violations(sources)
    for path, digest in sorted(protected.items()):
        stem = PurePosixPath(path).stem
        moved = by_stem.get(stem)
        if moved is None or checksum(current[moved]) != digest:
            violations.append(Violation("AL014", path, "existing_migration_changed_or_removed", 1))
    highest = max((PurePosixPath(path).name for path in protected), default="")
    prefixes: dict[int, set[str]] = {}
    for stem in set(by_stem) | set(protected_stems):
        prefix = re.match(r"(\d+)", stem)
        if prefix:
            prefixes.setdefault(int(prefix[1]), set()).add(stem)
    for path in sorted(path for stem, path in by_stem.items() if stem not in protected_stems):
        name = PurePosixPath(path).name
        prefix = re.match(r"(\d+)", name)
        if not prefix:
            violations.append(Violation("AL014", path, "missing_numeric_prefix", 1))
        elif len(prefixes[int(prefix[1])]) > 1:
            violations.append(Violation("AL014", path, "new_duplicate_numeric_prefix:" + str(int(prefix[1])), 1))
        if highest and name <= highest:
            violations.append(Violation("AL014", path, "new_migration_before_latest:" + highest, 1))
        violations.extend(migration_sql_violations(path, current[path]))
    return violations


# Tables whose indexes must be built concurrently (WP-5.11); keep in step
# with docs/architecture/MIGRATION_POLICY.md.
LARGE_TABLES = frozenset({
    "omnix_agent_run_events",
    "omnix_assets",
    "omnix_audit_events",
    "omnix_chat_messages",
    "omnix_job_events",
    "omnix_job_logs",
    "omnix_jobs",
    "omnix_memory_records",
    "omnix_module_records",
    "omnix_outbox_events",
    "omnix_trading_strategy_events",
})
_HEADER = re.compile(r"^--\s*omnix-migration:\s*phase=(expand|contract|data)\s+transactional=(true|false)\s*$")
_DESTRUCTIVE = re.compile(r"\bDROP\s+(COLUMN|TABLE)\b", re.I)
_CREATE_INDEX = re.compile(
    r"\bCREATE\s+(?:UNIQUE\s+)?INDEX\s+(CONCURRENTLY\s+)?(?:IF\s+NOT\s+EXISTS\s+)?\w+\s+ON\s+(?:ONLY\s+)?(\w+)",
    re.I,
)


def migration_sql_violations(path: str, sql: str) -> list[Violation]:
    """Header, expand-safety and large-table index checks for one new migration."""
    lines = [line.strip() for line in sql.splitlines() if line.strip()]
    header = _HEADER.match(lines[0]) if lines else None
    if header is None:
        return [Violation("AL014", path, "missing_migration_header", 1)]
    phase, transactional = header[1], header[2] == "true"
    body = re.sub(r"--[^\n]*", "", sql)
    violations = []
    if phase == "expand" and _DESTRUCTIVE.search(body):
        violations.append(Violation("AL014", path, "destructive_change_in_expand_migration", 1))
    for match in _CREATE_INDEX.finditer(body):
        table = match[2].lower()
        if table in LARGE_TABLES and (match[1] is None or transactional):
            violations.append(Violation("AL014", path, "blocking_index_on_large_table:" + table, 1))
    return violations


def reciprocal_violations(analysis: SourceAnalysis) -> list[Violation]:
    """AL015 (ADR-0016): two packages or modules that import each other at any scope.

    AL002 sees only module-level imports; imports inside functions hide the same
    dependency cycles from it.
    """
    return [Violation("AL015", "src/" + first.replace(".", "/") + "/", f"{first}<->{second}", 1)
            for first, second in analysis.reciprocal_dependencies()]


def cycle_violations(analysis: SourceAnalysis) -> list[Violation]:
    # The metric counts reciprocal package pairs. Lint additionally rejects
    # longer module-level package cycles, whose edges may use different modules.
    graph: dict[str, set[str]] = {}
    for source, targets in analysis.import_edges(module_level=True).items():
        if not source.startswith("app.") or not is_production(analysis.modules[source], analysis.config):
            continue
        owner = source.split(".")[1]
        graph.setdefault(owner, set())
        for target in targets:
            if (target.startswith("app.") and target.split(".")[1] != owner
                    and is_production(analysis.modules[target], analysis.config)):
                graph[owner].add(target.split(".")[1])
    index = 0
    indices: dict[str, int] = {}
    low: dict[str, int] = {}
    stack: list[str] = []
    active: set[str] = set()
    components: list[set[str]] = []

    def visit(node: str) -> None:
        nonlocal index
        indices[node] = low[node] = index
        index += 1
        stack.append(node)
        active.add(node)
        for target in sorted(graph.get(node, set())):
            if target not in indices:
                visit(target)
                low[node] = min(low[node], low[target])
            elif target in active:
                low[node] = min(low[node], indices[target])
        if low[node] == indices[node]:
            component = set()
            while True:
                target = stack.pop()
                active.remove(target)
                component.add(target)
                if target == node:
                    break
            if len(component) > 1:
                components.append(component)

    for node in sorted(graph):
        if node not in indices:
            visit(node)
    # Keep each directed cycle edge independently fingerprinted. One new edge
    # cannot hide behind an existing strongly connected component.
    return sorted((Violation("AL002", f"src/app/{source}/", f"app.{source}->app.{target}", 1)
                   for component in components for source in component
                   for target in graph[source] if target in component),
                  key=lambda item: (item.path, item.fingerprint))


def measure(sources: dict[str, str], config: dict, protected: dict[str, str]) -> dict:
    analysis = SourceAnalysis(sources, config)
    violations = (analysis.violations() + cycle_violations(analysis) + reciprocal_violations(analysis)
                  + analysis.table_ownership_violations()
                  + migration_violations(sources, protected))
    counts = Counter((item.rule, item.path, item.fingerprint) for item in violations)
    lines = {}
    for item in violations:
        lines.setdefault((item.rule, item.path, item.fingerprint), []).append(item.line)
    entries = [{"rule": rule, "path": path, "fingerprint": fingerprint, "count": count,
                "lines": sorted(lines[rule, path, fingerprint])}
               for (rule, path, fingerprint), count in sorted(counts.items())]
    return {"schema_version": 1, "scope": SCOPE, "rules": list(RULES),
            "policy_digest": checksum(json.dumps(config, sort_keys=True)),
            "violations": entries,
            "errors": ["Python source cannot compile: " + path for path in analysis.syntax_errors]}


def entry_counts(report: dict) -> dict[tuple[str, str, str], int]:
    entries = report.get("violations")
    if not isinstance(entries, list):
        raise AnalysisError("lint baseline violations must be a list")
    result = {}
    for entry in entries:
        if not isinstance(entry, dict):
            raise AnalysisError("lint baseline entry is invalid")
        key = (entry.get("rule"), entry.get("path"), entry.get("fingerprint"))
        count = entry.get("count")
        if (not all(isinstance(value, str) and value for value in key) or key[0] not in RULES
                or type(count) is not int or count < 1 or key in result):
            raise AnalysisError("lint baseline key or count is invalid")
        result[key] = count
    return result


def compare(current: dict, baseline: dict, *, shrinking: bool = False) -> list[str]:
    errors = list(current["errors"])
    for field in ("schema_version", "scope", "rules", "policy_digest"):
        if baseline.get(field) != current[field]:
            errors.append("lint baseline contract changed: " + field)
    before, now = entry_counts(baseline), entry_counts(current)
    for key in sorted(set(before) | set(now)):
        old, new = before.get(key, 0), now.get(key, 0)
        identity = ":".join(key)
        if new > old:
            errors.append(f"new violation: {identity} ({old} -> {new})")
        elif new < old and not shrinking:
            errors.append(f"stale baseline entry: {identity} ({old} -> {new}); shrink the baseline")
    return errors


def atomic_write(path: Path, contents: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = None
    try:
        with tempfile.NamedTemporaryFile(mode="w", encoding="utf-8", newline="\n",
                                         dir=path.parent, delete=False) as stream:
            temporary = Path(stream.name)
            stream.write(contents)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, path)
    finally:
        if temporary is not None:
            temporary.unlink(missing_ok=True)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=ROOT)
    parser.add_argument("--output", type=Path)
    parser.add_argument("--baseline", type=Path, default=Path("resources/architecture/lint-baseline.json"))
    parser.add_argument("--migration-base", default="origin/main")
    operation = parser.add_mutually_exclusive_group()
    operation.add_argument("--check", action="store_true")
    operation.add_argument("--update-baseline", action="store_true")
    args = parser.parse_args(argv)
    root = args.root.resolve()
    try:
        baseline_path = (root / args.baseline).resolve()
        output_path = (root / args.output).resolve() if args.output else None
        if output_path == baseline_path:
            raise AnalysisError("--output must differ from --baseline; use --update-baseline")
        previous = json.loads(baseline_path.read_text(encoding="utf-8")) if baseline_path.exists() else None
        config = load_layers(root / "resources/architecture/layers.toml")
        sources = tracked_sources(root)
        registry = registry_checksums(json.loads((root / REGISTRY).read_text(encoding="utf-8")))
        reference = reference_migrations(root, args.migration_base)
        protected = dict(registry)
        for path, digest in (reference or {}).items():
            if path in protected and protected[path] != digest:
                raise AnalysisError("migration registry differs from the base branch: " + path)
            protected[path] = digest
        current = measure(sources, config, protected)
        failures = list(current["errors"])
        if any(entry["rule"] == "AL014" for entry in current["violations"]):
            failures.append("AL014: migration changes cannot be added to the lint baseline")
        if args.check or args.update_baseline:
            if previous is not None:
                failures.extend(compare(current, previous, shrinking=args.update_baseline))
            elif args.check:
                failures.append("lint baseline is missing")
        output = json.dumps(current, indent=2, sort_keys=True) + "\n"
        if output_path:
            atomic_write(output_path, output)
        else:
            sys.stdout.write(output)
        if not failures and args.update_baseline:
            atomic_write(baseline_path, output)
        for failure in failures:
            print("architecture lint: " + failure, file=sys.stderr)
        return int(bool(failures))
    except (AnalysisError, OSError, ValueError, KeyError, TypeError, AttributeError, subprocess.SubprocessError) as exc:
        print("architecture lint: " + str(exc), file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
