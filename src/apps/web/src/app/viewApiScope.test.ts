import { afterEach, describe, expect, it, vi } from 'vitest';
import {
  activeViewModule,
  installViewApiFirewall,
  isApiAllowedForView,
  moduleIdFromPathname,
  resetViewApiFirewallForTests,
} from './viewApiScope';

describe('view API scope', () => {
  afterEach(() => {
    resetViewApiFirewallForTests();
    window.history.replaceState({}, '', '/chatbot');
  });

  it('resolves the most specific module route', () => {
    expect(moduleIdFromPathname('/voice-cloning')).toBe('voice-cloning');
    expect(moduleIdFromPathname('/voice-cloning/settings')).toBe('voice-cloning');
    expect(moduleIdFromPathname('/trading')).toBe('trading');
    expect(moduleIdFromPathname('/unknown')).toBe('chatbot');
  });

  it('only permits trading API families in the trading view', () => {
    expect(isApiAllowedForView('/api/trading/bars', 'trading')).toBe(true);
    expect(isApiAllowedForView('/api/trading-room/bars', 'trading')).toBe(false);
    expect(isApiAllowedForView('/api/chat/sessions', 'trading')).toBe(false);
    expect(isApiAllowedForView('/api/voice-library', 'trading')).toBe(false);
  });

  it('allows global market-data credentials from the settings view', () => {
    expect(isApiAllowedForView('/api/trading/market-data/providers/coinmarketcap/credentials', 'settings')).toBe(true);
    expect(isApiAllowedForView('/api/trading/bars', 'settings')).toBe(false);
  });

  it('allows the local-folder picker from the chatbot view', () => {
    expect(isApiAllowedForView('/api/agent-runs/workspace-picker', 'chatbot')).toBe(true);
    expect(isApiAllowedForView('/api/agent-runs/workspace-picker', 'trading')).toBe(false);
  });

  it('blocks off-view network calls without invoking the browser fetch', async () => {
    window.history.replaceState({}, '', '/trading');
    const delegate = vi.fn<typeof fetch>().mockResolvedValue(Response.json({ ok: true }));
    window.fetch = delegate;
    installViewApiFirewall();

    const blocked = await window.fetch('/api/chat/sessions');
    expect(blocked.status).toBe(403);
    expect(blocked.headers.get('x-omnix-view-api-blocked')).toBe('true');
    expect(delegate).not.toHaveBeenCalled();

    const allowed = await window.fetch('/api/trading/bars');
    expect(allowed.ok).toBe(true);
    expect(delegate).toHaveBeenCalledTimes(1);
  });

  it('follows browser navigation without reinstalling the firewall', async () => {
    const delegate = vi.fn<typeof fetch>().mockResolvedValue(Response.json({ ok: true }));
    window.fetch = delegate;
    installViewApiFirewall();

    window.history.replaceState({}, '', '/trading');
    expect(activeViewModule()).toBe('trading');
    expect((await window.fetch('/api/rpg/turns')).status).toBe(403);

    window.history.replaceState({}, '', '/rpg');
    expect(activeViewModule()).toBe('rpg');
    expect((await window.fetch('/api/rpg/turns')).ok).toBe(true);
  });

  it('bypasses global assistant wrappers for allowed trading requests', async () => {
    window.history.replaceState({}, '', '/trading');
    const rawFetch = vi.fn<typeof fetch>().mockResolvedValue(Response.json({ ok: true }));
    window.fetch = rawFetch;
    installViewApiFirewall();
    const assistantWrapper = vi.fn<typeof fetch>(window.fetch);
    window.fetch = assistantWrapper;
    installViewApiFirewall({ outermost: true });

    await window.fetch('/api/trading/paper/accounts');

    expect(rawFetch).toHaveBeenCalledTimes(1);
    expect(assistantWrapper).not.toHaveBeenCalled();
  });
});
