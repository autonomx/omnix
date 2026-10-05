"""One release version across the Python and web packages (WP-11.5)."""
from __future__ import annotations

import json
import re
import tomllib
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]


def test_the_package_versions_agree_and_are_semantic() -> None:
    python = tomllib.loads((ROOT / "pyproject.toml").read_text(encoding="utf-8"))["project"]["version"]
    web = json.loads((ROOT / "src" / "apps" / "web" / "package.json").read_text(encoding="utf-8"))["version"]
    root = json.loads((ROOT / "package.json").read_text(encoding="utf-8"))["version"]
    lock = json.loads((ROOT / "package-lock.json").read_text(encoding="utf-8"))

    assert re.fullmatch(r"\d+\.\d+\.\d+", python)
    assert web == root == python
    assert lock["version"] == lock["packages"][""]["version"] == python


def test_the_changelog_has_an_unreleased_section_or_the_current_version() -> None:
    python = tomllib.loads((ROOT / "pyproject.toml").read_text(encoding="utf-8"))["project"]["version"]
    changelog = (ROOT / "CHANGELOG.md").read_text(encoding="utf-8")

    assert "## [Unreleased]" in changelog or f"## [{python}]" in changelog
