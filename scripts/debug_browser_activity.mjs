import { chromium } from 'playwright';
import { createWriteStream, mkdirSync } from 'node:fs';
import { resolve } from 'node:path';

const cdpUrl = process.env.CDP_URL || 'http://127.0.0.1:9222';
const targetUrl = process.env.TARGET_URL || '';
const durationMs = Number(process.env.DURATION_MS || 180_000);
const slowRequestMs = Number(process.env.SLOW_REQUEST_MS || 5_000);

const logDir = resolve('resources', 'logs');
mkdirSync(logDir, { recursive: true });

const stamp = new Date().toISOString().replace(/[:.]/g, '-');
const logPath = resolve(logDir, `browser-activity-${stamp}.jsonl`);
const stream = createWriteStream(logPath, { flags: 'a' });

const pendingRequests = new Map();
const attachedPages = new WeakSet();

function clean(value) {
  if (value instanceof Error) {
    return { name: value.name, message: value.message, stack: value.stack };
  }
  if (typeof value === 'bigint') return value.toString();
  return value;
}

function write(event, data = {}) {
  stream.write(`${JSON.stringify({ ts: new Date().toISOString(), event, ...data }, (_key, value) => clean(value))}\n`);
}

async function attachPage(page) {
  if (attachedPages.has(page)) return;
  attachedPages.add(page);

  const pageId = page.guid || Math.random().toString(36).slice(2);
  write('page.attached', { pageId, url: page.url() });

  page.on('close', () => write('page.close', { pageId, url: page.url() }));
  page.on('crash', () => write('page.crash', { pageId, url: page.url() }));
  page.on('domcontentloaded', () => write('page.domcontentloaded', { pageId, url: page.url() }));
  page.on('load', () => write('page.load', { pageId, url: page.url() }));
  page.on('pageerror', (error) => write('page.error', { pageId, url: page.url(), error }));
  page.on('console', (message) => {
    write('console', {
      pageId,
      url: page.url(),
      type: message.type(),
      text: message.text(),
      location: message.location(),
    });
  });
  page.on('request', (request) => {
    const id = `${Date.now()}:${Math.random().toString(36).slice(2)}`;
    pendingRequests.set(request, {
      id,
      startedAt: Date.now(),
      url: request.url(),
      method: request.method(),
      resourceType: request.resourceType(),
    });
    write('request.start', {
      pageId,
      id,
      method: request.method(),
      resourceType: request.resourceType(),
      url: request.url(),
    });
  });
  page.on('response', async (response) => {
    const request = response.request();
    const tracked = pendingRequests.get(request);
    write('request.response', {
      pageId,
      id: tracked?.id,
      status: response.status(),
      ok: response.ok(),
      contentLength: await response.headerValue('content-length').catch(() => null),
      contentType: await response.headerValue('content-type').catch(() => null),
      url: response.url(),
      elapsedMs: tracked ? Date.now() - tracked.startedAt : undefined,
    });
  });
  page.on('requestfinished', (request) => {
    const tracked = pendingRequests.get(request);
    pendingRequests.delete(request);
    write('request.finish', {
      pageId,
      id: tracked?.id,
      url: request.url(),
      elapsedMs: tracked ? Date.now() - tracked.startedAt : undefined,
    });
  });
  page.on('requestfailed', (request) => {
    const tracked = pendingRequests.get(request);
    pendingRequests.delete(request);
    write('request.failed', {
      pageId,
      id: tracked?.id,
      method: request.method(),
      resourceType: request.resourceType(),
      url: request.url(),
      failure: request.failure(),
      elapsedMs: tracked ? Date.now() - tracked.startedAt : undefined,
    });
  });
  page.on('websocket', (socket) => {
    write('websocket.open', { pageId, url: socket.url() });
    socket.on('framereceived', (frame) => write('websocket.frame.received', { pageId, url: socket.url(), bytes: frame.payload.length }));
    socket.on('framesent', (frame) => write('websocket.frame.sent', { pageId, url: socket.url(), bytes: frame.payload.length }));
    socket.on('close', () => write('websocket.close', { pageId, url: socket.url() }));
  });

  const session = await page.context().newCDPSession(page).catch((error) => {
    write('cdp.attach.failed', { pageId, url: page.url(), error });
    return null;
  });
  if (session) {
    await Promise.allSettled([
      session.send('Log.enable'),
      session.send('Runtime.enable'),
      session.send('Page.enable'),
    ]);
    session.on('Log.entryAdded', ({ entry }) => write('cdp.log', { pageId, entry }));
    session.on('Runtime.exceptionThrown', ({ exceptionDetails }) => write('cdp.exception', { pageId, exceptionDetails }));
    session.on('Page.frameNavigated', ({ frame }) => write('cdp.frameNavigated', { pageId, frameUrl: frame.url, frameId: frame.id }));
    session.on('Inspector.targetCrashed', () => write('cdp.targetCrashed', { pageId, url: page.url() }));
  }
}

function writeSlowRequests() {
  const now = Date.now();
  for (const item of pendingRequests.values()) {
    const elapsedMs = now - item.startedAt;
    if (elapsedMs >= slowRequestMs) {
      write('request.pending.slow', { ...item, elapsedMs });
    }
  }
}

const browser = await chromium.connectOverCDP(cdpUrl);
write('browser.connected', { cdpUrl, version: browser.version() });

for (const context of browser.contexts()) {
  context.on('page', (page) => void attachPage(page));
  for (const page of context.pages()) await attachPage(page);
}

const firstContext = browser.contexts()[0] || await browser.newContext();
let page = firstContext.pages().find((candidate) => candidate.url().startsWith('http')) || firstContext.pages()[0];
if (!page) page = await firstContext.newPage();
await attachPage(page);

if (targetUrl) {
  write('navigate.start', { targetUrl });
  await page.goto(targetUrl, { waitUntil: 'domcontentloaded', timeout: 30_000 }).catch((error) => {
    write('navigate.failed', { targetUrl, error });
  });
}

write('capture.started', { logPath, durationMs, slowRequestMs });
const heartbeat = setInterval(() => {
  write('heartbeat', {
    pages: browser.contexts().flatMap((context) => context.pages().map((candidate) => candidate.url())),
    pendingRequests: pendingRequests.size,
  });
  writeSlowRequests();
}, 5_000);

await new Promise((resolveDone) => {
  const done = () => resolveDone();
  setTimeout(done, durationMs);
  process.once('SIGINT', done);
  process.once('SIGTERM', done);
});

clearInterval(heartbeat);
writeSlowRequests();
write('capture.finished', { pendingRequests: pendingRequests.size });
await browser.close().catch(() => {});
stream.end();
console.log(logPath);
