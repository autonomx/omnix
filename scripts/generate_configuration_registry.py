from __future__ import annotations

import argparse
import ast
import json
from pathlib import Path
import re

ROOT = Path(__file__).resolve().parents[1]
OUTPUT = ROOT / "src" / "app" / "config" / "variables.json"
NAME_PATTERN = re.compile(r"[A-Z][A-Z0-9_]{1,127}")
READER_TYPES = {
    "env_bool": "boolean",
    "env_int": "integer",
    "env_float": "number",
    "env_url": "url",
    "env_list": "list",
    "env_str": "string",
    "_flag": "boolean",
    "_env_flag": "boolean",
    "_bool_env": "boolean",
    "_int_env": "integer",
    "_interval_seconds": "number",
    "_float_env": "number",
    "_value": "string",
}
SENSITIVE = ("API_KEY", "TOKEN", "SECRET", "PASSWORD", "CREDENTIAL")


def _literal(node: ast.AST | None, constants: dict[str, object]) -> object | None:
    if node is None:
        return None
    if isinstance(node, ast.Constant):
        return node.value
    if isinstance(node, ast.Name):
        return constants.get(node.id)
    return None


def _constants(tree: ast.Module) -> dict[str, object]:
    result: dict[str, object] = {}
    for node in tree.body:
        if isinstance(node, ast.Assign) and len(node.targets) == 1:
            target = node.targets[0]
            if isinstance(target, ast.Name) and isinstance(node.value, ast.Constant):
                result[target.id] = node.value.value
    return result


def _environment_view(node: ast.AST) -> bool:
    return (
        isinstance(node, ast.Call)
        and isinstance(node.func, ast.Name)
        and node.func.id in {"environment", "_environment"}
    )


def _owner(path: Path) -> str:
    parts = path.parts
    if len(parts) >= 3 and parts[0] == "src" and parts[1] == "app":
        package = parts[2]
        return {
            "agent_runtime": "agent-runtime",
            "assistant_memory": "assistant-memory",
            "assistant_memory_v2": "assistant-memory",
            "assist_core": "hermes",
            "runtime": "kernel",
            "config": "kernel",
            "persistence": "kernel",
        }.get(package, package.replace("_", "-"))
    return "tooling"


def _default_text(value: object | None) -> str | None:
    if value is None:
        return None
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, (list, tuple)):
        return ",".join(str(item) for item in value)
    return str(value)


def discover_variables() -> list[dict[str, str | None]]:
    root = ROOT / "src"
    sources = [
        path
        for path in root.rglob("*.py")
        if "tests" not in path.relative_to(root).parts
        and path.name != "env.py"
    ]
    found: dict[str, list[tuple[str, str | None, str]]] = {}
    for path in [*sources, *((ROOT / "scripts").rglob("*.py"))]:
        try:
            tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        except (OSError, SyntaxError):
            continue
        constants = _constants(tree)
        for node in ast.walk(tree):
            name: object | None = None
            default: object | None = None
            reader_type = "string"
            if isinstance(node, ast.Call):
                function = node.func
                if isinstance(function, ast.Name) and function.id in READER_TYPES:
                    reader_type = READER_TYPES[function.id]
                    if node.args:
                        name = _literal(node.args[0], constants)
                    default_index = 1 if function.id != "env_int" else 1
                    default = _literal(node.args[default_index], constants) if len(node.args) > default_index else None
                elif isinstance(function, ast.Attribute) and function.attr == "get" and _environment_view(function.value):
                    if node.args:
                        name = _literal(node.args[0], constants)
                    default = _literal(node.args[1], constants) if len(node.args) > 1 else None
            elif isinstance(node, ast.Subscript) and _environment_view(node.value):
                name = _literal(node.slice, constants)
            if not isinstance(name, str) or not NAME_PATTERN.fullmatch(name):
                continue
            owner = _owner(path.relative_to(ROOT))
            default_value = None if any(token in name for token in SENSITIVE) else _default_text(default)
            found.setdefault(name, []).append((reader_type, default_value, owner))

    result = []
    for name, uses in sorted(found.items()):
        types = {item[0] for item in uses}
        default_values = {item[1] for item in uses}
        owners = sorted({item[2] for item in uses})
        value_type = next(iter(types)) if len(types) == 1 else "string"
        default = next(iter(default_values)) if len(default_values) == 1 else None
        owner = owners[0] if len(owners) == 1 else ", ".join(owners)
        label = name.removeprefix("OMNIX_").lower().replace("_", " ")
        result.append(
            {
                "name": name,
                "type": value_type,
                "default": default,
                "feature": owner,
                "description": f"Controls {label} for {owner}.",
            }
        )
    return result


def main() -> int:
    parser = argparse.ArgumentParser(description="Generate the known environment-variable registry.")
    parser.add_argument("--check", action="store_true")
    args = parser.parse_args()
    content = json.dumps(discover_variables(), indent=2, sort_keys=True) + "\n"
    current = OUTPUT.read_text(encoding="utf-8") if OUTPUT.exists() else ""
    if args.check:
        if current != content:
            raise SystemExit("configuration registry is stale; run scripts/generate_configuration_registry.py")
        return 0
    OUTPUT.write_text(content, encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
