"""ASGI entrypoint the launcher runs as the image service process."""
from __future__ import annotations

from starlette.concurrency import run_in_threadpool

from app.observability.logging import configure_logging

from .image_service_runtime import app, configure_device_permits


async def _prepare_launched_process() -> None:
    configure_logging()
    await run_in_threadpool(configure_device_permits)


async def _release_on_shutdown() -> None:
    # A clean stop (the desktop supervisor's Ctrl+Break, uvicorn's Ctrl+C) frees the GPU and the device's image
    # model slot at once, instead of leaving the next image service to wait for the lease to expire.
    from app.platform.image.lifecycle import unload_all_image_providers

    await run_in_threadpool(unload_all_image_providers)


# Configure logging and coordinate GPU use before any startup preload. Only the
# launched process does this; importing the runtime (tests, tools) leaves
# logging and permits untouched.
app.router.on_startup.insert(0, _prepare_launched_process)
app.router.on_shutdown.append(_release_on_shutdown)

__all__ = ["app"]
