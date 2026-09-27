"""Run the named architecture release gates; PostgreSQL gates require a disposable DB."""

from __future__ import annotations

import argparse
import os
from pathlib import Path
import subprocess
import sys
from urllib.parse import urlsplit

ROOT = Path(__file__).resolve().parents[1]
GATES = {
    'unit': (
        'src/tests/app/test_audiobook_background_ownership.py',
        'src/tests/unit/characters/test_management.py',
        'src/tests/app/test_character_management_api.py',
        'src/tests/app/test_runtime_config.py',
        'src/tests/app/test_runtime_architecture.py',
        'src/tests/app/test_gateway_route_policy.py',
        'src/tests/app/test_gateway_scaling_lifecycle.py',
        'src/tests/app/test_live_voice_runtime_offload.py',
        'src/tests/app/test_live_voice_execution_lane.py',
        'src/tests/app/test_durable_feature_worker.py',
        'src/tests/app/test_qwen_http_gateway.py',
        'src/tests/app/test_chat_execution_capacity.py',
        'src/tests/api/gateway/test_gateway_runtime_baseline.py',
        'src/tests/api/gateway/test_gateway_foundation.py',
        'src/tests/unit/test_import_isolation.py',
        'src/tests/persistence/test_sqlite_runtime_retirement.py',
        'src/tests/unit/test_tts_http_url_normalization.py',
    ),
    'postgresql': (
        'src/tests/persistence/test_execution_integration.py',
        'src/tests/persistence/test_chat_atomic_scaling_integration.py',
        'src/tests/persistence/test_chat_execution_ownership_integration.py',
        'src/tests/persistence/test_memory_job_execution_integration.py',
        'src/tests/persistence/test_gateway_readiness_integration.py',
        'src/tests/persistence/test_active_feature_factories_integration.py',
        'src/tests/persistence/test_runtime_retirement_integration.py',
        'src/tests/persistence/test_asset_streaming.py',
        'src/tests/persistence/test_rpg_campaign_genesis_integration.py',
    ),
    'multiprocess': ('src/tests/persistence/test_runtime_multiprocess.py',),
    'persistence-all': ('src/tests/persistence',),
}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--group', choices=tuple(GATES), required=True)
    parser.add_argument('--local-disposable', action='store_true')
    args = parser.parse_args()
    env = dict(os.environ, PYTHONPATH=str(ROOT / 'src'))
    if args.group != 'unit':
        url = ('postgresql://omnix_baseline:baseline_disposable@127.0.0.1:16432/omnix_refactor_baseline'
               if args.local_disposable else env.get('OMNIX_TEST_DATABASE_URL', ''))
        if urlsplit(url).path not in {'/omnix_test', '/omnix_refactor_baseline'}:
            parser.error('Integration gates truncate test data; use a disposable omnix_test or omnix_refactor_baseline database')
        env.update(OMNIX_TEST_DATABASE_URL=url, OMNIX_DATABASE_URL=url)
    return subprocess.call([sys.executable, '-m', 'pytest', *GATES[args.group], '-q', '--tb=short'], cwd=ROOT, env=env)


if __name__ == '__main__':
    raise SystemExit(main())