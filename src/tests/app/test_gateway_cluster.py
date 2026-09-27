from __future__ import annotations

import io
from pathlib import Path
import runpy
from types import SimpleNamespace

import pytest


cluster = runpy.run_path(str(Path(__file__).resolve().parents[3] / 'scripts/gateway_cluster.py'))


def test_replica_ports_validate_bounds():
    assert cluster['replica_ports'](8000, 2) == [8001, 8002]
    assert cluster['replica_ports'](8000, 0) == []
    for port, count in [(8000, -1), (8000, 9), (65535, 1), (0, 0)]:
        with pytest.raises(ValueError):
            cluster['replica_ports'](port, count)


def test_api_children_have_explicit_narrow_role(monkeypatch):
    monkeypatch.setenv('OMNIX_GATEWAY_BACKGROUND_ROLE', 'worker')
    monkeypatch.setenv('OMNIX_DATABASE_URL', 'inherited-test-value')
    child = cluster['child_environment']('api')
    assert child['OMNIX_GATEWAY_BACKGROUND_ROLE'] == 'api'
    assert child['OMNIX_TTS_STARTUP_WARMUP'] == '0'
    assert child['OMNIX_DATABASE_URL'] == 'inherited-test-value'
    assert cluster['child_environment']('worker')['OMNIX_GATEWAY_BACKGROUND_ROLE'] == 'worker'


def test_stop_requests_all_children_before_waiting():
    children = []
    calls = []
    class Control(io.StringIO):
        def close(self):
            calls.append(self.getvalue())
            super().close()
    def wait(timeout):
        assert calls == ['stop\n', 'stop\n']
        return 0
    children = [SimpleNamespace(stdin=Control(), wait=wait) for _ in range(2)]
    cluster['stop_children'](children)


def test_native_runtime_import_defers_database_and_gateway():
    import os
    import subprocess
    import sys
    env = dict(os.environ, PYTHONPATH=str(Path(__file__).resolve().parents[2]))
    result = subprocess.run([sys.executable, '-c',
        "import app.gateway.runtime_app, sys; "
        "assert 'app.gateway.main' not in sys.modules; "
        "assert 'app.persistence.startup' not in sys.modules"],
        env=env, capture_output=True, text=True, timeout=30)
    assert result.returncode == 0, result.stderr


def test_native_composition_uses_process_owned_job_store(monkeypatch):
    from fastapi import FastAPI
    from app.gateway import runtime_app
    app = FastAPI()
    store = object()
    app.state.runtime_services = SimpleNamespace(jobs=store)
    monkeypatch.setattr(runtime_app, 'create_production_app', lambda: app)
    assert runtime_app.create_runtime_app() is app
    assert sum(getattr(route, 'path', None) == '/events' for route in app.routes) == 1


def test_private_shutdown_reader_does_not_block_numpy_initialization():
    import os
    import queue
    import subprocess
    import sys
    import threading
    source = (
        "import runpy,sys,time; from types import SimpleNamespace; "
        "cluster=runpy.run_path(sys.argv[1]); server=SimpleNamespace(should_exit=False); "
        "cluster['watch_parent_stdin'](server); import numpy; print('ready',flush=True); "
        "exec('while not server.should_exit: time.sleep(.05)')"
    )
    child = subprocess.Popen([sys.executable, '-c', source,
        str(Path(__file__).resolve().parents[3] / 'scripts/gateway_cluster.py')],
        stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True,
        creationflags=getattr(subprocess, 'CREATE_NO_WINDOW', 0) if os.name == 'nt' else 0)
    received = queue.Queue()
    threading.Thread(target=lambda: received.put(child.stdout.readline()), daemon=True).start()
    try:
        assert received.get(timeout=15).strip() == 'ready'
        child.stdin.write('stop\n')
        child.stdin.flush()
        child.wait(10)
        assert child.returncode == 0, child.stderr.read()
    finally:
        if child.poll() is None:
            child.kill()
            child.wait(5)
        child.stdin.close()
        child.stdout.close()
        child.stderr.close()
