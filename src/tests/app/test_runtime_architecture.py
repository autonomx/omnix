"""Negative ownership, lifecycle, diagnostics and compatibility growth gates."""
import asyncio
from contextlib import contextmanager
import json
from pathlib import Path
from types import SimpleNamespace

import pytest

from app.gateway.background_runtime import (
    BackgroundWorker, BackgroundOwnershipUnavailable, GatewayBackgroundRuntime,
    register_background_worker,
)
from app.gateway.feature_registry import FeatureLifecycle, register_feature_lifecycle
from app.gateway.lifecycle import gateway_lifespan
from app.runtime.config import RuntimeConfig, GatewayRole
from app.runtime.capabilities import RuntimeCapabilities, RuntimeCapability


def application(config):
    return SimpleNamespace(state=SimpleNamespace(
        runtime_config=config, runtime_capabilities=RuntimeCapabilities.from_config(config),
        feature_lifecycles=[], runtime_started=False,
    ), router=SimpleNamespace(on_startup=[], on_shutdown=[]))


def test_api_rejects_worker_only_feature_lifecycle():
    app = application(RuntimeConfig(gateway_role=GatewayRole.API))
    with pytest.raises(RuntimeError, match='lacks runtime capabilities'):
        register_feature_lifecycle(app, FeatureLifecycle('scheduler', requires=frozenset({RuntimeCapability.RUN_SCHEDULERS})))
    assert app.state.feature_lifecycles == []


def test_gateway_rejects_undeclared_startup_hooks_before_api_can_run_them(monkeypatch):
    from app.gateway import feature_registry
    app = application(RuntimeConfig(gateway_role=GatewayRole.API))
    def registrar(gateway):
        gateway.router.on_startup.append(lambda: pytest.fail('undeclared worker startup ran'))
    monkeypatch.setattr(feature_registry, 'FEATURES', (feature_registry.GatewayFeature('test.feature', 'register'),))
    monkeypatch.setattr(feature_registry, 'import_module', lambda _: SimpleNamespace(register=registrar))
    with pytest.raises(RuntimeError, match='must declare lifecycle callbacks'):
        feature_registry.register_gateway_features(app)
    assert not getattr(app.state, 'features_registered', False)


def test_api_lifespan_never_runs_recovery_or_worker_hooks():
    app = application(RuntimeConfig(gateway_role=GatewayRole.API))
    calls = []
    monitor = SimpleNamespace(start=lambda: calls.append('worker'))
    register_background_worker(app, BackgroundWorker('worker', monitor, (monitor.start,), ()))
    with pytest.raises(BackgroundOwnershipUnavailable):
        monitor.start()

    async def run():
        async with gateway_lifespan(app, get_chat_store=object, get_job_store=object,
                                    recover_jobs=lambda *_: pytest.fail('API attempted recovery')):
            assert app.state.runtime_started
    asyncio.run(run())
    assert calls == []


def test_feature_startup_shutdown_order_and_partial_failure():
    app = application(RuntimeConfig())
    calls = []
    def fail():
        calls.append('two:start')
        raise ValueError('failed startup')
    register_feature_lifecycle(app, FeatureLifecycle('one', (lambda: calls.append('one:start'),), (lambda: calls.append('one:stop'),)))
    register_feature_lifecycle(app, FeatureLifecycle('two', (fail,), (lambda: calls.append('two:stop'),)))
    async def run():
        with pytest.raises(ValueError):
            async with gateway_lifespan(app, get_chat_store=object, get_job_store=object, recover_jobs=lambda *_: 0):
                pytest.fail('partial startup became ready')
    asyncio.run(run())
    assert calls == ['one:start', 'two:start', 'two:stop', 'one:stop']
    assert not app.state.runtime_started


def test_background_connection_loss_stops_workers_and_latches_authority(monkeypatch):
    calls = []
    owner = GatewayBackgroundRuntime(object(), 'test', poll_seconds=.01)
    owner.register('test', object(), (lambda: calls.append('started'),), (lambda: calls.append('stopped'),))
    owner.connection = SimpleNamespace(execute=lambda *_: (_ for _ in ()).throw(OSError('private credentials')))
    owner.healthy = True
    # Startup probes the authority before invoking callbacks.
    with pytest.raises(BackgroundOwnershipUnavailable):
        asyncio.run(owner.startup())
    assert owner.healthy is False
    asyncio.run(owner.shutdown())
    assert calls == ['stopped']
    with pytest.raises(BackgroundOwnershipUnavailable):
        owner.require_live()


def test_runtime_diagnostics_redacts_database_errors_and_reports_api_policy():
    from app.platform.runtime_diagnostics import RequestMetrics, runtime_diagnostics
    app = application(RuntimeConfig(gateway_role=GatewayRole.API))
    app.state.runtime_metrics = RequestMetrics()
    @contextmanager
    def connection():
        raise OSError('postgresql://user:secret@host/database')
        yield
    app.state.runtime_services = SimpleNamespace(jobs=SimpleNamespace(
        database=SimpleNamespace(connection=connection), context=SimpleNamespace(workspace_id='test'),
    ))
    payload = runtime_diagnostics(app).model_dump()
    assert payload['postgresql'] == {'connectivity': False, 'error_class': 'OSError'}
    assert payload['tts']['mode'] == 'worker_routed'
    assert 'secret' not in json.dumps(payload)
    assert payload['background']['owns_lock'] is False


def test_diagnostics_surface_survives_database_loss_without_fallback_reads(monkeypatch):
    from app.gateway.workers import WorkerHealthPayload
    from app.platform import diagnostics
    from app.platform.runtime_diagnostics import RequestMetrics
    app = application(RuntimeConfig(gateway_role=GatewayRole.API))
    app.state.runtime_metrics = RequestMetrics()
    @contextmanager
    def connection():
        raise OSError('postgresql://user:private@host/db')
        yield
    app.state.runtime_services = SimpleNamespace(jobs=SimpleNamespace(
        database=SimpleNamespace(connection=connection), context=SimpleNamespace(workspace_id='test'),
    ))
    monkeypatch.setattr(diagnostics, 'get_worker_health_payload', lambda: WorkerHealthPayload())
    payload = diagnostics.get_runtime_diagnostics_payload(app, model_residency_store_factory=lambda: pytest.fail('retried unavailable persistence'))
    assert payload.runtime.postgresql['connectivity'] is False
    assert payload.runtime.process['gateway_role'] == 'api'
    assert payload.model_residency.status == 'unavailable' and not payload.ok
    assert 'private' not in payload.model_dump_json()


def test_only_legacy_export_can_import_sqlite_and_runtime_installer_cannot_patch_modules():
    import ast
    root = Path(__file__).resolve().parents[2] / 'app'
    sqlite_modules = []
    for path in root.rglob('*.py'):
        tree = ast.parse(path.read_text(encoding='utf-8-sig'))
        if any(isinstance(node, ast.Import) and any(alias.name == 'sqlite3' for alias in node.names)
               or isinstance(node, ast.ImportFrom) and node.module == 'sqlite3' for node in ast.walk(tree)):
            sqlite_modules.append(path.relative_to(root).as_posix())
    assert sqlite_modules == ['persistence/legacy_export.py']
    installer = (root / 'persistence/runtime_install.py').read_text(encoding='utf-8')
    assert 'sys.modules' not in installer and 'setattr(' not in installer and 'sqlite3.connect =' not in installer


def test_compatibility_modules_are_allowlisted():
    root = Path(__file__).resolve().parents[3]
    inventory = json.loads((root / 'docs/architecture/compatibility-inventory.json').read_text(encoding='utf-8'))
    actual = {path.relative_to(root).as_posix() for path in (root / 'src/app').rglob('*_compat.py')}
    assert actual == {item['path'] for item in inventory['modules']}


def test_diagnostics_and_transition_logs_do_not_expose_nested_secrets(caplog):
    import logging
    from app.platform.diagnostics import redact_diagnostics
    from app.runtime.logging import runtime_transition
    value = {'nested': [{'api_key': 'private', 'password': 'private',
                         'endpoint': 'postgresql://user:private@host/db'}]}
    assert 'private' not in json.dumps(redact_diagnostics(value))
    with caplog.at_level(logging.WARNING):
        runtime_transition(logging.getLogger('test.runtime'), component='background_owner',
                           role='worker', transition='authority_lost', error=OSError('private'), level='warning')
    record = caplog.records[-1]
    assert record.error_class == 'OSError' and record.process_role == 'worker'
    assert 'private' not in caplog.text


def test_api_cannot_kick_campaign_genesis_worker(monkeypatch):
    from app import runtime_config
    from app.rpg.session.genesis import async_coordinator as genesis
    runtime_config.install_runtime_config(RuntimeConfig(gateway_role=GatewayRole.API))
    monkeypatch.setattr(genesis, 'campaign_genesis_async_enabled', lambda: True)
    monkeypatch.setattr(genesis.threading, 'Thread', lambda *args, **kwargs: pytest.fail('API started genesis thread'))
    assert genesis.kick_campaign_genesis_worker() is False


def test_genesis_worker_preserves_background_authority_and_stops_after_loss(monkeypatch):
    from app.rpg.session.genesis import async_coordinator as genesis
    from app.persistence.background_authority import require_background_owner
    checks = []
    class Owner:
        capabilities = RuntimeCapabilities.from_config(RuntimeConfig())
        def require_live(self):
            checks.append('checked')
            if len(checks) > 4:
                raise BackgroundOwnershipUnavailable('lost')
    owner = Owner()
    monkeypatch.setattr(genesis, '_background_owner', owner)
    monkeypatch.setattr(genesis, 'campaign_genesis_async_enabled', lambda: True)
    work = []
    def once(**kwargs):
        require_background_owner()
        work.append('ran')
        return {'status': 'completed'}
    monkeypatch.setattr(genesis, 'run_campaign_genesis_worker_once', once)
    try:
        assert genesis.kick_campaign_genesis_worker()
        genesis._worker_thread.join(5)
        assert not genesis._worker_thread.is_alive()
        assert work and not genesis._worker_active
    finally:
        genesis.stop_campaign_genesis_worker()


def test_runtime_tts_success_metrics_only_count_completed_audio(monkeypatch):
    from app.gateway import tts_stream_diagnostics as streams
    monkeypatch.setattr(streams, '_LAST_PCM_SUCCESS_AT', None)
    monkeypatch.setattr(streams, '_COMPLETED_PCM_STREAMS', 0)
    streams.stream_log('test', 'server', 'done_control_sent', sent_frames=0)
    streams.stream_log('test', 'server', 'done_control_sent', sent_frames=1, partial=True)
    assert streams.runtime_stream_snapshot()['completed_pcm_streams'] == 0
    streams.stream_log('test', 'server', 'done_control_sent', sent_frames=1, partial=False)
    metrics = streams.runtime_stream_snapshot()
    assert metrics['completed_pcm_streams'] == 1
    assert metrics['last_successful_pcm_request_age_seconds'] >= 0
