"""Render the supported Nginx configurations from the shared gateway routing policy."""
from __future__ import annotations

import argparse
from dataclasses import dataclass
import json
from pathlib import Path
import re

ROOT = Path(__file__).resolve().parents[1]

# The built web app loads only its own bundle; styles are injected at run time
# (Mantine) and media and avatars come from blob: URLs. Audio worklets are bundled
# module files and Pixi runs without eval (pixi.js/unsafe-eval is imported), so
# scripts stay 'self' only; Pixi decodes images in blob: workers (worker-src).
SPA_CONTENT_SECURITY_POLICY = (
    "default-src 'self'; script-src 'self'; style-src 'self' 'unsafe-inline'; "
    "img-src 'self' data: blob:; media-src 'self' data: blob:; font-src 'self' data:; "
    "connect-src 'self' data: blob:; worker-src 'self' blob:; object-src 'none'; "
    "base-uri 'self'; form-action 'self'; frame-ancestors 'none'"
)
# Matches the gateway's own policy (app.security.headers).
PERMISSIONS_POLICY = "microphone=(self), display-capture=(self), camera=(), geolocation=(), payment=(), usb=()"
HSTS = "max-age=31536000; includeSubDomains"


@dataclass(frozen=True)
class Tls:
    """HTTPS listener with a redirect from the plain-HTTP port."""

    listen: int = 443
    redirect_from: int = 80
    certificate: str = '/etc/nginx/tls/omnix.crt'
    key: str = '/etc/nginx/tls/omnix.key'


def _spa_headers(tls: Tls | None) -> str:
    lines = [
        f'add_header Content-Security-Policy "{SPA_CONTENT_SECURITY_POLICY}" always;',
        'add_header X-Content-Type-Options nosniff always;',
        'add_header Referrer-Policy no-referrer always;',
        'add_header X-Frame-Options DENY always;',
        f'add_header Permissions-Policy "{PERMISSIONS_POLICY}" always;',
    ]
    if tls is not None:
        lines.append(f'add_header Strict-Transport-Security "{HSTS}" always;')
    return ''.join(f'        {line}\n' for line in lines)


def _proxy(*, body_limit: str, rate: str, burst: int, strip_affinity: bool) -> str:
    strip = ('        # Clients cannot pick the worker; only the policy maps above route there.\n'
             '        proxy_set_header X-Omnix-Gateway-Affinity "";\n') if strip_affinity else ''
    return f'''        client_max_body_size {body_limit};
        limit_req zone={rate} burst={burst} nodelay;
        proxy_pass http://$omnix_target;
        proxy_http_version 1.1;
        proxy_set_header Host $host;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
        proxy_set_header X-Omnix-Call-Id $omnix_call_affinity_key;
        proxy_set_header Upgrade $http_upgrade;
        proxy_set_header Connection $omnix_connection;
{strip}        # Preserve one upstream for the whole stream and never replay a write.
        proxy_next_upstream off;
        proxy_buffering off;
        proxy_request_buffering off;
        proxy_read_timeout 3600s;
        add_header X-Omnix-Gateway-Route $omnix_target always;
'''


def render(
    policy: dict,
    *,
    worker: str = '127.0.0.1:8000',
    api: tuple[str, ...] = ('127.0.0.1:8001', '127.0.0.1:8002'),
    speech_on_api: bool = False,
    listen: int = 8080,
    tls: Tls | None = None,
) -> str:
    api_servers = '\n'.join(f'    server {address};' for address in api)
    chat = policy['chat_pattern']
    reads = policy['read_pattern'][1:]
    speech = '|'.join(
        re.escape(path)
        for path in policy['speech_paths']
        if path != policy['live_call_websocket_path']
    )
    live_websocket = re.escape(policy['live_call_websocket_path'])
    live_chat_pattern = policy['live_chat_pattern']
    live_chat = live_chat_pattern.removeprefix('^').removesuffix('$')
    call_id_header = policy['call_id_header']
    call_affinity_cookie = policy['call_affinity_cookie']
    methods = '|'.join(policy['read_methods'])
    limits = policy['rate_limits']
    bodies = policy['body_limits']
    trusted_affinity = bool(policy['external_worker_affinity'])
    affinity_variable = '$http_' + policy['worker_affinity_header'].replace('-', '_')
    target_map = (
        f'map {affinity_variable} $omnix_target {{\n'
        '    default $omnix_speech_target;\n'
        '    worker omnix_worker;\n'
        '}'
        if trusted_affinity else
        '# External requests cannot select the worker (policy external_worker_affinity=false).\n'
        'map $omnix_speech_target $omnix_target { default $omnix_speech_target; }'
    )

    def proxy(body_limit: str, zone: str) -> str:
        return _proxy(body_limit=body_limit, rate=f'omnix_{zone}', burst=int(limits[zone]['burst']),
                      strip_affinity=not trusted_affinity)

    upload_locations = ''.join(
        f'    location ~ {pattern} {{\n{proxy(limit, "api")}    }}\n'
        for pattern, limit in bodies['routes'].items()
    )
    headers = _spa_headers(tls)
    if tls is None:
        listener = f'    listen {listen};\n'
        redirect = ''
    else:
        listener = (
            f'    listen {tls.listen} ssl;\n'
            '    http2 on;\n'
            f'    ssl_certificate {tls.certificate};\n'
            f'    ssl_certificate_key {tls.key};\n'
            '    ssl_protocols TLSv1.2 TLSv1.3;\n'
            '    ssl_prefer_server_ciphers off;\n'
            '    ssl_session_cache shared:omnix_tls:10m;\n'
            '    ssl_session_timeout 1d;\n'
        )
        redirect = (
            'server {\n'
            f'    listen {tls.redirect_from};\n'
            '    return 301 https://$host$request_uri;\n'
            '}\n'
        )
    return f'''# Generated by scripts/render_gateway_ingress.py; install inside Nginx http {{}}.
# Replace addresses, certificate paths and the static web root for your deployment.
upstream omnix_worker {{ server {worker}; keepalive 32; }}
upstream omnix_api {{
    least_conn;
{api_servers}
    keepalive 64;
}}
map $http_{call_id_header.replace('-', '_')} $omnix_call_affinity_key {{
    default $http_{call_id_header.replace('-', '_')};
    "" $cookie_{call_affinity_cookie};
}}
upstream omnix_live_api {{
    hash $omnix_call_affinity_key consistent;
{api_servers}
    keepalive 64;
}}
map $http_upgrade $omnix_connection {{ default upgrade; '' ''; }}
# Change to 1 only when EVERY API process uses the shared remote TTS service.
map $host $omnix_speech_on_api {{ default {1 if speech_on_api else 0}; }}
map $uri $omnix_chat_target {{
    default omnix_worker;
    ~{chat} omnix_api;
}}
map "$request_method:$uri" $omnix_read_target {{
    default $omnix_chat_target;
    ~^(?:{methods}):{reads} omnix_api;
}}
map "$omnix_speech_on_api:$omnix_call_affinity_key:$request_method:$uri" $omnix_live_chat_target {{
    default $omnix_read_target;
    ~^0:.*:POST:{live_chat}$ omnix_worker;
    ~^1::POST:{live_chat}$ omnix_worker;
    ~^1:.+:POST:{live_chat}$ omnix_live_api;
}}
map "$omnix_speech_on_api:$omnix_call_affinity_key:$uri" $omnix_speech_target {{
    default $omnix_live_chat_target;
    ~^1:.+:{live_websocket}$ omnix_live_api;
    ~^1:.*:(?:{speech})$ omnix_api;
}}
{target_map}
# Per-client request rates (behind another proxy, set real_ip so this is the client).
limit_req_zone $binary_remote_addr zone=omnix_auth:10m rate={limits['auth']['rate']};
limit_req_zone $binary_remote_addr zone=omnix_api:10m rate={limits['api']['rate']};
limit_req_status 429;
{redirect}server {{
{listener}    server_tokens off;
    root /srv/omnix/web;
    location ~ {limits['auth']['pattern']} {{
{proxy(bodies['auth'], 'auth')}    }}
{upload_locations}    location ~ ^/(?:api(?:/|$)|events$|health$|ready$) {{
{proxy(bodies['default'], 'api')}    }}
    # Content-hashed build output: cache for a year.
    location /assets/ {{
{headers}        add_header Cache-Control "public, max-age=31536000, immutable" always;
        try_files $uri =404;
    }}
    location / {{
{headers}        add_header Cache-Control "no-cache" always;
        try_files $uri $uri/ /index.html;
    }}
}}
'''


def rendered_files() -> dict[Path, str]:
    policy = json.loads((ROOT / 'deploy/gateway-route-policy.json').read_text(encoding='utf-8'))
    return {
        # Production example: HTTPS on 443 with a redirect from 80.
        ROOT / 'deploy/nginx/omnix.conf': render(policy, tls=Tls()),
        # WP-6.8 multi-host topology: every API replica uses the remote TTS.
        ROOT / 'deploy/multihost/nginx.conf': render(
            policy,
            worker='gateway-worker:8000',
            api=('api-1:8000', 'api-2:8000'),
            speech_on_api=True,
        ),
        # WP-11.2 Compose: the web image routes to the gateway worker and the
        # `api` service, whose replicas Docker DNS resolves when Nginx starts.
        ROOT / 'deploy/docker/nginx/omnix.conf': render(
            policy,
            worker='gateway-worker:8000',
            api=('api:8000',),
        ),
        # The same with HTTPS on 8443 (redirect from 8080): mount it over the
        # default and provide /etc/nginx/tls/omnix.{crt,key}.
        ROOT / 'deploy/docker/nginx/omnix-tls.conf': render(
            policy,
            worker='gateway-worker:8000',
            api=('api:8000',),
            tls=Tls(listen=8443, redirect_from=8080),
        ),
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--check', action='store_true')
    args = parser.parse_args()
    for target, expected in rendered_files().items():
        if args.check:
            if not target.exists() or target.read_text(encoding='utf-8') != expected:
                parser.error(f'{target.relative_to(ROOT)} differs from routing policy; run scripts/render_gateway_ingress.py')
        else:
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_text(expected, encoding='utf-8', newline='\n')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
