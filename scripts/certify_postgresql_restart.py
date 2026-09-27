"""Certify actual disposable PostgreSQL loss, liveness and fresh-process recovery.

Only the named local test container or a CI service container ID is accepted;
inspection must confirm its configured database matches the disposable test URL.
"""
from __future__ import annotations

import argparse
from concurrent.futures import ThreadPoolExecutor
import json
import multiprocessing
import os
from pathlib import Path
import re
import subprocess
import time
from urllib.parse import urlsplit

import httpx

from certify_gateway_runtime import _serve


def certify(url, container):
    target = urlsplit(url)
    if target.hostname not in {'localhost', '127.0.0.1'} or target.path not in {'/omnix_test', '/omnix_refactor_baseline'}:
        raise ValueError('Restart certification requires a loopback disposable test database')
    if container != 'omnix-architecture-test' and not re.fullmatch(r'[a-f0-9]{64}', container):
        raise ValueError('Only the local architecture test container or a CI service ID can be restarted')
    inspected = json.loads(subprocess.check_output(['docker', 'inspect', container], text=True))[0]
    if inspected['HostConfig'].get('AutoRemove'):
        raise ValueError('Restart certification requires a retained disposable container (omit docker --rm)')
    environment = dict(entry.split('=', 1) for entry in inspected['Config']['Env'] if '=' in entry)
    if environment.get('POSTGRES_DB') != target.path[1:] or not inspected['State']['Running']:
        raise ValueError('Container must be running and own the configured disposable test database')
    bindings = inspected['NetworkSettings']['Ports'].get('5432/tcp') or []
    if not any(int(binding['HostPort']) == (target.port or 5432) for binding in bindings):
        raise ValueError('Test URL port must match the disposable container')

    context = multiprocessing.get_context('spawn')
    cohort = []
    stopped = False

    def start(role, tts=''):
        parent, child = context.Pipe()
        process = context.Process(target=_serve, args=(child, url, role, tts, 3))
        process.start()
        child.close()
        cohort.append((process, parent))
        assert parent.poll(45), f'{role} startup deadline exceeded'
        return parent.recv()['url']

    try:
        tts = start('tts')
        original = [start(role, tts) for role in ('worker', 'api')]
        with httpx.Client(timeout=35) as client:
            assert all(client.get(base + '/ready').status_code == 200 for base in original)
            subprocess.run(['docker', 'stop', '--time', '3', container], check=True, capture_output=True)
            stopped = True
            with ThreadPoolExecutor(max_workers=2) as pool:
                probes = [pool.submit(client.get, base + '/ready') for base in original]
                # PostgreSQL probes may wait on pool reconnects; liveness must
                # remain responsive on the event loop at the same time.
                for base in original:
                    assert client.get(base + '/health', timeout=2).status_code == 200
                assert all(probe.result().status_code == 503 for probe in probes)
            time.sleep(6)  # let supervisors observe loss and durable leases expire
            subprocess.run(['docker', 'start', container], check=True, capture_output=True)
            stopped = False
            deadline = time.monotonic() + 30
            while True:
                result = subprocess.run(['docker', 'exec', container, 'pg_isready', '-U', environment['POSTGRES_USER'], '-d', environment['POSTGRES_DB']], capture_output=True)
                if result.returncode == 0:
                    break
                assert time.monotonic() < deadline, 'PostgreSQL restart deadline exceeded'
                time.sleep(.2)
            # Old identities remain revoked even after connectivity returns.
            assert all(client.get(base + '/ready').status_code == 503 for base in original)
            diagnostics = client.get(original[0] + '/api/diagnostics').json()['runtime']
            assert diagnostics['background']['owns_lock'] is False
            replacement = [start(role, tts) for role in ('worker', 'api')]
            assert all(client.get(base + '/ready').status_code == 200 for base in replacement)
        return {'schema_version': 1, 'postgresql_restarted': True, 'liveness_preserved': True,
                'old_authority_revoked': True, 'fresh_processes_ready': True, 'ok': True}
    finally:
        try:
            if stopped:
                subprocess.run(['docker', 'start', container], check=True, capture_output=True)
        finally:
            for process, pipe in cohort:
                if process.is_alive():
                    try:
                        pipe.send('stop')
                    except (EOFError, OSError):
                        pass
                process.join(15)
                if process.is_alive():
                    process.terminate()
                    process.join(5)
                pipe.close()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--container', required=True)
    parser.add_argument('--local-disposable', action='store_true')
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    url = ('postgresql://omnix_baseline:baseline_disposable@127.0.0.1:16432/omnix_refactor_baseline'
           if args.local_disposable else os.environ.get('OMNIX_TEST_DATABASE_URL', ''))
    result = certify(url, args.container)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, indent=2) + '\n', encoding='utf-8')
    print(json.dumps(result))


if __name__ == '__main__':
    main()
