"""The accelerator a model service runs on, for ``/health`` and the Models tool (Voice Studio Phase 5 §4).

CUDA reports its device, total and free VRAM. Apple Silicon (MPS) shares memory
with the CPU: it reports the memory Metal recommends for the GPU as the total and
what is left of it, marked ``unified_memory`` so the UI does not call it VRAM.
Without either, the report is empty.
"""
from __future__ import annotations

import logging
from typing import Any

logger = logging.getLogger(__name__)


def gpu_memory(torch_module: Any = None) -> dict[str, Any]:
    """``{"device", "vram_total_bytes", "vram_free_bytes"[, "unified_memory"]}``, or ``{}``."""
    try:
        torch = torch_module
        if torch is None:
            import torch  # type: ignore[no-redef]
        if torch.cuda.is_available():
            free, total = torch.cuda.mem_get_info()
            return {"vram_free_bytes": int(free), "vram_total_bytes": int(total),
                    "device": torch.cuda.get_device_name(0)}
        mps = getattr(getattr(torch, "backends", None), "mps", None)
        if mps is not None and mps.is_available():
            total = int(torch.mps.recommended_max_memory())
            used = int(torch.mps.driver_allocated_memory())
            return {"vram_free_bytes": max(0, total - used), "vram_total_bytes": total,
                    "device": "Apple Silicon (MPS)", "unified_memory": True}
    except Exception:
        logger.debug("GPU memory query failed", exc_info=True)
    return {}


__all__ = ["gpu_memory"]
