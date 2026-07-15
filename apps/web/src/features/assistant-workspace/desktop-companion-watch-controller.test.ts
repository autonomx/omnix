import { describe, expect, it } from 'vitest';

import {
  activityPayload,
  parseShadowWatchSettings,
  scenarioForActivity,
} from './desktop-companion-watch-controller';

describe('desktop companion shadow watch settings', () => {
  it('only enables the watch loop for explicit shadow rollout', () => {
    const payload = {
      settings: {
        settings_control_center: {
          assistant: {
            desktopCompanionEnabled: true,
            desktopCompanionRolloutStage: 'shadow',
            desktopCompanionVisionModelId: 'qwen-vl',
            desktopCompanionRemoteVisionAllowed: true,
            desktopCompanionBackgroundCallsPerMinute: 8,
            desktopCompanionMinimumObservationIntervalMs: 9000,
            desktopCompanionObservationTimeoutMs: 11000,
            desktopCompanionObservationTtlMs: 13000,
            desktopCompanionCommentaryCooldownMs: 26000,
            desktopCompanionMinimumChangeConfidence: 0.61,
          },
        },
      },
    };

    expect(parseShadowWatchSettings(payload)).toEqual({
      enabled: true,
      visionModelId: 'qwen-vl',
      remoteVisionAllowed: true,
      backgroundCallsPerMinute: 8,
      minimumObservationIntervalMs: 9000,
      observationTimeoutMs: 11000,
      observationTtlMs: 13000,
      commentaryCooldownMs: 26000,
      minimumChangeConfidence: 0.61,
    });
  });

  it('does not accidentally enable text or speech before rollout wiring', () => {
    for (const stage of ['disabled', 'text', 'speech']) {
      const result = parseShadowWatchSettings({
        settings: { settings_control_center: { assistant: {
          desktopCompanionEnabled: true,
          desktopCompanionRolloutStage: stage,
        } } },
      });
      expect(result.enabled).toBe(false);
      expect(result.remoteVisionAllowed).toBe(false);
    }
  });
});

describe('desktop companion activity request', () => {
  it('maps browser activity fields to the strict gateway contract', () => {
    expect(activityPayload({
      activity: 'full_scene_change',
      hypothesis: 'likely_app_switch',
      confidence: 0.9,
      changedRatio: 0.8,
      meanDifference: 0.7,
      horizontalShift: 1,
      verticalShift: 2,
      focus: 0.3,
      capturedAtMs: 1000,
    }, 1920, 1080)).toMatchObject({
      activity: 'full_scene_change',
      hypothesis: 'likely_app_switch',
      changed_ratio: 0.8,
      mean_difference: 0.7,
      source_width: 1920,
      source_height: 1080,
    });
  });

  it('maps activity to identifier-only evaluation scenarios', () => {
    const base = {
      confidence: 0.9,
      changedRatio: 0.8,
      meanDifference: 0.7,
      horizontalShift: 0,
      verticalShift: 0,
      focus: 0.3,
      capturedAtMs: 1000,
    };
    const behavior = {
      currentPattern: 'settled' as const,
      settledSeconds: 1,
      browsingPace: 0,
      rapidBrowsing: false,
      likelyTyping: false,
      likelyMedia: false,
      transition: null,
      sampleCount: 4,
    };
    expect(scenarioForActivity({ ...base, activity: 'static', hypothesis: 'none' }, behavior)).toBe('static-screen');
    expect(scenarioForActivity({ ...base, activity: 'full_scene_change', hypothesis: 'likely_app_switch' }, behavior)).toBe('scene-change');
    expect(scenarioForActivity(
      { ...base, activity: 'localized_change', hypothesis: 'likely_typing' },
      { ...behavior, likelyTyping: true },
    )).toBe('typing');
    expect(scenarioForActivity(
      { ...base, activity: 'localized_change', hypothesis: 'likely_navigation' },
      { ...behavior, rapidBrowsing: true },
    )).toBe('rapid-browsing');
  });
});
