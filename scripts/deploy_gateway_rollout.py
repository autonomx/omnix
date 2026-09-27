"""Cut over the credential-aware local launcher after isolated qualification."""
from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import socket
import sys
import time

import httpx
import psutil


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--gateway-pid', type=int, required=True)
    parser.add_argument('--backup', type=Path, required=True)
    parser.add_argument('--qualification', type=Path, required=True)
    args = parser.parse_args()
    root = Path(__file__).resolve().parents[1]
    backup = args.backup.resolve()
    assert backup.is_relative_to(root / 'resources/artifacts/backups')
    with backup.open('rb') as source:
        assert source.read(5) == b'PGDMP', 'A completed custom PostgreSQL backup is required'
    qualified = json.loads(args.qualification.read_text(encoding='utf-8'))
    assert qualified['ok'] and len(qualified['readiness']) == 3
    assert sorted(item['background_role'] for item in qualified['readiness']) == ['api', 'api', 'worker']
    old = psutil.Process(args.gateway_pid)
    assert Path(old.cwd()).resolve() == root and 'run_omnix_gateway.py' in ' '.join(old.cmdline())
    environment = old.environ()
    assert not environment.get('OMNIX_GATEWAY_API_REPLICAS'), 'Launcher environment overrides local deployment configuration'
    for port in [8001, 8002]:
        with socket.socket() as listener:
            listener.bind(('127.0.0.1', port))
    os.environ.update(environment)
    sys.path.insert(0, str(root / 'src'))
    from app.persistence.config import DatabaseSettings
    from app.persistence.database import PostgresDatabase
    from app.persistence.migrations import apply_migrations, migration_status
    database = PostgresDatabase(DatabaseSettings(url=environment['OMNIX_DATABASE_URL'], pool_max=2, application_name='omnix-rollout'))
    report = {'backup': str(backup.relative_to(root)), 'backup_bytes': backup.stat().st_size,
              'backup_sha256': hashlib.sha256(backup.read_bytes()).hexdigest()}
    deployment_path = root / 'resources/data/gateway-deployment.json'
    previous = deployment_path.read_bytes() if deployment_path.exists() else None
    try:
        before = migration_status(database, initialize_table=False)
        assert before['ok'], 'Migration drift must be resolved before cutover'
        report['migrations_before'] = {'current': before['current_schema'], 'pending': before['pending']}
        with database.connection() as connection:
            active = connection.execute("SELECT count(*) FROM omnix_jobs WHERE job_type='chat.generate' AND status='running'").fetchone()[0]
        assert active == 0, 'Wait for active Chat generations before restarting the gateway'
        with httpx.Client(timeout=30) as client:
            snapshot = client.get('http://127.0.0.1:5055/api/services').raise_for_status().json()
            gateway = next(item for item in snapshot['services'] if item['id'] == 'gateway')
            assert gateway['pid'] == args.gateway_pid
            report['unchanged_services'] = {item['id']: item['pid'] for item in snapshot['services'] if item['id'] != 'gateway'}
            stopped = client.post('http://127.0.0.1:5055/api/services/gateway/stop').raise_for_status().json()
            assert stopped['ok']
            old.wait(15)
            print('Old gateway stopped; verifying forward migrations.', flush=True)
            try:
                migrated = apply_migrations(database)
                report['migrations'] = {'current': migrated['current_schema'], 'applied_now': migrated['applied_now'],
                                        'pending': migrated['pending'], 'checksum_drift': migrated['checksum_drift']}
                deployment_path.parent.mkdir(parents=True, exist_ok=True)
                deployment_path.write_text(json.dumps({'api_replicas': 2}, indent=2) + '\n', encoding='utf-8')
                started = client.post('http://127.0.0.1:5055/api/services/gateway/start').raise_for_status().json()
                assert started['ok']
                report['supervisor_pid'] = started['service']['pid']
                print(json.dumps({'supervisor_pid': report['supervisor_pid'], 'migrations': report['migrations']}), flush=True)
                deadline = time.monotonic() + 180
                report['readiness'] = []
                for port, role in [(8000, 'worker'), (8001, 'api'), (8002, 'api')]:
                    while True:
                        try:
                            response = client.get(f'http://127.0.0.1:{port}/ready', timeout=5)
                            payload = response.json()
                            if response.status_code == 200 and payload.get('ready') and payload.get('background_role') == role:
                                report['readiness'].append({'port': port, **payload})
                                print(json.dumps({'port': port, 'ready': True, 'role': role}), flush=True)
                                break
                        except (httpx.HTTPError, ValueError):
                            pass
                        if time.monotonic() > deadline:
                            raise TimeoutError('Deployed gateway cohort failed readiness')
                        time.sleep(.5)
            except BaseException:
                client.post('http://127.0.0.1:5055/api/services/gateway/stop').raise_for_status()
                if previous is None:
                    deployment_path.write_text('{"api_replicas": 0}\n', encoding='utf-8')
                else:
                    deployment_path.write_bytes(previous)
                client.post('http://127.0.0.1:5055/api/services/gateway/start').raise_for_status()
                raise
            after = client.get('http://127.0.0.1:5055/api/services').raise_for_status().json()
            assert report['unchanged_services'] == {item['id']: item['pid'] for item in after['services'] if item['id'] != 'gateway'}
        lock = int.from_bytes(hashlib.sha256(b'omnix:gateway-background:workspace:local').digest()[:8], 'big', signed=True)
        with database.connection() as connection:
            nodes = connection.execute("SELECT process_id FROM omnix_runtime_nodes WHERE node_type='gateway' AND status='active' AND lease_expires_at>clock_timestamp() AND metadata->>'workspace_id'='workspace:local'").fetchall()
            owners = connection.execute("SELECT count(*) FROM pg_locks WHERE locktype='advisory' AND granted AND classid::bigint=%s AND objid::bigint=%s AND objsubid=1", ((lock >> 32) & 0xffffffff, lock & 0xffffffff)).fetchone()[0]
        assert len(nodes) == 3 and owners == 1
        report['gateway_pids'] = [int(row[0]) for row in nodes]
        report['background_lock_owners'] = owners
        report['ok'] = True
        output = root / 'docs/measurements/gateway-deployment-2026-09-26.json'
        output.write_text(json.dumps(report, indent=2) + '\n', encoding='utf-8')
        print(json.dumps({'ok': True, 'gateway_pids': report['gateway_pids'], 'background_lock_owners': owners, 'output': str(output)}))
    finally:
        database.close()
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
