import { DisposableStore, type Disposable, type ModuleRuntimeContext } from './moduleRuntime';

export type { ModuleRuntimeContext } from './moduleRuntime';
import { moduleManifest, type OmnixModuleId } from './modules';

/**
 * Browser-side runtime of the active workspace (WP-9.1).
 *
 * Entering a workspace activates its runtime; leaving it disposes it. Every
 * initializer returns a cleanup that goes into the workspace's store, so
 * listeners, observers, timers, fetch middleware and client patches do not
 * outlive the route. Each module's manifest provides its runtime, loaded lazily, so Chat does not
 * boot trading, voice or audiobook runtimes (and vice versa).
 */

const activeStores = new Map<OmnixModuleId, DisposableStore>();
const activeReady = new Map<OmnixModuleId, Promise<void>>();
const settledReady = new WeakSet<Promise<void>>();

export interface ActiveViewRuntime extends Disposable {
  /** Settles when activation finished (or failed and was logged). */
  readonly ready: Promise<void>;
}

export function activateViewRuntime(moduleId: OmnixModuleId, context: ModuleRuntimeContext): ActiveViewRuntime {
  const store = new DisposableStore();
  activeStores.get(moduleId)?.dispose();
  activeStores.set(moduleId, store);
  const ready = loadViewRuntime(moduleId, context, store).catch((error: unknown) => {
    console.error(`[Omnix] ${moduleId} workspace runtime failed to initialize`, error);
  });
  activeReady.set(moduleId, ready);
  void ready.then(() => settledReady.add(ready));
  return {
    ready,
    dispose: () => {
      store.dispose();
      if (activeStores.get(moduleId) === store) activeStores.delete(moduleId);
      if (activeReady.get(moduleId) === ready) activeReady.delete(moduleId);
    },
  };
}

/**
 * Settles once the workspace's active runtime has finished activating (at once when none is active).
 *
 * Its initializers load as separate modules after the view renders: on a cold start (a dev server compiling each
 * on first request) the view is usable seconds before they are installed.
 */
export function viewRuntimeReady(moduleId: OmnixModuleId): Promise<void> {
  return activeReady.get(moduleId) ?? Promise.resolve();
}

/** Whether the workspace's runtime has finished activating (or none is active): then there is nothing to wait for. */
export function viewRuntimeIsReady(moduleId: OmnixModuleId): boolean {
  const ready = activeReady.get(moduleId);
  return ready === undefined || settledReady.has(ready);
}

/** Workspaces whose runtime is active (tests and diagnostics). */
export function activeViewRuntimes(): OmnixModuleId[] {
  return [...activeStores.keys()];
}

async function loadViewRuntime(moduleId: OmnixModuleId, context: ModuleRuntimeContext, store: DisposableStore): Promise<void> {
  await moduleManifest(moduleId).activateRuntime?.(context, store);
}

