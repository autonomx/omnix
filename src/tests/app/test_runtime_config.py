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


def test_production_config_cannot_be_reinterpreted_after_binding(monkeypatch):
    config = RuntimeConfig(gateway_role=GatewayRole.API)
    runtime.install_runtime_config(config)
    monkeypatch.setenv('OMNIX_GATEWAY_BACKGROUND_ROLE', 'worker')
    assert runtime.get_runtime_config() is config
    runtime.install_runtime_config(config)
    with pytest.raises(RuntimeError, match='already bound'):
        runtime.install_runtime_config(RuntimeConfig())


def test_api_capabilities_exclude_singleton_and_local_gpu_work():
    capabilities = RuntimeCapabilities.from_config(RuntimeConfig(gateway_role=GatewayRole.API))
    assert capabilities.allows(Capability.SERVE_API)
    assert capabilities.allows(Capability.RUN_CHAT_DISPATCH)
    for capability in (Capability.OWN_BACKGROUND_RUNTIME, Capability.RUN_LOCAL_TTS, Capability.RUN_RECOVERY, Capability.RUN_SCHEDULERS):
        with pytest.raises(RuntimeError, match='lacks runtime capabilities'):
            capabilities.require(capability)


def test_url_errors_do_not_echo_credentials():
    with pytest.raises(ValueError) as error:
        ServiceEndpoint('http://private:secret@example.com')
    assert 'secret' not in str(error.value)


def test_worker_discovery_is_an_immutable_normalized_snapshot(monkeypatch):
    config = RuntimeConfig.from_environment({'OMNIX_WORKER_CUSTOM_URL': 'http://LOCALHOST:8000/'})
    monkeypatch.setenv('OMNIX_WORKER_CUSTOM_URL', 'http://other:9000')
    assert config.worker_discovery_environment()['OMNIX_WORKER_CUSTOM_URL'] == 'http://localhost:8000'
