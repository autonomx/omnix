"""ASGI entrypoint the launcher runs as the image service process."""
from __future__ import annotations

from starlette.concurrency import run_in_threadpool

from .image_service_runtime import app, configure_device_permits


async def _coordinate_device_permits() -> None:
    await run_in_threadpool(configure_device_permits)


# Coordinate GPU use before any startup preload. Only the launched process
# does this; importing the runtime (tests, tools) leaves permits untouched.
app.router.on_startup.insert(0, _coordinate_device_permits)

__all__ = ["app"]
