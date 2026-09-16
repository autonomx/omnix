import { spawn, type ChildProcess } from 'node:child_process';
import { existsSync } from 'node:fs';
import { resolve } from 'node:path';

import { expect, test, type APIRequestContext, type Page } from '@playwright/test';

const RUN_E2E22 = process.env.OMNIX_RUN_COMPANION_ACTIVITY_E2E22 === '1';
const MANAGE_GATEWAY = process.env.OMNIX_E2E22_MANAGE_GATEWAY === '1';
const CONFIGURE_COMPANION = process.env.OMNIX_E2E22_CONFIGURE_COMPANION === '1';
const GATEWAY_ORIGIN = (process.env.OMNIX_E2E22_GATEWAY_URL || 'http://127.0.0.1:8000').replace(/\/$/u, '');
const GATEWAY_PORT = Number(process.env.OMNIX_E2E22_GATEWAY_PORT || '8000');
const CHAT_PROVIDER = process.env.OMNIX_E2E22_CHAT_PROVIDER || 'llm:chatgpt_codex';
const CHAT_MODEL = process.env.OMNIX_E2E22_CHAT_MODEL || 'llm:chatgpt_codex:gpt-5.6-luna';
const VISION_MODEL = process.env.OMNIX_E2E22_VISION_MODEL || 'gpt-5.6-luna';
const JOB_TIMEOUT_MS = Number(process.env.OMNIX_E2E22_JOB_TIMEOUT_MS || '180000');
const OBSERVATION_TIMEOUT_MS = Number(process.env.OMNIX_E2E22_OBSERVATION_TIMEOUT_MS || '180000');

type JsonRecord = Record<string, unknown>;

type ManagedGateway = {
  child: ChildProcess;
  output: string[];
  stop: () => Promise<void>;
  restart: () => Promise<void>;
};

type ActivitySnapshot = {
  capture_generation: string;
  observation_id: string;
  recovered_from_checkpoint: boolean;
  checkpoint_status: string;
  state: {
    character_id: string | null;
    generation: string | null;
    fields: Record<string, { value: unknown; authority_source: string }>;
    blockers: string[];
    open_loops: Array<{ description: string; status: string; authority_source: string }>;
    recent_meaningful_events: unknown[];
  };
};

test.describe.configure({ mode: 'serial', timeout: 12 * 60_000 });

test.describe('E2E-22 continuous game/work companion journey', () => {
  test.skip(!RUN_E2E22, 'Opt in with OMNIX_RUN_COMPANION_ACTIVITY_E2E22=1.');

  test('keeps explicit activity state across Watch, restart, stop, and resume', async ({ page, request }) => {
    let managedGateway: ManagedGateway | null = null;
    let sessionId = '';
    let characterId = '';
    let sharing = false;
    let watching = false;
    let originalSettingsProfile: JsonRecord | null = null;
    let captureSampleEvidence: { baseline?: unknown; scene?: unknown } = {};
    const browserPostRequests: string[] = [];
    page.on('request', (requestEvent) => {
      if (requestEvent.method() === 'POST') browserPostRequests.push(requestEvent.url());
    });

    try {
      if (MANAGE_GATEWAY) {
        managedGateway = await startManagedGateway();
      }
      await waitForGateway(request);

      const settings = await apiJson<JsonRecord>(request, 'GET', '/api/settings');
      const profile = record(record(settings.settings).settings_control_center);
      originalSettingsProfile = cloneRecord(profile);
      if (CONFIGURE_COMPANION) {
        await apiJson(request, 'POST', '/api/settings', {
          settings_profile_patch: {
            global: { providers: { llm: 'chatgpt_codex' } },
            providerConfigs: {
              chatgptCodex: {
                model: CHAT_MODEL.replace(/^llm:chatgpt_codex:/u, ''),
                reasoningEffort: 'medium',
                fastMode: true,
                codexPath: process.env.OMNIX_LIVE_CODEX_PATH || 'codex',
                transport: 'app_server',
              },
            },
            assistant: {
              desktopCompanionEnabled: true,
              desktopCompanionRolloutStage: 'shadow',
              desktopCompanionVisionModelId: VISION_MODEL,
              desktopCompanionRemoteVisionAllowed: true,
              desktopCompanionBackgroundCallsPerMinute: 30,
              desktopCompanionMinimumObservationIntervalMs: 2_000,
              desktopCompanionObservationTimeoutMs: 60_000,
              desktopCompanionObservationTtlMs: 120_000,
              desktopCompanionCommentaryCooldownMs: 5_000,
            },
          },
          base_revision: profile.revision,
        });
      }
      const effectiveSettings = CONFIGURE_COMPANION
        ? await apiJson<JsonRecord>(request, 'GET', '/api/settings')
        : settings;
      const effectiveProfile = record(record(effectiveSettings.settings).settings_control_center);
      const effectiveAssistant = record(effectiveProfile.assistant);
      expect(effectiveAssistant.desktopCompanionEnabled, 'Desktop Companion must be explicitly enabled for this opt-in test').toBe(true);
      expect(['shadow', 'text', 'speech']).toContain(effectiveAssistant.desktopCompanionRolloutStage);
      expect(effectiveAssistant.desktopCompanionRemoteVisionAllowed, 'The real Luna vision endpoint must be explicitly allowed').toBe(true);

      const characters = await apiJson<{ characters?: Array<{ id: string }> }>(request, 'GET', '/api/characters');
      const suffix = `${Date.now()}-${Math.random().toString(16).slice(2)}`;
      const character = await apiJson<{ id: string }>(request, 'POST', '/api/characters', {
        id: `codex-e2e22-${suffix}`,
        display_name: `Codex E2E22 ${suffix}`,
        description: 'Temporary isolated acceptance character.',
        personality_prompt: 'Be concise and acknowledge the user without inventing screen facts.',
        default_greeting: '',
        enabled: true,
      });
      characterId = character.id;
      expect(characters.characters ?? []).not.toContainEqual(expect.objectContaining({ id: characterId }));

      const session = await apiJson<{ id: string }>(request, 'POST', '/api/chat/sessions', {
        title: `Codex E2E22 ${suffix}`,
        provider_id: CHAT_PROVIDER,
        model_id: CHAT_MODEL,
        interaction_mode: 'character',
        character_id: characterId,
        read_memory: false,
        write_memory: false,
        shared_memory_access: 'none',
        transcript_policy: 'persistent',
      });
      sessionId = session.id;

      await installCanvasDisplayCapture(page, sessionId);
      await page.goto('/chatbot');
      await expect(page.getByLabel('Message', { exact: true })).toBeVisible({ timeout: 30_000 });
      await expect(page.getByRole('button', { name: 'Character', exact: true })).toHaveAttribute('aria-pressed', 'true');
      await page.getByRole('button', { name: `Codex E2E22 ${suffix}`, exact: true }).click();

      await setDesktopSharing(page, true);
      sharing = true;
      const captureDiagnostics = await inspectSyntheticCapture(page);
      expect(captureDiagnostics.videoWidth, JSON.stringify(captureDiagnostics)).toBeGreaterThan(0);
      expect(captureDiagnostics.videoHeight, JSON.stringify(captureDiagnostics)).toBeGreaterThan(0);
      expect(captureDiagnostics.trackReadyState, JSON.stringify(captureDiagnostics)).toBe('live');
      const baselineSample = await readSyntheticCaptureSample(page);
      captureSampleEvidence.baseline = baselineSample;

      const watchStart = page.locator('.desktop-companion-start');
      await expect(watchStart).toBeVisible({ timeout: 15_000 });
      await watchStart.click();
      watching = true;
      await expect(watchStart).toBeDisabled({ timeout: OBSERVATION_TIMEOUT_MS });
      await expect(page.locator('.desktop-companion-controls__status')).toHaveText(
        /Watching|Analyzing|Observed|Backoff/u,
        { timeout: OBSERVATION_TIMEOUT_MS },
      );

      // Give the controller a settled post-preflight baseline before introducing
      // the first meaningful scene transition.
      await drawCaptureScene(page, 'capture-baseline');
      await page.waitForTimeout(1_000);
      const firstObserveResponse = waitForDesktopObserve(page);
      await drawCaptureScene(page, 'iron-sentinel-fight');
      const sceneSample = await readSyntheticCaptureSample(page);
      captureSampleEvidence.scene = sceneSample;
      expect(sceneSample.checksum, JSON.stringify({ baselineSample, sceneSample })).not.toBe(baselineSample.checksum);
      expect(sceneSample.videoChecksums, JSON.stringify({ baselineSample, sceneSample })).not.toEqual(baselineSample.videoChecksums);
      const firstObserve = await firstObserveResponse;
      const firstObserveBody = await firstObserve.json() as JsonRecord;
      expect(firstObserve.ok(), JSON.stringify(firstObserveBody)).toBe(true);
      expect(firstObserveBody.status, JSON.stringify(firstObserveBody)).toBe('completed');
      const firstObservation = await waitForActivity(request, sessionId);
      expect(firstObservation.state.character_id).toBe(characterId);
      expect(firstObservation.state.generation).toBe(firstObservation.capture_generation);
      expect(firstObservation.observation_id).toBeTruthy();
      expect(JSON.stringify(firstObservation)).not.toMatch(/data:image\//u);

      await sendUserTurn(page, request, sessionId, "I'm trying to beat the Iron Sentinel. I'm stuck on phase two.");
      const objectiveSnapshot = await waitForActivityField(request, sessionId, 'current_objective', 'beat the Iron Sentinel');
      expect(objectiveSnapshot.state.fields.current_objective.authority_source).toBe('user_explicit');
      expect(objectiveSnapshot.state.blockers).toContain('phase two');

      await drawCaptureScene(page, 'iron-sentinel-blocked');
      const blockedObservation = await waitForNewActivity(request, sessionId, objectiveSnapshot.observation_id);
      expect(blockedObservation.capture_generation).toBe(objectiveSnapshot.capture_generation);

      await sendUserTurn(page, request, sessionId, "I'll try a bleed build next. Three more tries, then I'm done.");
      const strategySnapshot = await waitForActivityField(request, sessionId, 'strategy', 'a bleed build');
      expect(strategySnapshot.state.fields.strategy.authority_source).toBe('user_explicit');
      expect(strategySnapshot.state.open_loops).toEqual(expect.arrayContaining([
        expect.objectContaining({
          description: "Three more tries, then I'm done",
          status: 'open',
          authority_source: 'user_explicit',
        }),
      ]));

      await drawCaptureScene(page, 'iron-sentinel-success');
      const preRestart = await waitForNewActivity(request, sessionId, strategySnapshot.observation_id);
      const oldGeneration = preRestart.capture_generation;
      expect(oldGeneration).toBeTruthy();

      expect(managedGateway, 'Set OMNIX_E2E22_MANAGE_GATEWAY=1 so this journey can prove process recovery').not.toBeNull();
      await managedGateway!.restart();
      await waitForGateway(request);
      await drawCaptureScene(page, 'iron-sentinel-after-restart');
      const recovered = await waitForActivity(request, sessionId, (snapshot) => (
        snapshot.recovered_from_checkpoint && snapshot.capture_generation === oldGeneration
      ));
      expect(recovered.recovered_from_checkpoint).toBe(true);
      expect(recovered.state.fields.current_objective.value).toBe('beat the Iron Sentinel');
      expect(recovered.state.fields.strategy.value).toBe('a bleed build');
      expect(recovered.state.open_loops).toEqual(expect.arrayContaining([
        expect.objectContaining({ description: "Three more tries, then I'm done", status: 'open' }),
      ]));

      await page.locator('.desktop-companion-stop').click();
      watching = false;
      await expect(page.locator('.desktop-companion-controls__status')).toHaveText('Off', { timeout: 20_000 });
      await setDesktopSharing(page, false);
      sharing = false;

      await setDesktopSharing(page, true);
      sharing = true;
      const resumedStart = page.locator('.desktop-companion-start');
      await resumedStart.click();
      watching = true;
      await expect(resumedStart).toBeDisabled({ timeout: OBSERVATION_TIMEOUT_MS });
      await expect(page.locator('.desktop-companion-controls__status')).toHaveText(
        /Watching|Analyzing|Observed|Backoff/u,
        { timeout: OBSERVATION_TIMEOUT_MS },
      );
      await drawCaptureScene(page, 'capture-baseline');
      await page.waitForTimeout(1_000);
      const resumedObserveResponse = waitForDesktopObserve(page);
      await drawCaptureScene(page, 'iron-sentinel-resumed-new-generation');
      const resumedObserve = await resumedObserveResponse;
      const resumedObserveBody = await resumedObserve.json() as JsonRecord;
      expect(resumedObserve.ok(), JSON.stringify(resumedObserveBody)).toBe(true);
      expect(resumedObserveBody.status, JSON.stringify(resumedObserveBody)).toBe('completed');
      const resumed = await waitForActivity(request, sessionId, (snapshot) => (
        snapshot.capture_generation !== oldGeneration && snapshot.state.fields.current_objective?.value === 'beat the Iron Sentinel'
      ));
      expect(resumed.capture_generation).not.toBe(oldGeneration);
      expect(resumed.state.generation).toBe(resumed.capture_generation);
      expect(resumed.recovered_from_checkpoint).toBe(true);
      expect(resumed.state.fields.current_objective.authority_source).toBe('user_explicit');
      expect(resumed.state.fields.strategy.value).toBe('a bleed build');
      expect(resumed.state.open_loops).toEqual(expect.arrayContaining([
        expect.objectContaining({ description: "Three more tries, then I'm done", status: 'open' }),
      ]));
    } catch (error) {
      const message = error instanceof Error ? error.message : String(error);
      const gatewayTail = managedGateway?.output.join('').slice(-4000);
      let browserDiagnostics = '';
      try {
        browserDiagnostics = JSON.stringify(await page.evaluate(() => {
          const diagnosticWindow = window as Window & {
            __omnixE2E22StatusEvents?: unknown[];
            __omnixE2E22EvaluationEvents?: unknown[];
            __omnixE2E22Videos?: HTMLVideoElement[];
            __omnixE2E22VideoDraws?: unknown[];
            __omnixE2E22FrameRequestSupported?: boolean;
            __omnixE2E22FrameRequestCount?: number;
          };
          return {
            statusText: document.querySelector('.desktop-companion-controls__status')?.textContent,
            startDisabled: document.querySelector<HTMLButtonElement>('.desktop-companion-start')?.disabled,
            desktopChecked: document.querySelector('[data-omnix-context-tool-desktop]')?.getAttribute('aria-checked'),
            statusEvents: diagnosticWindow.__omnixE2E22StatusEvents ?? [],
            evaluationEvents: diagnosticWindow.__omnixE2E22EvaluationEvents ?? [],
            videos: (diagnosticWindow.__omnixE2E22Videos ?? []).map((video) => {
              const sampleCanvas = document.createElement('canvas');
              sampleCanvas.width = 48;
              sampleCanvas.height = 27;
              const sampleContext = sampleCanvas.getContext('2d');
              let checksum = 0;
              if (sampleContext && video.videoWidth > 0 && video.videoHeight > 0) {
                sampleContext.drawImage(video, 0, 0, sampleCanvas.width, sampleCanvas.height);
                const pixels = sampleContext.getImageData(0, 0, sampleCanvas.width, sampleCanvas.height).data;
                checksum = 2166136261;
                for (const pixel of pixels) {
                  checksum ^= pixel;
                  checksum = Math.imul(checksum, 16777619);
                }
                checksum >>>= 0;
              }
              return {
                className: video.className,
                readyState: video.readyState,
                videoWidth: video.videoWidth,
                videoHeight: video.videoHeight,
                currentTime: video.currentTime,
                checksum,
              };
            }),
            videoDraws: diagnosticWindow.__omnixE2E22VideoDraws?.slice(-30) ?? [],
            frameRequestSupported: diagnosticWindow.__omnixE2E22FrameRequestSupported,
            frameRequestCount: diagnosticWindow.__omnixE2E22FrameRequestCount,
          };
        }));
      } catch {
        // The original failure is more useful if the page is already unavailable.
      }
      const details = [
        message,
        `Capture samples: ${JSON.stringify(captureSampleEvidence)}`,
        `Browser POSTs: ${JSON.stringify(browserPostRequests.slice(-20))}`,
        browserDiagnostics && `Browser diagnostics: ${browserDiagnostics}`,
        gatewayTail && `Managed gateway output:\n${gatewayTail}`,
      ]
        .filter(Boolean)
        .join('\n');
      throw new Error(details);
    } finally {
      if (watching) {
        await page.locator('.desktop-companion-stop').click().catch(() => undefined);
      }
      if (sharing) {
        await setDesktopSharing(page, false).catch(() => undefined);
      }
      if (sessionId) await request.delete(`${GATEWAY_ORIGIN}/api/chat/sessions/${encodeURIComponent(sessionId)}`).catch(() => undefined);
      if (characterId) await request.delete(`${GATEWAY_ORIGIN}/api/characters/${encodeURIComponent(characterId)}`).catch(() => undefined);
      if (originalSettingsProfile) {
        const currentSettings = await request.get(`${GATEWAY_ORIGIN}/api/settings`).catch(() => null);
        if (currentSettings?.ok()) {
          const currentPayload = await currentSettings.json() as JsonRecord;
          const currentProfile = record(record(currentPayload.settings).settings_control_center);
          await request.post(`${GATEWAY_ORIGIN}/api/settings`, {
            data: {
              settings_profile_patch: originalSettingsProfile,
              base_revision: currentProfile.revision,
            },
          }).catch(() => undefined);
        }
      }
      await managedGateway?.stop().catch(() => undefined);
    }
  });
});

async function installCanvasDisplayCapture(page: Page, sessionId: string): Promise<void> {
  await page.addInitScript(({ selectedSessionId }) => {
    const captureWindow = window as Window & {
      __omnixE2E22Draw?: (scene: string) => void;
      __omnixE2E22Stream?: MediaStream;
      __omnixE2E22ProbeVideo?: HTMLVideoElement;
      __omnixE2E22StatusEvents?: unknown[];
      __omnixE2E22EvaluationEvents?: unknown[];
      __omnixE2E22Videos?: HTMLVideoElement[];
      __omnixE2E22VideoDraws?: unknown[];
      __omnixE2E22FrameRequestSupported?: boolean;
      __omnixE2E22FrameRequestCount?: number;
    };
    localStorage.setItem('omnix.chatbot.activeSession', selectedSessionId);
    const createdVideos: HTMLVideoElement[] = [];
    captureWindow.__omnixE2E22Videos = createdVideos;
    captureWindow.__omnixE2E22VideoDraws = [];
    captureWindow.__omnixE2E22FrameRequestCount = 0;
    const originalPlay = HTMLVideoElement.prototype.play;
    HTMLVideoElement.prototype.play = function playWithDiagnostics(...args) {
      if (!createdVideos.includes(this)) createdVideos.push(this);
      return originalPlay.apply(this, args);
    };
    const originalDrawImage = CanvasRenderingContext2D.prototype.drawImage;
    CanvasRenderingContext2D.prototype.drawImage = function drawImageWithDiagnostics(...args) {
      const source = args[0];
      if (source instanceof HTMLVideoElement && source !== captureWindow.__omnixE2E22ProbeVideo && source.videoWidth > 0 && source.videoHeight > 0) {
        const sampleCanvas = document.createElement('canvas');
        sampleCanvas.width = 48;
        sampleCanvas.height = 27;
        const sampleContext = sampleCanvas.getContext('2d');
        if (sampleContext) {
          originalDrawImage.call(sampleContext, source, 0, 0, sampleCanvas.width, sampleCanvas.height);
          const pixels = sampleContext.getImageData(0, 0, sampleCanvas.width, sampleCanvas.height).data;
          let checksum = 2166136261;
          for (const pixel of pixels) {
            checksum ^= pixel;
            checksum = Math.imul(checksum, 16777619);
          }
          captureWindow.__omnixE2E22VideoDraws?.push({
            at: performance.now(),
            currentTime: source.currentTime,
            checksum: checksum >>> 0,
          });
          if ((captureWindow.__omnixE2E22VideoDraws?.length ?? 0) > 200) {
            captureWindow.__omnixE2E22VideoDraws?.splice(0, 50);
          }
        }
      }
      return originalDrawImage.apply(this, args);
    };
    captureWindow.__omnixE2E22StatusEvents = [];
    captureWindow.__omnixE2E22EvaluationEvents = [];
    window.addEventListener('omnix:desktop-companion-status', (event) => {
      captureWindow.__omnixE2E22StatusEvents?.push((event as CustomEvent).detail ?? null);
    });
    window.addEventListener('omnix:desktop-companion-evaluation', (event) => {
      captureWindow.__omnixE2E22EvaluationEvents?.push((event as CustomEvent).detail ?? null);
    });

    let generation = 0;
    let canvas: HTMLCanvasElement | null = null;
    let context: CanvasRenderingContext2D | null = null;
    let captureTrack: CanvasCaptureMediaStreamTrack | null = null;
    let paintRevision = 0;

    function paint(scene: string): void {
      if (!canvas || !context) return;
      const palette: Record<string, [string, string, string]> = {
        'iron-sentinel-fight': ['#000000', '#ffffff', '#ff0000'],
        'iron-sentinel-blocked': ['#ffffff', '#000000', '#00ff00'],
        'iron-sentinel-success': ['#000000', '#ffffff', '#0000ff'],
        'iron-sentinel-after-restart': ['#ffffff', '#000000', '#ffff00'],
        'iron-sentinel-resumed-new-generation': ['#000000', '#ffffff', '#00ffff'],
      };
      const colors = palette[scene] ?? ['#111827', '#334155', '#e2e8f0'];
      context.fillStyle = colors[0];
      context.fillRect(0, 0, canvas.width, canvas.height);
      context.fillStyle = colors[1];
      context.fillRect(40, 60, canvas.width - 80, canvas.height - 120);
      context.fillStyle = colors[2];
      context.beginPath();
      context.arc(canvas.width / 2, canvas.height / 2, 120, 0, Math.PI * 2);
      context.fill();
      context.fillStyle = '#ffffff';
      context.font = 'bold 34px sans-serif';
      context.fillText('IRON SENTINEL', 70, 90);
      context.font = '24px sans-serif';
      context.fillText(`${scene.replaceAll('-', ' ').toUpperCase()} ${paintRevision}`, 70, canvas.height - 70);
      paintRevision += 1;
      if (captureTrack) {
        captureWindow.__omnixE2E22FrameRequestSupported = typeof captureTrack.requestFrame === 'function';
        if (captureTrack.requestFrame) {
          captureWindow.__omnixE2E22FrameRequestCount = (captureWindow.__omnixE2E22FrameRequestCount ?? 0) + 1;
          captureTrack.requestFrame();
        }
      }
    }

    captureWindow.__omnixE2E22Draw = paint;
    Object.defineProperty(navigator.mediaDevices, 'getDisplayMedia', {
      configurable: true,
      writable: true,
      value: async () => {
        generation += 1;
        canvas = document.createElement('canvas');
        canvas.width = 1280;
        canvas.height = 720;
        canvas.setAttribute('aria-hidden', 'true');
        canvas.style.cssText = 'position:fixed;left:-10000px;top:0;width:1280px;height:720px;opacity:0.001;pointer-events:none;';
        document.body.append(canvas);
        context = canvas.getContext('2d');
        paint('capture-baseline');
        const stream = canvas.captureStream(30);
        captureWindow.__omnixE2E22Stream = stream;
        const track = stream.getVideoTracks()[0];
        captureTrack = track ?? null;
        captureTrack?.requestFrame();
        if (track) {
          const originalGetSettings = track.getSettings.bind(track);
          try {
            Object.defineProperty(track, 'getSettings', {
              configurable: true,
              value: () => ({ ...originalGetSettings(), displaySurface: `browser-e2e22-${generation}` }),
            });
          } catch {
            // The browser's native track remains usable if its settings method is sealed.
          }
        }
        return stream;
      },
    });
  }, { selectedSessionId: sessionId });
}

async function drawCaptureScene(page: Page, scene: string): Promise<void> {
  await page.evaluate(async (nextScene) => {
    const captureWindow = window as Window & {
      __omnixE2E22Draw?: (value: string) => void;
      __omnixE2E22Stream?: MediaStream;
      __omnixE2E22ProbeVideo?: HTMLVideoElement;
      __omnixE2E22Videos?: HTMLVideoElement[];
    };
    for (let index = 0; index < 10; index += 1) {
      captureWindow.__omnixE2E22Draw?.(nextScene);
      await new Promise((resolvePromise) => window.setTimeout(resolvePromise, 100));
    }
    // Headless Chromium can stop delivering canvas repaints to an existing
    // consumer. Rebinding only the synthetic stream keeps the application
    // capture video on the real getDisplayMedia path and makes the fixture
    // deterministic without changing production code.
    const stream = captureWindow.__omnixE2E22Stream;
    for (const video of captureWindow.__omnixE2E22Videos ?? []) {
      if (!stream || video === captureWindow.__omnixE2E22ProbeVideo) continue;
      video.srcObject = null;
      video.srcObject = stream;
      try {
        await video.play();
      } catch {
        // The controller's capture video reports the media failure itself.
      }
    }
  }, scene);
  await page.waitForTimeout(500);
}

async function inspectSyntheticCapture(page: Page): Promise<{
  streamActive: boolean;
  trackReadyState: string;
  videoReadyState: number;
  videoWidth: number;
  videoHeight: number;
}> {
  return page.evaluate(async () => {
    const captureWindow = window as Window & {
      __omnixE2E22Stream?: MediaStream;
      __omnixE2E22ProbeVideo?: HTMLVideoElement;
    };
    const stream = captureWindow.__omnixE2E22Stream;
    const track = stream?.getVideoTracks()[0];
    const video = captureWindow.__omnixE2E22ProbeVideo ?? document.createElement('video');
    captureWindow.__omnixE2E22ProbeVideo = video;
    video.muted = true;
    video.playsInline = true;
    video.srcObject = stream ?? null;
    try {
      await video.play();
    } catch {
      // Return readiness fields so the assertion reports the media failure.
    }
    await new Promise((resolvePromise) => window.setTimeout(resolvePromise, 250));
    return {
      streamActive: stream?.active === true,
      trackReadyState: track?.readyState ?? 'missing',
      videoReadyState: video.readyState,
      videoWidth: video.videoWidth,
      videoHeight: video.videoHeight,
    };
  });
}

async function readSyntheticCaptureSample(page: Page): Promise<{
  checksum: number;
  videoWidth: number;
  videoHeight: number;
  videoChecksums: number[];
}> {
  return page.evaluate(async () => {
    const captureWindow = window as Window & {
      __omnixE2E22Stream?: MediaStream;
      __omnixE2E22ProbeVideo?: HTMLVideoElement;
    };
    const video = captureWindow.__omnixE2E22ProbeVideo ?? document.createElement('video');
    captureWindow.__omnixE2E22ProbeVideo = video;
    video.muted = true;
    video.playsInline = true;
    video.srcObject = captureWindow.__omnixE2E22Stream ?? null;
    try {
      await video.play();
    } catch {
      // The dimensions and checksum below still identify a failed media path.
    }
    await new Promise((resolvePromise) => window.setTimeout(resolvePromise, 250));
    const sample = (source: HTMLVideoElement): number => {
      const canvas = document.createElement('canvas');
      canvas.width = 48;
      canvas.height = 27;
      const context = canvas.getContext('2d');
      if (!context || source.videoWidth <= 0 || source.videoHeight <= 0) return 0;
      context.drawImage(source, 0, 0, canvas.width, canvas.height);
      const pixels = context.getImageData(0, 0, canvas.width, canvas.height).data;
      let checksum = 2166136261;
      for (const pixel of pixels) {
        checksum ^= pixel;
        checksum = Math.imul(checksum, 16777619);
      }
      return checksum >>> 0;
    };
    return {
      checksum: sample(video),
      videoWidth: video.videoWidth,
      videoHeight: video.videoHeight,
      videoChecksums: (captureWindow.__omnixE2E22Videos ?? []).map(sample),
    };
  });
}

function waitForDesktopObserve(page: Page): Promise<import('@playwright/test').Response> {
  return page.waitForResponse((response) => (
    response.request().method() === 'POST'
    && response.url().includes('/api/desktop-companion/observe')
  ), { timeout: OBSERVATION_TIMEOUT_MS });
}

async function setDesktopSharing(page: Page, enabled: boolean): Promise<void> {
  const item = page.locator('[data-omnix-context-tool-desktop]');
  const desired = String(enabled);
  if ((await item.getAttribute('aria-checked')) === desired) return;
  const addTools = page.getByRole('button', { name: 'Add tools', exact: true });
  if (!(await item.isVisible())) await addTools.click();
  await expect(item).toBeVisible({ timeout: 15_000 });
  await item.click();
  await expect(item).toHaveAttribute('aria-checked', desired, { timeout: 15_000 });
}

async function sendUserTurn(
  page: Page,
  request: APIRequestContext,
  sessionId: string,
  content: string,
): Promise<void> {
  const sessionMessagePath = `/sessions/${encodeURIComponent(sessionId)}/messages`;
  const rawSessionMessagePath = `/sessions/${sessionId}/messages`;
  const responsePromise = page.waitForResponse((response) => (
    response.request().method() === 'POST'
    && (response.url().includes(sessionMessagePath) || response.url().includes(rawSessionMessagePath))
  ), { timeout: 30_000 });
  await page.getByLabel('Message', { exact: true }).fill(content);
  await page.getByRole('button', { name: 'Queue response', exact: true }).click();
  const response = await responsePromise;
  expect(response.ok()).toBe(true);
  const accepted = await response.json() as { job?: { id?: string } };
  expect(accepted.job?.id).toBeTruthy();
  await waitForJob(request, accepted.job!.id!);
  await expect(page.locator('.assistant-chat-message.user').filter({ hasText: content })).toBeVisible({ timeout: 30_000 });
}

async function waitForJob(request: APIRequestContext, jobId: string): Promise<JsonRecord> {
  return waitForValue<JsonRecord>(async () => {
    const response = await request.get(`${GATEWAY_ORIGIN}/api/jobs/${encodeURIComponent(jobId)}`);
    if (!response.ok()) return null;
    const job = await response.json() as JsonRecord;
    const status = String(job.status ?? '');
    if (status === 'failed' || status === 'canceled' || status === 'stale') {
      throw new Error(`E2E-22 chat job ${jobId} ended ${status}: ${JSON.stringify(job.error ?? {})}`);
    }
    return status === 'completed' ? job : null;
  }, JOB_TIMEOUT_MS);
}

async function waitForActivity(
  request: APIRequestContext,
  sessionId: string,
  predicate: (snapshot: ActivitySnapshot) => boolean = () => true,
): Promise<ActivitySnapshot> {
  let latestSnapshot: ActivitySnapshot | null = null;
  return waitForValue<ActivitySnapshot>(async () => {
    const response = await request.get(`${GATEWAY_ORIGIN}/api/desktop-companion/activity?session_id=${encodeURIComponent(sessionId)}`);
    if (!response.ok()) return null;
    const snapshot = await response.json() as ActivitySnapshot | null;
    latestSnapshot = snapshot;
    return snapshot && predicate(snapshot) ? snapshot : null;
  }, OBSERVATION_TIMEOUT_MS).catch((error: unknown) => {
    const suffix = latestSnapshot ? ` Last snapshot: ${JSON.stringify(latestSnapshot)}` : '';
    throw new Error(`${String(error)}${suffix}`);
  });
}

async function waitForNewActivity(
  request: APIRequestContext,
  sessionId: string,
  previousObservationId: string,
): Promise<ActivitySnapshot> {
  return waitForActivity(request, sessionId, (snapshot) => snapshot.observation_id !== previousObservationId);
}

async function waitForActivityField(
  request: APIRequestContext,
  sessionId: string,
  fieldName: string,
  value: string,
): Promise<ActivitySnapshot> {
  return waitForActivity(request, sessionId, (snapshot) => snapshot.state.fields[fieldName]?.value === value);
}

async function waitForGateway(request: APIRequestContext): Promise<void> {
  await waitForValue(async () => {
    const response = await request.get(`${GATEWAY_ORIGIN}/health`);
    return response.ok() ? true : null;
  }, 60_000);
}

async function apiJson<T>(request: APIRequestContext, method: string, path: string, data?: unknown): Promise<T> {
  const response = await request.fetch(`${GATEWAY_ORIGIN}${path}`, {
    method,
    ...(data === undefined ? {} : { data }),
  });
  if (!response.ok()) throw new Error(`${method} ${path} failed with ${response.status()}: ${await response.text()}`);
  return response.json() as Promise<T>;
}

async function waitForValue<T>(read: () => Promise<T | null>, timeoutMs: number): Promise<T> {
  const deadline = Date.now() + timeoutMs;
  let lastError: unknown;
  while (Date.now() < deadline) {
    try {
      const value = await read();
      if (value !== null) return value;
    } catch (error) {
      lastError = error;
    }
    await new Promise((resolvePromise) => setTimeout(resolvePromise, 500));
  }
  throw new Error(`Timed out after ${timeoutMs}ms${lastError ? `: ${String(lastError)}` : ''}`);
}

async function startManagedGateway(): Promise<ManagedGateway> {
  const root = repositoryRoot();
  const python = process.env.OMNIX_E2E22_PYTHON || 'python';
  const args = ['-m', 'uvicorn', 'app.gateway.main:app', '--host', '127.0.0.1', '--port', String(GATEWAY_PORT)];
  const inheritedPythonPath = process.env.PYTHONPATH ? `${resolve(root, 'src')};${process.env.PYTHONPATH}` : resolve(root, 'src');
  const gatewayEnv = {
    ...process.env,
    PYTHONPATH: inheritedPythonPath,
    OMNIX_CHARACTER_MODE_ENABLED: process.env.OMNIX_E2E22_CHARACTER_MODE_ENABLED || '1',
  };
  const existingGateway = await fetch(`${GATEWAY_ORIGIN}/health`).catch(() => null);
  if (existingGateway?.ok) throw new Error(`Refusing to manage gateway: ${GATEWAY_ORIGIN} is already occupied.`);
  const output: string[] = [];
  let child = spawnManagedGateway(python, args, root, gatewayEnv, output);

  const stop = async (): Promise<void> => {
    if (child.exitCode !== null) return;
    child.kill();
    const exited = await waitForExit(child, 10_000);
    if (!exited) {
      throw new Error(`Managed gateway did not exit after SIGTERM: ${output.join('').slice(-4000)}`);
    }
    await waitForGatewayDown(30_000);
  };
  const start = async (): Promise<void> => {
    await waitForValue(async () => {
      if (child.exitCode !== null) {
        throw new Error(`Managed gateway exited before becoming healthy: ${output.join('').slice(-4000)}`);
      }
      const response = await fetch(`${GATEWAY_ORIGIN}/health`);
      return response.ok ? true : null;
    }, 60_000);
  };
  await start();

  return {
    child,
    output,
    stop,
    restart: async () => {
      await stop();
      child = spawnManagedGateway(python, args, root, gatewayEnv, output);
      await waitForValue(async () => {
        if (child.exitCode !== null) {
          throw new Error(`Managed gateway exited during restart: ${output.join('').slice(-4000)}`);
        }
        const response = await fetch(`${GATEWAY_ORIGIN}/health`);
        return response.ok ? true : null;
      }, 60_000);
    },
  };
}

function spawnManagedGateway(
  python: string,
  args: string[],
  root: string,
  gatewayEnv: NodeJS.ProcessEnv,
  output: string[],
): ChildProcess {
  const child = spawn(python, args, {
    cwd: root,
    env: gatewayEnv,
    stdio: ['ignore', 'pipe', 'pipe'],
    windowsHide: true,
  });
  child.stdout?.on('data', (chunk: Buffer) => output.push(chunk.toString()));
  child.stderr?.on('data', (chunk: Buffer) => output.push(chunk.toString()));
  return child;
}

async function waitForGatewayDown(timeoutMs: number): Promise<void> {
  await waitForValue(async () => {
    const response = await fetch(`${GATEWAY_ORIGIN}/health`).catch(() => null);
    return response?.ok ? null : true;
  }, timeoutMs);
}

async function waitForExit(child: ChildProcess, timeoutMs: number): Promise<boolean> {
  if (child.exitCode !== null) return true;
  return Promise.race([
    new Promise<boolean>((resolvePromise) => child.once('exit', () => resolvePromise(true))),
    new Promise<boolean>((resolvePromise) => setTimeout(() => resolvePromise(false), timeoutMs)),
  ]);
}

function repositoryRoot(): string {
  const configured = process.env.OMNIX_E2E22_REPO_ROOT?.trim();
  if (configured) return configured;
  let candidate = process.cwd();
  for (let depth = 0; depth < 8 && !existsSync(resolve(candidate, 'src', 'app', 'gateway')); depth += 1) {
    candidate = resolve(candidate, '..');
  }
  if (!existsSync(resolve(candidate, 'src', 'app', 'gateway'))) {
    throw new Error(`Could not locate repository root from ${process.cwd()}.`);
  }
  return candidate;
}

function record(value: unknown): JsonRecord {
  return value && typeof value === 'object' && !Array.isArray(value) ? value as JsonRecord : {};
}

function cloneRecord(value: JsonRecord): JsonRecord {
  return JSON.parse(JSON.stringify(value)) as JsonRecord;
}
