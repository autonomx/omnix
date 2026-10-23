import { afterEach, describe, expect, it } from 'vitest';
import { desktopBridge, hasFramelessWindow, isDesktopApp, type DesktopBridge } from './desktopBridge';

const base = {
  version: '0.1.0', platform: 'win32', setTitleBarOverlay: () => undefined, revealLogs: () => undefined,
  openExternal: () => undefined, requestLoginCode: async () => false,
};

afterEach(() => {
  delete window.omnixDesktop;
  delete window.marketPulse;
});

describe('desktopBridge', () => {
  it('is absent in a browser', () => {
    expect(desktopBridge()).toBeNull();
    expect(isDesktopApp()).toBe(false);
    expect(hasFramelessWindow()).toBe(false);
  });

  it('prefers the Omnix desktop app, whose windows keep their title bar', () => {
    window.omnixDesktop = { ...base, product: 'omnix', frameless: false } satisfies DesktopBridge;
    window.marketPulse = { ...base };
    expect(desktopBridge()?.product).toBe('omnix');
    expect(hasFramelessWindow()).toBe(false);
  });

  it("treats MarketPulse's windows as frameless", () => {
    window.marketPulse = { ...base };
    expect(isDesktopApp()).toBe(true);
    expect(hasFramelessWindow()).toBe(true);
  });
});
