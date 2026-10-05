"""Module conformance (ADR-0016, PA-4.1): what every catalog module must have.

Static checks, read from the tracked sources:

- ``feature``: ``feature.py`` exports ``FEATURE`` with this id and a tier;
- ``contract``: a ``contracts.py`` module or ``contracts/`` package;
- ``migrations``: its ``migrations/`` folder changes only its own tables, and no
  kernel-folder migration changes only its tables;
- ``declarations``: a ``declarations.py`` that imports only kernel modules;
- ``tests``: ``src/tests/<package>/`` holds tests (PA-2.5);
- ``web``: when it owns gateway operations, a web manifest lists it in ``backendModules``.

``tenant_isolation`` reads a freshly migrated PostgreSQL database: every table
the migrations create is isolated (row-level security enabled and forced, and a
``tenant_isolation`` policy in one of the two ``0106`` forms) or exempt (an
``omnix:tenant-exempt: <reason>`` table comment, or a ``tenant_exempt`` reason
in the frozen historical owner map).

``resources/architecture/module-conformance-baseline.json`` lists the gaps that
remain; it only shrinks. ``python scripts/module_conformance.py`` prints them.
"""
from __future__ import annotations

import ast
import json
import re
import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
BASELINE = ROOT / "resources" / "architecture" / "module-conformance-baseline.json"
STATIC_CHECKS = ("feature", "contract", "migrations", "declarations", "tests", "web")
TIERS = frozenset({"kernel", "shared_services", "platform", "app"})
KERNEL_OWNER = "kernel"
EXEMPT_COMMENT = "omnix:tenant-exempt:"

for path in (ROOT / "scripts", ROOT / "src"):
    if str(path) not in sys.path:
        sys.path.insert(0, str(path))


def catalog() -> dict[str, str]:
    """Catalog module id -> its Python package (``app.rpg.hermes``)."""
    from app.runtime.feature_catalog import FEATURE_CATALOG

    return {module_id: target.split(":", 1)[0].removesuffix(".feature") for module_id, target in FEATURE_CATALOG.items()}


def _package_dir(package: str) -> Path:
    return ROOT / "src" / Path(*package.split("."))


def _analysis() -> Any:
    from architecture_analysis import SourceAnalysis, load_layers, tracked_sources

    return SourceAnalysis(tracked_sources(ROOT), load_layers(ROOT / "resources" / "architecture" / "layers.toml"))


def _feature_gap(module_id: str, package: str) -> bool:
    from app.runtime.feature_catalog import load_feature

    feature = load_feature(module_id)
    return feature.id != module_id or getattr(feature, "tier", None) not in TIERS


def _contract_gap(package: str) -> bool:
    directory = _package_dir(package)
    return not ((directory / "contracts.py").is_file() or (directory / "contracts" / "__init__.py").is_file())


def _migration_gaps(analysis: Any) -> set[str]:
    """Modules whose migrations change another module's tables, or that still have kernel-folder migrations."""
    import table_ownership

    owners = analysis.table_owner_map()
    packages = {"src/" + package.replace(".", "/"): sorted(unit.ids)[0] for package, unit in analysis.module_units().items()}
    unit_ids = {sorted(unit.ids)[0]: unit.ids for unit in analysis.module_units().values()}
    gaps: set[str] = set()
    for violation in analysis._migration_ownership_violations(owners):
        owner = table_ownership.module_owner(violation.path, packages)
        gaps.update(unit_ids.get(owner, {owner}) if owner else ())
    for owner in table_ownership.single_owner_kernel_migrations(analysis.sources, owners).values():
        gaps.add(owner)
    return gaps


def _declarations_gap(package: str, analysis: Any) -> bool:
    path = _package_dir(package) / "declarations.py"
    if not path.is_file():
        return True
    tree = ast.parse(path.read_text(encoding="utf-8"))
    for node in ast.walk(tree):
        names = [alias.name for alias in node.names] if isinstance(node, ast.Import) else (
            [node.module] if isinstance(node, ast.ImportFrom) and node.module and node.level == 0 else [])
        for name in names:
            if name.startswith("app.") and (analysis.layer_of(name) or ("",))[0] != "kernel":
                return True
    return False


def _tests_gap(package: str) -> bool:
    directory = ROOT / "src" / "tests" / package.rsplit(".", 1)[-1]
    return not any(directory.rglob("test_*.py"))


def web_backend_modules() -> set[str]:
    """Backend modules some web manifest lists in ``backendModules``."""
    listed: set[str] = set()
    for manifest in (ROOT / "web" / "src" / "features").glob("*/module.ts"):
        for match in re.finditer(r"\bbackendModules:\s*\[([^\]]*)\]", manifest.read_text(encoding="utf-8")):
            listed.update(re.findall(r"'([a-z0-9-]+)'", match.group(1)))
    return listed


def operation_owners() -> set[str]:
    path = ROOT / "web" / "src" / "api" / "generated" / "route-owners.json"
    return set(json.loads(path.read_text(encoding="utf-8"))["operations"].values()) - {KERNEL_OWNER}


def static_gaps() -> dict[str, list[str]]:
    """Catalog module id -> the static checks it does not pass."""
    analysis = _analysis()
    migration_gaps = _migration_gaps(analysis)
    listed, owning = web_backend_modules(), operation_owners()
    result: dict[str, list[str]] = {}
    for module_id, package in sorted(catalog().items()):
        failed = {
            "feature": _feature_gap(module_id, package),
            "contract": _contract_gap(package),
            "migrations": module_id in migration_gaps,
            "declarations": _declarations_gap(package, analysis),
            "tests": _tests_gap(package),
            "web": module_id in owning and module_id not in listed,
        }
        result[module_id] = [check for check in STATIC_CHECKS if failed[check]]
    return result


# The two policy forms of 0106_row_level_security.sql, as pg_policies prints them.
_SETTING = r"current_setting\('omnix\.{name}'::text, true\)"
_WORKSPACE_USING = re.compile(
    rf"^\(\((?P<column>workspace_id|id) = {_SETTING.format(name='workspace_id')}\) OR \({_SETTING.format(name='system')} = 'on'::text\)\)$"
)
_WORKSPACE_CHECK = re.compile(
    rf"^\(\((?P<column>workspace_id|id) = {_SETTING.format(name='workspace_id')}\) OR (?:\((?P=column) IS NULL\) OR )?"
    rf"\({_SETTING.format(name='system')} = 'on'::text\)\)$"
)
_PARENT = re.compile(
    r"^\(EXISTS \( SELECT 1 FROM (?P<parent>[a-z_][a-z0-9_]*) parent WHERE \(parent\.(?P<key>[a-z_][a-z0-9_]*) = "
    r"(?P<child>[a-z_][a-z0-9_]*)\.(?P<fk>[a-z_][a-z0-9_]*)\)\)\)$"
)


def _normalize(expression: str | None) -> str:
    return " ".join((expression or "").split())


def table_status(connection: Any) -> dict[str, dict[str, Any]]:
    """Each public table's row-level security, tenant policy, workspace column, comment and foreign keys."""
    rows = connection.execute(
        """SELECT c.relname, c.relrowsecurity, c.relforcerowsecurity, obj_description(c.oid, 'pg_class'),
                  (SELECT p.qual FROM pg_policies p WHERE p.schemaname = 'public' AND p.tablename = c.relname
                     AND p.policyname = 'tenant_isolation' AND p.cmd = 'ALL'),
                  (SELECT p.with_check FROM pg_policies p WHERE p.schemaname = 'public' AND p.tablename = c.relname
                     AND p.policyname = 'tenant_isolation' AND p.cmd = 'ALL'),
                  (SELECT count(*) FROM pg_policies p WHERE p.schemaname = 'public' AND p.tablename = c.relname)
             FROM pg_class c JOIN pg_namespace n ON n.oid = c.relnamespace
            WHERE n.nspname = 'public' AND c.relkind IN ('r', 'p')"""
    ).fetchall()
    keys = connection.execute(
        """SELECT child.relname, child_column.attname, parent.relname, parent_column.attname
             FROM pg_constraint k
             JOIN pg_class child ON child.oid = k.conrelid
             JOIN pg_class parent ON parent.oid = k.confrelid
             JOIN pg_attribute child_column ON child_column.attrelid = k.conrelid AND child_column.attnum = k.conkey[1]
             JOIN pg_attribute parent_column ON parent_column.attrelid = k.confrelid AND parent_column.attnum = k.confkey[1]
            WHERE k.contype = 'f' AND cardinality(k.conkey) = 1"""
    ).fetchall()
    status = {
        name: {"rls": bool(rls), "forced": bool(forced), "comment": comment or "", "using": _normalize(using),
               "check": _normalize(check), "policies": int(count), "foreign_keys": set()}
        for name, rls, forced, comment, using, check, count in rows
    }
    for child, column, parent, parent_column in keys:
        if child in status:
            status[child]["foreign_keys"].add((column, parent, parent_column))
    return status


def isolated(table: str, status: dict[str, dict[str, Any]], seen: frozenset[str] = frozenset()) -> bool:
    """Forced row-level security with a 0106-form tenant policy; a child's parent must be isolated too."""
    entry = status.get(table)
    if entry is None or table in seen or not (entry["rls"] and entry["forced"]) or entry["policies"] != 1:
        return False
    using, check = entry["using"], entry["check"]
    workspace = _WORKSPACE_USING.match(using)
    if workspace and _WORKSPACE_CHECK.match(check) and _WORKSPACE_CHECK.match(check).group("column") == workspace.group("column"):
        return True
    parent = _PARENT.match(using)
    if parent and check == using and parent.group("child") == table:
        key = (parent.group("fk"), parent.group("parent"), parent.group("key"))
        return key in entry["foreign_keys"] and isolated(parent.group("parent"), status, seen | {table})
    return False


def tenant_gaps(connection: Any, owners: dict[str, str], historical: dict[str, dict]) -> dict[str, list[str]]:
    """Owner -> the tables its migrations create that are neither isolated nor exempt."""
    status = table_status(connection)
    gaps: dict[str, list[str]] = {}
    for table, owner in sorted(owners.items()):
        if table not in status or isolated(table, status):
            continue
        if status[table]["comment"].startswith(EXEMPT_COMMENT) or historical.get(table, {}).get("tenant_exempt"):
            continue
        gaps.setdefault(owner, []).append(table)
    return gaps


def exemptions(connection: Any, owners: dict[str, str], historical: dict[str, dict]) -> dict[str, str]:
    """Every exempt table and its reason, for the report."""
    status = table_status(connection)
    result = {}
    for table in sorted(owners):
        if table not in status or isolated(table, status):
            continue
        comment = status[table]["comment"]
        reason = comment[len(EXEMPT_COMMENT):].strip() if comment.startswith(EXEMPT_COMMENT) else historical.get(table, {}).get("tenant_exempt")
        if reason:
            result[table] = reason
    return result


def table_owners_and_historical() -> tuple[dict[str, str], dict[str, dict]]:
    import table_ownership

    analysis = _analysis()
    return analysis.table_owner_map(), table_ownership.load_historical(analysis.sources)


def load_baseline() -> dict[str, Any]:
    return json.loads(BASELINE.read_text(encoding="utf-8"))


def main() -> int:
    gaps = static_gaps()
    for module_id, failed in gaps.items():
        print(f"{module_id}: {', '.join(failed) or 'conforms'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
