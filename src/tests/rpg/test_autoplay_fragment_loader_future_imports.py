from __future__ import annotations

import importlib.util
import builtins
import io
import re
import shutil
import zipfile
from pathlib import Path
from typing import Callable, List


def _load_loader():
    module_path = Path(__file__).with_name("autoplay_llm_campaign.py")
    spec = importlib.util.spec_from_file_location("autoplay_llm_campaign_loader_under_test", module_path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"Could not load autoplay loader module from {module_path}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _load_combiner() -> Callable[[List[Path]], str]:
    module = _load_loader()
    combiner = getattr(module, "_combine_autoplay_campaign_fragments", None)
    if not callable(combiner):
        raise RuntimeError("_combine_autoplay_campaign_fragments missing from autoplay loader module")
    return combiner


def test_autoplay_fragment_combiner_hoists_future_imports(tmp_path) -> None:
    combine_autoplay_campaign_fragments = _load_combiner()
    early = tmp_path / "000_early_runtime_guard.pyfrag"
    later = tmp_path / "100_runtime_core.pyfrag"
    early.write_text("import atexit\nX = 1\n", encoding="utf-8")
    later.write_text("from __future__ import annotations\nY: list[str] = []\n", encoding="utf-8")

    combined = combine_autoplay_campaign_fragments([early, later])

    lines = combined.splitlines()
    assert lines[0] == "from __future__ import annotations"
    assert combined.count("from __future__ import annotations") == 1
    assert combined.index("from __future__ import annotations") < combined.index("import atexit")
    compile(combined, "combined_test.py", "exec")


def test_real_autoplay_fragments_compile_without_patching_stdlib_path(tmp_path) -> None:
    module = _load_loader()
    fragments = module._autoplay_campaign_fragment_paths()
    combined = module._combine_autoplay_campaign_fragments(fragments)

    assert len(fragments) >= 100
    assert "from pathlib import Path" not in combined
    assert not re.search(r"(?m)^\s*[A-Za-z_]\w*Path\.write_text\s*=", combined)
    assert "_install_autoplay_path_write_hook(" in combined
    compile(combined, str(tmp_path / "autoplay_campaign_combined.py"), "exec")


def test_committed_autoplay_runtime_matches_source_fragments() -> None:
    module = _load_loader()
    generated_path = module._autoplay_campaign_generated_path()

    assert generated_path.read_text(encoding="utf-8") == module._combine_autoplay_campaign_fragments(
        module._autoplay_campaign_fragment_paths()
    )


def test_path_write_hooks_are_private_and_enabled_only_for_the_cli() -> None:
    module = _load_loader()
    original_write_text = Path.write_text
    private_path_type = module._AUTOPLAY_PATH_CLASS

    def replacement_write_text(self, data, *args, **kwargs):
        return original_write_text(self, data, *args, **kwargs)

    module._AUTOPLAY_INSTALL_PATH_HOOKS = False
    module._install_autoplay_path_write_hook(private_path_type, replacement_write_text)
    assert Path.write_text is original_write_text
    assert private_path_type.write_text is original_write_text

    module._AUTOPLAY_INSTALL_PATH_HOOKS = True
    module._install_autoplay_path_write_hook(private_path_type, replacement_write_text)
    assert Path.write_text is original_write_text
    assert private_path_type.write_text is replacement_write_text
    assert isinstance(Path("."), private_path_type)


def test_importing_composed_autoplay_runtime_does_not_patch_process_io() -> None:
    originals = (
        Path.write_text,
        Path.write_bytes,
        builtins.open,
        io.open,
        shutil.copyfile,
        shutil.copy2,
        zipfile.ZipFile.write,
        zipfile.ZipFile.writestr,
    )

    _load_loader()

    assert (
        Path.write_text,
        Path.write_bytes,
        builtins.open,
        io.open,
        shutil.copyfile,
        shutil.copy2,
        zipfile.ZipFile.write,
        zipfile.ZipFile.writestr,
    ) == originals


def test_autoplay_fragment_combiner_dedupes_multiple_future_imports(tmp_path) -> None:
    combine_autoplay_campaign_fragments = _load_combiner()
    first = tmp_path / "001_first.pyfrag"
    second = tmp_path / "002_second.pyfrag"
    first.write_text("from __future__ import annotations\nA = 1\n", encoding="utf-8")
    second.write_text("from __future__ import annotations\nB = 2\n", encoding="utf-8")

    combined = combine_autoplay_campaign_fragments([first, second])

    assert combined.count("from __future__ import annotations") == 1
    compile(combined, "combined_test.py", "exec")
