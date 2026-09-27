import { existsSync, readFileSync } from 'node:fs';
import type { IncomingMessage } from 'node:http';
import type { Duplex } from 'node:stream';
import { resolve } from 'node:path';
import type { Plugin, ProxyOptions, ViteDevServer } from 'vite';

const PREFIX = '/__omnix_gateway_replica_';
const CHAT = /^\/api\/chat\/sessions(?:\/[^/]+(?:\/(?:attachments|messages(?:\/stream)?))?)?$/u;
const SPEECH = new Set(['/api/tts/stream/websocket', '/api/tts/stream/server-sent-events']);
const READS = /^(?:\/events|\/api\/jobs(?:\/[^/]+)?|\/api\/trading\/(?:bars|quotes))$/u;

function origin(value: string): string {
  const url = new URL(value);
  if (!['http:', 'https:'].includes(url.protocol) || url.username || url.password
    || url.pathname !== '/' || url.search || url.hash) {
    throw new Error('Gateway targets must be HTTP(S) origins without credentials or paths');
  }
  return url.origin;
}

export function resolveApiOrigins(worker: string, repositoryRoot: string, env = process.env): string[] {
  if (env.OMNIX_GATEWAY_API_ORIGINS !== undefined) {
    const targets = env.OMNIX_GATEWAY_API_ORIGINS.split(',').map((s) => s.trim()).filter(Boolean).map(origin);
    if (targets.length > 8 || new Set(targets).size !== targets.length || targets.includes(origin(worker))) {
      throw new Error('Configure at most eight distinct API origins separate from the worker');
    }
    return targets;
  }
  // Explicit gateway overrides (including isolated E2E servers) remain single target.
  if (env.VITE_GATEWAY_ORIGIN?.trim() || env.OMNIX_E2E22_GATEWAY_URL?.trim()) return [];
  const path = resolve(repositoryRoot, 'resources/data/gateway-deployment.json');
  const count: unknown = env.OMNIX_GATEWAY_API_REPLICAS !== undefined
    ? Number(env.OMNIX_GATEWAY_API_REPLICAS)
    : existsSync(path) ? JSON.parse(readFileSync(path, 'utf8')).api_replicas ?? 0 : 0;
  if (typeof count !== 'number' || !Number.isInteger(count) || count < 0 || count > 8) {
    throw new Error('Gateway API replica count must be an integer from zero to eight');
  }
  const base = new URL(origin(worker));
  if (!['localhost', '127.0.0.1', '[::1]'].includes(base.hostname)) return [];
  const port = Number(base.port || (base.protocol === 'https:' ? 443 : 80));
  if (port + count > 65535) throw new Error('Gateway replica ports exceed the valid range');
  return Array.from({ length: count }, (_, index) => {
    const target = new URL(base);
    target.port = String(port + index + 1);
    return target.origin;
  });
}

export function canUseApi(req: Pick<IncomingMessage, 'url' | 'method' | 'headers'>): boolean {
  if (req.headers['x-omnix-gateway-affinity'] === 'worker') return false;
  const path = (req.url ?? '').split('?')[0];
  return CHAT.test(path) || SPEECH.has(path)
    || (['GET', 'HEAD'].includes(req.method ?? 'GET') && READS.test(path));
}

export function gatewayRouting(worker: string, replicas: string[]): {
  plugin: Plugin; proxy: Record<string, ProxyOptions>;
} {
  let cursor = 0;
  const proxyOptions = (target: string, label: string, prefix?: string): ProxyOptions => ({
    target, changeOrigin: true, ws: true,
    ...(prefix ? { rewrite: (url: string) => url.slice(prefix.length) } : {}),
    configure(proxy) {
      proxy.on('proxyRes', (upstream) => {
        upstream.headers['x-omnix-gateway-route'] = label;
      });
      proxy.on('proxyReqWs', (upstream) => {
        upstream.once('upgrade', (response) => {
          response.headers['x-omnix-gateway-route'] = label;
        });
      });
      proxy.on('proxyReq', (upstream, _req, res) => {
        // Preserve SSE cancellation: closing the downstream must close its upstream.
        const cancel = () => { if (!res.writableEnded) upstream.destroy(); };
        res.once('close', cancel);
        res.once('finish', () => res.off('close', cancel));
      });
    },
  });
  const proxy: Record<string, ProxyOptions> = {};
  replicas.forEach((target, index) => {
    const prefix = `${PREFIX}${index}`;
    proxy[`^${prefix}/`] = proxyOptions(origin(target), `api-${index + 1}`, prefix);
  });
  proxy['^/(?:api(?:/|$)|events(?:\\?|$)|health(?:\\?|$)|ready(?:\\?|$))'] = proxyOptions(origin(worker), 'worker');
  const install = (server: Pick<ViteDevServer, 'middlewares' | 'httpServer' | 'config'>) => {
    const route = (req: IncomingMessage) => {
      if (replicas.length && canUseApi(req)) {
        const index = cursor++ % replicas.length;
        req.url = `${PREFIX}${index}${req.url}`;
        return index;
      }
      return undefined;
    };
    server.middlewares.use((req, res, next) => {
      if (req.url?.startsWith(PREFIX)) {
        res.writeHead(404).end();
        return;
      }
      route(req);
      next();
    });
    // Upgrade requests bypass Connect. Select before Vite's proxy listener runs;
    // its fixed target then owns the connection for its entire lifetime.
    const upgrade = (req: IncomingMessage, socket: Duplex) => {
      if (req.url?.startsWith(PREFIX)) {
        req.url = '/__omnix_gateway_rejected';
        socket.end('HTTP/1.1 404 Not Found\r\nConnection: close\r\n\r\n');
        return;
      }
      const path = req.url;
      const index = route(req);
      if (index !== undefined) server.config.logger.info(`Gateway WebSocket ${path?.split('?')[0]} -> api-${index + 1}`);
    };
    server.httpServer?.prependListener('upgrade', upgrade);
    server.httpServer?.once('close', () => server.httpServer?.off('upgrade', upgrade));
  };
  return { proxy, plugin: {
    name: 'omnix-gateway-replica-routing',
    configureServer: install,
    configurePreviewServer: install,
  } };
}
