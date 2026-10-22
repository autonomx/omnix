"""Install a wheel into a runtime pack folder, checking every file against the wheel's RECORD (roadmap §4.3).

The desktop app installs runtime packs without pip: the staged interpreter
has none, and pip cannot resume multi-gigabyte downloads. A verified wheel is
unpacked here instead, following the wheel format (PEP 427):

- ``purelib`` and ``platlib`` files go to ``<pack>/site``, the folder
  ``app.desktop.service_boot`` puts on ``sys.path``;
- ``<name>.data/scripts`` goes to ``<pack>/scripts`` and ``<name>.data/data``
  to ``<pack>/data`` (headers are not needed and are skipped);
- a file RECORD lists must match its SHA-256, and no path may leave the pack
  folder. The wheel itself was checked against the lock before it got here, so
  a file RECORD leaves out is installed (PyTorch's CUDA wheels add DLLs after
  building RECORD, and pip accepts them too); the installed RECORD is rewritten
  to list every installed file with its digest, as pip does, so
  ``verify_installed`` checks all of them later.

Console scripts are never generated: services start through
``service_boot``, never through an entry-point launcher.
"""
from __future__ import annotations

import base64
import csv
import hashlib
import io
import os
import zipfile
from dataclasses import dataclass
from pathlib import Path, PurePosixPath


class WheelError(ValueError):
    pass


@dataclass(frozen=True)
class InstalledWheel:
    name: str
    version: str
    files: int


def _record_digest(data: bytes) -> str:
    return "sha256=" + base64.urlsafe_b64encode(hashlib.sha256(data).digest()).rstrip(b"=").decode("ascii")


def _safe_parts(name: str) -> tuple[str, ...]:
    path = PurePosixPath(name)
    if path.is_absolute() or any(part in {"", ".", ".."} or ":" in part or "\\" in part for part in path.parts):
        raise WheelError(f"unsafe path in wheel: {name!r}")
    return path.parts


def install_wheel(wheel: Path, pack: Path) -> InstalledWheel:
    """Unpack ``wheel`` into ``pack`` (site, scripts, data). Raises WheelError on anything unexpected."""
    with zipfile.ZipFile(wheel) as archive:
        names = [info.filename for info in archive.infolist() if not info.is_dir()]
        dist_infos = {name.split("/", 1)[0] for name in names if name.split("/", 1)[0].endswith(".dist-info")}
        if len(dist_infos) != 1:
            raise WheelError(f"{wheel.name}: expected one .dist-info folder, found {sorted(dist_infos)}")
        dist_info = dist_infos.pop()
        stem = dist_info[: -len(".dist-info")]
        name, _, version = stem.partition("-")
        metadata = archive.read(f"{dist_info}/WHEEL").decode("utf-8")
        if "Wheel-Version: 1." not in metadata:
            raise WheelError(f"{wheel.name}: unsupported wheel version")
        record_name = f"{dist_info}/RECORD"
        record: dict[str, str] = {}
        for row in csv.reader(io.StringIO(archive.read(record_name).decode("utf-8"))):
            if row:
                record[row[0]] = row[1] if len(row) > 1 else ""
        site, scripts, data = pack / "site", pack / "scripts", pack / "data"
        data_prefix = f"{stem}.data/"
        written = 0
        installed: list[tuple[str, str, int]] = []
        for member in names:
            _safe_parts(member)
            if member == record_name:
                continue  # rewritten below with every installed file
            content = archive.read(member)
            digest = _record_digest(content)
            expected = record.get(member)
            if expected and expected != digest:
                raise WheelError(f"{wheel.name}: {member} does not match its RECORD digest")
            if member.startswith(data_prefix):
                scheme, _, rest = member[len(data_prefix):].partition("/")
                if not rest:
                    raise WheelError(f"{wheel.name}: {member} has no scheme folder")
                if scheme in {"purelib", "platlib"}:
                    target = site.joinpath(*_safe_parts(rest))
                elif scheme == "scripts":
                    target = scripts.joinpath(*_safe_parts(rest))
                elif scheme == "data":
                    target = data.joinpath(*_safe_parts(rest))
                elif scheme == "headers":
                    continue
                else:
                    raise WheelError(f"{wheel.name}: unknown data scheme {scheme!r}")
            else:
                target = site.joinpath(*_safe_parts(member))
            if pack.resolve() not in target.resolve().parents:
                raise WheelError(f"{wheel.name}: {member} would leave the pack")
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(content)
            installed.append((Path(os.path.relpath(target, site)).as_posix(), digest, len(content)))
            written += 1
        # The installer that put the files there, as pip records it, and the RECORD of what it installed.
        installer = site / dist_info / "INSTALLER"
        installer.write_text("omnix-desktop\n", encoding="utf-8")
        installed.append((f"{dist_info}/INSTALLER", _record_digest(installer.read_bytes()), installer.stat().st_size))
        lines = io.StringIO()
        writer = csv.writer(lines, lineterminator="\n")
        writer.writerows(installed)
        writer.writerow((f"{dist_info}/RECORD", "", ""))
        (site / dist_info / "RECORD").write_text(lines.getvalue(), encoding="utf-8")
    return InstalledWheel(name=name, version=version, files=written)


def verify_installed(site: Path) -> list[str]:
    """Problems with an installed pack's files: each RECORD entry must exist with its digest."""
    problems = []
    for record in sorted(site.glob("*.dist-info/RECORD")):
        for row in csv.reader(io.StringIO(record.read_text(encoding="utf-8"))):
            if not row or not row[1]:
                continue
            relative = row[0]
            # Scripts and data live beside site: ../scripts and ../data in the installed RECORD.
            target = (site / PurePosixPath(relative)) if relative.startswith("../") else \
                site.joinpath(*PurePosixPath(relative).parts)
            try:
                content = target.read_bytes()
            except OSError:
                problems.append(f"{relative}: missing")
                continue
            if _record_digest(content) != row[1]:
                problems.append(f"{relative}: changed")
    return problems


__all__ = ["InstalledWheel", "WheelError", "install_wheel", "verify_installed"]
