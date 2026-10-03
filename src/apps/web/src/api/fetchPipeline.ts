/**
 * One fetch pipeline for the browser (WP-9.2).
 *
 * Features used to replace `window.fetch` and restore a reference captured at
 * install time, so disposing one wrapper could drop the wrappers installed
 * after it. Now a middleware registers with `registerFetchMiddleware` and gets
 * a function that removes it, in any order. This module is the only code that
 * assigns `window.fetch`: it installs one dispatcher that runs
 *
 *   feature middlewares (newest first) -> transport middlewares -> base fetch
 *
 * Feature middleware may rewrite a request (for example to a direct gateway
 * origin) before the transport layer (the view firewall: workspace scope,
 * client and CSRF headers, request ids, 401 handling) sees it.
 */

export type FetchNext = (input: RequestInfo | URL, init?: RequestInit) => Promise<Response>;
export type FetchMiddleware = (input: RequestInfo | URL, init: RequestInit | undefined, next: FetchNext) => Promise<Response>;

type Layer = 'feature' | 'transport';

interface Entry {
  readonly name: string;
  readonly layer: Layer;
  readonly middleware: FetchMiddleware;
}

let entries: Entry[] = [];
let base: typeof fetch | null = null;
let dispatcher: typeof fetch | null = null;

function chain(): Entry[] {
  const features = entries.filter((entry) => entry.layer === 'feature').reverse();
  const transport = entries.filter((entry) => entry.layer === 'transport').reverse();
  return [...features, ...transport];
}

function run(ordered: readonly Entry[], input: RequestInfo | URL, init?: RequestInit): Promise<Response> {
  const terminal = base ?? fetch;
  const step = (index: number): FetchNext => (nextInput, nextInit) => (
    index < ordered.length
      ? ordered[index].middleware(nextInput, nextInit, step(index + 1))
      : terminal(nextInput, nextInit)
  );
  return step(0)(input, init);
}

function dispatch(input: RequestInfo | URL, init?: RequestInit): Promise<Response> {
  return run(chain(), input, init);
}

function ensureInstalled(): void {
  if (typeof window === 'undefined' || typeof window.fetch !== 'function') return;
  if (dispatcher && window.fetch === dispatcher) return;
  // First use, or something (a test stub) replaced fetch: run on top of it.
  base = window.fetch.bind(window);
  dispatcher = dispatch as typeof fetch;
  // The one place that sets window.fetch: the pipeline's dispatcher.
  // eslint-disable-next-line no-restricted-syntax
  window.fetch = dispatcher;
}

/** Add a middleware; the returned function removes it (idempotent). */
export function registerFetchMiddleware(
  name: string,
  middleware: FetchMiddleware,
  options: { layer?: Layer } = {},
): () => void {
  const entry: Entry = { name, layer: options.layer ?? 'feature', middleware };
  entries = [...entries, entry];
  ensureInstalled();
  return () => {
    entries = entries.filter((candidate) => candidate !== entry);
  };
}

/**
 * The chain below a named middleware: for a feature's own requests, which must
 * not pass through itself (or newer middleware) but still get the transport
 * layer. Before the middleware is registered, or after it is removed, this is
 * the whole chain.
 */
export function fetchBelow(name: string): FetchNext {
  return (input, init) => {
    ensureInstalled();
    const ordered = chain();
    const position = ordered.findIndex((entry) => entry.name === name);
    return run(position < 0 ? ordered : ordered.slice(position + 1), input, init);
  };
}

/** The fetch underneath every middleware (for calls that must skip them). */
export function baseFetch(input: RequestInfo | URL, init?: RequestInit): Promise<Response> {
  ensureInstalled();
  return (base ?? fetch)(input, init);
}

export function activeFetchMiddlewares(): readonly string[] {
  return chain().map((entry) => entry.name);
}

/** Remove every middleware and put the base fetch back (tests). */
export function resetFetchPipelineForTests(): void {
  // eslint-disable-next-line no-restricted-syntax -- tests restore the base fetch
  if (typeof window !== 'undefined' && dispatcher && window.fetch === dispatcher && base) window.fetch = base;
  entries = [];
  base = null;
  dispatcher = null;
}
