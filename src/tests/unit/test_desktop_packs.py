"""Desktop runtime and model packs: verified wheel installs, resumable downloads, atomic installs (roadmap §4.3)."""
from __future__ import annotations

import base64
import contextlib
import hashlib
import json
import zipfile
from pathlib import Path

import pytest

from app.models import packs
from app.models.catalog import parse_catalog
from app.models.packfiles import PackFile, write_pack_files
from app.models.wheels import WheelError, install_wheel, verify_installed

REVISION = "0123456789abcdef0123456789abcdef01234567"


def _digest(data: bytes) -> str:
    return "sha256=" + base64.urlsafe_b64encode(hashlib.sha256(data).digest()).rstrip(b"=").decode()


def make_wheel(folder: Path, name: str = "demo", version: str = "1.0", *, files: dict[str, bytes] | None = None,
               tamper: str | None = None, unrecorded: dict[str, bytes] | None = None) -> Path:
    files = files or {f"{name}/__init__.py": b"VALUE = 1\n", f"{name}-{version}.data/scripts/tool": b"#!python\n"}
    dist = f"{name}-{version}.dist-info"
    entries = dict(files)
    entries[f"{dist}/METADATA"] = f"Metadata-Version: 2.1\nName: {name}\nVersion: {version}\n".encode()
    entries[f"{dist}/WHEEL"] = b"Wheel-Version: 1.0\nRoot-Is-Purelib: true\nTag: py3-none-any\n"
    record = "".join(f"{path},{_digest(data)},{len(data)}\n" for path, data in entries.items())
    record += f"{dist}/RECORD,,\n"
    path = folder / f"{name}-{version}-py3-none-any.whl"
    with zipfile.ZipFile(path, "w") as archive:
        for member, data in entries.items():
            archive.writestr(member, b"tampered" if member == tamper else data)
        archive.writestr(f"{dist}/RECORD", record)
        for member, data in (unrecorded or {}).items():
            archive.writestr(member, data)
    return path


def test_a_wheel_installs_into_site_scripts_and_data(tmp_path: Path) -> None:
    wheel = make_wheel(tmp_path)
    pack = tmp_path / "pack"
    installed = install_wheel(wheel, pack)
    assert installed.name == "demo" and installed.version == "1.0"
    assert (pack / "site" / "demo" / "__init__.py").read_bytes() == b"VALUE = 1\n"
    assert (pack / "scripts" / "tool").is_file()
    assert (pack / "site" / "demo-1.0.dist-info" / "INSTALLER").read_text().strip() == "omnix-desktop"
    assert verify_installed(pack / "site") == []
    (pack / "site" / "demo" / "__init__.py").write_bytes(b"VALUE = 2\n")
    assert verify_installed(pack / "site") == ["demo/__init__.py: changed"]


def test_a_file_record_leaves_out_is_installed_and_still_verified(tmp_path: Path) -> None:
    """PyTorch's CUDA wheels carry DLLs their RECORD does not list (torchvision's cudart64_12.dll)."""
    wheel = make_wheel(tmp_path, unrecorded={"demo/cudart64_12.dll": b"dll"})
    pack = tmp_path / "pack"
    install_wheel(wheel, pack)
    assert (pack / "site" / "demo" / "cudart64_12.dll").read_bytes() == b"dll"
    assert verify_installed(pack / "site") == []
    (pack / "site" / "demo" / "cudart64_12.dll").write_bytes(b"changed")
    (pack / "scripts" / "tool").write_bytes(b"changed")
    assert verify_installed(pack / "site") == ["../scripts/tool: changed", "demo/cudart64_12.dll: changed"]


def test_a_file_that_does_not_match_record_is_refused(tmp_path: Path) -> None:
    wheel = make_wheel(tmp_path, tamper="demo/__init__.py")
    with pytest.raises(WheelError, match="does not match its RECORD"):
        install_wheel(wheel, tmp_path / "pack")


def test_a_path_that_leaves_the_pack_is_refused(tmp_path: Path) -> None:
    wheel = make_wheel(tmp_path, files={"../escape.py": b"x"})
    with pytest.raises(WheelError, match="unsafe path"):
        install_wheel(wheel, tmp_path / "pack")


class _Response:
    def __init__(self, status: int, body: bytes) -> None:
        self.status_code = status
        self.body = body

    def iter_bytes(self, size: int):
        for start in range(0, len(self.body), 4):
            yield self.body[start:start + 4]


class _Client:
    """Serves files over a fake HTTP with Range support; ``fail_after`` cuts the first transfer short."""

    def __init__(self, files: dict[str, bytes], *, fail_after: int | None = None, ranges: bool = True) -> None:
        self.files = files
        self.fail_after = fail_after
        self.ranges = ranges
        self.requests: list[tuple[str, dict]] = []

    @contextlib.contextmanager
    def stream(self, method: str, url: str, headers: dict | None = None):
        headers = headers or {}
        self.requests.append((url, headers))
        data = self.files[url]
        start = int(headers["Range"].split("=")[1].rstrip("-")) if "Range" in headers else 0
        if start and self.ranges:
            response = _Response(206, data[start:])
        else:
            response = _Response(200, data)
        if self.fail_after is not None:
            limit, self.fail_after = self.fail_after, None

            class _Broken(_Response):
                def iter_bytes(self, size: int):
                    yield self.body[:limit]
                    raise ConnectionError("connection reset")

            response = _Broken(response.status_code, response.body)
        yield response


def test_an_interrupted_download_resumes_and_is_checked(tmp_path: Path) -> None:
    data = b"0123456789" * 10
    client = _Client({"https://files.pythonhosted.org/w.whl": data}, fail_after=40)
    target = tmp_path / "w.whl"
    seen: list[int] = []
    # A broken-off transfer is worth retrying: the job framework runs it again and it resumes.
    with pytest.raises(packs.PackDownloadError, match="ConnectionError"):
        packs.download_file("https://files.pythonhosted.org/w.whl", target, sha256=hashlib.sha256(data).hexdigest(),
                            size=len(data), progress=seen.append, cancelled=lambda: False, client=client)
    assert (tmp_path / "w.whl.part").stat().st_size == 40
    packs.download_file("https://files.pythonhosted.org/w.whl", target, sha256=hashlib.sha256(data).hexdigest(),
                        size=len(data), progress=seen.append, cancelled=lambda: False, client=client)
    assert target.read_bytes() == data
    assert client.requests[-1][1] == {"Range": "bytes=40-"}


def test_a_download_with_the_wrong_digest_is_deleted(tmp_path: Path) -> None:
    client = _Client({"https://files.pythonhosted.org/w.whl": b"evil"})
    with pytest.raises(packs.PackError, match="expected"):
        packs.download_file("https://files.pythonhosted.org/w.whl", tmp_path / "w.whl", sha256="0" * 64, size=4,
                            progress=lambda n: None, cancelled=lambda: False, client=client)
    assert not (tmp_path / "w.whl").exists() and not (tmp_path / "w.whl.part").exists()


def test_a_server_error_is_retryable_and_a_missing_file_is_not(tmp_path: Path) -> None:
    class _Status(_Client):
        def __init__(self, status: int) -> None:
            super().__init__({})
            self.status = status

        @contextlib.contextmanager
        def stream(self, method: str, url: str, headers: dict | None = None):
            yield _Response(self.status, b"")

    def fetch(status: int) -> None:
        packs.download_file("https://files.pythonhosted.org/w.whl", tmp_path / "w.whl", sha256="0" * 64, size=4,
                            progress=lambda n: None, cancelled=lambda: False, client=_Status(status))

    with pytest.raises(packs.PackDownloadError, match="503"):
        fetch(503)
    with pytest.raises(packs.PackError, match="404") as refused:
        fetch(404)
    assert not isinstance(refused.value, packs.PackDownloadError)


def test_a_server_that_ignores_ranges_starts_over(tmp_path: Path) -> None:
    data = b"abcdefgh"
    (tmp_path / "w.whl.part").write_bytes(b"abc")
    client = _Client({"https://files.pythonhosted.org/w.whl": data}, ranges=False)
    packs.download_file("https://files.pythonhosted.org/w.whl", tmp_path / "w.whl", sha256=hashlib.sha256(data).hexdigest(),
                        size=len(data), progress=lambda n: None, cancelled=lambda: False, client=client)
    assert (tmp_path / "w.whl").read_bytes() == data


@pytest.fixture
def pack_setup(tmp_path: Path, monkeypatch):
    """A catalog with a Torch layer and an overlay, their file lists, and a fake repository root."""
    repo = tmp_path / "repo"
    (repo / "requirements" / "desktop" / "wheelhouse").mkdir(parents=True)
    wheels = tmp_path / "upstream"
    wheels.mkdir()
    torch_wheel = make_wheel(wheels, "torchlike", "2.6.0")
    overlay_wheel = make_wheel(wheels, "servicelib", "1.0")
    bundled = make_wheel(repo / "requirements" / "desktop" / "wheelhouse", "sdistonly", "3.2")
    urls = {"https://files.pythonhosted.org/torchlike.whl": torch_wheel.read_bytes(),
            "https://files.pythonhosted.org/servicelib.whl": overlay_wheel.read_bytes()}

    def listed(path: Path, item: str, *wheel_files: tuple[Path, str]) -> None:
        files = [PackFile(wheel.name.split("-")[0], wheel.name.split("-")[1], wheel.name,
                          hashlib.sha256(wheel.read_bytes()).hexdigest(), wheel.stat().st_size, source, url)
                 for wheel, source, url in wheel_files]
        write_pack_files(path, item, "windows-x64", f"{item}.lock", f"lock of {item}", files)

    listed(repo / "torch.json", "torch-win", (torch_wheel, "index", "https://files.pythonhosted.org/torchlike.whl"))
    listed(repo / "tts.json", "tts-win", (overlay_wheel, "index", "https://files.pythonhosted.org/servicelib.whl"),
           (bundled, "bundled", ""))
    catalog = parse_catalog({
        "runtimes": {
            "torch-win": {"kind": "torch-layer", "platform": "windows-x64", "lock": "t.lock", "files": "torch.json"},
            "tts-win": {"kind": "overlay", "base": "torch-win", "platform": "windows-x64", "service": "tts",
                        "lock": "tts.lock", "files": "tts.json"},
        },
        "models": {"tts-model": {"repo": "org/tts", "revision": REVISION, "service": "tts",
                                 "files": {"model.bin": {"sha256": hashlib.sha256(b"weights").hexdigest(), "size": 7}}}},
    })
    monkeypatch.setattr("app.runtime.paths.repo_root", lambda: repo)
    store = packs.RuntimeStore(tmp_path / "packs", catalog)
    return store, _Client(urls), repo


def test_a_runtime_installs_only_on_its_base_and_lands_complete(pack_setup) -> None:
    store, client, _ = pack_setup
    with pytest.raises(packs.PackError, match="install that first"):
        store.install("tts-win", client=client)
    seen: list[tuple[int, int, str]] = []
    store.install("torch-win", client=client, progress=lambda d, t, m: seen.append((d, t, m)))
    store.install("tts-win", client=client)
    assert store.installed("torch-win") and store.current("tts-win")
    assert (store.site("tts-win") / "servicelib" / "__init__.py").is_file()
    assert (store.site("tts-win") / "sdistonly" / "__init__.py").is_file()
    assert store.verify("tts-win") == []
    assert seen[-1][0] == seen[-1][1] and "Preparing" in seen[-1][2]
    # The bytecode is compiled at install, inside the pack, naming the pack's own folder (not the staging one).
    compiled = next((store.site("tts-win") / "servicelib" / "__pycache__").glob("__init__.*.pyc"))
    assert str(store.site("tts-win")) in compiled.read_bytes().decode("latin-1")
    # Downloads are cleaned up once the pack is in place; nothing half-built is left in staging.
    assert not any((store.staging / "downloads").glob("*.whl"))
    assert not (store.staging / "tts-win.build").exists()


def test_each_pack_downloads_into_its_own_folder(pack_setup) -> None:
    """Overlays installing at once share wheel filenames: one finishing must not delete another's downloads."""
    store, client, _ = pack_setup
    other = store.staging / "downloads" / "tts-win" / "servicelib-1.0-py3-none-any.whl.part"
    other.parent.mkdir(parents=True)
    other.write_bytes(b"half a wheel")
    store.install("torch-win", client=client)
    assert other.read_bytes() == b"half a wheel"
    assert not (store.staging / "downloads" / "torch-win").exists()


def test_a_cancelled_install_leaves_no_pack(pack_setup) -> None:
    store, client, _ = pack_setup
    with pytest.raises(packs.PackCancelled):
        store.install("torch-win", client=client, cancelled=lambda: True)
    assert not store.installed("torch-win")
    assert not store.folder("torch-win").exists()


def test_a_worker_killed_while_unpacking_leaves_no_pack_and_the_rerun_completes(pack_setup, monkeypatch) -> None:
    store, client, _ = pack_setup
    store.install("torch-win", client=client)
    real_install = packs.install_wheel
    unpacked: list[Path] = []

    def killed_after_one(wheel: Path, target: Path) -> None:
        if unpacked:
            raise KeyboardInterrupt  # the process dies part-way through the overlay's wheels
        unpacked.append(wheel)
        real_install(wheel, target)

    monkeypatch.setattr(packs, "install_wheel", killed_after_one)
    with pytest.raises(KeyboardInterrupt):
        store.install("tts-win", client=client)
    assert (store.staging / "tts-win.build").exists() and not store.installed("tts-win")
    assert not store.folder("tts-win").exists()

    # The job runs again after the restart: the half-built folder is discarded and the pack lands complete.
    monkeypatch.setattr(packs, "install_wheel", real_install)
    store.install("tts-win", client=client)
    assert store.current("tts-win") and store.verify("tts-win") == []
    assert not (store.staging / "tts-win.build").exists()


def test_a_pack_in_use_is_left_whole_and_its_removal_is_retried(pack_setup, monkeypatch) -> None:
    store, client, _ = pack_setup
    store.install("torch-win", client=client)
    real_rename = Path.rename

    def locked(self: Path, target: Path) -> Path:
        if self == store.folder("torch-win"):
            raise PermissionError("a DLL in it is loaded")  # Windows, while the service runs
        return real_rename(self, target)

    monkeypatch.setattr(Path, "rename", locked)
    with pytest.raises(packs.PackBusy):
        store.remove("torch-win")
    assert store.current("torch-win") and store.verify("torch-win") == []
    monkeypatch.setattr(Path, "rename", real_rename)
    store.remove("torch-win")
    assert not store.present("torch-win")
    assert not list(store.runtimes.glob(".*"))


def test_leftovers_of_an_interrupted_update_or_removal_are_swept(pack_setup) -> None:
    store, client, _ = pack_setup
    for leftover in (".torch-win.old-1", ".tts-win.removing-2"):
        (store.runtimes / leftover / "site").mkdir(parents=True)
    half = store.folder("tts-win")
    (half / "site").mkdir(parents=True)  # a removal that failed part-way: no manifest
    assert store.present("tts-win") and not store.installed("tts-win")
    store.install("torch-win", client=client)
    assert sorted(item.name for item in store.runtimes.iterdir()) == ["torch-win", "tts-win"]
    store.remove("tts-win")
    assert not half.exists()


def test_the_torch_layer_cannot_be_removed_under_an_overlay(pack_setup) -> None:
    store, client, _ = pack_setup
    store.install("torch-win", client=client)
    store.install("tts-win", client=client)
    with pytest.raises(packs.PackError, match="needed by"):
        store.remove("torch-win")
    with pytest.raises(packs.PackError, match="needed by Voice output"):
        store.remove("tts-win", needed_by=["Voice output"])
    store.remove("tts-win")
    store.remove("torch-win")
    assert not store.installed("torch-win")


def test_a_changed_file_list_marks_the_pack_out_of_date(pack_setup) -> None:
    store, client, repo = pack_setup
    store.install("torch-win", client=client)
    listed = json.loads((repo / "torch.json").read_text())
    listed["lock_sha256"] = "f" * 64
    (repo / "torch.json").write_text(json.dumps(listed))
    assert store.installed("torch-win") and not store.current("torch-win")
    assert "older file list" in store.verify("torch-win")[0]


def test_an_update_replaces_the_pack_only_once_its_services_have_stopped(pack_setup) -> None:
    store, client, repo = pack_setup
    store.install("torch-win", client=client)
    listed = json.loads((repo / "torch.json").read_text())
    listed["lock_sha256"] = "f" * 64  # the app update ships a new file list
    (repo / "torch.json").write_text(json.dumps(listed))
    seen: list[tuple[bool, bool]] = []

    def before_swap(runtime_id: str) -> None:
        # The new version is unpacked; the old one is still in place, and marked so the supervisor stops it.
        seen.append((store.updating(runtime_id), store.installed(runtime_id) and not store.current(runtime_id)))

    store.install("torch-win", client=client, before_swap=before_swap)
    assert seen == [(True, True)]
    assert store.current("torch-win") and not store.updating("torch-win")
    assert not list(store.runtimes.glob(".*"))


def test_a_tampered_bundled_wheel_is_refused(pack_setup) -> None:
    store, client, repo = pack_setup
    store.install("torch-win", client=client)
    (repo / "requirements" / "desktop" / "wheelhouse" / "sdistonly-3.2-py3-none-any.whl").write_bytes(b"x")
    with pytest.raises(packs.PackError, match="reinstall Omnix"):
        store.install("tts-win", client=client)


def test_a_model_installs_into_the_cache_and_is_removed(pack_setup, tmp_path: Path) -> None:
    store, _, _ = pack_setup
    models = packs.ModelStore(tmp_path / "hf", store.catalog)

    def fetch(*, repo_id: str, filename: str, revision: str, cache_dir: str, **kwargs) -> str:
        target = Path(cache_dir) / ("models--" + repo_id.replace("/", "--")) / "snapshots" / revision / filename
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(b"weights")
        return str(target)

    models.install("tts-model", fetch=fetch)
    assert models.installed("tts-model") and models.verify("tts-model") == []
    assert models.snapshot("tts-model").name == REVISION
    models.remove("tts-model")
    assert not models.installed("tts-model")
    assert not (tmp_path / "hf" / "models--org--tts").exists()


def test_packs_are_off_without_a_packs_folder(monkeypatch) -> None:
    monkeypatch.delenv("OMNIX_PACKS_DIR", raising=False)
    assert not packs.desktop_mode()
    with pytest.raises(packs.PackError, match="does not manage packs"):
        packs.runtime_store()
