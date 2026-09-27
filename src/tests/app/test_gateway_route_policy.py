"""Ingress and the development proxy share one explicit route contract."""
import importlib.util
import json
from pathlib import Path
import re

ROOT = Path(__file__).resolve().parents[3]
POLICY = json.loads((ROOT / 'deploy/gateway-route-policy.json').read_text(encoding='utf-8'))


def test_generated_ingress_matches_policy():
    spec = importlib.util.spec_from_file_location('render_gateway_ingress', ROOT / 'scripts/render_gateway_ingress.py')
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    assert (ROOT / 'deploy/nginx/omnix.conf').read_text(encoding='utf-8') == module.render(POLICY)
    source = (ROOT / 'src/apps/web/gateway-routing.ts').read_text(encoding='utf-8')
    assert "import routingPolicy from '../../../deploy/gateway-route-policy.json'" in source
    assert 'proxy_next_upstream off;' in module.render(POLICY)
    assert 'proxy_buffering off;' in module.render(POLICY)


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
