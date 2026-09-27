"""Lexical binding and value provenance for import-free Python source checks.

This interprets syntax, not application code. Branches retain both possible
origins; imported objects and locally constructed instances remain distinct.
"""

from __future__ import annotations

import ast
from dataclasses import dataclass
import re
from typing import Callable

FUNCTIONS = (ast.FunctionDef, ast.AsyncFunctionDef)


@dataclass(frozen=True)
class Origin:
    kind: str
    name: str = ""


Value = frozenset[Origin]
UNKNOWN: Value = frozenset({Origin("unknown")})
LOCAL: Value = frozenset({Origin("value")})


def value(kind: str, name: str = "") -> Value:
    return frozenset({Origin(kind, name)})


def class_hint(name: str) -> bool:
    return bool(re.search(r"(?:_cls|_class)$|^cls$", name))


class LocalNames(ast.NodeVisitor):
    """Find compile-time function locals without entering nested scopes."""

    def __init__(self) -> None:
        self.names: set[str] = set()
        self.globals: set[str] = set()
        self.nonlocals: set[str] = set()

    def visit_Name(self, node: ast.Name) -> None:
        if isinstance(node.ctx, (ast.Store, ast.Del)):
            self.names.add(node.id)

    def visit_Import(self, node: ast.Import) -> None:
        self.names.update(item.asname or item.name.split(".")[0] for item in node.names)

    def visit_ImportFrom(self, node: ast.ImportFrom) -> None:
        self.names.update(item.asname or item.name for item in node.names if item.name != "*")

    def visit_FunctionDef(self, node: ast.FunctionDef) -> None:
        self.names.add(node.name)

    visit_AsyncFunctionDef = visit_FunctionDef

    def visit_ClassDef(self, node: ast.ClassDef) -> None:
        self.names.add(node.name)

    def visit_Lambda(self, node: ast.Lambda) -> None:
        return

    def visit_Global(self, node: ast.Global) -> None:
        self.globals.update(node.names)

    def visit_Nonlocal(self, node: ast.Nonlocal) -> None:
        self.nonlocals.update(node.names)

    def visit_ExceptHandler(self, node: ast.ExceptHandler) -> None:
        if node.name:
            self.names.add(node.name)
        self.generic_visit(node)

    def visit_ListComp(self, node: ast.ListComp) -> None:
        # Comprehension targets belong to their implicit function scope.
        for child in ast.walk(node):
            if isinstance(child, ast.NamedExpr) and isinstance(child.target, ast.Name):
                self.names.add(child.target.id)

    visit_SetComp = visit_ListComp
    visit_DictComp = visit_ListComp
    visit_GeneratorExp = visit_ListComp

    def visit_MatchAs(self, node: ast.MatchAs) -> None:
        if node.name:
            self.names.add(node.name)
        self.generic_visit(node)

    visit_MatchStar = visit_MatchAs

    def visit_MatchMapping(self, node: ast.MatchMapping) -> None:
        if node.rest:
            self.names.add(node.rest)
        self.generic_visit(node)


class Frame:
    def __init__(self, parent: Frame | None = None, *, name: str = "", local_names: LocalNames | None = None, class_scope: bool = False) -> None:
        self.parent = parent
        self.name = name
        self.bindings: dict[str, Value] = {}
        self.local_names = local_names
        self.class_scope = class_scope
        self.comprehension_scope = False

    def resolve(self, name: str) -> Value:
        if name in self.bindings:
            return self.bindings[name]
        if self.local_names and name in self.local_names.names - self.local_names.globals - self.local_names.nonlocals:
            return UNKNOWN
        if self.local_names and name in self.local_names.globals:
            module = self
            while module.parent is not None:
                module = module.parent
            return module.resolve(name)
        if self.parent:
            return self.parent.resolve(name)
        if name == "builtins":
            return value("foreign", "builtins")
        if name in {"setattr", "delattr", "getattr", "type", "classmethod", "staticmethod", "__import__"}:
            return value("builtin", "builtins." + name)
        if name in {"FastAPI", "APIRouter", "StreamingResponse"}:
            return value("foreign", name)
        return UNKNOWN


class PythonBindings(ast.NodeVisitor):
    def __init__(self, tree: ast.Module, import_target: Callable[[ast.ImportFrom], str]) -> None:
        self.import_target = import_target
        self.frame = Frame()
        self.origins: dict[ast.AST, Value] = {}
        self.classes: dict[str, Frame] = {}
        self.metaclasses: dict[str, Value] = {}
        self.functions: dict[str, tuple[ast.AST, Frame]] = {}
        self.deferred: list[tuple[ast.AST, Frame, Value | None, Frame]] = []
        self.visit(tree)
        # A function's free module/closure names are looked up when called,
        # after its containing scope is assembled. Locals still shadow them.
        index = 0
        while index < len(self.deferred):
            node, parent, owner, definition = self.deferred[index]
            index += 1
            self._function_body(node, parent, owner, definition)

    def visit(self, node: ast.AST | None) -> Value:
        if node is None:
            return UNKNOWN
        result = super().visit(node)
        observed = result if isinstance(result, frozenset) else UNKNOWN
        self.origins[node] = observed
        return observed

    def names(self, node: ast.AST) -> set[str]:
        return {origin.name for origin in self.origins.get(node, UNKNOWN) if origin.name}

    def foreign(self, node: ast.AST) -> bool:
        origins = self.origins.get(node, UNKNOWN)
        return any(origin.kind == "foreign" for origin in origins) or (
            isinstance(node, ast.Name) and class_hint(node.id)
            and any(origin.kind == "unknown" for origin in origins)
        )

    def registry(self, node: ast.AST) -> bool:
        return any(origin.kind == "registry" for origin in self.origins.get(node, UNKNOWN))

    def qualified(self, node: ast.AST, fallback: str) -> str:
        names = self.names(node)
        return next(iter(names)) if len(names) == 1 and not next(iter(names)).startswith("<") else fallback

    def visit_Name(self, node: ast.Name) -> Value:
        return self.frame.resolve(node.id)

    def visit_Constant(self, node: ast.Constant) -> Value:
        return LOCAL

    def visit_Import(self, node: ast.Import) -> None:
        for item in node.names:
            self.frame.bindings[item.asname or item.name.split(".")[0]] = value(
                "foreign", item.name if item.asname else item.name.split(".")[0])

    def visit_ImportFrom(self, node: ast.ImportFrom) -> None:
        base = self.import_target(node)
        for item in node.names:
            if item.name != "*":
                self.frame.bindings[item.asname or item.name] = value("foreign", f"{base}.{item.name}".strip("."))

    def visit_Attribute(self, node: ast.Attribute) -> Value:
        return self.attribute(self.visit(node.value), node.attr)

    def attribute(self, origins: Value, attribute: str) -> Value:
        result = set()
        for origin in origins:
            name = origin.name + "." + attribute
            if name == "sys.modules":
                result.add(Origin("registry", name))
            elif name == "sys.meta_path":
                result.add(Origin("meta_path", name))
            elif origin.kind in {"foreign", "registry", "meta_path"}:
                result.add(Origin("foreign", name))
            elif attribute == "__class__" and origin.kind in {"foreign_instance", "own_instance"}:
                result.add(Origin("foreign" if origin.kind == "foreign_instance" else "own_class", origin.name))
            elif origin.kind in {"own_class", "own_instance"} and origin.name in self.classes:
                result.update(self.classes[origin.name].bindings.get(attribute, UNKNOWN))
            else:
                result.add(Origin("unknown"))
        return frozenset(result)

    def visit_Subscript(self, node: ast.Subscript) -> Value:
        base = self.visit(node.value)
        self.visit(node.slice)
        if any(origin.kind == "registry" for origin in base):
            return value("foreign", "sys.modules[]")
        if self.names(node.value) & {"builtins.type", "typing.Type"}:
            return frozenset(Origin("hint_own" if origin.kind == "own_class" else "hint_foreign", origin.name)
                             for origin in self.origins[node.slice])
        return UNKNOWN

    def visit_Call(self, node: ast.Call) -> Value:
        functions = self.visit(node.func)
        arguments = [self.visit(arg) for arg in node.args]
        for item in node.keywords:
            self.visit(item.value)
        names = {origin.name for origin in functions}
        if names & {"importlib.import_module", "builtins.__import__", "sys.modules.get"}:
            name = node.args[0].value if node.args and isinstance(node.args[0], ast.Constant) and isinstance(node.args[0].value, str) else "<imported module>"
            return value("foreign", name)
        if names & {"builtins.getattr"} and arguments:
            if len(node.args) > 1 and isinstance(node.args[1], ast.Constant) and isinstance(node.args[1].value, str):
                return self.attribute(arguments[0], node.args[1].value)
            return arguments[0]
        if names & {"builtins.type"} and arguments:
            if len(arguments) == 3:
                return value("own_class", "<local dynamic class>")
            result = frozenset()
            for item in arguments[0]:
                if item.kind == "own_instance":
                    result |= value("own_class", item.name)
                elif item.kind == "foreign_instance":
                    result |= value("foreign", item.name)
                elif item.kind == "own_class":
                    result |= self.metaclasses.get(item.name, value("foreign", "builtins.type"))
                else:
                    result |= value("foreign", "builtins.type")
            return result
        result = set()
        for function in functions:
            if function.kind == "function" and function.name in self.functions:
                definition, parent = self.functions[function.name]
                previous = self.frame
                self.frame = parent
                result.update(self.annotation(getattr(definition, "returns", None)))
                self.frame = previous
            elif function.kind == "own_class" or function.kind == "foreign" and function.name.rsplit(".", 1)[-1][:1].isupper():
                result.add(Origin("foreign_instance" if function.kind == "foreign" else "own_instance", function.name))
            else:
                result.add(Origin("unknown"))
        return frozenset(result)

    def bind(self, target: ast.AST, observed: Value) -> None:
        if isinstance(target, ast.Name):
            self.frame.bindings[target.id] = observed
        elif isinstance(target, (ast.Tuple, ast.List)):
            for item in target.elts:
                self.bind(item, UNKNOWN)
        elif isinstance(target, ast.Starred):
            self.bind(target.value, UNKNOWN)

    def visit_Assign(self, node: ast.Assign) -> None:
        observed = self.visit(node.value)
        for target in node.targets:
            self.visit(target)
            self.bind(target, observed)

    def visit_AnnAssign(self, node: ast.AnnAssign) -> None:
        observed = self.visit(node.value) if node.value is not None else self.annotation(node.annotation)
        self.visit(node.target)
        self.bind(node.target, observed)

    def visit_NamedExpr(self, node: ast.NamedExpr) -> Value:
        observed = self.visit(node.value)
        current = self.frame
        while self.frame.comprehension_scope and self.frame.parent is not None:
            self.frame = self.frame.parent
        self.bind(node.target, observed)
        self.frame = current
        return observed

    def visit_AugAssign(self, node: ast.AugAssign) -> None:
        self.visit(node.target)
        self.visit(node.value)
        self.bind(node.target, UNKNOWN)

    def visit_Delete(self, node: ast.Delete) -> None:
        for target in node.targets:
            self.visit(target)
            self.bind(target, UNKNOWN)

    def annotation(self, node: ast.AST | None) -> Value:
        if isinstance(node, ast.Constant) and node.value is None:
            return LOCAL
        if isinstance(node, ast.Constant) and isinstance(node.value, str):
            try:
                node = ast.parse(node.value, mode="eval").body
            except SyntaxError:
                return UNKNOWN
        if isinstance(node, ast.Subscript):
            self.visit(node.value)
            if self.names(node.value) & {"builtins.type", "typing.Type"}:
                return frozenset(Origin("own_class" if origin.kind == "own_class" else "foreign", origin.name)
                                 for origin in self.visit(node.slice))
            if self.names(node.value) & {"typing.Annotated", "typing.ClassVar", "typing.Final"}:
                return self.annotation(node.slice.elts[0] if isinstance(node.slice, ast.Tuple) else node.slice)
            if self.names(node.value) & {"typing.Union", "typing.Optional"}:
                items = node.slice.elts if isinstance(node.slice, ast.Tuple) else [node.slice]
                return frozenset().union(*(self.annotation(item) for item in items))
        if isinstance(node, ast.BinOp) and isinstance(node.op, ast.BitOr):
            return self.annotation(node.left) | self.annotation(node.right)
        origins = self.visit(node)
        result = set()
        for origin in origins:
            if origin.kind in {"hint_own", "hint_foreign"}:
                result.add(Origin("own_class" if origin.kind == "hint_own" else "foreign", origin.name))
            elif origin.name == "types.ModuleType":
                result.add(Origin("foreign", "<module parameter>"))
            elif origin.name == "typing.Any":
                result.update(UNKNOWN)
            elif origin.kind in {"foreign", "own_class"}:
                result.add(Origin("own_instance" if origin.kind == "own_class" else "foreign_instance", origin.name))
            else:
                result.add(origin)
        return frozenset(result)

    def visit_FunctionDef(self, node: ast.FunctionDef) -> None:
        for decorator in node.decorator_list:
            self.visit(decorator)
        for default in node.args.defaults + [item for item in node.args.kw_defaults if item is not None]:
            self.visit(default)
        name = f"{self.frame.name}.{node.name}@{node.lineno}:{node.col_offset}".strip(".")
        self.functions[name] = (node, self.frame)
        self.frame.bindings[node.name] = value("function", name)
        owner = value("own_class", self.frame.name) if self.frame.class_scope else None
        parent = self.frame.parent if owner else self.frame
        assert parent is not None
        self.deferred.append((node, parent, owner, self.frame))

    visit_AsyncFunctionDef = visit_FunctionDef

    def visit_Lambda(self, node: ast.Lambda) -> Value:
        for default in node.args.defaults + [item for item in node.args.kw_defaults if item is not None]:
            self.visit(default)
        self.deferred.append((node, self.frame, None, self.frame))
        return value("function", "<lambda>")

    def _function_body(self, node: ast.AST, parent: Frame, owner: Value | None, definition: Frame) -> None:
        previous = self.frame
        self.frame = definition
        names = LocalNames()
        statements = [node.body] if isinstance(node, ast.Lambda) else node.body
        for statement in statements:
            names.visit(statement)
        args = node.args
        parameters = args.posonlyargs + args.args + args.kwonlyargs + [arg for arg in (args.vararg, args.kwarg) if arg]
        names.names.update(arg.arg for arg in parameters)
        parameter_values = {arg.arg: self.annotation(arg.annotation) for arg in parameters}
        defaults = list(zip((args.posonlyargs + args.args)[-len(args.defaults):], args.defaults)) if args.defaults else []
        defaults += list(zip(args.kwonlyargs, args.kw_defaults))
        for arg, default in defaults:
            if default is not None and arg.annotation is None:
                # Callers may override a default. It supplies a possible
                # origin, never proof that every invocation owns that value.
                parameter_values[arg.arg] = self.origins.get(default, UNKNOWN) | UNKNOWN
        if owner and args.posonlyargs + args.args:
            first = (args.posonlyargs + args.args)[0].arg
            decorators = {name for decorator in node.decorator_list for name in self.names(decorator)}
            if "builtins.classmethod" in decorators:
                parameter_values[first] = owner
            elif "builtins.staticmethod" not in decorators:
                parameter_values[first] = frozenset(Origin("own_instance", origin.name) for origin in owner)
        self.frame = Frame(parent, name=f"{parent.name}.{getattr(node, 'name', '<lambda>')}".strip("."), local_names=names)
        self.frame.bindings.update(parameter_values)
        for statement in statements:
            self.visit(statement)
        self.frame = previous

    def visit_ClassDef(self, node: ast.ClassDef) -> None:
        for expression in node.bases + node.decorator_list + [item.value for item in node.keywords]:
            self.visit(expression)
        parent = self.frame
        # Definition identity is internal only. Redefinitions and classes with
        # the same name in different closures must not share their members.
        name = f"{parent.name}.{node.name}@{node.lineno}:{node.col_offset}".strip(".")
        explicit_meta = next((item.value for item in node.keywords if item.arg == "metaclass"), None)
        if explicit_meta is not None:
            self.metaclasses[name] = self.origins[explicit_meta]
        else:
            inherited = frozenset().union(*(self.metaclasses.get(origin.name, value("foreign", "builtins.type"))
                                           for base in node.bases for origin in self.origins[base]))
            if any(origin.kind == "own_class" for origin in inherited):
                inherited -= value("foreign", "builtins.type")
            self.metaclasses[name] = inherited or value("foreign", "builtins.type")
        self.frame = Frame(parent, name=name, class_scope=True)
        self.classes[name] = self.frame
        for statement in node.body:
            self.visit(statement)
        self.frame = parent
        self.frame.bindings[node.name] = value("own_class", name)

    def branches(self, alternatives: list[list[ast.AST]]) -> None:
        before = dict(self.frame.bindings)
        outcomes = []
        for statements in alternatives:
            self.frame.bindings = dict(before)
            for statement in statements:
                self.visit(statement)
            outcomes.append(dict(self.frame.bindings))
        keys = set(before).union(*(outcome.keys() for outcome in outcomes))
        self.frame.bindings = {key: frozenset().union(*(outcome.get(key, before.get(key, UNKNOWN)) for outcome in outcomes))
                               for key in keys}

    def visit_If(self, node: ast.If) -> None:
        self.visit(node.test)
        self.branches([node.body, node.orelse])

    def visit_For(self, node: ast.For) -> None:
        self.visit(node.iter)
        self.visit(node.target)
        before = dict(self.frame.bindings)
        self.bind(node.target, self.iteration_value(node.iter))
        for statement in node.body:
            self.visit(statement)
        after = self.frame.bindings
        self.frame.bindings = {key: before.get(key, UNKNOWN) | after.get(key, UNKNOWN) for key in before.keys() | after.keys()}
        for statement in node.orelse:
            self.visit(statement)

    visit_AsyncFor = visit_For

    def iteration_value(self, node: ast.AST) -> Value:
        if isinstance(node, (ast.List, ast.Tuple, ast.Set)):
            return frozenset().union(*(self.origins.get(item, UNKNOWN) for item in node.elts)) or UNKNOWN
        return UNKNOWN

    def comprehension(self, node: ast.AST) -> Value:
        parent = self.frame
        names = LocalNames()
        for generator in node.generators:
            names.visit(generator.target)
        self.visit(node.generators[0].iter)
        self.frame = Frame(parent, name="<comprehension>", local_names=names)
        self.frame.comprehension_scope = True
        for index, generator in enumerate(node.generators):
            if index:
                self.visit(generator.iter)
            self.visit(generator.target)
            self.bind(generator.target, self.iteration_value(generator.iter))
            for condition in generator.ifs:
                self.visit(condition)
        if isinstance(node, ast.DictComp):
            self.visit(node.key)
            self.visit(node.value)
        else:
            self.visit(node.elt)
        self.frame = parent
        return LOCAL

    visit_ListComp = comprehension
    visit_SetComp = comprehension
    visit_DictComp = comprehension
    visit_GeneratorExp = comprehension

    def visit_While(self, node: ast.While) -> None:
        self.visit(node.test)
        self.branches([node.body, []])
        for statement in node.orelse:
            self.visit(statement)

    def visit_With(self, node: ast.With) -> None:
        for item in node.items:
            self.visit(item.context_expr)
            if item.optional_vars:
                self.visit(item.optional_vars)
                self.bind(item.optional_vars, UNKNOWN)
        for statement in node.body:
            self.visit(statement)

    visit_AsyncWith = visit_With

    def visit_ExceptHandler(self, node: ast.ExceptHandler) -> None:
        self.visit(node.type)
        if node.name:
            self.frame.bindings[node.name] = value("foreign_instance", "<exception>")
        for statement in node.body:
            self.visit(statement)
        if node.name:
            self.frame.bindings[node.name] = UNKNOWN

    def visit_Try(self, node: ast.Try) -> None:
        self.branches([node.body + node.orelse] + [[handler] for handler in node.handlers])
        for statement in node.finalbody:
            self.visit(statement)

    visit_TryStar = visit_Try

    def capture_pattern(self, pattern: ast.AST, subject: Value) -> None:
        if isinstance(pattern, ast.MatchAs):
            if pattern.pattern:
                self.capture_pattern(pattern.pattern, subject)
            if pattern.name:
                self.frame.bindings[pattern.name] = subject
        elif isinstance(pattern, ast.MatchStar):
            if pattern.name:
                self.frame.bindings[pattern.name] = LOCAL
        else:
            if isinstance(pattern, ast.MatchMapping) and pattern.rest:
                self.frame.bindings[pattern.rest] = LOCAL
            for child in ast.iter_child_nodes(pattern):
                if isinstance(child, ast.pattern):
                    self.capture_pattern(child, UNKNOWN)
                else:
                    self.visit(child)

    def visit_Match(self, node: ast.Match) -> None:
        subject = self.visit(node.subject)
        before = dict(self.frame.bindings)
        outcomes = []
        exhaustive = False
        for case in node.cases:
            self.frame.bindings = dict(before)
            self.capture_pattern(case.pattern, subject)
            self.visit(case.guard)
            for statement in case.body:
                self.visit(statement)
            outcomes.append(dict(self.frame.bindings))
            exhaustive |= isinstance(case.pattern, ast.MatchAs) and case.pattern.pattern is None and case.guard is None
        if not exhaustive:
            outcomes.append(before)
        keys = set(before).union(*(outcome.keys() for outcome in outcomes))
        self.frame.bindings = {key: frozenset().union(*(outcome.get(key, before.get(key, UNKNOWN)) for outcome in outcomes))
                               for key in keys}
