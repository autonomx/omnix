from __future__ import annotations

from pathlib import Path
import subprocess
import sys

from app.config.registry import render_configuration_markdown


def test_configuration_doc_is_generated_from_registry() -> None:
    root = Path(__file__).resolve().parents[3]
    assert (root / "docs" / "CONFIGURATION.md").read_text(encoding="utf-8") == render_configuration_markdown()
    subprocess.run(
        [sys.executable, str(root / "scripts" / "generate_configuration_docs.py"), "--check"],
        cwd=root,
        check=True,
    )



def test_a_reader_imported_under_another_name_still_registers_its_variable() -> None:
    """`from app.config.env import env_str as _env_str` (runtime/net.py) used to hide OMNIX_BIND_HOST."""
    import ast
    import importlib.util
    import json

    root = Path(__file__).resolve().parents[3]
    spec = importlib.util.spec_from_file_location("registry_generator", root / "scripts" / "generate_configuration_registry.py")
    generator = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(generator)
    tree = ast.parse("from app.config.env import env_str as _env_str, env_int as port_of, env_bool")

    assert generator._reader_aliases(tree) == {"_env_str": "env_str", "port_of": "env_int"}
    registry = json.loads((root / "src" / "app" / "config" / "variables.json").read_text(encoding="utf-8"))
    assert {"name": "OMNIX_BIND_HOST", "type": "string"}.items() <= next(
        item for item in registry if item["name"] == "OMNIX_BIND_HOST"
    ).items()
