"""What this machine can run, without importing Torch (desktop roadmap §4.4, DT-2.1).

The setup screen runs before any GPU runtime is installed, so this probe asks
the operating system: ``nvidia-smi`` for NVIDIA GPUs, VRAM and the driver, WMI
for other display adapters (so an AMD or Intel GPU shows as "no CUDA"), and
``sysctl`` on macOS. Memory includes the commit headroom Windows has left, the
limit a model load runs into (``app.providers.host_memory``). It reports facts;
``app.models.verdicts`` turns them into what the setup screen offers.
"""
from __future__ import annotations

import json
import logging
import os
import shutil
import subprocess
import sys
from collections.abc import Callable
from pathlib import Path
from typing import Any

from app.models.catalog import current_platform

logger = logging.getLogger(__name__)

Run = Callable[[list[str]], str | None]
TIMEOUT_SECONDS = 8


def _run(command: list[str]) -> str | None:
    try:
        completed = subprocess.run(command, capture_output=True, text=True, timeout=TIMEOUT_SECONDS, check=False,
                                   stdin=subprocess.DEVNULL, creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
    except (OSError, subprocess.SubprocessError):
        return None
    return completed.stdout if completed.returncode == 0 else None


def _nvidia_smi() -> str | None:
    found = shutil.which("nvidia-smi")
    if found:
        return found
    if sys.platform == "win32":
        candidate = Path(os.environ.get("SystemRoot", r"C:\Windows")) / "System32" / "nvidia-smi.exe"
        if candidate.is_file():
            return str(candidate)
    return None


def nvidia_gpus(run: Run = _run) -> list[dict[str, Any]]:
    executable = _nvidia_smi()
    if executable is None:
        return []
    output = run([executable, "--query-gpu=name,memory.total,memory.free,driver_version",
                  "--format=csv,noheader,nounits"])
    gpus = []
    for line in (output or "").splitlines():
        parts = [part.strip() for part in line.split(",")]
        if len(parts) != 4:
            continue
        name, total, free, driver = parts
        try:
            gpus.append({"name": name, "vendor": "nvidia", "vram_total_mb": int(float(total)),
                         "vram_free_mb": int(float(free)), "driver": driver})
        except ValueError:
            continue
    return gpus


def windows_adapters(run: Run = _run) -> list[dict[str, Any]]:
    """Every display adapter Windows knows, NVIDIA or not (names only: WMI's memory field caps at 4 GB)."""
    output = run(["powershell", "-NoProfile", "-NonInteractive", "-Command",
                  "Get-CimInstance Win32_VideoController | Select-Object Name | ConvertTo-Json -Compress"])
    if not output:
        return []
    try:
        data = json.loads(output)
    except ValueError:
        return []
    rows = data if isinstance(data, list) else [data]
    adapters = []
    for row in rows:
        name = str((row or {}).get("Name") or "").strip()
        if not name:
            continue
        lowered = name.lower()
        vendor = ("nvidia" if "nvidia" in lowered else "amd" if ("amd" in lowered or "radeon" in lowered)
                  else "intel" if "intel" in lowered else "other")
        adapters.append({"name": name, "vendor": vendor})
    return adapters


def _sysctl(name: str, run: Run) -> str:
    return (run(["sysctl", "-n", name]) or "").strip()


def macos_facts(run: Run = _run) -> dict[str, Any]:
    arm = _sysctl("hw.optional.arm64", run) == "1"
    chip = _sysctl("machdep.cpu.brand_string", run)
    try:
        memory = int(_sysctl("hw.memsize", run) or 0)
    except ValueError:
        memory = 0
    return {"apple_silicon": arm, "chip": chip, "memory_bytes": memory}


def memory_facts() -> dict[str, Any]:
    from app.providers.host_memory import available_commit_bytes

    facts: dict[str, Any] = {"total_bytes": None, "available_bytes": None,
                             "commit_available_bytes": available_commit_bytes(), "commit_limit_bytes": None}
    if sys.platform == "win32":
        import ctypes
        from ctypes import wintypes

        class MemoryStatus(ctypes.Structure):
            _fields_ = [("dwLength", wintypes.DWORD), ("dwMemoryLoad", wintypes.DWORD),
                        ("ullTotalPhys", ctypes.c_ulonglong), ("ullAvailPhys", ctypes.c_ulonglong),
                        ("ullTotalPageFile", ctypes.c_ulonglong), ("ullAvailPageFile", ctypes.c_ulonglong),
                        ("ullTotalVirtual", ctypes.c_ulonglong), ("ullAvailVirtual", ctypes.c_ulonglong),
                        ("ullAvailExtendedVirtual", ctypes.c_ulonglong)]

        status = MemoryStatus()
        status.dwLength = ctypes.sizeof(MemoryStatus)
        if ctypes.windll.kernel32.GlobalMemoryStatusEx(ctypes.byref(status)):
            facts.update(total_bytes=int(status.ullTotalPhys), available_bytes=int(status.ullAvailPhys),
                         commit_limit_bytes=int(status.ullTotalPageFile))
    elif hasattr(os, "sysconf"):
        try:
            pages = os.sysconf("SC_PHYS_PAGES")
            size = os.sysconf("SC_PAGE_SIZE")
            facts["total_bytes"] = int(pages * size)
        except (OSError, ValueError):
            pass
    return facts


def disk_facts(folder: Path) -> dict[str, Any]:
    probe = folder
    while not probe.exists() and probe.parent != probe:
        probe = probe.parent
    try:
        usage = shutil.disk_usage(probe)
    except OSError:
        return {"path": str(folder), "free_bytes": None, "total_bytes": None}
    return {"path": str(folder), "free_bytes": int(usage.free), "total_bytes": int(usage.total)}


def probe(*, packs_folder: Path | None = None, run: Run = _run, platform: str | None = None) -> dict[str, Any]:
    """The facts the setup screen needs. Never raises: a fact it cannot read is left empty."""
    platform = platform or current_platform()
    facts: dict[str, Any] = {"platform": platform, "gpus": [], "adapters": [], "nvidia_driver": "",
                             "apple_silicon": False, "chip": ""}
    try:
        if platform.startswith("windows") or platform.startswith("linux"):
            facts["gpus"] = nvidia_gpus(run)
            if platform.startswith("windows"):
                facts["adapters"] = windows_adapters(run)
            if facts["gpus"]:
                facts["nvidia_driver"] = facts["gpus"][0]["driver"]
        elif platform.startswith("macos"):
            mac = macos_facts(run)
            facts.update(apple_silicon=mac["apple_silicon"], chip=mac["chip"])
    except Exception:  # a probe that breaks must not take the setup screen with it
        logger.warning("Hardware probe failed", exc_info=True)
    facts["memory"] = memory_facts()
    if platform.startswith("macos") and not facts["memory"].get("total_bytes"):
        facts["memory"]["total_bytes"] = macos_facts(run)["memory_bytes"] or None
    from app.runtime.paths import resources_models_root

    facts["disk"] = disk_facts(packs_folder or resources_models_root())
    return facts


__all__ = ["disk_facts", "macos_facts", "memory_facts", "nvidia_gpus", "probe", "windows_adapters"]
