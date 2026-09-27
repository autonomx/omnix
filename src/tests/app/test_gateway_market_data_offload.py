import asyncio
import threading
import time

from fastapi import FastAPI
import httpx
import pytest

from app.trading.api import create_trading_router


@pytest.mark.parametrize('path,method', [('/bars', 'bars'), ('/quotes', 'quote')])
def test_market_network_calls_do_not_block_health(path, method):
    entered = threading.Event()
    release = threading.Event()
    threads = []
    class Service:
        def blocked(self, *args):
            threads.append(threading.get_ident())
            entered.set()
            release.wait(2)
            raise ValueError('fixture completed')
        bars = quote = blocked
    app = FastAPI()
    app.include_router(create_trading_router(market_service_factory=Service))
    @app.get('/health')
    async def health():
        return {'ok': True}
    async def exercise():
        loop_thread = threading.get_ident()
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url='http://test') as client:
            call = asyncio.create_task(client.get('/api/trading' + path, params={'instrument_id': 'equity:NASDAQ:AAPL'}))
            try:
                assert await asyncio.to_thread(entered.wait, 1)
                started = time.perf_counter()
                assert (await client.get('/health')).status_code == 200
                assert time.perf_counter() - started < .2
                assert threads == [threads[0]] and threads[0] != loop_thread
            finally:
                release.set()
            assert (await call).status_code == 422
    asyncio.run(exercise())
