"""CPU certification: real PostgreSQL + worker/two API processes + mocked compute.

Uses the production composition and HTTP/SSE/WebSocket transports. Feature
registration is restricted to voice and event-loop services in this test fixture
so certification cannot start market collectors or call external model services.
"""
from __future__ import annotations

import argparse
import asyncio
import io
import json
import multiprocessing
import os
from pathlib import Path
import socket
import statistics
import sys
import threading
import time
import tracemalloc
import uuid
import wave

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'src'))


def _serve(control, url, role, tts_url, ownership_lease_seconds=30):
    import uvicorn
    from fastapi import FastAPI, Response
    listener = socket.socket()
    listener.bind(('127.0.0.1', 0))
    port = listener.getsockname()[1]
    if role == 'tts':
        app = FastAPI()
        @app.get('/health')
        def health():
            return {'ok': True, 'status': 'ready', 'details': {'mode': 'certification_mock'}}
        @app.get('/api/tts/speakers')
        def speakers():
            return {'speakers': ['default']}
        @app.post('/api/tts/generate_stream_audio')
        def synthesize():
            output = io.BytesIO()
            with wave.open(output, 'wb') as audio:
                audio.setnchannels(1)
                audio.setsampwidth(2)
                audio.setframerate(24000)
                audio.writeframes(b'\x00\x20\x00\xe0' * 2400)
            return Response(output.getvalue(), media_type='audio/wav')
    else:
        os.environ.update(OMNIX_DATABASE_URL=url, OMNIX_PERSISTENCE_MODE='postgresql',
                          OMNIX_GATEWAY_BACKGROUND_ROLE=role, OMNIX_TTS_URL=tts_url,
                          OMNIX_GATEWAY_TTS_HTTP='1', OMNIX_TTS_STARTUP_WARMUP='0',
                          OMNIX_GATEWAY_REQUIRED_WORKERS='tts')
        from app.gateway import feature_registry
        feature_registry.FEATURES = tuple(feature for feature in feature_registry.FEATURES if feature.module in {
            'app.gateway.live_voice_runtime_offload', 'app.gateway.event_loop_lag_monitor',
            'app.gateway.tts_pcm_websocket', 'app.gateway.tts_runtime_routes',
            'app.gateway.blocking_route_offload',
        })
        from app.chat import generation_jobs
        generation_jobs._generate_reply = lambda *args, **kwargs: {'content': 'Certified deterministic reply.', 'metadata': {}}
        from app import shared
        def no_local_registry():
            raise AssertionError('certification processes must use remote TTS')
        shared.get_audio_registry = no_local_registry
        from app.production import create_production_app
        app = create_production_app()
        # Failure certification can shorten observation deadlines without
        # changing durable checks or the production defaults.
        app.state.execution_owner.lease_seconds = ownership_lease_seconds
        app.state.execution_owner.heartbeat_seconds = min(5, ownership_lease_seconds / 3)
    tracemalloc.start()
    server = uvicorn.Server(uvicorn.Config(app, log_level='error', access_log=False))
    async def commands():
        while not server.started:
            await asyncio.sleep(.05)
        control.send({'url': f'http://127.0.0.1:{port}'})
        while True:
            command = await asyncio.to_thread(control.recv)
            if command == 'stop':
                server.should_exit = True
                return
            services = getattr(app.state, 'runtime_services', None)
            control.send({'python_bytes': tracemalloc.get_traced_memory()[0], 'threads': threading.active_count(),
                          'tasks': len(asyncio.all_tasks()), 'process_id': os.getpid(), 'role': role,
                          'requests': app.state.runtime_metrics.snapshot() if services else {},
                          'pool': services.jobs.database.pool_statistics() if services else {}})
    async def run():
        await asyncio.gather(server.serve(sockets=[listener]), commands())
    try:
        asyncio.run(run())
    finally:
        listener.close()
        control.close()


def certify(url, duration):
    import httpx
    from websockets.sync.client import connect
    context = multiprocessing.get_context('spawn')
    cohort = []
    def start(role, tts=''):
        parent, child = context.Pipe()
        process = context.Process(target=_serve, args=(child, url, role, tts))
        process.start()
        child.close()
        cohort.append((process, parent))
        if not parent.poll(45):
            raise TimeoutError(f'{role} process did not become ready')
        return parent.recv()['url'], parent
    samples, completed, events, frames = [], 0, 0, 0
    restart_count = 0
    snapshots = []
    sessions = []
    try:
        tts, _ = start('tts')
        gateways = [start(role, tts) for role in ('worker', 'api', 'api')]
        with httpx.Client(timeout=20) as client:
            def request(method, address, **kwargs):
                started = time.perf_counter()
                response = client.request(method, address, **kwargs)
                response.raise_for_status()
                samples.append((time.perf_counter() - started) * 1000)
                return response.json()
            for address, _ in gateways:
                assert request('GET', address + '/ready')['ready']
            started = time.monotonic()
            while time.monotonic() - started < duration:
                base = gateways[completed % 3][0]
                other = gateways[(completed + 1) % 3][0]
                session = request('POST', base + '/api/chat/sessions', json={
                    'title': 'Architecture certification', 'read_memory': False, 'write_memory': False,
                })
                sessions.append((base, session['id']))
                path = f"/api/chat/sessions/{session['id']}"
                payload = {'content': 'certify', 'agent_mode': False, 'user_turn_id': 'certification:' + uuid.uuid4().hex}
                first = request('POST', base + path + '/messages', json=payload)
                duplicate = request('POST', other + path + '/messages', json=payload)
                assert first['job']['id'] == duplicate['job']['id']
                deadline = time.monotonic() + 15
                while True:
                    job = request('GET', other + '/api/jobs/' + first['job']['id'])
                    job = job.get('job', job)
                    if job['status'] == 'completed':
                        break
                    assert job['status'] not in {'failed', 'canceled'} and time.monotonic() < deadline, job
                    time.sleep(.05)
                transcript = request('GET', other + path)
                assert sum(message['role'] == 'assistant' for message in transcript['messages']) == 1
                with client.stream('GET', other + '/events') as stream:
                    stream.raise_for_status()
                    for line in stream.iter_lines():
                        if line.startswith('data:') or line.startswith(':'):
                            events += 1
                            break
                stream_id = 'certification-' + uuid.uuid4().hex
                with connect(other.replace('http://', 'ws://') + '/api/tts/stream/websocket', open_timeout=10) as websocket:
                    websocket.send(json.dumps({'text': 'certification', 'language': 'en', 'append_silence': False,
                                               'diagnostics_stream_id': stream_id}))
                    while True:
                        message = websocket.recv(timeout=15)
                        if isinstance(message, bytes):
                            frames += 1
                        else:
                            message = json.loads(message)
                            assert message.get('type') != 'error', message
                            if message.get('type') == 'done':
                                websocket.send(json.dumps({'type': 'diagnostic', 'stream_id': stream_id,
                                                           'event': 'playback_finished', 'details': {}}))
                                break
                request('DELETE', base + path)
                sessions.pop()
                completed += 1
                if not restart_count and time.monotonic() - started >= duration / 2:
                    # Restart a serving replica between turns; independent tests
                    # kill claimed owners and terminate PostgreSQL connections.
                    retiring = gateways[2][1]
                    retiring.send('stop')
                    process = next(process for process, pipe in cohort if pipe is retiring)
                    process.join(15)
                    assert not process.is_alive(), 'API replica did not shut down'
                    gateways[2] = start('api', tts)
                    assert request('GET', gateways[2][0] + '/ready')['ready']
                    restart_count += 1
                if completed in {1, 5}:
                    for _, pipe in gateways:
                        pipe.send('snapshot')
                        assert pipe.poll(10)
                        snapshots.append(pipe.recv())
            for _, pipe in gateways:
                pipe.send('snapshot')
                assert pipe.poll(10)
                snapshots.append(pipe.recv())
            diagnostics = [request('GET', address + '/api/diagnostics')['runtime'] for address, _ in gateways]
            assert all(snapshot['requests']['active_requests'] == 0 for snapshot in snapshots)
            assert all(item['chat']['queued_dispatches'] == 0 for item in diagnostics)
            assert all(item['jobs']['expired_lease_count'] == 0 for item in diagnostics)
            assert frames > 0 and events > 0 and completed > 0
            growth = []
            for snapshot in snapshots[-3:]:
                warmed = next((item for item in snapshots[3:-3] if item['process_id'] == snapshot['process_id']), None)
                if warmed is None:
                    continue
                item = {'role': snapshot['role'], 'python_bytes': snapshot['python_bytes'] - warmed['python_bytes'],
                        'threads': snapshot['threads'] - warmed['threads'], 'tasks': snapshot['tasks'] - warmed['tasks']}
                growth.append(item)
                assert item['python_bytes'] < 64 * 1024 * 1024 and item['threads'] < 32 and item['tasks'] < 32, item
        samples.sort()
        return {'schema_version': 1, 'mode': 'production_composition_with_mock_compute',
                'duration_seconds': duration, 'completed_chats': completed, 'duplicate_outputs': 0,
                'error_count': 0, 'sse_connections': events, 'pcm_frames': frames,
                'controlled_replica_restarts': restart_count, 'resource_growth_after_warmup': growth,
                'p50_ms': statistics.median(samples), 'p95_ms': samples[int(len(samples) * .95)],
                'p99_ms': samples[int(len(samples) * .99)], 'resource_snapshots': snapshots,
                'diagnostics': diagnostics, 'ok': True}
    finally:
        for process, pipe in cohort:
            if process.is_alive():
                try:
                    pipe.send('stop')
                except (EOFError, OSError):
                    pass
            process.join(10)
            if process.is_alive():
                process.terminate()
                process.join(5)
            pipe.close()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--duration-seconds', type=int, default=60)
    parser.add_argument('--local-disposable', action='store_true')
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    from urllib.parse import urlsplit
    url = ('postgresql://omnix_baseline:baseline_disposable@127.0.0.1:16432/omnix_refactor_baseline'
           if args.local_disposable else os.environ.get('OMNIX_TEST_DATABASE_URL', ''))
    if urlsplit(url).path not in {'/omnix_test', '/omnix_refactor_baseline'} or not 5 <= args.duration_seconds <= 3600:
        parser.error('requires a disposable omnix_test/omnix_refactor_baseline database and 5–3600 seconds')
    result = certify(url, args.duration_seconds)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, indent=2) + '\n', encoding='utf-8')
    print(json.dumps({key: value for key, value in result.items() if key not in {'diagnostics', 'resource_snapshots'}}))


if __name__ == '__main__':
    main()
