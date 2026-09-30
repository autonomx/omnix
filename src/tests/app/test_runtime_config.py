from dataclasses import FrozenInstanceError

import pytest

from app.runtime import config as runtime
from app.runtime.config import GatewayRole, RuntimeConfig, ServiceEndpoint
from app.runtime.capabilities import RuntimeCapabilities, RuntimeCapability as Capability


def test_defaults_and_explicit_config_are_immutable():
    config = RuntimeConfig.from_environment({})
    assert config.owns_background_runtime and config.allow_local_tts
    with pytest.raises(FrozenInstanceError):
        config.gateway_role = GatewayRole.API
    api = RuntimeConfig(gateway_role=GatewayRole.API, tts=ServiceEndpoint('http://localhost:5101/'))
    assert api.use_remote_tts and not api.allow_local_tts
    assert api.tts.url == 'http://localhost:5101'


@pytest.mark.parametrize('env', [
    {'OMNIX_GATEWAY_BACKGROUND_ROLE': 'standby'},
    {'OMNIX_GATEWAY_BACKGROUND_ROLE': 'api', 'OMNIX_GATEWAY_OWNS_BACKGROUND_RUNTIME': '1'},
    {'OMNIX_GATEWAY_BACKGROUND_ROLE': 'api', 'OMNIX_GATEWAY_ALLOW_LOCAL_TTS': '1'},
    {'OMNIX_GATEWAY_TTS_HTTP': '1'},
    {'OMNIX_GATEWAY_TTS_HTTP': 'maybe'},
    {'OMNIX_TTS_URL': 'file:///tmp/service'},
    {'OMNIX_TTS_URL': 'http://user:secret@example.com'},
    {'OMNIX_TTS_URL': 'http://localhost:invalid'},
    {'OMNIX_WORKER_CUSTOM_URL': 'http://user:secret@example.com'},
    {'OMNIX_GATEWAY_API_ORIGINS': 'http://localhost:5001,http://localhost:5001/'},
    {'OMNIX_GATEWAY_API_ORIGINS': 'https://example.com/path'},
])
def test_invalid_topology_fails_closed(env):
    with pytest.raises(ValueError):
        RuntimeConfig.from_environment(env)


def test_worker_remote_tts_and_required_service_policy():
    config = RuntimeConfig.from_environment({
        'OMNIX_GATEWAY_TTS_HTTP': '1', 'OMNIX_TTS_URL': 'http://localhost:5101',
        'OMNIX_GATEWAY_REQUIRED_WORKERS': 'tts,stt',
    })
    assert config.tts.required and config.use_remote_tts
    assert not config.allow_local_tts
    assert config.required_workers == ('stt', 'tts')


def test_job_priority_aging_configuration_is_bounded():
    assert RuntimeConfig.from_environment({}).job_priority_aging_seconds == 60
    assert RuntimeConfig.from_environment({
        'OMNIX_JOB_PRIORITY_AGING_SECONDS': '15',
    }).job_priority_aging_seconds == 15
    for value in ('0', '86401', 'fast'):
        with pytest.raises(ValueError, match='OMNIX_JOB_PRIORITY_AGING_SECONDS'):
            RuntimeConfig.from_environment({'OMNIX_JOB_PRIORITY_AGING_SECONDS': value})


def test_scheduler_executor_sizes_are_configurable_and_bounded():
    assert RuntimeConfig.from_environment({}).scheduler_thread_workers == 4
    assert RuntimeConfig.from_environment({}).scheduler_process_workers == 2
    configured = RuntimeConfig.from_environment({
        "OMNIX_SCHEDULER_THREAD_WORKERS": "8",
        "OMNIX_SCHEDULER_PROCESS_WORKERS": "3",
    })
    assert configured.scheduler_thread_workers == 8
    assert configured.scheduler_process_workers == 3
    for name, value in (
        ("OMNIX_SCHEDULER_THREAD_WORKERS", "0"),
        ("OMNIX_SCHEDULER_THREAD_WORKERS", "65"),
        ("OMNIX_SCHEDULER_PROCESS_WORKERS", "0"),
        ("OMNIX_SCHEDULER_PROCESS_WORKERS", "17"),
    ):
        with pytest.raises(ValueError, match=name):
            RuntimeConfig.from_environment({name: value})


def test_production_config_cannot_be_reinterpreted_after_binding(monkeypatch):
    config = RuntimeConfig(gateway_role=GatewayRole.API)
    runtime.install_runtime_config(config)
    monkeypatch.setenv('OMNIX_GATEWAY_BACKGROUND_ROLE', 'worker')
    assert runtime.get_runtime_config() is config
    runtime.install_runtime_config(config)
    with pytest.raises(RuntimeError, match='already bound'):
        runtime.install_runtime_config(RuntimeConfig())


def test_unbound_runtime_config_reads_the_typed_environment(monkeypatch):
    monkeypatch.setenv('OMNIX_GATEWAY_BACKGROUND_ROLE', 'api')
    monkeypatch.setenv('OMNIX_TTS_URL', 'http://localhost:5101')

    config = runtime.get_runtime_config()

    assert config.gateway_role is GatewayRole.API
    assert config.use_remote_tts
    assert config.tts is not None and config.tts.url == 'http://localhost:5101'


def test_api_capabilities_exclude_singleton_and_local_gpu_work():
    capabilities = RuntimeCapabilities.from_config(RuntimeConfig(gateway_role=GatewayRole.API))
    assert capabilities.allows(Capability.SERVE_API)
    assert capabilities.allows(Capability.RUN_CHAT_DISPATCH)
    for capability in (Capability.OWN_BACKGROUND_RUNTIME, Capability.RUN_LOCAL_TTS, Capability.RUN_RECOVERY, Capability.RUN_SCHEDULERS):
        with pytest.raises(RuntimeError, match='lacks runtime capabilities'):
            capabilities.require(capability)


def test_scheduler_role_owns_task_scheduling_without_global_background_authority():
    config = RuntimeConfig.from_environment(
        {"OMNIX_GATEWAY_BACKGROUND_ROLE": "scheduler"}
    )
    capabilities = RuntimeCapabilities.from_config(config)
    assert config.runs_schedulers and not config.owns_background_runtime
    assert capabilities.allows(Capability.RUN_SCHEDULERS)
    for capability in (
        Capability.OWN_BACKGROUND_RUNTIME,
        Capability.RUN_RECOVERY,
        Capability.RUN_LOCAL_TTS,
    ):
        with pytest.raises(RuntimeError, match="lacks runtime capabilities"):
            capabilities.require(capability)


def test_url_errors_do_not_echo_credentials():
    with pytest.raises(ValueError) as error:
        ServiceEndpoint('http://private:secret@example.com')
    assert 'secret' not in str(error.value)


def test_worker_discovery_is_an_immutable_normalized_snapshot(monkeypatch):
    config = RuntimeConfig.from_environment({'OMNIX_WORKER_CUSTOM_URL': 'http://LOCALHOST:8000/'})
    monkeypatch.setenv('OMNIX_WORKER_CUSTOM_URL', 'http://other:9000')
    assert config.worker_discovery_environment()['OMNIX_WORKER_CUSTOM_URL'] == 'http://localhost:8000'


def test_migrate_on_start_is_limited_to_local_development_workers():
    from app.production import maybe_apply_migrations_on_start

    calls = []
    assert maybe_apply_migrations_on_start(
        RuntimeConfig(),
        env={"OMNIX_MIGRATE_ON_START": "false"},
        apply_migrations_fn=lambda: calls.append("apply"),
    ) is False
    assert calls == []

    assert maybe_apply_migrations_on_start(
        RuntimeConfig(),
        env={
            "OMNIX_MIGRATE_ON_START": "true",
            "OMNIX_AUTH_MODE": "local",
            "OMNIX_ENV": "development",
        },
        apply_migrations_fn=lambda: calls.append("apply"),
    ) is True
    assert calls == ["apply"]

    unsafe = (
        (RuntimeConfig(gateway_role=GatewayRole.API), {"OMNIX_AUTH_MODE": "local", "OMNIX_ENV": "development"}),
        (RuntimeConfig(), {"OMNIX_AUTH_MODE": "oidc", "OMNIX_ENV": "development"}),
        (RuntimeConfig(), {"OMNIX_AUTH_MODE": "local", "OMNIX_ENV": "production"}),
    )
    for config, values in unsafe:
        with pytest.raises(RuntimeError, match="local-auth development worker"):
            maybe_apply_migrations_on_start(
                config,
                env={"OMNIX_MIGRATE_ON_START": "true", **values},
                apply_migrations_fn=lambda: calls.append("unsafe"),
            )
    assert calls == ["apply"]
