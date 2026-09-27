"""Install the pinned Windows Node toolchain in the ignored workspace .tools directory."""
from __future__ import annotations

import hashlib
import platform
import re
import urllib.request
import zipfile
from pathlib import Path


def install(root: Path) -> Path:
    version = (root / ".node-version").read_text(encoding="utf-8").strip()
    if not re.fullmatch(r"22\.\d+\.\d+", version):
        raise ValueError("Expected a pinned Node 22 version")
    if platform.system() != "Windows" or platform.machine().lower() not in {"amd64", "x86_64"}:
        raise RuntimeError("Use your Node version manager with .node-version on this platform")
    name = f"node-v{version}-win-x64"
    destination = root / ".tools"
    executable = destination / name / "node.exe"
    if executable.exists():
        return executable
    destination.mkdir(parents=True, exist_ok=True)
    filename = f"{name}.zip"
    base_url = f"https://nodejs.org/dist/v{version}/"
    checksums = urllib.request.urlopen(base_url + "SHASUMS256.txt", timeout=60).read().decode("ascii")
    expected = next(line.split()[0] for line in checksums.splitlines() if line.split()[-1] == filename)
    archive = destination / filename
    urllib.request.urlretrieve(base_url + filename, archive)
    actual = hashlib.sha256(archive.read_bytes()).hexdigest()
    if actual != expected:
        raise RuntimeError("Node archive checksum does not match the official release")
    with zipfile.ZipFile(archive) as bundle:
        for item in bundle.infolist():
            target = (destination / item.filename).resolve()
            if not target.is_relative_to((destination / name).resolve()):
                raise RuntimeError("Unexpected Node archive path")
        bundle.extractall(destination)
    print(f"Verified Node {version}: SHA256 {actual}")
    return executable


if __name__ == "__main__":
    print(install(Path(__file__).resolve().parents[1]))
