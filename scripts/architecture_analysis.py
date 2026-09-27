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
ROUTE_METHODS = {"get", "post", "put", "patch", "delete", "options", "head", "api_route", "websocket"}
PLATFORM_TABLES = {
    "omnix_jobs", "omnix_job_events", "omnix_job_attempts", "omnix_outbox",
    "omnix_outbox_events", "omnix_audit_events", "omnix_workspaces", "omnix_users",
    "omnix_workspace_memberships",
}
FUNCTIONS = (ast.FunctionDef, ast.AsyncFunctionDef)


class AnalysisError(ValueError):
    pass


def included_path(path: str) -> bool:
    normalized = PurePosixPath(path)
    return not (
        normalized.is_absolute() or ".." in normalized.parts
        or EXCLUDED_PARTS.intersection(normalized.parts)
        or path.startswith("src/apps/web/src/api/generated/")
    )


def tracked_sources(root: Path, *, revision: str | None = None) -> dict[str, str]:
    command = ["git", "ls-tree", "-r", "--name-only", "-z", revision] if revision else ["git", "ls-files", "-z"]
    result = subprocess.run(command, cwd=root, capture_output=True, check=True)
    sources = {}
    for name in sorted(set(result.stdout.decode("utf-8").split("\0"))):
        if not name or not included_path(name):
            continue
        if Path(name).suffix.lower() not in {".py", ".pyfrag", ".ts", ".tsx", ".css", ".json", ".toml", ".ini", ".cfg", ".sql", ".html"}:
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
        if path in {"resources/architecture/metrics-baseline.json", "resources/architecture/runtime-metrics.json", "resources/architecture/lint-baseline.json"} or path.startswith("docs/measurements/"):
            continue
        digest.update(path.encode("utf-8") + b"\0" + source.replace("\r\n", "\n").encode("utf-8") + b"\0")
    return digest.hexdigest()


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
    matches = [(name, prefix) for name, layer in config.get("layers", {}).items()
               for prefix in layer["packages"] if package_prefix(module, prefix)]
    return max(matches, key=lambda pair: len(pair[1]), default=None)


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
            owner = source.split(".")[1]
            for target in targets:
                if target.startswith("app.") and target.split(".")[1] != owner:
                    edges.setdefault(owner, set()).add(target.split(".")[1])
        return sorted({tuple(sorted((source, target))) for source, targets in edges.items()
                       for target in targets if source in edges.get(target, set())})

    def violations(self) -> list[Violation]:
        result = []
        owners = self.config.get("owners", {})
        for path, tree in self.trees.items():
            if not is_production(path, self.config):
                continue
            relative = path.removeprefix("src/")
            aliases = import_aliases(tree, path)
            bindings = self.bindings(path)
            parents = {child: node for node in ast.walk(tree) for child in ast.iter_child_nodes(node)}
            patches: set[ast.AST] = set()

            def add(rule: str, node: ast.AST, subject: str, scope: str) -> None:
                result.append(Violation(rule, path, f"{scope or '<module>'}:{subject}", getattr(node, "lineno", 1)))

            def foreign(node: ast.AST) -> bool:
                return bindings.foreign(node)

            for node, scope in scoped_nodes(tree):
                if isinstance(node, (ast.Import, ast.ImportFrom)):
                    imports = ([item.name for item in node.names] if isinstance(node, ast.Import)
                               else sorted({f"{import_target(node, path)}.{item.name}"
                                            if f"{import_target(node, path)}.{item.name}" in self.modules
                                            else import_target(node, path) for item in node.names}))
                    source_layer = layer_for(module_name(path), self.config)
                    for target in imports:
                        target_layer = layer_for(target, self.config)
                        if source_layer and target_layer:
                            allowed = self.config["layers"][source_layer[0]]["may_import"]
                            same_feature = source_layer[0] == target_layer[0] == "features" and source_layer[1] == target_layer[1]
                            if ("*" not in allowed and not same_feature and (target_layer[0] not in allowed
                                or source_layer[0] == target_layer[0] == "features")):
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
                    if call_name in {"print", "builtins.print"} and path.startswith("src/app/"):
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
