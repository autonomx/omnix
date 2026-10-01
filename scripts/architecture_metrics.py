"""Measure the complete enterprise architecture scorecard without importing Omnix.

Source metrics use only tracked files. Runtime measurements require a separate,
source-bound report from the disposable environment; absent evidence is unknown,
never a fabricated zero. Both checking and updating fail closed on unknowns.
"""

from __future__ import annotations

import argparse
import ast
from collections import Counter
import configparser
from datetime import datetime, timezone
import fnmatch
import json
import math
import os
from pathlib import Path, PurePosixPath
import re
import sys
import subprocess
import tempfile
import tomllib
from typing import Any

from architecture_analysis import (
    AnalysisError, FUNCTIONS, SourceAnalysis, import_aliases, is_production, is_test, keyword,
    literal_string, load_layers, module_name, qualified_name, route_decorators, scoped_nodes,
    source_digest, tracked_sources,
)

ROOT = Path(__file__).resolve().parents[1]
SCHEMA_VERSION = 1
# Targets with a contextual denominator remain explicit rather than silently
# changing a percentage/route target into a fixed arbitrary count.
LOWER_TARGETS: dict[str, int | str] = {
    "package_cycles": 0, "layer_violations": 0, "foreign_attribute_assignments": 0,
    "install_hook_functions": 0, "fastapi_init_patchers": 0,
    "async_handlers_without_await": 0, "schema_excluded_routes": 0,
    "untyped_body_routes": 0, "routes_without_permission": 0,
    "bootstrap_calls_outside_startup": 0, "env_reads_outside_config": 0,
    "print_calls": 0, "silent_broad_excepts": 10, "star_imports": 0,
    "platform_table_sql_outside_owner": 0, "direct_requests_calls": 0,
    "local_blob_store_constructions": 1, "absolute_storage_path_reads": 0,
    "unbounded_fetchall": 0, "capped_500_queries": 0, "rpg_nondeterminism": 0,
    "files_over_1200_lines": 5, "functions_over_150_lines": 20,
    "largest_class_lines": 800, "quarantined_tests": 0, "collection_errors": 0,
    "fixed_sleeps_in_tests": 5, "mypy_ignored_modules": "0 kernel; <=10% total",
    "compat_modules": 0, "process_local_state_unapproved": 0,
    "unbounded_module_caches": 0,
    "unreachable_rpg_modules": 0, "web_fetch_assignment_files": 0,
    "web_omnix_window_flags": 0, "web_raw_fetch_outside_api": 0,
    "web_handwritten_api_types": 0, "web_important": 50, "web_hardcoded_colors": 300,
    "web_mutation_observer_files": 2, "web_set_interval_files": 5,
    "web_custom_event_dispatch_files": 0, "web_unreachable_modules": 0,
    "eslint_baseline_disables": 0, "boot_imported_modules": "ratchet",
    "inline_prompt_strings": 10,
}
HIGHER_TARGETS: dict[str, int | str] = {
    "rls_coverage_pct": 100, "retention_policies_executed_pct": 100,
    "outbox_consumer_coverage_pct": 100, "web_openapi_path_coverage_pct": 100,
    "web_error_boundaries": "number of routes",
}
RUNTIME_METRICS = {
    "collection_errors", "boot_imported_modules", "rls_coverage_pct",
    "retention_policies_executed_pct", "outbox_consumer_coverage_pct",
}
AL_METRICS = {
    "AL001": "layer_violations", "AL003": "foreign_attribute_assignments",
    "AL004": "install_hook_functions", "AL005": "async_handlers_without_await",
    "AL006": "platform_table_sql_outside_owner", "AL007": "env_reads_outside_config",
    "AL008": "print_calls", "AL009": "silent_broad_excepts", "AL010": "star_imports",
    "AL011": "local_blob_store_constructions", "AL012": "bootstrap_calls_outside_startup",
    "AL013": "rpg_nondeterminism",
}
PUBLIC_PATHS = {"/health", "/ready", "/docs", "/redoc", "/openapi.json", "/favicon.ico"}
VERBS = {"get", "post", "put", "patch", "delete", "head", "options", "request"}
TRANSPORT_EXCEPTIONS_DOC = "docs/architecture/api-transport-exceptions.md"
PROCESS_STATE_INVENTORY = "resources/architecture/process-local-state.json"
PROCESS_STATE_DOC = "docs/architecture/PROCESS_LOCAL_STATE.md"
_PROCESS_STATE_CONSTRUCTORS = {
    "dict", "list", "set", "defaultdict", "OrderedDict", "deque",
    "Counter", "Lock", "RLock", "Semaphore", "BoundedSemaphore", "Condition",
    "Event", "Barrier", "Queue", "SimpleQueue", "ThreadPoolExecutor",
}


def finite_number(value: Any) -> bool:
    return isinstance(value, (int, float)) and not isinstance(value, bool) and math.isfinite(value) and value >= 0


def mask_js(source: str, *, strings: bool = False) -> str:
    """Mask comments, optionally quoted strings, while preserving line offsets."""
    pattern = r"/\*[\s\S]*?\*/|//[^\n]*|(?:\"(?:\\.|[^\"\\])*\"|'(?:\\.|[^'\\])*'|`(?:\\.|[^`\\])*`)"
    def replace(match: re.Match) -> str:
        text = match.group()
        if text.startswith(("/*", "//")) or strings:
            return "".join("\n" if char == "\n" else " " for char in text)
        return text
    return re.sub(pattern, replace, source)


def js_function_spans(source: str) -> list[tuple[int, int]]:
    code = mask_js(source, strings=True)
    starts = set()
    patterns = [
        r"\b(?:async\s+)?function\s*(?:[\w$]+)?\s*(?:<[^\n;{}]*>)?\s*\([^;{}]*?\)\s*(?::[^\n{}]+)?\s*\{",
        r"(?:\([^;{}]*?\)|[\w$]+)\s*(?::[^\n{}]+)?\s*=>\s*\{",
        r"^\s*(?:(?:public|private|protected|static|async)\s+)*[\w$]+\s*\([^;{}]*?\)\s*(?::[^\n{}]+)?\s*\{",
    ]
    for pattern in patterns:
        for match in re.finditer(pattern, code, re.M):
            if re.match(r"\s*(?:if|for|while|switch|catch|with)\s*\(", match.group()):
                continue
            starts.add(match.end() - 1)
    spans = []
    for start in sorted(starts):
        depth = 1
        for index in range(start + 1, len(code)):
            depth += (code[index] == "{") - (code[index] == "}")
            if depth == 0:
                spans.append((source.count("\n", 0, start) + 1, source.count("\n", 0, index) + 1))
                break
    return spans


def _route_factories(source: str) -> list[tuple[str, int, int]]:
    code = mask_js(source, strings=True)
    result = []
    for match in re.finditer(r"\bfunction\s+(\w+)(?:<[^;{}]*>)?\s*\([^;{}]*\)\s*\{", code):
        start = match.end() - 1
        depth = 1
        for end in range(start + 1, len(code)):
            depth += (code[end] == "{") - (code[end] == "}")
            if depth == 0:
                if re.search(r"\bcreate(?:Root|File)?Route\s*\(", code[start:end]):
                    result.append((match.group(1), start, end + 1))
                break
    return result


def _read_json(sources: dict[str, str], path: str, default: Any) -> Any:
    if path not in sources:
        return default
    try:
        return json.loads(sources[path])
    except (ValueError, TypeError) as exc:
        raise AnalysisError(f"invalid metric input: {path}") from exc


def _route_internal(call: ast.Call, router_prefixes: dict[str, str]) -> bool:
    path = literal_string(call.args[0]) if call.args else ""
    prefix = router_prefixes.get(qualified_name(call.func.value), "")
    return (prefix + (path or "")).startswith("/internal/")


def _documented_transport_exceptions(sources: dict[str, str]) -> set[tuple[str, str, str]]:
    """Return exact (source, method, local path) entries from the reviewed inventory."""
    source = sources.get(TRANSPORT_EXCEPTIONS_DOC, "")
    result: set[tuple[str, str, str]] = set()
    for line in source.splitlines():
        if not line.startswith("|"):
            continue
        cells = [cell.strip().strip("`") for cell in line.strip().strip("|").split("|")]
        if len(cells) != 4 or not cells[0].startswith("src/app/"):
            continue
        result.add((cells[0], cells[1].upper(), cells[2]))
    return result


def _process_state_inventory(sources: dict[str, str]) -> dict[tuple[str, str], dict[str, Any]]:
    inventory = _read_json(sources, PROCESS_STATE_INVENTORY, {"entries": []})
    if not isinstance(inventory, dict) or not isinstance(inventory.get("entries"), list):
        raise AnalysisError("process-state inventory requires an entries list")
    entries: dict[tuple[str, str], dict[str, Any]] = {}
    for entry in inventory["entries"]:
        if not isinstance(entry, dict) or not isinstance(entry.get("path"), str) or not isinstance(entry.get("symbol"), str):
            raise AnalysisError("process-state inventory requires an exact path and symbol")
        identity = (entry["path"], entry["symbol"])
        if identity in entries:
            raise AnalysisError(f"duplicate process-state inventory entry: {identity[0]}:{identity[1]}")
        entries[identity] = entry
    return entries


def scan_process_local_state(sources: dict[str, str]) -> list[dict[str, Any]]:
    """Find module-owned mutable containers, locks and unbounded function caches."""
    findings: dict[tuple[str, str], dict[str, Any]] = {}
    for path, source in sorted(sources.items()):
        if not path.startswith("src/app/") or not path.endswith(".py"):
            continue
        try:
            tree = ast.parse(source)
        except SyntaxError:
            continue
        aliases = import_aliases(tree, path)
        mutated_names: set[str] = set()
        for mutation in ast.walk(tree):
            if isinstance(mutation, ast.Global):
                mutated_names.update(mutation.names)
            if isinstance(mutation, ast.Call) and isinstance(mutation.func, ast.Attribute):
                receiver = mutation.func.value
                if isinstance(receiver, ast.Name) and mutation.func.attr in {
                    "add", "append", "clear", "discard", "extend", "insert", "move_to_end",
                    "pop", "popitem", "remove", "setdefault", "update",
                }:
                    mutated_names.add(receiver.id)
            elif isinstance(mutation, (ast.Assign, ast.AnnAssign, ast.AugAssign, ast.Delete)):
                targets = mutation.targets if isinstance(mutation, ast.Assign) else [mutation.target] if hasattr(mutation, "target") else mutation.targets
                for target in targets:
                    nested_target = isinstance(target, (ast.Subscript, ast.Attribute))
                    while isinstance(target, (ast.Subscript, ast.Attribute)):
                        target = target.value
                    if nested_target and isinstance(target, ast.Name):
                        mutated_names.add(target.id)
        for node, scope in scoped_nodes(tree):
            if scope:
                continue
            if isinstance(node, (ast.Assign, ast.AnnAssign)):
                value = node.value
                targets = node.targets if isinstance(node, ast.Assign) else [node.target]
                for target in targets:
                    if not isinstance(target, ast.Name) or target.id == "__all__":
                        continue
                    name = target.id
                    call_name = qualified_name(value.func, aliases).split(".")[-1] if isinstance(value, ast.Call) else ""
                    mutable_literal = isinstance(value, (ast.Dict, ast.List, ast.Set))
                    if isinstance(value, ast.Dict):
                        empty_literal = not value.keys
                    elif isinstance(value, (ast.List, ast.Set)):
                        empty_literal = not value.elts
                    else:
                        empty_literal = False
                    known_constructor = call_name in _PROCESS_STATE_CONSTRUCTORS and (
                        call_name not in {"dict", "list", "set"}
                        or isinstance(value, ast.Call) and not value.args and not value.keywords
                    )
                    default_plane = name.upper().endswith("PLANE") and isinstance(value, ast.Call)
                    if not (known_constructor or empty_literal or mutable_literal and name in mutated_names or default_plane):
                        continue
                    kind = "container"
                    if call_name in {"Lock", "RLock", "Semaphore", "BoundedSemaphore", "Condition", "Event", "Barrier"}:
                        kind = "lock"
                    elif call_name == "ThreadPoolExecutor":
                        kind = "executor"
                    elif call_name in {"Queue", "SimpleQueue"}:
                        kind = "queue"
                    elif default_plane:
                        kind = "runtime_resource"
                    findings[(path, name)] = {
                        "path": path,
                        "symbol": name,
                        "line": node.lineno,
                        "kind": kind,
                    }
            elif isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                for decorator in node.decorator_list:
                    decorator_func = decorator.func if isinstance(decorator, ast.Call) else decorator
                    decorator_name = qualified_name(decorator_func, aliases).split(".")[-1]
                    if decorator_name not in {"lru_cache", "cache", "bounded_lru_cache"}:
                        continue
                    maxsize = (
                        keyword(decorator, "max_entries")
                        if decorator_name == "bounded_lru_cache" and isinstance(decorator, ast.Call)
                        else keyword(decorator, "maxsize") if isinstance(decorator, ast.Call)
                        else None
                    )
                    symbol = f"{node.name}.__cache__"
                    findings[(path, symbol)] = {
                        "path": path,
                        "symbol": symbol,
                        "line": node.lineno,
                        "kind": "function_cache",
                        "cache_decorator": qualified_name(decorator_func, aliases),
                        "maxsize": (
                            maxsize.value if isinstance(maxsize, ast.Constant)
                            else ast.unparse(maxsize) if maxsize is not None
                            else 128 if decorator_name == "lru_cache" else None
                        ),
                    }
    return [findings[key] for key in sorted(findings)]


def process_local_state_report(sources: dict[str, str]) -> tuple[list[dict[str, Any]], int, int]:
    """Attach reviewed categories and measure unapproved/unbounded state."""
    scanned = scan_process_local_state(sources)
    inventory = _process_state_inventory(sources)
    findings = []
    unapproved = 0
    unbounded = 0
    scanned_ids = set()
    for candidate in scanned:
        identity = (candidate["path"], candidate["symbol"])
        scanned_ids.add(identity)
        entry = inventory.get(identity)
        approved = bool(
            entry
            and entry.get("category") in {"cache", "coordination", "per-connection"}
            and isinstance(entry.get("reason"), str)
            and entry["reason"].strip()
        )
        finding = {
            **candidate,
            "category": entry.get("category") if entry else None,
            "reason": entry.get("reason") if entry else None,
            "approved": approved,
        }
        if not approved and candidate["kind"] == "container":
            # An unreviewed mutable map may be an unbounded cache. Fail closed
            # until the inventory assigns its ownership category.
            unbounded += 1
        if approved and entry["category"] == "cache" and candidate["kind"] in {"container", "runtime_resource"}:
            max_symbol = entry.get("max_entries_symbol")
            ttl_symbol = entry.get("ttl_symbol")
            invalidation = entry.get("invalidation")
            max_entries, ttl_seconds = _verified_cache_policy(
                sources.get(candidate["path"], ""),
                candidate["symbol"],
                max_symbol,
                ttl_symbol,
                invalidation,
            )
            if max_entries is not None and ttl_seconds is not None:
                finding.update({
                    "max_entries": max_entries,
                    "ttl_seconds": ttl_seconds,
                    "invalidation": invalidation,
                })
            else:
                unbounded += 1
        if candidate["kind"] == "function_cache":
            policy = _verified_function_cache_policy(
                sources.get(candidate["path"], ""),
                candidate,
                entry,
            ) if approved and entry and entry.get("category") == "cache" else None
            if policy is not None:
                finding.update({
                    "max_entries": policy[0],
                    "ttl_seconds": policy[1],
                    "invalidation": entry.get("invalidation"),
                })
            else:
                # functools caches have a size bound but no expiry. They remain
                # unbounded for this policy until replaced with an expiring,
                # explicitly invalidatable cache implementation.
                unbounded += 1
        if not approved:
            unapproved += 1
        findings.append(finding)
    stale = sorted(set(inventory) - scanned_ids)
    if stale:
        raise AnalysisError(
            "stale process-state inventory entries: "
            + ", ".join(f"{path}:{symbol}" for path, symbol in stale)
        )
    return findings, unapproved, unbounded


def _verified_cache_policy(
    source: str,
    cache_symbol: str,
    max_symbol: Any,
    ttl_symbol: Any,
    invalidation: Any,
) -> tuple[int | None, float | None]:
    """Verify cache bounds and invalidation references against source AST."""
    if not all(isinstance(item, str) and item for item in (max_symbol, ttl_symbol, invalidation)):
        return None, None
    try:
        tree = ast.parse(source)
    except SyntaxError:
        return None, None
    constants = _numeric_module_constants(tree)
    functions: dict[str, ast.FunctionDef | ast.AsyncFunctionDef] = {}
    for node in tree.body:
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            functions[node.name] = node
    max_entries = constants.get(max_symbol)
    ttl_seconds = constants.get(ttl_symbol)
    if not (isinstance(max_entries, int) and not isinstance(max_entries, bool) and max_entries > 0):
        return None, None
    if not (isinstance(ttl_seconds, (int, float)) and not isinstance(ttl_seconds, bool) and ttl_seconds > 0):
        return None, None
    reads = {node.id for node in ast.walk(tree) if isinstance(node, ast.Name) and isinstance(node.ctx, ast.Load)}
    if max_symbol not in reads or ttl_symbol not in reads:
        return None, None
    invalidator = functions.get(invalidation)
    if invalidator is None:
        return None, None
    clears_cache = any(
        isinstance(node, ast.Call)
        and isinstance(node.func, ast.Attribute)
        and isinstance(node.func.value, ast.Name)
        and node.func.value.id == cache_symbol
        and node.func.attr in {"clear", "pop", "popitem"}
        for node in ast.walk(invalidator)
    )
    if not clears_cache:
        return None, None
    return max_entries, float(ttl_seconds)


def _verified_function_cache_policy(
    source: str,
    candidate: dict[str, Any],
    inventory_entry: dict[str, Any] | None,
) -> tuple[int, float] | None:
    """Verify the project TTL cache decorator and its explicit clear API."""
    if inventory_entry is None:
        return None
    if candidate.get("cache_decorator") != "app.caching.bounded_cache.bounded_lru_cache":
        return None
    function_name = candidate["symbol"].removesuffix(".__cache__")
    if inventory_entry.get("invalidation") != f"{function_name}.cache_clear":
        return None
    try:
        tree = ast.parse(source)
    except SyntaxError:
        return None
    constants = _numeric_module_constants(tree)
    functions: dict[str, ast.FunctionDef | ast.AsyncFunctionDef] = {}
    for node in tree.body:
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            functions[node.name] = node
    function = functions.get(function_name)
    if function is None:
        return None
    for decorator in function.decorator_list:
        if not isinstance(decorator, ast.Call):
            continue
        if qualified_name(decorator.func).split(".")[-1] != "bounded_lru_cache":
            continue
        raw_max = keyword(decorator, "max_entries")
        raw_ttl = keyword(decorator, "ttl_seconds")
        max_entries = raw_max.value if isinstance(raw_max, ast.Constant) else constants.get(raw_max.id) if isinstance(raw_max, ast.Name) else None
        ttl_seconds = raw_ttl.value if isinstance(raw_ttl, ast.Constant) else constants.get(raw_ttl.id) if isinstance(raw_ttl, ast.Name) else None
        if not (
            isinstance(max_entries, int)
            and not isinstance(max_entries, bool)
            and max_entries > 0
            and isinstance(ttl_seconds, (int, float))
            and not isinstance(ttl_seconds, bool)
            and ttl_seconds > 0
        ):
            return None
        declared_max = inventory_entry.get("max_entries")
        declared_ttl = inventory_entry.get("ttl_seconds")
        if declared_max != max_entries or declared_ttl != ttl_seconds:
            return None
        return max_entries, float(ttl_seconds)
    return None


def _numeric_module_constants(tree: ast.Module) -> dict[str, int | float]:
    def evaluate(node: ast.AST) -> int | float | None:
        if isinstance(node, ast.Constant) and isinstance(node.value, (int, float)) and not isinstance(node.value, bool):
            return node.value
        if isinstance(node, ast.UnaryOp) and isinstance(node.op, (ast.UAdd, ast.USub)):
            value = evaluate(node.operand)
            if value is not None:
                return value if isinstance(node.op, ast.UAdd) else -value
        if isinstance(node, ast.BinOp) and isinstance(node.op, (ast.Add, ast.Sub, ast.Mult, ast.Div, ast.FloorDiv)):
            left = evaluate(node.left)
            right = evaluate(node.right)
            if left is not None and right is not None:
                try:
                    value = {
                        ast.Add: lambda: left + right,
                        ast.Sub: lambda: left - right,
                        ast.Mult: lambda: left * right,
                        ast.Div: lambda: left / right,
                        ast.FloorDiv: lambda: left // right,
                    }[type(node.op)]()
                except (ArithmeticError, OverflowError):
                    return None
                return value if math.isfinite(float(value)) else None
        return None

    constants: dict[str, int | float] = {}
    for node in ast.walk(tree):
        if not isinstance(node, (ast.Assign, ast.AnnAssign)):
            continue
        value = evaluate(node.value)
        if value is None:
            continue
        targets = node.targets if isinstance(node, ast.Assign) else [node.target]
        for target in targets:
            if isinstance(target, ast.Name):
                constants[target.id] = value
    return constants


def process_local_state_markdown(findings: list[dict[str, Any]]) -> str:
    rows = [
        "# Process-local state inventory",
        "",
        "Generated by `python scripts/architecture_metrics.py --write-process-local-state-doc` from the module-scope scan of `src/app`.",
        "The scan includes mutable module containers, synchronization/resource objects, and cached functions.",
        "Each entry is assigned one of the roadmap categories: cache, coordination, or per-connection.",
        "",
        "| Source | Kind | Category | Bound | TTL (seconds) | Invalidation / authority | Review reason |",
        "|---|---|---|---:|---:|---|---|",
    ]
    for item in findings:
        source = f"`{item['path']}:{item['line']}` `{item['symbol']}`"
        bound = str(item.get("max_entries", "—"))
        ttl = str(item.get("ttl_seconds", "—"))
        invalidation = str(item.get("invalidation", "—")).replace("|", "\\|")
        reason = str(item.get("reason", "UNREVIEWED")).replace("|", "\\|")
        details = f"{item['kind']} ({item.get('cache_decorator')} maxsize={item.get('maxsize')})" if item["kind"] == "function_cache" else item["kind"]
        rows.append(
            f"| {source} | {details} | {item.get('category') or 'UNREVIEWED'} | {bound} | {ttl} | {invalidation} | {reason} |"
        )
    rows.extend(["", f"Scanned entries: {len(findings)}; unapproved entries: {sum(not item['approved'] for item in findings)}; unbounded caches: {sum(item['kind'] == 'function_cache' or item['category'] == 'cache' and item['kind'] in {'container', 'runtime_resource'} and 'max_entries' not in item for item in findings)}.", ""])
    return "\n".join(rows)


def _permission(value: ast.AST | None) -> bool:
    if value is None:
        return False
    return any(isinstance(node, ast.Call) and qualified_name(node.func).split(".")[-1] == "Depends"
               and node.args and any(part in qualified_name(node.args[0].func if isinstance(node.args[0], ast.Call) else node.args[0]).lower()
                                     for part in ("permission", "authorize", "service_token"))
               for node in ast.walk(value))


def _fastapi_class(bindings, node: ast.AST) -> bool:
    return bindings.foreign(node) and bool(bindings.names(node) & {
        "FastAPI", "fastapi.FastAPI", "fastapi.applications.FastAPI",
    })


def python_metrics(analysis: SourceAnalysis) -> tuple[dict[str, int], dict[str, Any]]:
    values: Counter = Counter({key: 0 for key in LOWER_TARGETS if key not in RUNTIME_METRICS})
    evidence: dict[str, Any] = {"python_syntax_errors": analysis.syntax_errors}
    evidence["unbounded_fetchall_calls"] = []
    evidence["capped_500_query_sites"] = []
    evidence["absolute_storage_path_read_sites"] = []
    transport_exceptions = _documented_transport_exceptions(analysis.sources)
    violations = analysis.violations()
    for violation in violations:
        if violation.rule == "AL003" and not violation.path.startswith("src/app/"):
            continue
        values[AL_METRICS[violation.rule]] += 1
    # Function/file metrics count locations, while lint fingerprints group
    # stable subjects for a shrinking baseline. Preserve every detection here.
    evidence["lint_counts"] = dict(Counter(item.rule for item in violations))
    evidence["package_cycles"] = analysis.package_cycles()
    values["package_cycles"] = len(evidence["package_cycles"])
    blob_owners = {"src/" + path for path in analysis.config.get("owners", {}).get("blob_store_construction", [])}
    evidence["other_fixed_sleeps_in_tests"] = []
    values["files_over_1200_lines"] = sum(
        path.endswith((".py", ".ts", ".tsx")) and len(source.splitlines()) > 1200
        for path, source in analysis.sources.items()
    )
    for path, tree in analysis.trees.items():
        production = is_production(path, analysis.config)
        aliases = import_aliases(tree, path)
        parents = {child: node for node in ast.walk(tree) for child in ast.iter_child_nodes(node)}
        if production:
            values["compat_modules"] += PurePosixPath(path).name.endswith("_compat.py")
        router_prefixes, router_permissions = {}, set()
        for node in ast.walk(tree):
            if isinstance(node, ast.Assign) and isinstance(node.value, ast.Call):
                if qualified_name(node.value.func, aliases).split(".")[-1] in {"APIRouter", "FastAPI"}:
                    for target in node.targets:
                        if isinstance(target, ast.Name):
                            router_prefixes[target.id] = literal_string(keyword(node.value, "prefix")) or ""
                            if _permission(keyword(node.value, "dependencies")):
                                router_permissions.add(target.id)
        fastapi_patch = False
        storage_read = False
        bindings = analysis.bindings(path) if production else None
        for node, scope in scoped_nodes(tree):
            if isinstance(node, ast.ClassDef):
                values["largest_class_lines"] = max(values["largest_class_lines"], node.end_lineno - node.lineno + 1)
            if isinstance(node, FUNCTIONS):
                values["functions_over_150_lines"] += node.end_lineno - node.lineno + 1 > 150
            if isinstance(node, ast.Call) and is_test(path):
                if node.args and isinstance(node.args[0], ast.Constant) and isinstance(node.args[0].value, (int, float)):
                    name = qualified_name(node.func, aliases)
                    if name == "time.sleep":
                        values["fixed_sleeps_in_tests"] += 1
                    elif name == "asyncio.sleep" or isinstance(node.func, ast.Attribute) and node.func.attr == "wait_for_timeout":
                        evidence["other_fixed_sleeps_in_tests"].append({"path": path, "line": node.lineno, "call": name})
            if not production:
                continue
            if isinstance(node, FUNCTIONS):
                annotations = [arg.annotation for arg in node.args.posonlyargs + node.args.args + node.args.kwonlyargs]
                untyped = any(qualified_name(item.value if isinstance(item, ast.Subscript) else item, aliases) in {"dict", "typing.Dict", "Dict", "typing.Any", "Any"} for item in annotations)
                for route in route_decorators(node):
                    internal = _route_internal(route, router_prefixes)
                    route_path = literal_string(route.args[0]) or "" if route.args else ""
                    method = qualified_name(route.func).split(".")[-1].upper()
                    raw_request_names = {
                        arg.arg
                        for arg in node.args.posonlyargs + node.args.args + node.args.kwonlyargs
                        if arg.annotation is not None
                        and qualified_name(arg.annotation, aliases).split(".")[-1] == "Request"
                    }
                    raw_body = any(
                        isinstance(item, ast.Call)
                        and isinstance(item.func, ast.Attribute)
                        and item.func.attr in {"json", "body"}
                        and isinstance(item.func.value, ast.Name)
                        and item.func.value.id in raw_request_names
                        for item in ast.walk(node)
                    )
                    untyped_body = untyped or raw_body
                    values["untyped_body_routes"] += untyped_body
                    if untyped_body:
                        evidence.setdefault("untyped_body_routes", []).append({
                            "path": path,
                            "line": node.lineno,
                            "method": method,
                            "route_path": route_path,
                        })
                    documented_transport = (path, method, route_path) in transport_exceptions
                    if (
                        isinstance(keyword(route, "include_in_schema"), ast.Constant)
                        and keyword(route, "include_in_schema").value is False
                        and not internal
                        and not documented_transport
                    ):
                        values["schema_excluded_routes"] += 1
                    full_path = router_prefixes.get(qualified_name(route.func.value), "") + route_path
                    if full_path not in PUBLIC_PATHS and not internal:
                        permitted = qualified_name(route.func.value) in router_permissions or _permission(keyword(route, "dependencies")) or any(_permission(default) for default in node.args.defaults + node.args.kw_defaults)
                        values["routes_without_permission"] += not permitted
            if isinstance(node, ast.Call):
                name = qualified_name(node.func, aliases)
                if path.startswith("src/app/") and name.startswith("requests.") and name.split(".")[-1] in VERBS:
                    values["direct_requests_calls"] += 1
                if path not in blob_owners and name in {"getattr", "builtins.getattr"} and len(node.args) > 1 and literal_string(node.args[1]) == "storage_path":
                    storage_read = True
                if (bindings.names(node.func) & {"builtins.setattr", "builtins.delattr"} and len(node.args) > 1
                        and _fastapi_class(bindings, node.args[0]) and literal_string(node.args[1]) == "__init__"):
                    fastapi_patch = True
                if "/persistence/" in path and isinstance(node.func, ast.Attribute) and node.func.attr == "fetchall":
                    query_scope = node
                    while query_scope in parents and not isinstance(query_scope, FUNCTIONS + (ast.Module,)):
                        query_scope = parents[query_scope]
                    receiver = node.func.value
                    sql = None
                    if isinstance(receiver, ast.Call) and qualified_name(receiver.func).endswith(".execute") and receiver.args:
                        sql = literal_string(receiver.args[0])
                        if isinstance(receiver.args[0], ast.Name):
                            sql = _assigned_sql(query_scope, receiver.args[0].id, node.lineno)
                    elif isinstance(receiver, ast.Name):
                        sql = _assigned_sql(query_scope, receiver.id, node.lineno)
                    if not sql or not re.search(r"\bLIMIT\b", sql, re.I):
                        values["unbounded_fetchall"] += 1
                        evidence["unbounded_fetchall_calls"].append({
                            "path": path,
                            "line": node.lineno,
                            "sql": sql,
                        })
                if "list" in scope.lower() or "/persistence/" in path:
                    for item in node.keywords:
                        if item.arg == "limit" and isinstance(item.value, ast.Constant) and item.value.value == 500:
                            values["capped_500_queries"] += 1
                            evidence["capped_500_query_sites"].append({
                                "path": path,
                                "line": node.lineno,
                                "kind": "limit_keyword",
                            })
                if name.split(".")[-1] == "min" and "list" in scope.lower() and any(isinstance(arg, ast.Constant) and arg.value == 500 for arg in node.args):
                    values["capped_500_queries"] += 1
                    evidence["capped_500_query_sites"].append({
                        "path": path,
                        "line": node.lineno,
                        "kind": "min_call",
                    })
            if isinstance(node, ast.Attribute) and isinstance(node.ctx, ast.Load) and node.attr == "storage_path" and path not in blob_owners:
                storage_read = True
                evidence["absolute_storage_path_read_sites"].append({
                    "path": path,
                    "line": node.lineno,
                })
            if isinstance(node, ast.Attribute) and isinstance(node.ctx, (ast.Store, ast.Del)) and node.attr == "__init__":
                fastapi_patch |= _fastapi_class(bindings, node.value)
            string = literal_string(node)
            parent_string = literal_string(parents[node]) if node in parents else None
            if string is not None and parent_string is None:
                if re.search(r"\bLIMIT\s+500\b", string, re.I):
                    values["capped_500_queries"] += 1
                    evidence["capped_500_query_sites"].append({
                        "path": path,
                        "line": node.lineno,
                        "kind": "sql_limit",
                    })
                if not path.startswith("src/app/prompts/") and len(string) >= 50:
                    parent = parents.get(node)
                    names = [qualified_name(target) for target in parent.targets] if isinstance(parent, ast.Assign) else []
                    if isinstance(parent, ast.AnnAssign):
                        names.append(qualified_name(parent.target))
                    if "prompt" in scope.lower() or any("prompt" in name.lower() for name in names):
                        values["inline_prompt_strings"] += 1
        values["fastapi_init_patchers"] += fastapi_patch
        values["absolute_storage_path_reads"] += storage_read
    process_state, unapproved_state, unbounded_caches = process_local_state_report(analysis.sources)
    values["process_local_state_unapproved"] = unapproved_state
    values["unbounded_module_caches"] = unbounded_caches
    evidence["process_local_state_candidates"] = [
        {"path": item["path"], "symbol": item["symbol"], "approved": item["approved"]}
        for item in process_state
    ]
    evidence["process_local_state_inventory_kind"] = "module_scope_scan_plus_reviewed_entries"
    evidence["process_local_state"] = process_state
    values["quarantined_tests"] = _quarantines(analysis.sources)
    patterns, strict_patterns = _mypy_override_patterns(analysis.sources)
    values["mypy_ignored_modules"] = len(patterns)
    ignored = {module_name(path) for path in analysis.sources if path.startswith("src/app/") and path.endswith(".py")
               and any(fnmatch.fnmatchcase(module_name(path), pattern) for pattern in patterns)
               and not any(fnmatch.fnmatchcase(module_name(path), pattern) for pattern in strict_patterns)}
    evidence["mypy_ignored_modules"] = sorted(ignored)
    evidence["mypy_ignored_patterns"] = sorted(patterns)
    evidence["mypy_strict_patterns"] = sorted(strict_patterns)
    evidence["unreachable_rpg_modules"] = _unreachable_python(analysis)
    values["unreachable_rpg_modules"] = len(evidence["unreachable_rpg_modules"])
    evidence["absolute_storage_path_read_files"] = sorted({
        item["path"] for item in evidence["absolute_storage_path_read_sites"]
    })
    return dict(values), evidence


def _assigned_sql(tree: ast.AST, name: str, before_line: int, *, depth: int = 0) -> str | None:
    if depth > 10:
        return None
    candidates = []
    nodes = [tree]
    while nodes:
        node = nodes.pop()
        if node is not tree and isinstance(node, FUNCTIONS + (ast.ClassDef,)):
            continue
        nodes.extend(ast.iter_child_nodes(node))
        if isinstance(node, (ast.Assign, ast.AnnAssign)) and node.lineno < before_line:
            targets = node.targets if isinstance(node, ast.Assign) else [node.target]
            if any(isinstance(target, ast.Name) and target.id == name for target in targets):
                value = node.value
                if isinstance(value, ast.Call) and qualified_name(value.func).endswith(".execute") and value.args:
                    value = value.args[0]
                sql = _assigned_sql(tree, value.id, node.lineno, depth=depth + 1) if isinstance(value, ast.Name) else literal_string(value)
                candidates.append((node.lineno, sql))
    return max(candidates, key=lambda pair: pair[0], default=(0, None))[1]


def _quarantines(sources: dict[str, str]) -> int:
    total = 0
    for path, source in sources.items():
        if PurePosixPath(path).name == "quarantine.toml":
            payload = tomllib.loads(source)
            entries = payload.get("tests", payload.get("quarantine", []))
            if not isinstance(entries, (list, dict)):
                raise AnalysisError(f"invalid quarantine entries: {path}")
            total += len(entries)
    return total


def _mypy_override_patterns(sources: dict[str, str]) -> tuple[set[str], set[str]]:
    ignored_patterns: set[str] = set()
    strict_patterns: set[str] = set()
    for path, source in sources.items():
        if PurePosixPath(path).name == "pyproject.toml":
            for override in tomllib.loads(source).get("tool", {}).get("mypy", {}).get("overrides", []):
                modules = override.get("module", [])
                modules = [modules] if isinstance(modules, str) else modules
                if override.get("ignore_errors") is True:
                    ignored_patterns.update(modules)
                elif override.get("ignore_errors") is False:
                    strict_patterns.update(modules)
        if PurePosixPath(path).name in {"mypy.ini", ".mypy.ini", "setup.cfg"}:
            parser = configparser.ConfigParser()
            parser.read_string(source)
            for section in parser.sections():
                if section.startswith("mypy-") and parser.getboolean(section, "ignore_errors", fallback=False):
                    ignored_patterns.update(pattern.strip() for pattern in section.removeprefix("mypy-").split(","))
    return ignored_patterns, strict_patterns


def _unreachable_python(analysis: SourceAnalysis) -> list[str]:
    graph = analysis.import_edges()
    roots = {name for name in graph if name in {"app.production", "app.worker", "launch", "main"} or analysis.modules[name].endswith("/__main__.py")}
    # Scripts and registered literal module names are additional entry points.
    for path, tree in analysis.trees.items():
        if path.startswith("scripts/"):
            aliases = import_aliases(tree, path)
            for target in aliases.values():
                roots.update(name for name in graph if target == name or target.startswith(name + "."))
        if not is_test(path):
            for node in ast.walk(tree):
                if isinstance(node, ast.Constant) and isinstance(node.value, str):
                    # Feature catalogs use ``module:attribute`` entry points.
                    # The module is imported lazily by the composition root,
                    # so the module portion is a real reachability root.
                    target_module = node.value.partition(":")[0]
                    if target_module in graph:
                        roots.add(target_module)
    reached = _reach(graph, roots)
    return sorted(analysis.modules[name] for name in graph if name.startswith("app.rpg.") and name not in reached and not is_test(analysis.modules[name]))


def _reach(graph: dict[str, set[str]], roots: set[str]) -> set[str]:
    reached, pending = set(), list(roots)
    while pending:
        node = pending.pop()
        if node in reached:
            continue
        reached.add(node)
        pending.extend(graph.get(node, set()) - reached)
    return reached


def _web_graph(sources: dict[str, str]) -> dict[str, set[str]]:
    graph = {path: set() for path in sources if path.startswith("src/apps/web/src/") and path.endswith((".ts", ".tsx", ".css")) and not is_test(path)}
    for path in graph:
        code = mask_js(sources[path])
        imports = re.findall(r"(?:\bfrom\s*|\bimport\s*(?:\(\s*)?)[\"']([^\"']+)[\"']", code)
        for specifier in imports:
            if specifier.startswith("@/"):
                base = PurePosixPath("src/apps/web/src") / specifier[2:]
            elif specifier.startswith("."):
                parts = list(PurePosixPath(path).parent.parts)
                for part in specifier.split("/"):
                    if part == "..":
                        if parts:
                            parts.pop()
                    elif part != ".":
                        parts.append(part)
                base = PurePosixPath(*parts)
            else:
                continue
            candidates = [str(base)] + [str(base) + suffix for suffix in (".ts", ".tsx", ".css", "/index.ts", "/index.tsx")]
            if base.suffix == ".js":
                candidates.extend([str(base.with_suffix(".ts")), str(base.with_suffix(".tsx"))])
            graph[path].update(candidate for candidate in candidates if candidate in graph)
        for glob in re.findall(r"import\.meta\.glob\(\s*[\"']([^\"']+)[\"']", code):
            parts = list(PurePosixPath(path).parent.parts)
            for part in glob.split("/"):
                if part == "..":
                    if parts:
                        parts.pop()
                elif part != ".":
                    parts.append(part)
            absolute = str(PurePosixPath(*parts))
            graph[path].update(candidate for candidate in graph if fnmatch.fnmatchcase(candidate, absolute))
    return graph


def _normalize_api_path(path: str) -> str:
    path = path.split("?")[0]
    path = re.sub(r"\$\{[^}]*\}|\{[^}]*\}", "{}", path)
    return path.rstrip("/") or "/"


def web_metrics(sources: dict[str, str], openapi: dict) -> tuple[dict[str, int | float], dict[str, Any]]:
    values = Counter({key: 0 for key in LOWER_TARGETS if key.startswith(("web_", "eslint_"))})
    flags, api_paths, dynamic_calls = set(), set(), []
    handwritten, route_count, boundaries = set(), 0, 0
    schema_names = set(openapi.get("components", {}).get("schemas", {}))
    for path, source in sources.items():
        if path.startswith("src/apps/web/") and path.endswith(
            (".js", ".jsx", ".ts", ".tsx", ".mjs", ".cjs", ".mts", ".cts")
        ):
            values["eslint_baseline_disables"] += len(
                re.findall(r"eslint-disable(?:-next-line|-line)?[^\n]*", source)
            )
        if not path.startswith("src/apps/web/src/") or is_test(path) or not path.endswith((".ts", ".tsx", ".css")):
            continue
        code = mask_js(source)
        css = path.endswith(".css")
        if not css:
            values["web_fetch_assignment_files"] += bool(re.search(r"(?:window|globalThis)\s*(?:\.fetch|\[\s*['\"]fetch['\"]\s*\])\s*=(?!=)", code) or re.search(r"Object\.defineProperty\(\s*(?:window|globalThis)\s*,\s*['\"]fetch['\"]", code))
            # Window aliases, TypeScript casts and computed installation keys
            # are established forms in this repository. Count distinct flag
            # identities, including their Window-interface declarations.
            flags.update(re.findall(r"\b(__omnix[\w]*)\b", code))
            if not path.startswith("src/apps/web/src/api/"):
                calls = list(re.finditer(r"(?<![\w.])(?:window\.)?fetch\s*\(", code))
                values["web_raw_fetch_outside_api"] += len(calls)
                for call in calls:
                    argument = code[call.end():].lstrip()
                    if not argument.startswith(("'", '"', "`")):
                        dynamic_calls.append(f"{path}:{code.count(chr(10), 0, call.start()) + 1}")
            for declaration in re.finditer(
                r"(?m)^\s*(?:(?:export|declare|default)\s+)*(interface|type)\s+(\w+)\s*"
                r"(?:<[^;{}]*>)?\s*(?:extends\s+[^\{]+\s*)?(?:\{|=)",
                mask_js(source, strings=True),
            ):
                name = declaration.group(2)
                remaining = code[declaration.end():].lstrip()
                if declaration.group(1) == "type" and re.match(r"(?:components|operations|paths)\s*\[", remaining):
                    continue
                if name in schema_names or re.search(r"(?:Request|Response|Payload)$", name):
                    handwritten.add((path, name))
            values["web_mutation_observer_files"] += bool(re.search(r"\b(?:window\.)?MutationObserver\s*\(", code))
            values["web_set_interval_files"] += bool(re.search(r"\b(?:window\.)?setInterval\s*\(", code))
            values["web_custom_event_dispatch_files"] += bool(re.search(r"\bdispatchEvent\s*\(\s*new\s+CustomEvent\s*\(", code))
            route_count += len(re.findall(r"\bcreate(?:Root|File)?Route\s*\(", code))
            boundaries += len(re.findall(r"\berrorComponent\s*:", code))
            # A helper's route declaration produces one route per concrete
            # invocation; the factory itself is not an additional route.
            for name, start, end in _route_factories(source):
                body = code[start:end]
                calls = len(re.findall(r"\b" + re.escape(name) + r"\s*\(\s*['\"]", code[:start] + code[end:]))
                declarations = len(re.findall(r"\bcreate(?:Root|File)?Route\s*\(", body))
                route_count += declarations * (calls - 1)
                boundaries += len(re.findall(r"\berrorComponent\s*:", body)) * (calls - 1)
            api_paths.update(_normalize_api_path(match) for match in re.findall(r"['\"`](/(?:api|internal)/[^'\"`\s]*|/health|/ready|/events)(?:['\"`])", code))
        values["web_important"] += len(re.findall(r"!important\b", code, re.I)) if css else 0
        colors = r"#(?:[0-9a-fA-F]{8}|[0-9a-fA-F]{6}|[0-9a-fA-F]{4}|[0-9a-fA-F]{3})\b|\b(?:rgb|rgba|hsl|hsla|oklch|oklab)\s*\([^)]*\)"
        if css:
            # Only declaration values, not selectors such as #abc.
            declarations = " ".join(re.findall(r"[\w-]+\s*:\s*([^;{}]+)(?:;|(?=\}))", code))
            values["web_hardcoded_colors"] += len(re.findall(colors, declarations))
            values["web_hardcoded_colors"] += len(re.findall(r"\b(?:black|white|red|green|blue|gray|grey|silver|maroon|yellow|lime|aqua|teal|navy|fuchsia|purple|olive)\b", declarations, re.I))
        elif path.endswith(".tsx"):
            values["web_hardcoded_colors"] += len(re.findall(colors, code))
    values["web_omnix_window_flags"] = len(flags)
    values["web_handwritten_api_types"] = len(handwritten)
    values["web_error_boundaries"] = boundaries
    graph = _web_graph(sources)
    roots = {"src/apps/web/src/main.tsx", "src/apps/web/src/main.ts"} & graph.keys()
    reached = _reach(graph, roots)
    unreachable = sorted(path for path in graph if path.endswith((".ts", ".tsx")) and path not in reached and not path.endswith(".d.ts"))
    values["web_unreachable_modules"] = len(unreachable)
    schema_paths = {_normalize_api_path(path) for path in openapi.get("paths", {})}
    matched = api_paths & schema_paths
    denominator = len(api_paths) + len(dynamic_calls)
    values["web_openapi_path_coverage_pct"] = round(100 * len(matched) / denominator, 6) if denominator else 0
    return dict(values), {
        "web_unreachable_modules": unreachable, "web_api_paths": sorted(api_paths),
        "web_api_paths_missing_schema": sorted(api_paths - schema_paths),
        "web_dynamic_fetch_calls": dynamic_calls, "web_route_count": route_count,
        "web_handwritten_api_types": [list(pair) for pair in sorted(handwritten)],
    }


def runtime_values(report: dict | None, digest: str) -> tuple[dict, list[str]]:
    values = {key: None for key in RUNTIME_METRICS}
    errors = []
    if report is None:
        return values, ["runtime measurement report is missing"]
    if report.get("schema_version") != SCHEMA_VERSION or report.get("source_digest") != digest or report.get("environment") != "disposable":
        return values, ["runtime measurement report does not match these sources and disposable environment"]
    try:
        measured = datetime.fromisoformat(report["measured_at"])
        age = (datetime.now(timezone.utc) - measured).total_seconds()
        if measured.tzinfo is None or age < -300 or age > 48 * 3600:
            raise ValueError("expired timestamp")
    except (ValueError, TypeError, KeyError):
        return values, ["runtime measurement timestamp is invalid or older than 48 hours"]
    for key in RUNTIME_METRICS:
        value = report.get("metrics", {}).get(key)
        if not finite_number(value) or key.endswith("_pct") and value > 100:
            errors.append(f"runtime metric is missing or invalid: {key}")
        else:
            values[key] = value
    return values, errors


def measure(sources: dict[str, str], config: dict, *, openapi: dict | None = None, runtime_report: dict | None = None) -> dict:
    analysis = SourceAnalysis(sources, config)
    values, evidence = python_metrics(analysis)
    web_values, web_evidence = web_metrics(analysis.sources, openapi or {})
    for key, value in web_values.items():
        values[key] = value
    values["functions_over_150_lines"] += sum(
        end - start + 1 > 150 for path, source in analysis.sources.items()
        if path.endswith((".ts", ".tsx")) for start, end in js_function_spans(source)
    )
    digest = source_digest(analysis.sources)
    observed, errors = runtime_values(runtime_report, digest)
    values.update(observed)
    if analysis.syntax_errors:
        errors.append("Python source could not be parsed: " + ", ".join(analysis.syntax_errors))
    if openapi is None:
        values["web_openapi_path_coverage_pct"] = None
        errors.append("generated OpenAPI document is missing")
    metrics = {key: {"value": values.get(key), "direction": direction, "target": target}
               for direction, definitions in (("lower", LOWER_TARGETS), ("higher", HIGHER_TARGETS))
               for key, target in definitions.items()}
    return {"schema_version": SCHEMA_VERSION, "scope": "tracked_nonvendor_source",
            "source_digest": digest, "metrics": metrics, "errors": errors,
            "evidence": {**evidence, **web_evidence}}


def compare(current: dict, baseline: dict) -> list[str]:
    errors = list(current.get("errors", []))
    if baseline.get("schema_version") != SCHEMA_VERSION or baseline.get("scope") != current.get("scope"):
        return errors + ["baseline schema or scope mismatch"]
    expected = set(LOWER_TARGETS) | set(HIGHER_TARGETS)
    if set(current.get("metrics", {})) != expected or set(baseline.get("metrics", {})) != expected:
        return errors + ["baseline metric set mismatch"]
    for key in sorted(expected):
        observed, previous = current["metrics"][key], baseline["metrics"][key]
        value, before = observed["value"], previous.get("value")
        if not finite_number(value) or not finite_number(before):
            errors.append(f"{key}: measurement is missing or invalid")
            continue
        if observed["direction"] != previous.get("direction") or observed["target"] != previous.get("target"):
            errors.append(f"{key}: direction or target changed")
        elif observed["direction"] == "lower" and value > before or observed["direction"] == "higher" and value < before:
            errors.append(f"{key}: worsened from {before} to {value}")
    return errors


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path)
    parser.add_argument("--root", type=Path, default=ROOT)
    parser.add_argument("--revision", help="measure a committed source revision instead of the working tree")
    parser.add_argument("--baseline", type=Path, default=Path("resources/architecture/metrics-baseline.json"))
    parser.add_argument("--runtime-report", type=Path, default=Path("resources/architecture/runtime-metrics.json"))
    operation = parser.add_mutually_exclusive_group()
    operation.add_argument("--check", action="store_true")
    operation.add_argument("--update-baseline", action="store_true")
    operation.add_argument("--scan-process-local-state", action="store_true")
    operation.add_argument("--write-process-local-state-doc", action="store_true")
    args = parser.parse_args(argv)
    root = args.root.resolve()
    try:
        baseline_path = (root / args.baseline).resolve()
        output_path = (root / args.output).resolve() if args.output else None
        if output_path == baseline_path:
            raise AnalysisError("--output must differ from --baseline; use --update-baseline to update the ratchet")
        previous = json.loads(baseline_path.read_text(encoding="utf-8")) if (args.check or args.update_baseline) and baseline_path.exists() else None
        sources = tracked_sources(root, revision=args.revision)
        if args.scan_process_local_state:
            findings, unapproved, unbounded = process_local_state_report(sources)
            sys.stdout.write(json.dumps({
                "entries": findings,
                "unapproved": unapproved,
                "unbounded_module_caches": unbounded,
            }, indent=2, sort_keys=True) + "\n")
            return 0
        if args.write_process_local_state_doc:
            findings, unapproved, unbounded = process_local_state_report(sources)
            _atomic_write(root / PROCESS_STATE_DOC, process_local_state_markdown(findings))
            if unapproved or unbounded:
                print(
                    f"architecture metrics: process-state doc generated with {unapproved} unapproved entries and {unbounded} unbounded caches",
                    file=sys.stderr,
                )
                return 1
            return 0
        config = load_layers(root / "resources/architecture/layers.toml")
        schema_path = root / "src/apps/web/src/api/generated/openapi.json"
        if args.revision:
            schema = json.loads(subprocess.run(["git", "show", f"{args.revision}:src/apps/web/src/api/generated/openapi.json"], cwd=root, capture_output=True, check=True).stdout)
        else:
            schema = json.loads(schema_path.read_text(encoding="utf-8")) if schema_path.exists() else None
        report_path = root / args.runtime_report
        report = json.loads(report_path.read_text(encoding="utf-8")) if report_path.exists() else None
        current = measure(sources, config, openapi=schema, runtime_report=report)
        output = json.dumps(current, indent=2, sort_keys=True, allow_nan=False) + "\n"
        if output_path:
            _atomic_write(output_path, output)
        else:
            sys.stdout.write(output)
        failures = list(current["errors"])
        if args.check or args.update_baseline:
            if previous is not None:
                failures = compare(current, previous)
            elif args.check:
                failures.append("metrics baseline is missing")
            if not failures and args.update_baseline:
                _atomic_write(baseline_path, output)
        if failures:
            for failure in failures:
                print(f"architecture metrics: {failure}", file=sys.stderr)
            return 1
        return 0
    except (AnalysisError, OSError, ValueError, KeyError, subprocess.SubprocessError) as exc:
        print(f"architecture metrics: {exc}", file=sys.stderr)
        return 2


def _atomic_write(path: Path, contents: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = None
    try:
        with tempfile.NamedTemporaryFile(mode="w", encoding="utf-8", newline="\n", dir=path.parent, delete=False) as stream:
            temporary = Path(stream.name)
            stream.write(contents)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, path)
    finally:
        if temporary is not None:
            temporary.unlink(missing_ok=True)


if __name__ == "__main__":
    raise SystemExit(main())
