"""Ingress and the development proxy share one explicit route contract."""
import importlib.util
import json
from pathlib import Path
import re
import sys

ROOT = Path(__file__).resolve().parents[3]
POLICY = json.loads((ROOT / 'deploy/gateway-route-policy.json').read_text(encoding='utf-8'))


def _renderer():
    spec = importlib.util.spec_from_file_location('render_gateway_ingress', ROOT / 'scripts/render_gateway_ingress.py')
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module  # dataclasses resolve their module by name
    spec.loader.exec_module(module)
    return module


def test_generated_ingress_matches_policy():
    module = _renderer()
    for target, expected in module.rendered_files().items():
        assert target.read_text(encoding='utf-8') == expected, target
    source = (ROOT / 'src/apps/web/gateway-routing.ts').read_text(encoding='utf-8')
    assert "import routingPolicy from '../../../deploy/gateway-route-policy.json'" in source
    assert 'proxy_next_upstream off;' in module.render(POLICY)
    assert 'proxy_buffering off;' in module.render(POLICY)


def test_ingress_hardening():
    module = _renderer()
    plain, secure = module.render(POLICY), module.render(POLICY, tls=module.Tls())
    # The SPA policy allows no eval and no third-party origins; the app is never framed.
    csp = module.SPA_CONTENT_SECURITY_POLICY
    assert "'unsafe-eval'" not in csp and 'http' not in csp.replace("'self'", '')
    assert "frame-ancestors 'none'" in csp and "object-src 'none'" in csp
    # Audio worklets are bundled module files, so scripts load from the app's origin only.
    assert "script-src 'self';" in csp
    assert plain.count('add_header Content-Security-Policy') == 2  # assets and the SPA fallback
    # HSTS only where the listener is HTTPS, which redirects plain HTTP.
    assert 'Strict-Transport-Security' not in plain
    assert 'Strict-Transport-Security' in secure
    assert 'listen 443 ssl;' in secure and 'return 301 https://$host$request_uri;' in secure
    # Login and the API are rate limited per client; excess answers 429.
    assert 'limit_req zone=omnix_auth' in plain and 'limit_req zone=omnix_api' in plain
    assert 'limit_req_status 429;' in plain
    # A client cannot select the worker with the affinity header.
    assert POLICY['external_worker_affinity'] is False
    assert '$http_x_omnix_gateway_affinity' not in plain
    assert plain.count('proxy_set_header X-Omnix-Gateway-Affinity "";') == plain.count('proxy_pass ')


def _megabytes(limit: str) -> int:
    assert limit.endswith('m')
    return int(limit[:-1]) * 1024 * 1024


def test_ingress_body_limits_admit_what_the_gateway_accepts():
    from app.audiobook.extraction import MAX_SOURCE_BYTES
    from app.rpg.worlds.world_bundle import MAX_WORLD_BUNDLE_BYTES
    from app.security.model_service import DEFAULT_MAX_UPLOAD_BYTES

    limits = POLICY['body_limits']
    assert _megabytes(limits['default']) >= DEFAULT_MAX_UPLOAD_BYTES
    assert _megabytes(limits['routes']['^/api/audiobook/projects/[^/]+/source$']) >= MAX_SOURCE_BYTES
    assert _megabytes(limits['routes']['^/api/rpg/worlds/import$']) >= MAX_WORLD_BUNDLE_BYTES
    assert re.fullmatch(next(iter(limits['routes'])), '/api/audiobook/projects/p1/source')


def test_api_route_allowlist_leaves_control_and_unclassified_writes_on_worker():
    chat, reads = re.compile(POLICY['chat_pattern']), re.compile(POLICY['read_pattern'])
    for path in ('/api/chat/sessions', '/api/chat/sessions/id/messages/stream', '/api/chat/sessions/id/attachments'):
        assert chat.fullmatch(path)
    for path in ('/events', '/api/jobs/id', '/api/trading/quotes'):
        assert reads.fullmatch(path)
    for path in ('/api/jobs/id/cancel', '/api/trading/orders', '/api/rpg/sessions', '/ready', '/health'):
        assert not chat.fullmatch(path) and not reads.fullmatch(path)
    assert POLICY['read_methods'] == ['GET', 'HEAD']
    assert POLICY['default_target'] == 'worker'
    assert POLICY['live_call_websocket_path'] in POLICY['speech_paths']
    assert POLICY['call_id_header'] == 'x-omnix-call-id'
    assert POLICY['call_affinity_cookie'] == 'omnix_call_affinity'


def test_live_call_ingress_uses_consistent_replica_affinity():
    rendered = (ROOT / 'deploy/nginx/omnix.conf').read_text(encoding='utf-8')
    assert 'hash $omnix_call_affinity_key consistent;' in rendered
    assert '~^1:.+:/api/tts/live\\-call/websocket$ omnix_live_api;' in rendered
    assert '~^1:.+:POST:/api/chat/sessions/[^/]+/messages/stream$ omnix_live_api;' in rendered
    assert '~^1::POST:/api/chat/sessions/[^/]+/messages/stream$ omnix_worker;' in rendered
    assert '$omnix_call_affinity_key:$request_method:$uri' in rendered
