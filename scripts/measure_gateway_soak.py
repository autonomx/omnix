"""Measure sustained read traffic alongside real Chat, voice and market workloads."""
from __future__ import annotations

import argparse
import json
import statistics
import threading
import time
from collections import Counter
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import httpx

from validate_gateway_rollout import capture, chat, trading, voice


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--base-url', default='http://127.0.0.1:5173')
    parser.add_argument('--model', required=True)
    parser.add_argument('--duration-seconds', type=int, default=180)
    parser.add_argument('--workers', type=int, default=4)
    parser.add_argument('--output', required=True)
    args = parser.parse_args()
    if not 30 <= args.duration_seconds <= 3600 or not 1 <= args.workers <= 16:
        parser.error('duration must be 30–3600 seconds and workers 1–16')
    base = args.base_url.rstrip('/')
    stop = threading.Event()
    lock = threading.Lock()
    samples = []
    errors = Counter()
    routes = Counter()
    paths = ['/health', '/ready', '/api/jobs?limit=20', '/api/chat/sessions?limit=20']

    def reader(index):
        with httpx.Client(timeout=10) as client:
            while not stop.is_set():
                path = paths[index % len(paths)]
                index += 1
                started = time.perf_counter()
                try:
                    response = client.get(base + path)
                    response.raise_for_status()
                    if path == '/ready' and not response.json().get('ready'):
                        raise RuntimeError('readiness_false')
                    with lock:
                        samples.append((time.perf_counter() - started) * 1000)
                        routes[response.headers.get('x-omnix-gateway-route', 'unreported')] += 1
                except Exception as error:
                    with lock:
                        errors[f'{path}:{type(error).__name__}'] += 1
                stop.wait(.2)

    started = time.perf_counter()
    report = {'duration_requested_seconds': args.duration_seconds, 'read_workers': args.workers,
              'base_url': base, 'workloads': {}}
    with ThreadPoolExecutor(max_workers=args.workers) as readers, ThreadPoolExecutor(max_workers=4) as workload_pool:
        pending_readers = [readers.submit(reader, index) for index in range(args.workers)]
        work = {
            'chat_start': workload_pool.submit(capture, chat, [base], 0, args.model),
            'voice_start': workload_pool.submit(capture, voice, base),
            'trading_crypto': workload_pool.submit(capture, trading, base, 'crypto:BINANCE:spot:BTC-USDT'),
            'trading_equity': workload_pool.submit(capture, trading, base, 'equity:NASDAQ:AAPL'),
        }
        last_progress = 0
        midpoint_started = False
        try:
            while (elapsed := time.perf_counter() - started) < args.duration_seconds:
                if not midpoint_started and elapsed >= args.duration_seconds / 2:
                    work['chat_midpoint'] = workload_pool.submit(capture, chat, [base], 1, args.model)
                    work['voice_midpoint'] = workload_pool.submit(capture, voice, base)
                    midpoint_started = True
                if elapsed - last_progress >= 30:
                    with lock:
                        print(json.dumps({'elapsed_seconds': round(elapsed), 'successful_reads': len(samples),
                                          'read_errors': sum(errors.values())}), flush=True)
                    last_progress = elapsed
                stop.wait(1)
        finally:
            stop.set()
        for future in pending_readers:
            future.result()
        for name, future in work.items():
            report['workloads'][name] = future.result()
    ordered = sorted(samples)
    report['elapsed_seconds'] = round(time.perf_counter() - started, 3)
    report['reads'] = {
        'successful': len(samples), 'errors': dict(errors), 'routes': dict(routes),
        'p50_ms': round(statistics.median(ordered), 2) if ordered else None,
        'p95_ms': round(ordered[min(len(ordered) - 1, int(len(ordered) * .95))], 2) if ordered else None,
        'p99_ms': round(ordered[min(len(ordered) - 1, int(len(ordered) * .99))], 2) if ordered else None,
        'max_ms': round(max(ordered), 2) if ordered else None,
    }
    report['ok'] = bool(samples) and not errors and all(value['ok'] for value in report['workloads'].values())
    output = Path(args.output)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(report, indent=2) + '\n', encoding='utf-8')
    print(json.dumps(report), flush=True)
    return 0 if report['ok'] else 1


if __name__ == '__main__':
    raise SystemExit(main())
