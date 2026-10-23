"""Desktop runtime pack locks: the shared Torch layer, derived overlays and pack file lists (roadmap §4.3)."""
from __future__ import annotations

import hashlib
import json
import subprocess
import sys
from pathlib import Path

import pytest

from app.models.locks import (
    LockError, check_overlay, check_torch_pins, derive_overlay, parse_lock, torch_layer_lock,
)
from app.models.packfiles import PackFile, check_pack_files, load_pack_files, resolve, write_pack_files

ROOT = Path(__file__).resolve().parents[3]


def _block(name: str, version: str, *digests: str, via: str = "-r x.in") -> str:
    hashes = " \\\n".join(f"    --hash=sha256:{digest * 64}" for digest in digests)
    return f"{name}=={version} \\\n{hashes}\n    # via {via}\n"


SERVICE = (
    "#\n# header\n#\n"
    + _block("numpy", "1.26.4", "1")
    + _block("torch", "2.6.0+cu124", "2", "3")
    + _block("torchaudio", "2.6.0+cu124", "4")
    + _block("torchvision", "0.21.0+cu124", "5")
    + "# The following packages are considered to be unsafe in a requirements file:\n"
    + _block("setuptools", "84.0.0", "6")
)


def test_an_overlay_is_its_source_lock_without_torch_and_torchaudio() -> None:
    source = parse_lock(SERVICE)
    overlay = parse_lock(derive_overlay(source, source_name="svc.lock.txt"))
    assert [item.key for item in overlay.requirements] == ["numpy", "torchvision", "setuptools"]
    assert check_overlay(overlay, source) == []
    assert "Do not edit" in overlay.header


def test_check_overlay_catches_drift() -> None:
    source = parse_lock(SERVICE)
    drifted = parse_lock(_block("numpy", "2.0.0", "1") + _block("torch", "2.6.0+cu124", "2", "3"))
    problems = check_overlay(drifted, source)
    assert "numpy: overlay 2.0.0, source 1.26.4" in problems
    assert "torch belongs to the Torch layer, not the overlay" in problems
    assert "torchvision is in the source lock but not the overlay" in problems


def test_the_torch_layer_needs_every_service_to_agree() -> None:
    first = parse_lock(SERVICE)
    layer = parse_lock(torch_layer_lock({"a": first, "b": first}))
    assert [item.key for item in layer.requirements] == ["torch", "torchaudio"]
    other = parse_lock(SERVICE.replace("2.6.0+cu124 \\\n    --hash=sha256:" + "2" * 64,
                                       "2.5.1+cu124 \\\n    --hash=sha256:" + "2" * 64))
    with pytest.raises(LockError, match="locks torch==2.5.1"):
        torch_layer_lock({"a": first, "b": other})


def test_torchvision_must_be_the_build_for_the_layers_torch() -> None:
    service = parse_lock(SERVICE)
    layer = parse_lock(torch_layer_lock({"svc": service}))
    assert check_torch_pins(layer, {"svc": service}) == []
    wrong = parse_lock(SERVICE.replace("torchvision==0.21.0+cu124", "torchvision==0.20.1+cu124"))
    assert any("not built for torch 2.6.0" in item for item in check_torch_pins(layer, {"svc": wrong}))


def test_a_lock_entry_without_hashes_is_refused() -> None:
    with pytest.raises(LockError, match="no hashes"):
        parse_lock("numpy==1.26.4\n")


def _fake_index(lock_text: str):
    lock = parse_lock(lock_text)
    numpy = lock.get("numpy")
    torch = lock.get("torch")
    assert numpy and torch
    pypi = {"urls": [
        {"filename": "numpy-1.26.4-cp311-cp311-win_amd64.whl", "url": "https://files.pythonhosted.org/numpy.whl",
         "digests": {"sha256": "1" * 64}, "size": 100},
        {"filename": "numpy-1.26.4-cp311-cp311-macosx_14_0_arm64.whl", "url": "https://files.pythonhosted.org/m.whl",
         "digests": {"sha256": "9" * 64}, "size": 100},
        {"filename": "numpy-1.26.4.tar.gz", "url": "https://files.pythonhosted.org/numpy.tar.gz",
         "digests": {"sha256": "1" * 64}, "size": 50},
    ]}
    index = ('<a href="/whl/cu124/torch-2.6.0%2Bcu124-cp311-cp311-win_amd64.whl#sha256=' + "2" * 64 + '">t</a>'
             '<a href="/whl/cu124/torch-2.6.0%2Bcu124-cp311-cp311-linux_x86_64.whl#sha256=' + "3" * 64 + '">l</a>')

    def fetch(url: str) -> bytes:
        if "pypi.org/pypi/numpy" in url:
            return json.dumps(pypi).encode()
        if "download.pytorch.org/whl/cu124/torch/" in url:
            return index.encode()
        raise AssertionError(url)

    return fetch


def test_resolve_picks_the_platforms_wheel_with_a_locked_digest(tmp_path: Path) -> None:
    text = _block("numpy", "1.26.4", "1") + _block("torch", "2.6.0+cu124", "2", "3")
    files, needs = resolve(parse_lock(text), "windows-x64", wheelhouse=tmp_path, fetch=_fake_index(text),
                           size_of=lambda url: 2500)
    assert needs == []
    assert [(item.filename, item.size) for item in files] == [
        ("numpy-1.26.4-cp311-cp311-win_amd64.whl", 100), ("torch-2.6.0+cu124-cp311-cp311-win_amd64.whl", 2500)]
    assert files[1].url.startswith("https://download.pytorch.org/whl/cu124/")


def test_a_source_only_package_needs_a_bundled_wheel(tmp_path: Path) -> None:
    text = _block("numpy", "1.26.4", "1")

    def fetch(url: str) -> bytes:
        return json.dumps({"urls": [{"filename": "numpy-1.26.4.tar.gz", "url": "https://files.pythonhosted.org/n.tgz",
                                     "digests": {"sha256": "1" * 64}, "size": 5}]}).encode()

    _, needs = resolve(parse_lock(text), "windows-x64", wheelhouse=tmp_path, fetch=fetch)
    assert needs == ["numpy==1.26.4"]
    (tmp_path / "numpy-1.26.4-py3-none-any.whl").write_bytes(b"built")
    files, needs = resolve(parse_lock(text), "windows-x64", wheelhouse=tmp_path, fetch=fetch)
    assert needs == [] and files[0].source == "bundled"
    assert files[0].sha256 == hashlib.sha256(b"built").hexdigest()


def test_check_pack_files_refuses_unlocked_digests_and_stale_lists(tmp_path: Path) -> None:
    text = _block("numpy", "1.26.4", "1")
    good = PackFile("numpy", "1.26.4", "numpy-1.26.4-cp311-cp311-win_amd64.whl", "1" * 64, 100, "index",
                    "https://files.pythonhosted.org/numpy.whl")
    path = tmp_path / "pack.json"
    write_pack_files(path, "rt", "windows-x64", "x.lock", text, [good])
    assert check_pack_files(load_pack_files(path), parse_lock(text), text, wheelhouse=tmp_path) == []
    forged = PackFile(**{**good.as_dict(), "sha256": "f" * 64})
    write_pack_files(path, "rt", "windows-x64", "x.lock", text, [forged])
    assert any("digest is not in the lock" in item for item in
               check_pack_files(load_pack_files(path), parse_lock(text), text, wheelhouse=tmp_path))
    changed = text.replace("numpy==1.26.4", "numpy==1.26.5")
    assert any("another version" in item for item in
               check_pack_files(load_pack_files(path), parse_lock(changed), changed, wheelhouse=tmp_path))
    # A comment (a header naming one more service on the Torch layer) is not another version.
    write_pack_files(path, "rt", "windows-x64", "x.lock", text, [good])
    commented = "# also used by another service\n" + text
    assert check_pack_files(load_pack_files(path), parse_lock(commented), commented, wheelhouse=tmp_path) == []


def test_pack_files_only_come_from_pypi_or_pytorch(tmp_path: Path) -> None:
    text = _block("numpy", "1.26.4", "1")
    elsewhere = PackFile("numpy", "1.26.4", "numpy.whl", "1" * 64, 1, "index", "https://example.com/numpy.whl")
    path = tmp_path / "pack.json"
    write_pack_files(path, "rt", "windows-x64", "x.lock", text, [elsewhere])
    with pytest.raises(ValueError, match="not from PyPI"):
        load_pack_files(path)


def test_the_shipped_desktop_locks_pass_the_release_gate() -> None:
    """Gate item 4: overlays are derived, Torch pins agree, every pack file list matches its lock."""
    completed = subprocess.run([sys.executable, str(ROOT / "scripts" / "desktop_locks.py"), "check"],
                               capture_output=True, text=True, cwd=ROOT, check=False)
    assert completed.returncode == 0, completed.stdout + completed.stderr


def test_the_gateway_the_desktop_app_stages_cannot_import_torch() -> None:
    """The gateway and job worker run on the staged interpreter with requirements/gateway.lock.txt alone: TTS, STT and
    images can only run in their services (roadmap DT-3.3, OMNIX_GATEWAY_TTS_HTTP)."""
    import re

    lock = (ROOT / "requirements" / "gateway.lock.txt").read_text(encoding="utf-8")
    pinned = {match.group(1).lower() for match in re.finditer(r"^([A-Za-z0-9_.-]+)==", lock, flags=re.MULTILINE)}
    assert pinned and not pinned & {"torch", "torchaudio", "torchvision", "nemo-toolkit", "diffusers"}
