"""Shared, import-free source analysis for the architecture metrics and lint.

Only tracked repository source is read. Parsing never imports application code,
executes a provider, opens a database, or follows a source symlink.
"""

from __future__ import annotations

import ast
from dataclasses import dataclass
import hashlib
from pathlib import Path, PurePosixPath
import re
import subprocess
import tomllib
from typing import Iterable

from architecture_bindings import PythonBindings


EXCLUDED_PARTS = {"node_modules", "vendor", "vendored", "third_party", "third-party", ".venv", "venv", ".tools"}
TRACKED_SOURCE_SUFFIXES = frozenset({
    ".py", ".pyfrag", ".ts", ".tsx", ".css", ".json", ".toml", ".ini",
    ".cfg", ".sql", ".html", ".md",
})
ROUTE_METHODS = {"get", "post", "put", "patch", "delete", "options", "head", "api_route", "websocket"}
PLATFORM_TABLES = {
    "omnix_jobs", "omnix_job_events", "omnix_job_attempts", "omnix_outbox",
    "omnix_outbox_events", "omnix_audit_events", "omnix_workspaces", "omnix_users",
    "omnix_workspace_memberships",
}
FUNCTIONS = (ast.FunctionDef, ast.AsyncFunctionDef)


class AnalysisError(ValueError):
    pass


def is_generated_feature_api(path: str) -> bool:
    """A web feature's generated gateway types (PA-2.4), written by `api:types`."""
    parts = PurePosixPath(path).parts
    return len(parts) == 6 and parts[:3] == ("web", "src", "features") and parts[4:] == ("api", "generated.ts")


def included_path(path: str) -> bool:
    normalized = PurePosixPath(path)
    return not (
        normalized.is_absolute() or ".." in normalized.parts
        or EXCLUDED_PARTS.intersection(normalized.parts)
        or path.startswith("web/src/api/generated/")
        or is_generated_feature_api(path)
    )


def tracked_sources(root: Path, *, revision: str | None = None) -> dict[str, str]:
    command = ["git", "ls-tree", "-r", "--name-only", "-z", revision] if revision else ["git", "ls-files", "-z"]
    result = subprocess.run(command, cwd=root, capture_output=True, check=True)
    sources = {}
    for name in sorted(set(result.stdout.decode("utf-8").split("\0"))):
        if not name or not included_path(name):
            continue
        if Path(name).suffix.lower() not in TRACKED_SOURCE_SUFFIXES:
            continue
        if revision:
            data = subprocess.run(["git", "show", f"{revision}:{name}"], cwd=root, capture_output=True, check=True).stdout
        else:
            path = root / name
            if not path.exists():
                # A tracked deletion is an improvement, not an unreadable file.
                continue
            if path.is_symlink() or not path.is_file():
                raise AnalysisError(f"tracked source is not a regular file: {name}")
            if not path.resolve().is_relative_to(root.resolve()):
                raise AnalysisError(f"tracked source escapes the repository: {name}")
            data = path.read_bytes()
        try:
            sources[name] = data.decode("utf-8-sig")
        except UnicodeDecodeError as exc:
            raise AnalysisError(f"tracked source is not UTF-8: {name}") from exc
    return sources


def source_digest(sources: dict[str, str]) -> str:
    digest = hashlib.sha256()
    for path, source in sorted(sources.items()):
        # Runtime evidence is bound to code/configuration, not to the reports
        # containing that evidence or the baseline that consumes it.
        if (
            path in {
                "docs/ENTERPRISE_ARCHITECTURE_REVIEW_2026-09-27.md",
                "docs/ENTERPRISE_ARCHITECTURE_ROADMAP_2026-09-27.md",
                "resources/architecture/metrics-baseline.json",
                "resources/architecture/runtime-metrics.json",
                "resources/architecture/lint-baseline.json",
            }
            or path.startswith("docs/roadmap/")
            or path.startswith("docs/measurements/")
        ):
            continue
        digest.update(path.encode("utf-8") + b"\0" + source.replace("\r\n", "\n").encode("utf-8") + b"\0")
    return digest.hexdigest()


# PA-5.3: platform capabilities, apps and composition packages sit in tier folders.
TIER_FOLDERS = frozenset({"app.platform", "app.apps", "app.composition"})


def top_package(module: str) -> str:
    """The top-level package of an ``app`` module: ``app.<package>``, or ``app.<tier>.<package>`` in a tier folder."""
    parts = module.split(".")
    return ".".join(parts[:3] if ".".join(parts[:2]) in TIER_FOLDERS and len(parts) > 2 else parts[:2])


def module_name(path: str) -> str:
    parts = PurePosixPath(path).with_suffix("").parts
    if parts and parts[0] == "src":
        parts = parts[1:]
    if parts and parts[-1] == "__init__":
        parts = parts[:-1]
    return ".".join(parts)


def qualified_name(node: ast.AST | None, aliases: dict[str, str] | None = None) -> str:
    if isinstance(node, ast.Name):
        return (aliases or {}).get(node.id, node.id)
    if isinstance(node, ast.Attribute):
        base = qualified_name(node.value, aliases)
        return f"{base}.{node.attr}" if base else ""
    if isinstance(node, ast.Subscript):
        return qualified_name(node.value, aliases) + "[]"
    return ""


def imported_modules(node: ast.Import | ast.ImportFrom, path: str, modules: dict[str, str]) -> list[str]:
    """The modules one import statement names, preferring a submodule over its package."""
    if isinstance(node, ast.Import):
        return [item.name for item in node.names]
    base = import_target(node, path)
    return sorted({f"{base}.{item.name}" if f"{base}.{item.name}" in modules else base for item in node.names})


def import_target(node: ast.ImportFrom, path: str) -> str:
    if not node.level:
        return node.module or ""
    current = module_name(path).split(".")
    package = current if PurePosixPath(path).name == "__init__.py" else current[:-1]
    keep = len(package) - node.level + 1
    if keep < 0:
        raise AnalysisError(f"relative import escapes package: {path}")
    return ".".join(package[:keep] + ([node.module] if node.module else []))


def import_aliases(tree: ast.AST, path: str) -> dict[str, str]:
    aliases = {}
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for item in node.names:
                aliases[item.asname or item.name.split(".")[0]] = item.name if item.asname else item.name.split(".")[0]
        elif isinstance(node, ast.ImportFrom):
            base = import_target(node, path)
            for item in node.names:
                if item.name != "*":
                    aliases[item.asname or item.name] = f"{base}.{item.name}".strip(".")
    return aliases


def scoped_nodes(tree: ast.AST, *, descend_functions: bool = True) -> Iterable[tuple[ast.AST, str]]:
    def visit(node: ast.AST, scope: str):
        yield node, scope
        if isinstance(node, FUNCTIONS + (ast.ClassDef,)):
            scope = f"{scope}.{node.name}".strip(".")
            if isinstance(node, FUNCTIONS) and not descend_functions:
                return
        for child in ast.iter_child_nodes(node):
            yield from visit(child, scope)
    yield from visit(tree, "")


def function_body_nodes(node: ast.AST) -> Iterable[ast.AST]:
    for child in ast.iter_child_nodes(node):
        if isinstance(child, FUNCTIONS + (ast.ClassDef, ast.Lambda)):
            continue
        yield child
        yield from function_body_nodes(child)


def route_decorators(node: ast.AST) -> list[ast.Call]:
    return [decorator for decorator in getattr(node, "decorator_list", [])
            if isinstance(decorator, ast.Call) and isinstance(decorator.func, ast.Attribute)
            and decorator.func.attr in ROUTE_METHODS]


def keyword(call: ast.Call, name: str) -> ast.AST | None:
    return next((item.value for item in call.keywords if item.arg == name), None)


def literal_string(node: ast.AST) -> str | None:
    if isinstance(node, ast.Constant) and isinstance(node.value, str):
        return node.value
    if isinstance(node, ast.JoinedStr):
        return "".join(value.value if isinstance(value, ast.Constant) and isinstance(value.value, str) else "{}" for value in node.values)
    if isinstance(node, ast.BinOp) and isinstance(node.op, ast.Add):
        left, right = literal_string(node.left), literal_string(node.right)
        return (left or "") + (right or "") if left is not None or right is not None else None
    return None


def is_test(path: str) -> bool:
    parts = PurePosixPath(path).parts
    return "tests" in parts or "test" in parts or bool(re.search(r"(?:^|[./])test_|\.(?:test|spec)\.", path))


def cli_module(path: str, tree: ast.Module) -> bool:
    """A module run as a command: ``cli.py``/``*_cli.py``/``__main__.py``, under ``cli/``, or with a main guard."""
    if path.endswith(("/cli.py", "_cli.py", "/__main__.py")) or "/cli/" in path:
        return True
    for node in tree.body:
        if isinstance(node, ast.If) and isinstance(node.test, ast.Compare):
            left, comparators = node.test.left, node.test.comparators
            if (isinstance(left, ast.Name) and left.id == "__name__" and len(comparators) == 1
                    and isinstance(comparators[0], ast.Constant) and comparators[0].value == "__main__"):
                return True
    return False


def is_production(path: str, config: dict) -> bool:
    return not is_test(path) and (path.startswith("src/app/") or path in config.get("production", {}).get("entrypoints", []))


@dataclass(frozen=True)
class Violation:
    rule: str
    path: str
    fingerprint: str
    line: int


def package_prefix(module: str, prefix: str) -> bool:
    return module == prefix or module.startswith(prefix + ".")


def layer_for(module: str, config: dict) -> tuple[str, str] | None:
    """The statically listed layer (kernel, shared services, composition) of a module."""
    matches = [(name, prefix) for name, layer in config.get("layers", {}).items()
               for prefix in layer.get("packages", ()) if package_prefix(module, prefix)]
    return max(matches, key=lambda pair: len(pair[1]), default=None)


@dataclass(frozen=True)
class ModuleUnit:
    """An ADR-0016 module: a feature package with its nested features folded in."""

    package: str
    tier: str | None
    ids: frozenset[str]
    depends_on: frozenset[str]
    tier_conflicts: tuple[str, ...]
    words: frozenset[str] = frozenset()


def load_layers(path: Path) -> dict:
    with path.open("rb") as handle:
        return tomllib.load(handle)


class SourceAnalysis:
    def __init__(self, sources: dict[str, str], config: dict) -> None:
        self.sources = {path: source for path, source in sources.items() if included_path(path)}
        self.config = config
        self.trees: dict[str, ast.Module] = {}
        self.syntax_errors: list[str] = []
        for path, source in self.sources.items():
            if not path.endswith(".py"):
                continue
            try:
                tree = ast.parse(source, filename=path)
                # AST parsing alone accepts return/break outside valid scopes.
                # Compilation checks those constraints without executing code.
                compile(tree, path, "exec", dont_inherit=True)
                self.trees[path] = tree
            except SyntaxError:
                self.syntax_errors.append(path)
        self.modules = {module_name(path): path for path in self.trees if path.startswith("src/")}
        self._bindings: dict[str, PythonBindings] = {}
        self._units: dict[str, ModuleUnit] | None = None

    def feature_dependencies(self) -> dict[str, tuple[str, frozenset[str], str | None]]:
        """Read package feature ids, declared dependencies and tiers without imports."""
        return {package: declaration[:3] for package, declaration in self._feature_declarations().items()}

    def _feature_declarations(self) -> dict[str, tuple[str, frozenset[str], str | None, str]]:
        result: dict[str, tuple[str, frozenset[str], str | None, str]] = {}
        for module, path in self.modules.items():
            if not module.endswith(".feature"):
                continue
            package = module.removesuffix(".feature")
            for node in self.trees[path].body:
                if not isinstance(node, (ast.Assign, ast.AnnAssign)):
                    continue
                targets = node.targets if isinstance(node, ast.Assign) else [node.target]
                if not any(isinstance(target, ast.Name) and target.id == "FEATURE" for target in targets):
                    continue
                call = node.value
                if not isinstance(call, ast.Call) or qualified_name(call.func).split(".")[-1] != "FeatureModule":
                    continue
                values = {
                    keyword.arg: keyword.value
                    for keyword in call.keywords
                    if keyword.arg is not None
                }
                try:
                    feature_id = ast.literal_eval(values["id"])
                except (KeyError, ValueError, TypeError):
                    continue
                # depends_on and uses both declare a one-way contract dependency;
                # only depends_on also requires the other feature to be enabled.
                try:
                    dependencies = tuple(
                        item
                        for key in ("depends_on", "uses")
                        if values.get(key) is not None
                        for item in ast.literal_eval(values[key])
                    )
                except (ValueError, TypeError):
                    continue
                if (
                    not isinstance(feature_id, str)
                    or not isinstance(dependencies, (tuple, list, set, frozenset))
                    or any(not isinstance(item, str) for item in dependencies)
                ):
                    continue
                try:
                    tier = ast.literal_eval(values["tier"]) if "tier" in values else None
                except (ValueError, TypeError):
                    tier = None
                try:
                    title = ast.literal_eval(values["title"]) if "title" in values else ""
                except (ValueError, TypeError):
                    title = ""
                result[package] = (feature_id, frozenset(dependencies), tier if isinstance(tier, str) else None,
                                   title if isinstance(title, str) else "")
                break
        return result

    def module_units(self) -> dict[str, ModuleUnit]:
        """Feature packages grouped into ADR-0016 module units, keyed by the outermost package."""
        if self._units is None:
            features = self._feature_declarations()
            roots = [package for package in features
                     if not any(other != package and package_prefix(package, other) for other in features)]
            units = {}
            for root in roots:
                members = {package: features[package] for package in features if package_prefix(package, root)}
                ids = frozenset(member[0] for member in members.values())
                tier = features[root][2]
                units[root] = ModuleUnit(
                    package=root,
                    tier=tier,
                    ids=ids,
                    depends_on=frozenset().union(*(member[1] for member in members.values())) - ids,
                    tier_conflicts=tuple(sorted(package for package, member in members.items()
                                                if package != root and member[2] != tier)),
                    words=frozenset(
                        word for package, member in members.items()
                        for word in (package.rsplit(".", 1)[-1], *member[0].replace("-", "_").split("_"),
                                     member[0].replace("-", "_"), *re.findall(r"[a-z0-9]+", member[3].lower()))
                        if len(word) >= 3 and word not in {"and", "the"}
                    ),
                )
            self._units = units
        return self._units

    def layer_of(self, module: str) -> tuple[str, str] | None:
        """The layer and owning unit of a module: a listed layer, a declared tier, or a transitional owner."""
        layers = self.config.get("layers", {})
        tier_layers = {layer["tier"]: name for name, layer in layers.items() if "tier" in layer}
        units = self.module_units()
        candidates = [(len(prefix), name, prefix) for name, layer in layers.items()
                      for prefix in layer.get("packages", ()) if package_prefix(module, prefix)]
        candidates += [(len(package), tier_layers[unit.tier], package) for package, unit in units.items()
                       if unit.tier in tier_layers and package_prefix(module, package)]
        owners = self.config.get("modules", {}).get("package_owners", {})
        candidates += [(len(prefix), tier_layers[units[owner].tier], owner) for prefix, owner in owners.items()
                       if owner in units and units[owner].tier in tier_layers and package_prefix(module, prefix)]
        if not candidates:
            return None
        _, layer, unit = max(candidates)
        return layer, unit

    def table_owner_map(self) -> dict[str, str]:
        """Every live table's owner: the frozen historical map plus module-folder migrations (PA-2.2)."""
        import table_ownership

        packages = {"src/" + package.replace(".", "/"): sorted(unit.ids)[0] for package, unit in self.module_units().items()}
        return table_ownership.table_owners(self.sources, table_ownership.load_historical(self.sources), packages)

    def _code_owner(self, module: str) -> frozenset[str] | None:
        layer = self.layer_of(module)
        if layer is None:
            return None
        if layer[0] == "kernel":
            return frozenset({"kernel"})
        if layer[0] == "shared_services":
            return frozenset({"shared"})
        units = self.module_units()
        return units[layer[1]].ids if layer[1] in units else None

    def table_ownership_violations(self) -> list[Violation]:
        """AL016: SQL may reference only tables its own module owns (ADR-0016, PA-2.2)."""
        owners = self.table_owner_map()
        if not owners:
            return []
        position = re.compile(
            r"\b(?:from|join|into|update|table|references)\s+(?:only\s+|if\s+(?:not\s+)?exists\s+)?([a-z_][a-z0-9_]*)",
            re.I,
        )
        result = []
        for path, tree in self.trees.items():
            if not is_production(path, self.config):
                continue
            own = self._code_owner(module_name(path))
            if own is None:
                continue
            for node, scope in scoped_nodes(tree):
                texts = []
                if isinstance(node, ast.Constant) and isinstance(node.value, str):
                    texts = [node.value]
                for text in texts:
                    for match in position.finditer(text):
                        table = match.group(1).lower()
                        owner = owners.get(table)
                        if owner is not None and owner not in own:
                            result.append(Violation("AL016", path, f"{scope or '<module>'}:{table}", getattr(node, "lineno", 1)))
        result.extend(self._migration_ownership_violations(owners))
        return result

    def _migration_ownership_violations(self, owners: dict[str, str]) -> list[Violation]:
        """A migration in a module's own folder changes only that module's tables."""
        import table_ownership

        packages = {"src/" + package.replace(".", "/"): sorted(unit.ids)[0] for package, unit in self.module_units().items()}
        units = {sorted(unit.ids)[0]: unit.ids for unit in self.module_units().values()}
        statement = re.compile(
            r"\b(alter\s+table|drop\s+table|create\s+(?:unique\s+)?index\s+(?:concurrently\s+)?(?:if\s+not\s+exists\s+)?[a-z_0-9]*\s+on|insert\s+into|update|delete\s+from)\s+(?:only\s+|if\s+exists\s+)?([a-z_][a-z0-9_]*)",
            re.I,
        )
        result = []
        for path, text in table_ownership.migration_sources(self.sources).items():
            if path.startswith(table_ownership.KERNEL_MIGRATIONS):
                continue
            module = table_ownership.module_owner(path, packages)
            if module is None:
                continue
            for match in statement.finditer(text):
                verb, table = " ".join(match.group(1).lower().split()[:2]), match.group(2).lower()
                owner = owners.get(table)
                if owner is None or owner in units.get(module, frozenset({module})):
                    continue
                tail = text[match.end():match.end() + 400].lower()
                if (table in table_ownership.REGISTRATION_TABLES and verb == "insert into"
                        and "on conflict do nothing" in " ".join(tail.split()).split(";")[0]):
                    continue
                line = text.count("\n", 0, match.start()) + 1
                result.append(Violation("AL016", path, f"<migration>:{verb}:{table}", line))
        return result

    def reciprocal_dependencies(self) -> list[tuple[str, str]]:
        """Distinct packages or modules that import each other at any import scope (AL015).

        Composition imports everything by design; an import into composition is
        already an AL001 violation, so pairs with composition are not repeated here.
        """
        layers = self.config.get("layers", {})
        edges: dict[str, set[str]] = {}
        for source, targets in self.import_edges().items():
            source_layer = self.layer_of(source)
            if (source_layer is None or "*" in layers[source_layer[0]]["may_import"]
                    or not is_production(self.modules[source], self.config)):
                continue
            for target in targets:
                target_layer = self.layer_of(target)
                if (target_layer is not None and target_layer[1] != source_layer[1]
                        and "*" not in layers[target_layer[0]]["may_import"]
                        and is_production(self.modules[target], self.config)):
                    edges.setdefault(source_layer[1], set()).add(target_layer[1])
        return sorted({tuple(sorted((source, target))) for source, targets in edges.items()
                       for target in targets if source in edges.get(target, set())})

    def boundary_imports(self) -> dict[str, list[str]]:
        """ADR-0016 import sites by kind, for the roadmap ratchet metrics."""
        layers = self.config.get("layers", {})
        units = self.module_units()
        contract = self.config.get("modules", {}).get("contract_module", "contracts")
        result: dict[str, list[str]] = {
            "reverse_contract_imports": [], "app_to_app_imports": [],
            "composition_imports_outside_composition": [],
        }
        for path, tree in self.trees.items():
            if not is_production(path, self.config):
                continue
            source = self.layer_of(module_name(path))
            if source is None or "*" in layers[source[0]]["may_import"]:
                continue
            for node, _ in scoped_nodes(tree):
                if not isinstance(node, (ast.Import, ast.ImportFrom)):
                    continue
                for target in imported_modules(node, path, self.modules):
                    destination = self.layer_of(target)
                    if destination is None or destination[1] == source[1]:
                        continue
                    site = f"{path}:{node.lineno}:{target}"
                    if "*" in layers[destination[0]]["may_import"]:
                        result["composition_imports_outside_composition"].append(site)
                    source_tier = layers[source[0]].get("tier")
                    target_tier = layers[destination[0]].get("tier")
                    if source_tier == target_tier == "app":
                        result["app_to_app_imports"].append(site)
                    if (source_tier and target_tier and package_prefix(target, destination[1] + "." + contract)
                            and units[source[1]].ids & units[destination[1]].depends_on):
                        result["reverse_contract_imports"].append(site)
        return {key: sorted(sites) for key, sites in result.items()}

    def import_allowed(self, source: tuple[str, str], target: tuple[str, str], module: str) -> bool:
        """ADR-0016 dependency rules for one import between classified modules."""
        layers = self.config["layers"]
        allowed = layers[source[0]]["may_import"]
        if "*" in allowed or source[1] == target[1]:
            return True
        target_tier = layers[target[0]].get("tier")
        if target_tier is None:
            return target[0] in allowed
        units = self.module_units()
        if layers[source[0]].get("tier") is None or target_tier != "platform":
            return False
        contract = target[1] + "." + self.config.get("modules", {}).get("contract_module", "contracts")
        return package_prefix(module, contract) and bool(units[target[1]].ids & units[source[1]].depends_on)

    def bindings(self, path: str) -> PythonBindings:
        if path not in self._bindings:
            self._bindings[path] = PythonBindings(self.trees[path], lambda node: import_target(node, path))
        return self._bindings[path]

    def import_edges(self, *, module_level: bool = False) -> dict[str, set[str]]:
        edges: dict[str, set[str]] = {name: set() for name in self.modules}
        for name, path in self.modules.items():
            for node, _ in scoped_nodes(self.trees[path], descend_functions=not module_level):
                targets = []
                if isinstance(node, ast.Import):
                    targets = [item.name for item in node.names]
                elif isinstance(node, ast.ImportFrom):
                    base = import_target(node, path)
                    targets = [base] + [f"{base}.{item.name}" for item in node.names if item.name != "*"]
                elif not module_level and isinstance(node, ast.Call) and qualified_name(node.func).endswith(("import_module", "__import__")):
                    if node.args and isinstance(node.args[0], ast.Constant) and isinstance(node.args[0].value, str):
                        targets = [node.args[0].value]
                for target in targets:
                    if target in self.modules:
                        edges[name].add(target)
                    # Executing a submodule import also executes its package.
                    for index in range(1, len(target.split("."))):
                        parent = ".".join(target.split(".")[:index])
                        if parent in self.modules:
                            edges[name].add(parent)
        return edges

    def package_cycles(self) -> list[tuple[str, str]]:
        edges: dict[str, set[str]] = {}
        for source, targets in self.import_edges(module_level=True).items():
            if not source.startswith("app."):
                continue
            owner = top_package(source)
            for target in targets:
                if target.startswith("app.") and top_package(target) != owner:
                    edges.setdefault(owner, set()).add(top_package(target))
        return sorted({tuple(sorted((source, target))) for source, targets in edges.items()
                       for target in targets if source in edges.get(target, set())})

    def violations(self) -> list[Violation]:
        result = []
        owners = self.config.get("owners", {})
        units = self.module_units()
        unit_paths = {"src/" + package.replace(".", "/") + "/feature.py": package for package in units}
        for path, tree in self.trees.items():
            if not is_production(path, self.config):
                continue
            relative = path.removeprefix("src/")
            aliases = import_aliases(tree, path)
            bindings = self.bindings(path)
            parents = {child: node for node in ast.walk(tree) for child in ast.iter_child_nodes(node)}
            patches: set[ast.AST] = set()
            # A command-line program prints its output; that is not logging (AL008).
            cli_program = cli_module(path, tree)

            def add(rule: str, node: ast.AST, subject: str, scope: str) -> None:
                result.append(Violation(rule, path, f"{scope or '<module>'}:{subject}", getattr(node, "lineno", 1)))

            def foreign(node: ast.AST) -> bool:
                return bindings.foreign(node)

            # ADR-0016: every app module belongs to a layer, and a feature's
            # nested features share its tier.
            source_module = module_name(path)
            source_layer = self.layer_of(source_module)
            # A tier folder's own __init__ (PA-5.3) holds only its docstring.
            tier_folder = source_module in TIER_FOLDERS and all(
                isinstance(node, ast.Expr) and isinstance(node.value, ast.Constant) for node in tree.body)
            if source_layer is None and source_module.startswith("app.") and not tier_folder:
                add("AL001", tree, "<uncovered>", "")
            if path in unit_paths:
                unit = units[unit_paths[path]]
                if unit.tier is None:
                    add("AL001", tree, "<missing-tier>", "")
                for conflict in unit.tier_conflicts:
                    add("AL001", tree, "<tier-conflict>:" + conflict, "")

            for node, scope in scoped_nodes(tree):
                if isinstance(node, (ast.Import, ast.ImportFrom)):
                    for target in imported_modules(node, path, self.modules):
                        target_layer = self.layer_of(target)
                        if source_layer and target_layer and not self.import_allowed(source_layer, target_layer, target):
                            add("AL001", node, target, scope)
                    if isinstance(node, ast.ImportFrom) and path.startswith("src/app/") and any(item.name == "*" for item in node.names):
                        add("AL010", node, import_target(node, path), scope)

                targets = []
                if isinstance(node, ast.Assign):
                    targets = list(node.targets)
                elif isinstance(node, (ast.AnnAssign, ast.AugAssign)):
                    targets = [node.target]
                elif isinstance(node, ast.Delete):
                    targets = list(node.targets)
                elif isinstance(node, (ast.For, ast.AsyncFor, ast.comprehension)):
                    targets = [node.target]
                elif isinstance(node, (ast.With, ast.AsyncWith)):
                    targets = [item.optional_vars for item in node.items if item.optional_vars is not None]
                elif isinstance(node, ast.Call):
                    call_name = qualified_name(node.func, aliases)
                    if bindings.names(node.func) & {"builtins.setattr", "builtins.delattr"} and node.args:
                        if foreign(node.args[0]):
                            attribute = literal_string(node.args[1]) if len(node.args) > 1 else None
                            add("AL003", node, bindings.qualified(node.args[0], qualified_name(node.args[0])) + "." + (attribute or "<dynamic>"), scope)
                            patches.add(node)
                    if bindings.names(node.func) & {"sys.meta_path.insert", "sys.meta_path.append"}:
                        add("AL003", node, bindings.qualified(node.func, call_name), scope)
                        patches.add(node)
                    if call_name in {"os.getenv", "os.environ.get", "os.environ.pop", "os.environ.copy", "os.environ.items", "os.environ.keys", "os.environ.values", "os.environ.setdefault"}:
                        if not path.startswith("src/app/config/") and path != "src/app/runtime/net.py":
                            add("AL007", node, call_name + ":" + str(literal_string(node.args[0]) if node.args else "<dynamic>"), scope)
                    if call_name in {"print", "builtins.print"} and path.startswith("src/app/") and not cli_program:
                        add("AL008", node, "print", scope)
                    if call_name.split(".")[-1] == "LocalBlobStore" and relative not in owners.get("blob_store_construction", []):
                        add("AL011", node, call_name, scope)
                    if call_name.split(".")[-1] in {"local_tenant_context", "bootstrap_local_tenant"}:
                        if not path.startswith("src/app/security/") and relative not in owners.get("tenant_bootstrap", []) and "/cli/" not in path and not path.endswith("/__main__.py"):
                            add("AL012", node, call_name, scope)
                    core = any(package_prefix(module_name(path), prefix) for prefix in self.config.get("rpg_core", {}).get("packages", []))
                    unseeded = call_name == "random.Random" and not node.args and not any(item.arg in {"x", "seed"} for item in node.keywords)
                    if core and (unseeded or call_name.startswith("random.") and call_name != "random.Random"
                                 or call_name in {"time.time", "datetime.now", "datetime.utcnow", "datetime.datetime.now", "datetime.datetime.utcnow", "uuid.uuid4"}):
                        add("AL013", node, call_name, scope)

                for target in targets:
                    for part in ast.walk(target):
                        if (isinstance(part, ast.Attribute) and isinstance(part.ctx, (ast.Store, ast.Del)) and foreign(part.value)
                                or isinstance(part, ast.Subscript) and isinstance(part.ctx, (ast.Store, ast.Del)) and bindings.registry(part.value)):
                            add("AL003", node, bindings.qualified(part, qualified_name(part)), scope)
                            patches.add(node)
                            break
                if isinstance(node, ast.Subscript) and isinstance(node.ctx, ast.Load) and qualified_name(node.value, aliases) == "os.environ":
                    if not path.startswith("src/app/config/") and path != "src/app/runtime/net.py":
                        add("AL007", node, "os.environ:" + str(literal_string(node.slice)), scope)
                if isinstance(node, (ast.Name, ast.Attribute)) and isinstance(node.ctx, ast.Load) and qualified_name(node, aliases) == "os.environ":
                    parent = parents.get(node)
                    if not isinstance(parent, (ast.Subscript, ast.Attribute)) and not path.startswith("src/app/config/") and path != "src/app/runtime/net.py":
                        add("AL007", node, "os.environ:<whole environment>", scope)
                if isinstance(node, ast.AsyncFunctionDef) and route_decorators(node):
                    if not any(isinstance(child, (ast.Await, ast.AsyncFor, ast.AsyncWith)) for child in function_body_nodes(node)):
                        add("AL005", node, node.name, scope)
                if isinstance(node, ast.ExceptHandler):
                    broad = node.type is None or qualified_name(node.type, aliases) in {"Exception", "builtins.Exception"}
                    silent = all(isinstance(item, (ast.Pass, ast.Continue)) or isinstance(item, ast.Return) and (item.value is None or isinstance(item.value, ast.Constant) and item.value.value is None)
                                 or isinstance(item, ast.Expr) and isinstance(item.value, ast.Constant) and item.value.value is Ellipsis for item in node.body)
                    if broad and silent:
                        add("AL009", node, "except", scope)
                string = literal_string(node)
                parent_string = literal_string(parents[node]) if node in parents else None
                if string is not None and parent_string is None and relative not in owners.get("platform_table_sql", []):
                    if re.search(r"\b(?:SELECT|INSERT|UPDATE|DELETE|ALTER|CREATE|TRUNCATE|FROM|JOIN)\b", string, re.I):
                        tables = sorted({table for table in PLATFORM_TABLES if re.search(r"\b" + table + r"\b", string, re.I)})
                        if tables:
                            add("AL006", node, ",".join(tables), scope)
            for node, scope in scoped_nodes(tree):
                if isinstance(node, FUNCTIONS) and re.match(r"(?:_?install_|patch_)", node.name) and any(child in patches for child in ast.walk(node)):
                    add("AL004", node, node.name, scope)
        return result
