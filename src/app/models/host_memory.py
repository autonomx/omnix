"""Host memory a model load can still use.

On Windows that is the commit charge left (physical memory plus the page file):
a load past it fails with "the paging file is too small" (os error 1455) or
crashes, and on the way it starves every other process. Elsewhere it is the
memory the kernel reports as available plus free swap.
"""
from __future__ import annotations

import logging
import os
import sys

logger = logging.getLogger(__name__)


def available_commit_bytes() -> int | None:
    """Bytes of commit (Windows) or available memory plus free swap left now; None when unknown."""
    try:
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
            if not ctypes.windll.kernel32.GlobalMemoryStatusEx(ctypes.byref(status)):
                return None
            return int(status.ullAvailPageFile)
        if os.path.exists("/proc/meminfo"):
            values: dict[str, int] = {}
            with open("/proc/meminfo", encoding="ascii") as handle:
                for line in handle:
                    name, _, rest = line.partition(":")
                    values[name] = int(rest.split()[0]) * 1024
            return values.get("MemAvailable", 0) + values.get("SwapFree", 0)
    except Exception:
        logger.debug("Host memory query failed", exc_info=True)
    return None


__all__ = ["available_commit_bytes"]
