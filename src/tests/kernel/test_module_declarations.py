"""Module declarations: the kernel reads them without loading the module (ADR-0016, PA-2.1, PA-2.2)."""
from __future__ import annotations

import json
import subprocess
import sys
import tomllib
from pathlib import Path

import pytest

from app.persistence.declarations import declaration_modules, module_settings_sections

ROOT = Path(__file__).resolve().parents[3]
FIXTURE = ROOT / "src" / "tests" / "fixtures" / "settings_profile_documents.json"


def _loaded_app_modules(statement: str) -> list[str]:
    """``app.*`` modules a clean interpreter has loaded after running ``statement``."""
    script = f"import sys\n{statement}\nprint('\\n'.join(sorted(name for name in sys.modules if name.startswith('app.'))))"
    result = subprocess.run([sys.executable, "-c", script], cwd=ROOT / "src", capture_output=True, text=True, check=True)
    return result.stdout.split()


def _kernel_packages() -> tuple[str, ...]:
    layers = tomllib.loads((ROOT / "resources" / "architecture" / "layers.toml").read_text(encoding="utf-8"))
    return tuple(layers["layers"]["kernel"]["packages"])


@pytest.mark.parametrize("module", declaration_modules())
def test_a_modules_declarations_load_only_the_kernel(module: str) -> None:
    kernel = _kernel_packages()
    own = {module, *(module.rsplit(".", depth)[0] for depth in range(1, module.count(".")))}

    foreign = [name for name in _loaded_app_modules(f"import {module}")
               if name not in own and not any(name == package or name.startswith(package + ".") for package in kernel)]

    assert foreign == []


def test_building_the_settings_profile_imports_no_feature() -> None:
    loaded = _loaded_app_modules("import app.platform.settings_profile_models")

    assert [name for name in loaded if name.endswith(".feature")] == []


def test_stored_settings_documents_are_unchanged() -> None:
    from app.platform.settings_profile_models import SettingsProfile

    fixture = json.loads(FIXTURE.read_text(encoding="utf-8"))

    assert json.dumps(SettingsProfile().model_dump(mode="json", by_alias=True)) == fixture["default"]
    sample = SettingsProfile.model_validate(fixture["sample_input"]).model_dump(mode="json", by_alias=True)
    assert json.dumps(sample) == fixture["sample"]


def test_every_declared_section_is_in_the_profile_whatever_is_enabled() -> None:
    from app.platform.settings_profile_models import SettingsProfile

    fields = set(SettingsProfile.model_fields)

    assert {section.field for section in module_settings_sections()} == {"voice", "storyteller", "podcast", "rpg"}
    assert {section.field for section in module_settings_sections()} <= fields


def test_saving_one_section_keeps_another_modules_section_exactly() -> None:
    from app.platform.settings_profile_core import SETTINGS_PROFILE_KEY
    from app.platform.settings_profile_repository import save_settings_profile

    rpg = {"difficulty": "harsh", "worldActivity": "living_world", "campaignDefaults": {"tone": "grim"}}
    settings: dict = {SETTINGS_PROFILE_KEY: {"rpg": rpg}}
    save_settings_profile(settings, {"rpg": rpg})
    stored_rpg = json.dumps(settings[SETTINGS_PROFILE_KEY]["rpg"])

    save_settings_profile(settings, {"voice": {"language": "German"}})

    assert settings[SETTINGS_PROFILE_KEY]["voice"]["language"] == "German"
    assert json.dumps(settings[SETTINGS_PROFILE_KEY]["rpg"]) == stored_rpg
