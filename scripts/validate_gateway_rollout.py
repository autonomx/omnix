"""Measure real Chat, GPU speech, and read-only market data through running gateways."""
from __future__ import annotations

import argparse
from collections import Counter
from concurrent.futures import ThreadPoolExecutor
import io
import json
from pathlib import Path
import statistics
import threading
import time
import uuid
import wave

import httpx
from websockets.sync.client import connect

GATEWAY_ROUTES = Counter()
ROUTES_LOCK = threading.Lock()


def record_route(headers):
    route = headers.get('x-omnix-gateway-route')
    if route:
        with ROUTES_LOCK:
            GATEWAY_ROUTES[route] += 1
    return route


def request(client, method, url, **kwargs):
    response = client.request(method, url, **kwargs)
    record_route(response.headers)
    response.raise_for_status()
    return response.json()


def chat(urls, index, model):
    base = urls[index % len(urls)]
    other = urls[(index + 1) % len(urls)]
    with httpx.Client(timeout=30) as client:
        session = request(client, 'POST', base + '/api/chat/sessions', json={
            'title': 'Framework rollout validation ' + uuid.uuid4().hex[:8],
            'provider_id': 'llm:chatgpt_codex', 'model_id': model,
            'read_memory': False, 'write_memory': False,
        })
        session_id = session['id']
        payload = {'content': 'Reply with one short sentence confirming this harmless application validation request was received. Do not use tools.',
                   'agent_mode': False, 'user_turn_id': 'rollout:' + uuid.uuid4().hex,
                   'provider_id': 'llm:chatgpt_codex', 'model_id': model}
        started = time.perf_counter()
        accepted = request(client, 'POST', base + f'/api/chat/sessions/{session_id}/messages', json=payload)
        admission_ms = (time.perf_counter() - started) * 1000
        duplicate = request(client, 'POST', other + f'/api/chat/sessions/{session_id}/messages', json=payload)
        assert accepted['job']['id'] == duplicate['job']['id'], 'Cross-replica idempotency failed'
        deadline = time.monotonic() + 180
        while True:
            job = request(client, 'GET', other + '/api/jobs/' + accepted['job']['id'])
            job = job.get('job', job)
            if job['status'] in {'completed', 'failed', 'canceled', 'cancelled'}:
                break
            if time.monotonic() > deadline:
                raise TimeoutError('Real Chat job did not finish within 180 seconds')
            time.sleep(.25)
        if job['status'] != 'completed':
            raise RuntimeError('Chat job failed: ' + json.dumps(job.get('error'))[:700])
        completed = request(client, 'GET', other + f'/api/chat/sessions/{session_id}')
        assistants = [m for m in completed['messages'] if m['role'] == 'assistant']
        users = [m for m in completed['messages'] if m['role'] == 'user']
        assert len(assistants) == len(users) == 1 and assistants[0]['content'].strip()
        result = {'ok': True, 'provider': 'chatgpt_codex', 'model': model,
                  'admission_ms': round(admission_ms, 2), 'completion_seconds': round(time.perf_counter() - started, 3),
                  'cross_replica_idempotency': True, 'persisted_assistant_messages': len(assistants)}
        request(client, 'DELETE', base + f'/api/chat/sessions/{session_id}')
        return result


def voice(base):
    stream_id = 'chat-rollout-' + uuid.uuid4().hex
    pcm = bytearray()
    frames = 0
    sample_rate = 24000
    first_audio = None
    started = time.perf_counter()
    with connect(base.replace('http', 'ws', 1) + '/api/tts/stream/websocket', open_timeout=15, close_timeout=5) as ws:
        gateway_route = record_route(ws.response.headers)
        ws.send(json.dumps({'text': 'The audio system is ready for a clear and simple conversation.',
                            'diagnostics_stream_id': stream_id, 'language': 'en', 'append_silence': False}))
        while True:
            message = ws.recv(timeout=120)
            if isinstance(message, bytes):
                if first_audio is None:
                    first_audio = time.perf_counter() - started
                pcm.extend(message)
                frames += 1
                continue
            control = json.loads(message)
            sample_rate = control.get('sample_rate', sample_rate)
            if control.get('type') == 'error':
                raise RuntimeError('GPU TTS failed: ' + str(control.get('message'))[:500])
            if control.get('type') == 'done':
                ws.send(json.dumps({'type': 'diagnostic', 'stream_id': stream_id, 'event': 'playback_finished', 'details': {}}))
                break
    tts_seconds = time.perf_counter() - started
    assert pcm and frames > 0, 'TTS returned no PCM audio'
    wav = io.BytesIO()
    with wave.open(wav, 'wb') as audio:
        audio.setnchannels(1)
        audio.setsampwidth(2)
        audio.setframerate(sample_rate)
        audio.writeframes(pcm)
    started = time.perf_counter()
    with httpx.Client(timeout=120) as client:
        transcript = request(client, 'POST', 'http://127.0.0.1:5201/transcribe',
                             files={'file': ('rollout-validation.wav', wav.getvalue(), 'audio/wav')})
        health = request(client, 'GET', 'http://127.0.0.1:5101/health')
    assert transcript.get('success') and transcript.get('text', '').strip(), 'STT returned no transcript'
    return {'ok': True, 'gateway_route': gateway_route, 'tts_provider': health.get('provider', health.get('provider_class')),
            'stt_provider': transcript.get('provider'), 'pcm_frames': frames,
            'audio_seconds': round(len(pcm) / (2 * sample_rate), 3),
            'first_audio_ms': round(first_audio * 1000, 2), 'tts_seconds': round(tts_seconds, 3),
            'stt_seconds': round(time.perf_counter() - started, 3), 'transcript': transcript['text']}


def streaming_chat(urls, model):
    started = time.perf_counter()
    events = []
    first_content = None
    with httpx.Client(timeout=180) as client:
        session = request(client, 'POST', urls[0] + '/api/chat/sessions', json={
            'title': 'Framework streaming validation ' + uuid.uuid4().hex[:8],
            'provider_id': 'llm:chatgpt_codex', 'model_id': model,
            'read_memory': False, 'write_memory': False})
        path = f"/api/chat/sessions/{session['id']}"
        with client.stream('POST', urls[0] + path + '/messages/stream', json={
            'content': 'Reply with one brief sentence about clear communication. Do not use tools.',
            'provider_id': 'llm:chatgpt_codex', 'model_id': model, 'agent_mode': False,
            'user_turn_id': 'rollout-stream:' + uuid.uuid4().hex}) as response:
            response.raise_for_status()
            gateway_route = record_route(response.headers)
            for line in response.iter_lines():
                if not line.startswith('data: '):
                    continue
                event = json.loads(line[6:])
                if event.get('type') == 'error':
                    raise RuntimeError('Real Chat stream failed: ' + str(event.get('message'))[:600])
                if first_content is None and event.get('type') in {'delta', 'complete', 'token', 'chunk'}:
                    first_content = time.perf_counter() - started
                events.append(event)
        assert any(event.get('type') == 'done' for event in events), 'SSE stream lacked a completion event'
        transcript = request(client, 'GET', urls[-1] + path)
        assistants = [item for item in transcript['messages'] if item['role'] == 'assistant']
        assert len(assistants) == 1 and assistants[0]['content'].strip()
        request(client, 'DELETE', urls[0] + path)
    return {'ok': True, 'gateway_route': gateway_route, 'provider': 'chatgpt_codex', 'model': model, 'events': len(events),
            'first_content_ms': round(first_content * 1000, 2) if first_content else None,
            'elapsed_seconds': round(time.perf_counter() - started, 3), 'persisted_assistant_messages': 1}


def trading(base, instrument):
    started = time.perf_counter()
    with httpx.Client(timeout=60) as client:
        bars = request(client, 'GET', base + '/api/trading/bars', params={'instrument_id': instrument, 'interval': '1d', 'limit': 30})
        quote = request(client, 'GET', base + '/api/trading/quotes', params={'instrument_id': instrument})
    assert bars.get('bars') and float(quote['price']) > 0
    return {'ok': True, 'instrument': instrument, 'provider': quote['provider'],
            'bars': len(bars['bars']), 'quote_freshness': quote.get('freshness_mode'),
            'elapsed_seconds': round(time.perf_counter() - started, 3)}


def capture(function, *args):
    try:
        return function(*args)
    except Exception as exc:
        return {'ok': False, 'error_type': type(exc).__name__, 'error': str(exc)[:900]}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--urls', nargs='+', required=True)
    parser.add_argument('--model', required=True)
    parser.add_argument('--output', required=True)
    parser.add_argument('--require-api-routes', action='store_true', help='Require both local replicas and stream routing through ingress')
    args = parser.parse_args()
    GATEWAY_ROUTES.clear()
    urls = [url.rstrip('/') for url in args.urls]
    report = {'urls': urls, 'readiness': [], 'workloads': {}}
    with httpx.Client(timeout=15) as client:
        for base in urls:
            report['readiness'].append(request(client, 'GET', base + '/ready'))
    stop = threading.Event()
    health_samples = []
    health_errors = []
    def health_monitor():
        with httpx.Client(timeout=10) as client:
            while not stop.is_set():
                for base in urls:
                    started = time.perf_counter()
                    try:
                        response = client.get(base + '/health')
                        response.raise_for_status()
                        health_samples.append((time.perf_counter() - started) * 1000)
                    except Exception as exc:
                        health_errors.append(type(exc).__name__)
                stop.wait(.2)
    monitor = threading.Thread(target=health_monitor, daemon=True)
    monitor.start()
    try:
        with ThreadPoolExecutor(max_workers=6) as pool:
            jobs = {f'chat_{i}': pool.submit(capture, chat, urls, i, args.model) for i in range(3)}
            jobs['voice'] = pool.submit(capture, voice, urls[-1])
            jobs['trading_crypto'] = pool.submit(capture, trading, urls[-1], 'crypto:BINANCE:spot:BTC-USDT')
            jobs['trading_equity'] = pool.submit(capture, trading, urls[0], 'equity:NASDAQ:AAPL')
            jobs['chat_stream'] = pool.submit(capture, streaming_chat, urls, args.model)
            for name, future in jobs.items():
                report['workloads'][name] = future.result()
                print(json.dumps({name: report['workloads'][name]}), flush=True)
    finally:
        stop.set()
        monitor.join(15)
    samples = sorted(health_samples)
    report['health_under_load'] = {'samples': len(samples), 'errors': len(health_errors),
        'p50_ms': round(statistics.median(samples), 2) if samples else None,
        'p95_ms': round(samples[min(len(samples) - 1, int(len(samples) * .95))], 2) if samples else None,
        'max_ms': round(max(samples), 2) if samples else None}
    report['ok'] = all(item['ok'] for item in report['workloads'].values()) and not health_errors
    report['gateway_routes'] = dict(GATEWAY_ROUTES)
    if args.require_api_routes:
        report['routing_qualified'] = (
            all(GATEWAY_ROUTES[route] > 0 for route in ('api-1', 'api-2'))
            and all(str(report['workloads'][name].get('gateway_route', '')).startswith('api-')
                    for name in ('voice', 'chat_stream'))
        )
        report['ok'] = report['ok'] and report['routing_qualified']
    output = Path(args.output)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(report, indent=2) + '\n', encoding='utf-8')
    print(json.dumps({'ok': report['ok'], 'health_under_load': report['health_under_load'], 'output': str(output)}))
    return 0 if report['ok'] else 1


if __name__ == '__main__':
    raise SystemExit(main())
