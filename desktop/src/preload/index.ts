import { contextBridge, ipcRenderer } from 'electron';

// The bridge (web/src/shared/desktopBridge.ts's `window.omnixDesktop`) for the gateway's pages, and
// `omnixDesktopShell` for the bundled splash and error pages. Each call is checked again in the main process against
// the calling page's origin.
const info = ipcRenderer.sendSync('ox:info') as { version: string; platform: string; origin: string | null };

if (location.protocol === 'file:') {
  contextBridge.exposeInMainWorld('omnixDesktopShell', {
    onStatus: (listener: (status: unknown) => void) => {
      ipcRenderer.on('ox:status', (_event, status) => listener(status));
      ipcRenderer.send('ox:status-ready');
    },
    retry: () => ipcRenderer.send('ox:retry'),
    newPorts: () => ipcRenderer.send('ox:new-ports'),
    restore: () => ipcRenderer.send('ox:restore-snapshot'),
    previousRelease: () => ipcRenderer.send('ox:previous-release'),
    exportDiagnostics: () => ipcRenderer.send('ox:export-diagnostics'),
    revealLogs: () => ipcRenderer.send('ox:reveal-logs'),
    quit: () => ipcRenderer.send('ox:quit'),
    closeWindow: () => ipcRenderer.send('ox:close-window'),
  });
} else if (info.origin && location.origin === info.origin) {
  contextBridge.exposeInMainWorld('omnixDesktop', {
    product: 'omnix',
    // Omnix's windows keep the native title bar; nothing is drawn over a title-bar area.
    frameless: false,
    version: info.version,
    platform: info.platform,
    setTitleBarOverlay: () => undefined,
    revealLogs: () => ipcRenderer.send('ox:reveal-logs'),
    openExternal: (url: string) => ipcRenderer.send('ox:open-external', String(url)),
    requestLoginCode: (): Promise<boolean> => ipcRenderer.invoke('ox:request-login-code'),
    // The model services' states (starting, running, blocked, failed), as the supervisor reports them.
    serviceStates: (): Promise<Record<string, { state: string; message: string }>> => ipcRenderer.invoke('ox:service-states'),
    // After an install or removal on the setup screen: look at the packs now rather than within five seconds.
    refreshServices: (): Promise<Record<string, { state: string; message: string }>> => ipcRenderer.invoke('ox:refresh-services'),
    // Moving the packs folder needs a folder picker and a restart of the model services: the shell does both.
    choosePacksFolder: (): Promise<string | null> => ipcRenderer.invoke('ox:choose-packs-folder'),
    exportDiagnostics: () => ipcRenderer.send('ox:export-diagnostics'),
  });
}
