"""Hash-locked requirement files: parse them, derive overlays, check the shared Torch layer (roadmap §4.3).

The model services' locks (``src/services/<service>/*.lock.txt``) are
pip-compile output: one ``name==version`` block per package, with every
allowed file's ``--hash=sha256:`` on continuation lines. The desktop app
splits each GPU service's lock in two:

- the **Torch layer** (``torch`` and ``torchaudio``), shared by every service
  on a platform and installed once;
- the service's **overlay**: its lock with exactly those two blocks removed.

Overlays are derived from the service locks, never edited by hand, so
``check_overlay`` fails when one drifts from its source.
"""
from __future__ import annotations

import re
from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from pathlib import Path

# The packages the shared layer holds. torchvision stays in each overlay that locks it (roadmap §4.3).
TORCH_LAYER_PACKAGES = ("torch", "torchaudio")
# torchvision's compiled extension is built for one Torch release.
TORCHVISION_FOR_TORCH = {"2.6.0": "0.21.0", "2.5.1": "0.20.1", "2.7.0": "0.22.0", "2.7.1": "0.22.1"}

_REQUIREMENT = re.compile(r"^(?P<name>[A-Za-z0-9][A-Za-z0-9._-]*)(?:\[[^\]]*\])?==(?P<version>[^\s;\\]+)")
_HASH = re.compile(r"--hash=sha256:([0-9a-f]{64})")


class LockError(ValueError):
    pass


def normalize(name: str) -> str:
    """PEP 503 name normalization."""
    return re.sub(r"[-_.]+", "-", name).lower()


@dataclass(frozen=True)
class LockedRequirement:
    name: str
    version: str
    hashes: frozenset[str]
    text: str

    @property
    def key(self) -> str:
        return normalize(self.name)

    @property
    def public_version(self) -> str:
        """The version without its local label (``2.6.0+cu124`` -> ``2.6.0``)."""
        return self.version.split("+", 1)[0]


@dataclass(frozen=True)
class Lock:
    header: str
    requirements: tuple[LockedRequirement, ...]

    def by_key(self) -> dict[str, LockedRequirement]:
        return {item.key: item for item in self.requirements}

    def get(self, name: str) -> LockedRequirement | None:
        return self.by_key().get(normalize(name))

    def render(self) -> str:
        return self.header + "".join(item.text for item in self.requirements)


def parse_lock(text: str) -> Lock:
    """Blocks of a pip-compile lock. Each block keeps its exact text, comments included."""
    lines = text.splitlines(keepends=True)
    header: list[str] = []
    blocks: list[list[str]] = []
    for line in lines:
        if _REQUIREMENT.match(line):
            blocks.append([line])
        elif blocks:
            blocks[-1].append(line)
        else:
            header.append(line)
    requirements = []
    for block in blocks:
        match = _REQUIREMENT.match(block[0])
        assert match is not None
        body = "".join(block)
        hashes = frozenset(_HASH.findall(body))
        if not hashes:
            raise LockError(f"{match['name']}=={match['version']} has no hashes")
        requirements.append(LockedRequirement(match["name"], match["version"], hashes, body))
    keys = [item.key for item in requirements]
    duplicates = sorted({key for key in keys if keys.count(key) > 1})
    if duplicates:
        raise LockError(f"locked twice: {duplicates}")
    return Lock("".join(header), tuple(requirements))


def read_lock(path: Path) -> Lock:
    return parse_lock(path.read_text(encoding="utf-8"))


def _trailing_section_comment(text: str) -> tuple[str, str]:
    """Splits a pip-compile section heading ("# The following packages ...") off the end of a block."""
    lines = text.splitlines(keepends=True)
    index = len(lines)
    while index > 0 and lines[index - 1].startswith("# The following packages"):
        index -= 1
    return "".join(lines[:index]), "".join(lines[index:])


def derive_overlay(source: Lock, *, source_name: str, packages: Iterable[str] = TORCH_LAYER_PACKAGES) -> str:
    """The source lock without the Torch layer's blocks, with a header naming where it came from."""
    dropped = {normalize(name) for name in packages}
    missing = sorted(dropped - set(source.by_key()))
    if missing:
        raise LockError(f"{source_name} does not lock {missing}")
    kept: list[str] = []
    for item in source.requirements:
        if item.key in dropped:
            # A section heading that pip-compile put at the end of a dropped block belongs to the next block.
            _, heading = _trailing_section_comment(item.text)
            if heading:
                kept.append(heading)
            continue
        kept.append(item.text)
    header = (
        "#\n"
        f"# Desktop overlay generated from {source_name} by scripts/desktop_locks.py derive.\n"
        f"# It is that lock without {', '.join(sorted(dropped))}, which the shared Torch layer provides.\n"
        "# Do not edit: change the source lock and derive again.\n"
        "#\n"
    )
    return header + "".join(kept)


def torch_layer_lock(sources: Mapping[str, Lock], *, packages: Iterable[str] = TORCH_LAYER_PACKAGES) -> str:
    """The Torch layer's lock: the blocks every source lock agrees on, byte for byte (versions and hashes)."""
    wanted = [normalize(name) for name in packages]
    chosen: dict[str, LockedRequirement] = {}
    for source_name, lock in sources.items():
        for key in wanted:
            item = lock.get(key)
            if item is None:
                raise LockError(f"{source_name} does not lock {key}")
            first = chosen.setdefault(key, item)
            if (first.version, first.hashes) != (item.version, item.hashes):
                raise LockError(f"{source_name} locks {key}=={item.version}, another service {first.version}")
    header = (
        "#\n"
        "# The desktop app's shared Torch layer, generated by scripts/desktop_locks.py derive from the\n"
        f"# service locks that run on it: {', '.join(sorted(sources))}.\n"
        "# Do not edit.\n"
        "#\n"
    )
    body = "".join(_trailing_section_comment(chosen[key].text)[0] for key in wanted)
    return header + body


def check_overlay(overlay: Lock, source: Lock, *, packages: Iterable[str] = TORCH_LAYER_PACKAGES) -> list[str]:
    """Problems: an overlay must be its source lock minus exactly the Torch layer's packages."""
    dropped = {normalize(name) for name in packages}
    problems = []
    expected = {key: item for key, item in source.by_key().items() if key not in dropped}
    actual = overlay.by_key()
    for key in sorted(set(expected) | set(actual)):
        if key in dropped:
            problems.append(f"{key} belongs to the Torch layer, not the overlay")
        elif key not in actual:
            problems.append(f"{key} is in the source lock but not the overlay")
        elif key not in expected:
            problems.append(f"{key} is in the overlay but not the source lock")
        elif (actual[key].version, actual[key].hashes) != (expected[key].version, expected[key].hashes):
            problems.append(f"{key}: overlay {actual[key].version}, source {expected[key].version}")
    return problems


def check_torch_pins(layer: Lock, service_locks: Mapping[str, Lock]) -> list[str]:
    """Problems: every service locks the layer's exact Torch, and any torchvision is the one built for it."""
    problems = []
    torch = layer.get("torch")
    if torch is None:
        return ["the Torch layer does not lock torch"]
    for key in (normalize(name) for name in TORCH_LAYER_PACKAGES):
        pinned = layer.get(key)
        for name, lock in service_locks.items():
            item = lock.get(key)
            if pinned is None or item is None:
                problems.append(f"{name}: {key} missing")
            elif (item.version, item.hashes) != (pinned.version, pinned.hashes):
                problems.append(f"{name}: {key}=={item.version}, the Torch layer has {pinned.version}")
    expected_vision = TORCHVISION_FOR_TORCH.get(torch.public_version)
    for name, lock in service_locks.items():
        vision = lock.get("torchvision")
        if vision is None:
            continue
        if expected_vision is None:
            problems.append(f"{name}: no known torchvision for torch {torch.public_version}")
        elif vision.public_version != expected_vision:
            problems.append(f"{name}: torchvision {vision.public_version} is not built for torch "
                            f"{torch.public_version} (needs {expected_vision})")
        elif torch.version != torch.public_version and vision.version.split("+", 1)[-1] != torch.version.split("+", 1)[-1]:
            problems.append(f"{name}: torchvision {vision.version} and torch {torch.version} differ in build")
    return problems


__all__ = [
    "Lock", "LockError", "LockedRequirement", "TORCH_LAYER_PACKAGES", "TORCHVISION_FOR_TORCH", "check_overlay",
    "check_torch_pins", "derive_overlay", "normalize", "parse_lock", "read_lock", "torch_layer_lock",
]
