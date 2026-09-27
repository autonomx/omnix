import hashlib
from io import BytesIO
from pathlib import Path
import zipfile

import pytest

from scripts import install_node_toolchain as installer


def archive_bytes(filename):
    buffer = BytesIO()
    with zipfile.ZipFile(buffer, "w") as archive:
        archive.writestr(filename, b"node fixture")
    return buffer.getvalue()


def download_fixture(tmp_path, monkeypatch, filename, *, checksum=None):
    (tmp_path / ".node-version").write_text("22.23.3\n", encoding="utf-8")
    monkeypatch.setattr(installer.platform, "system", lambda: "Windows")
    monkeypatch.setattr(installer.platform, "machine", lambda: "AMD64")
    data = archive_bytes(filename)
    expected = checksum or hashlib.sha256(data).hexdigest()
    sums = f"{expected}  node-v22.23.3-win-x64.zip\n".encode("ascii")
    monkeypatch.setattr(installer.urllib.request, "urlopen", lambda *_args, **_kwargs: BytesIO(sums))
    monkeypatch.setattr(installer.urllib.request, "urlretrieve", lambda _url, path: Path(path).write_bytes(data))


def test_installer_verifies_and_extracts_pinned_archive(tmp_path, monkeypatch):
    download_fixture(tmp_path, monkeypatch, "node-v22.23.3-win-x64/node.exe")
    executable = installer.install(tmp_path)
    assert executable == tmp_path / ".tools/node-v22.23.3-win-x64/node.exe"
    assert executable.read_bytes() == b"node fixture"


def test_installer_rejects_bad_checksum_before_extraction(tmp_path, monkeypatch):
    download_fixture(tmp_path, monkeypatch, "node-v22.23.3-win-x64/node.exe", checksum="0" * 64)
    with pytest.raises(RuntimeError, match="checksum"):
        installer.install(tmp_path)
    assert not (tmp_path / ".tools/node-v22.23.3-win-x64/node.exe").exists()


def test_installer_rejects_archive_path_escape(tmp_path, monkeypatch):
    download_fixture(tmp_path, monkeypatch, "../escaped-node.exe")
    with pytest.raises(RuntimeError, match="archive path"):
        installer.install(tmp_path)
    assert not (tmp_path / "escaped-node.exe").exists()


def test_installer_rejects_invalid_pinned_version(tmp_path):
    (tmp_path / ".node-version").write_text("../22.23.3\n", encoding="utf-8")
    with pytest.raises(ValueError, match="pinned Node"):
        installer.install(tmp_path)
