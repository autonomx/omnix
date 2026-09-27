"""Application lifecycle orchestration, independent of route registration."""

import asyncio
from contextlib import asynccontextmanager
import inspect
import logging

logger = logging.getLogger(__name__)


async def _invoke(callback):
    result = callback()
    if inspect.isawaitable(result):
        await result


@asynccontextmanager
async def gateway_lifespan(app, *, get_chat_store, get_job_store, recover_jobs):
    recovered = await asyncio.to_thread(
        lambda: recover_jobs(get_chat_store(), get_job_store())
    )
    if recovered:
        logger.warning("Recovered %s abandoned Chat generation jobs", recovered)
    try:
        background = getattr(app.state, "background_runtime", None)
        if background is not None:
            await background.startup()
        for callback in app.router.on_startup:
            await _invoke(callback)
        app.state.runtime_started = True
        yield
    finally:
        app.state.runtime_started = False
        failures = []
        for callback in reversed(app.router.on_shutdown):
            try:
                await _invoke(callback)
            except Exception as exc:
                failures.append(exc)
                logger.exception("Gateway shutdown callback failed")
        if failures:
            raise RuntimeError("Gateway shutdown callbacks failed") from failures[0]
