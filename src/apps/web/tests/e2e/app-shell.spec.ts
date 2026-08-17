import { expect, test } from '@playwright/test';

const modules = [
  'RPG',
  'Chatbot',
  'Storyteller',
  'Podcast',
  'Voice / TTS',
  'Voice Cloning',
  'STT',
  'Image Generation',
  'Providers',
  'Models',
  'Jobs / Runs',
  'Assets',
  'Reports',
  'Settings',
  'Diagnostics',
];

test('shared Omnix app shell exposes all module entrypoints', async ({ page }) => {
  await page.goto('/');

  await expect(page.getByRole('heading', { name: 'Omnix' })).toBeVisible();

  for (const module of modules) {
    await expect(page.getByRole('link', { name: module })).toBeVisible();
  }
});

test('module navigation keeps features in the shared shell', async ({ page }) => {
  await page.goto('/');
  await page.getByRole('link', { name: 'Podcast' }).click();

  await expect(page).toHaveURL(/\/podcast$/);
  await expect(page.getByRole('main').getByRole('heading', { name: 'Podcast', level: 2 })).toBeVisible();
  await expect(page.getByRole('heading', { name: 'Episode request' })).toBeVisible();
});

test('platform modules render mocked gateway data and empty states', async ({ page }) => {
  await page.route('**/api/providers', async (route) => {
    await route.fulfill({
      contentType: 'application/json',
      body: JSON.stringify({ providers: [], models: [] }),
    });
  });

  await page.route('**/api/diagnostics', async (route) => {
    await route.fulfill({
      contentType: 'application/json',
      body: JSON.stringify({
        ok: true,
        status: 'ready',
        event_stream: { status: 'ready' },
        workers: {
          contract_version: 'omnix_worker_health_contract_v1',
          format_version: 'omnix_gateway_foundation_v1',
          ok: true,
          status: 'not_configured',
          workers: [],
        },
        logs: [],
      }),
    });
  });

  await page.goto('/providers');
  await expect(page.getByRole('main').getByRole('heading', { name: 'Providers', level: 2 })).toBeVisible();
  await expect(page.getByText('No providers returned by gateway.')).toBeVisible();

  await page.getByRole('link', { name: 'Diagnostics' }).click();
  await expect(page).toHaveURL(/\/diagnostics$/);
  await expect(page.getByRole('heading', { name: 'Gateway status' })).toBeVisible();
  await expect(page.getByText('not_configured')).toBeVisible();
});

test('release readiness smoke covers diagnostics, job cancellation, assets, and reports', async ({ page }) => {
  let jobStatus = 'running';

  await page.route('**/api/diagnostics', async (route) => {
    await route.fulfill({
      contentType: 'application/json',
      body: JSON.stringify({
        ok: true,
        status: 'ready',
        event_stream: { status: 'ready' },
        workers: {
          contract_version: 'omnix_worker_health_contract_v1',
          format_version: 'omnix_gateway_foundation_v1',
          ok: true,
          status: 'ready',
          workers: [
            { id: 'tts', ok: true, status: 'ready', mocked: true },
            { id: 'image', ok: true, status: 'ready', mocked: true },
          ],
        },
        logs: [{ level: 'info', message: 'release smoke' }],
      }),
    });
  });

  await page.route('**/api/jobs', async (route) => {
    await route.fulfill({
      contentType: 'application/json',
      body: JSON.stringify({
        jobs: [
          {
            id: 'job:release-smoke',
            module: 'image-generation',
            type: 'image.generate',
            status: jobStatus,
            resource_class: 'gpu:image',
            created_at: '2026-06-15T00:00:00Z',
            updated_at: '2026-06-15T00:00:01Z',
            priority: 1,
            progress: { current: jobStatus === 'canceled' ? 1 : 0, total: 1, message: jobStatus },
            stages: [{ id: 'run', label: 'Generate image', resource_class: 'gpu:image', status: jobStatus }],
            logs: [{ level: 'info', message: 'queued from smoke' }],
          },
        ],
      }),
    });
  });

  await page.route('**/api/jobs/job%3Arelease-smoke/cancel', async (route) => {
    jobStatus = 'canceled';
    await route.fulfill({
      contentType: 'application/json',
      body: JSON.stringify({
        id: 'job:release-smoke',
        module: 'image-generation',
        type: 'image.generate',
        status: 'canceled',
        resource_class: 'gpu:image',
        created_at: '2026-06-15T00:00:00Z',
        updated_at: '2026-06-15T00:00:02Z',
        priority: 1,
        progress: { current: 1, total: 1, message: 'canceled' },
        stages: [{ id: 'run', label: 'Generate image', resource_class: 'gpu:image', status: 'canceled' }],
        logs: [{ level: 'info', message: 'canceled from smoke' }],
        cancel: {
          requested: true,
          requested_at: '2026-06-15T00:00:02Z',
          acknowledged_at: '2026-06-15T00:00:02Z',
          reason: 'Canceled from Omnix web Jobs module',
        },
      }),
    });
  });

  await page.route('**/api/assets', async (route) => {
    await route.fulfill({
      contentType: 'application/json',
      body: JSON.stringify({
        assets: [
          {
            id: 'asset:release-image',
            module: 'image-generation',
            type: 'image',
            mime_type: 'image/png',
            storage_path: 'resources/data/generated_images/release.png',
            created_at: '2026-06-15T00:00:00Z',
          },
        ],
      }),
    });
  });

  await page.route('**/api/reports', async (route) => {
    await route.fulfill({
      contentType: 'application/json',
      body: JSON.stringify({
        reports: [
          { id: 'release/smoke.json', kind: 'json_report', path: 'resources/data/test-results/release/smoke.json', size_bytes: 128 },
        ],
      }),
    });
  });

  await page.goto('/diagnostics');
  await expect(page.getByRole('heading', { name: 'Gateway status' })).toBeVisible();
  await expect(page.getByText('Event stream', { exact: true })).toBeVisible();
  await expect(page.getByText('ready').first()).toBeVisible();
  await expect(page.getByText('release smoke')).toBeVisible();

  await page.getByRole('link', { name: 'Jobs / Runs' }).click();
  await expect(page.getByRole('heading', { name: 'image.generate' })).toBeVisible();
  await page.getByRole('button', { name: 'Cancel' }).click();
  await expect(page.getByText('canceled').first()).toBeVisible();

  await page.getByRole('link', { name: 'Assets' }).click();
  await expect(page.getByRole('heading', { name: 'image / image-generation' })).toBeVisible();
  await expect(page.getByText('resources/data/generated_images/release.png')).toBeVisible();

  await page.getByRole('link', { name: 'Reports' }).click();
  await expect(page.getByRole('heading', { name: 'release/smoke.json' })).toBeVisible();
  await expect(page.getByText('128 bytes')).toBeVisible();
});

test('chatbot module queues a shared chat generation job', async ({ page }) => {
  let session: {
    id: string;
    title: string;
    provider_id: string;
    model_id: string;
    message_count: number;
    messages: Array<{ id: string; role: string; content: string; created_at: string; metadata?: Record<string, unknown> }>;
    created_at: string;
    updated_at: string;
  } = {
    id: 'chat:1',
    title: 'Hello Omnix',
    provider_id: 'openai',
    model_id: 'gpt-mini',
    message_count: 0,
    messages: [],
    created_at: '2026-06-14T00:00:00Z',
    updated_at: '2026-06-14T00:00:00Z',
  };

  await page.route('**/api/providers', async (route) => {
    await route.fulfill({
      contentType: 'application/json',
      body: JSON.stringify({
        providers: [
          {
            id: 'openai',
            label: 'OpenAI compatible',
            family: 'llm',
            source: 'settings',
            status: 'configured',
            capabilities: ['chat'],
          },
        ],
        models: [
          {
            id: 'gpt-mini',
            label: 'GPT mini',
            provider_id: 'openai',
            location: 'remote',
            capabilities: ['chat'],
          },
        ],
      }),
    });
  });

  await page.route('**/api/chat/sessions', async (route) => {
    if (route.request().method() === 'POST') {
      await route.fulfill({ contentType: 'application/json', body: JSON.stringify(session) });
      return;
    }

    await route.fulfill({ contentType: 'application/json', body: JSON.stringify({ sessions: [] }) });
  });

  await page.route('**/api/chat/sessions/chat%3A1', async (route) => {
    await route.fulfill({ contentType: 'application/json', body: JSON.stringify(session) });
  });

  await page.route('**/api/chat/sessions/chat%3A1/messages', async (route) => {
    session = {
      ...session,
      message_count: 1,
      messages: [
        {
          id: 'msg:1',
          role: 'user',
          content: 'Hello Omnix',
          created_at: '2026-06-14T00:00:01Z',
          metadata: { generation_status: 'queued' },
        },
      ],
    };
    await route.fulfill({
      contentType: 'application/json',
      body: JSON.stringify({
        generation_status: 'queued',
        session,
        user_message: session.messages[0],
        job: {
          id: 'job:1',
          module: 'chatbot',
          type: 'chat.generate',
          status: 'queued',
          resource_class: 'gpu:llm',
          created_at: '2026-06-14T00:00:01Z',
          updated_at: '2026-06-14T00:00:01Z',
          priority: 0,
        },
      }),
    });
  });

  await page.goto('/chatbot');

  await expect(page.getByRole('main').getByRole('heading', { name: 'Chatbot', level: 2 })).toBeVisible();
  await page.getByLabel('Provider').selectOption('openai');
  await page.getByLabel('Model').selectOption('gpt-mini');
  await page.getByLabel('Message').fill('Hello Omnix');
  await page.getByRole('button', { name: 'Queue response' }).click();

  await expect(page.getByText('Generation job queued: job:1')).toBeVisible();
});

test('voice module queues a shared TTS job', async ({ page }) => {
  await page.route('**/api/providers', async (route) => {
    await route.fulfill({
      contentType: 'application/json',
      body: JSON.stringify({
        providers: [
          {
            id: 'faster-qwen3-tts',
            label: 'Faster Qwen TTS',
            family: 'tts',
            source: 'settings',
            status: 'configured',
            capabilities: ['tts'],
          },
        ],
        models: [],
      }),
    });
  });

  await page.route('**/api/jobs', async (route) => {
    if (route.request().method() === 'POST') {
      await route.fulfill({
        contentType: 'application/json',
        body: JSON.stringify({
          id: 'job:tts',
          module: 'voice',
          type: 'tts.synthesize',
          status: 'queued',
          resource_class: 'gpu:tts',
          created_at: '2026-06-14T00:00:01Z',
          updated_at: '2026-06-14T00:00:01Z',
          priority: 0,
        }),
      });
      return;
    }

    await route.fulfill({
      contentType: 'application/json',
      body: JSON.stringify({ jobs: [] }),
    });
  });

  await page.route('**/api/assets', async (route) => {
    await route.fulfill({
      contentType: 'application/json',
      body: JSON.stringify({ assets: [] }),
    });
  });

  await page.goto('/voice');

  await expect(page.getByRole('main').getByRole('heading', { name: 'Voice / TTS', level: 2 })).toBeVisible();
  await page.getByLabel('Provider').selectOption('faster-qwen3-tts');
  await page.getByLabel('Text').fill('A short line for synthesis.');
  await page.getByRole('button', { name: 'Queue synthesis' }).click();

  await expect(page.getByText('TTS job queued: job:tts')).toBeVisible();
});

test('stt module queues a shared transcription job', async ({ page }) => {
  await page.route('**/api/providers', async (route) => {
    await route.fulfill({
      contentType: 'application/json',
      body: JSON.stringify({
        providers: [
          {
            id: 'parakeet',
            label: 'Parakeet STT',
            family: 'stt',
            source: 'settings',
            status: 'configured',
            capabilities: ['stt'],
          },
        ],
        models: [],
      }),
    });
  });

  await page.route('**/api/jobs', async (route) => {
    if (route.request().method() === 'POST') {
      await route.fulfill({
        contentType: 'application/json',
        body: JSON.stringify({
          id: 'job:stt',
          module: 'stt',
          type: 'stt.transcribe',
          status: 'queued',
          resource_class: 'gpu:stt',
          created_at: '2026-06-14T00:00:01Z',
          updated_at: '2026-06-14T00:00:01Z',
          priority: 0,
        }),
      });
      return;
    }

    await route.fulfill({
      contentType: 'application/json',
      body: JSON.stringify({ jobs: [] }),
    });
  });

  await page.route('**/api/assets', async (route) => {
    await route.fulfill({
      contentType: 'application/json',
      body: JSON.stringify({
        assets: [
          {
            id: 'asset:audio',
            module: 'voice',
            type: 'audio',
            mime_type: 'audio/wav',
            storage_path: 'artifacts/input.wav',
            created_at: '2026-06-14T00:00:00Z',
          },
        ],
      }),
    });
  });

  await page.goto('/stt');

  await expect(page.getByRole('main').getByRole('heading', { name: 'STT', level: 2 })).toBeVisible();
  await page.getByLabel('Provider').selectOption('parakeet');
  await page.getByLabel('Audio asset').selectOption('asset:audio');
  await page.getByRole('button', { name: 'Queue transcription' }).click();

  await expect(page.getByText('STT job queued: job:stt')).toBeVisible();
});

test('image generation module queues a shared image job', async ({ page }) => {
  await page.route('**/api/providers', async (route) => {
    await route.fulfill({
      contentType: 'application/json',
      body: JSON.stringify({
        providers: [
          {
            id: 'flux',
            label: 'Flux local',
            family: 'image',
            source: 'settings',
            status: 'configured',
            capabilities: ['image'],
          },
        ],
        models: [],
      }),
    });
  });

  await page.route('**/api/jobs', async (route) => {
    if (route.request().method() === 'POST') {
      await route.fulfill({
        contentType: 'application/json',
        body: JSON.stringify({
          id: 'job:image',
          module: 'image-generation',
          type: 'image.generate',
          status: 'queued',
          resource_class: 'gpu:image',
          created_at: '2026-06-14T00:00:01Z',
          updated_at: '2026-06-14T00:00:01Z',
          priority: 0,
        }),
      });
      return;
    }

    await route.fulfill({
      contentType: 'application/json',
      body: JSON.stringify({ jobs: [] }),
    });
  });

  await page.route('**/api/assets', async (route) => {
    await route.fulfill({
      contentType: 'application/json',
      body: JSON.stringify({ assets: [] }),
    });
  });

  await page.goto('/image-generation');

  await expect(page.getByRole('main').getByRole('heading', { name: 'Image Generation', level: 2 })).toBeVisible();
  await page.getByLabel('Provider').selectOption('flux');
  await page.getByLabel('Prompt').fill('A bright workstation render.');
  await page.getByRole('button', { name: 'Queue image' }).click();

  await expect(page.getByText('Image job queued: job:image')).toBeVisible();
});

test('storyteller module queues a shared story job', async ({ page }) => {
  await page.route('**/api/providers', async (route) => {
    await route.fulfill({
      contentType: 'application/json',
      body: JSON.stringify({
        providers: [
          {
            id: 'lmstudio',
            label: 'LM Studio',
            family: 'llm',
            source: 'settings',
            status: 'configured',
            capabilities: ['chat', 'completion'],
          },
        ],
        models: [],
      }),
    });
  });

  await page.route('**/api/jobs', async (route) => {
    if (route.request().method() === 'POST') {
      await route.fulfill({
        contentType: 'application/json',
        body: JSON.stringify({
          id: 'job:story',
          module: 'storyteller',
          type: 'story.generate',
          status: 'queued',
          resource_class: 'gpu:llm',
          created_at: '2026-06-14T00:00:01Z',
          updated_at: '2026-06-14T00:00:01Z',
          priority: 0,
        }),
      });
      return;
    }

    await route.fulfill({
      contentType: 'application/json',
      body: JSON.stringify({ jobs: [] }),
    });
  });

  await page.route('**/api/assets', async (route) => {
    await route.fulfill({
      contentType: 'application/json',
      body: JSON.stringify({ assets: [] }),
    });
  });

  await page.goto('/storyteller');

  await expect(page.getByRole('main').getByRole('heading', { name: 'Storyteller', level: 2 })).toBeVisible();
  await page.getByLabel('Provider').selectOption('lmstudio');
  await page.getByLabel('Title').fill('The Glass Orchard');
  await page.getByLabel('Premise').fill('A city grows fruit made of memory.');
  await page.getByRole('button', { name: 'Queue story' }).click();

  await expect(page.getByText('Story job queued: job:story')).toBeVisible();
});

test('podcast module queues a shared podcast job', async ({ page }) => {
  await page.route('**/api/providers', async (route) => {
    await route.fulfill({
      contentType: 'application/json',
      body: JSON.stringify({
        providers: [
          {
            id: 'lmstudio',
            label: 'LM Studio',
            family: 'llm',
            source: 'settings',
            status: 'configured',
            capabilities: ['chat'],
          },
          {
            id: 'faster-qwen3-tts',
            label: 'Faster Qwen TTS',
            family: 'tts',
            source: 'settings',
            status: 'configured',
            capabilities: ['tts'],
          },
        ],
        models: [],
      }),
    });
  });

  await page.route('**/api/jobs', async (route) => {
    if (route.request().method() === 'POST') {
      await route.fulfill({
        contentType: 'application/json',
        body: JSON.stringify({
          id: 'job:podcast',
          module: 'podcast',
          type: 'podcast.generate',
          status: 'queued',
          resource_class: 'gpu:llm',
          created_at: '2026-06-14T00:00:01Z',
          updated_at: '2026-06-14T00:00:01Z',
          priority: 0,
        }),
      });
      return;
    }

    await route.fulfill({
      contentType: 'application/json',
      body: JSON.stringify({ jobs: [] }),
    });
  });

  await page.route('**/api/assets', async (route) => {
    await route.fulfill({
      contentType: 'application/json',
      body: JSON.stringify({ assets: [] }),
    });
  });

  await page.goto('/podcast');

  await expect(page.getByRole('main').getByRole('heading', { name: 'Podcast', level: 2 })).toBeVisible();
  await page.getByLabel('LLM provider').selectOption('lmstudio');
  await page.getByLabel('TTS provider').selectOption('faster-qwen3-tts');
  await page.getByLabel('Title').fill('Signals');
  await page.getByLabel('Brief').fill('Discuss local AI workstation design.');
  await page.getByRole('button', { name: 'Queue episode' }).click();

  await expect(page.getByText('Podcast job queued: job:podcast')).toBeVisible();
});

test('voice cloning module queues a shared voice profile job', async ({ page }) => {
  await page.route('**/api/providers', async (route) => {
    await route.fulfill({
      contentType: 'application/json',
      body: JSON.stringify({
        providers: [
          {
            id: 'qwen-voice',
            label: 'Qwen Voice',
            family: 'tts',
            source: 'settings',
            status: 'configured',
            capabilities: ['tts', 'voice_cloning'],
          },
        ],
        models: [],
      }),
    });
  });

  await page.route('**/api/jobs', async (route) => {
    if (route.request().method() === 'POST') {
      await route.fulfill({
        contentType: 'application/json',
        body: JSON.stringify({
          id: 'job:voice-profile',
          module: 'voice-cloning',
          type: 'voice-cloning.train',
          status: 'queued',
          resource_class: 'gpu:tts',
          created_at: '2026-06-14T00:00:01Z',
          updated_at: '2026-06-14T00:00:01Z',
          priority: 0,
        }),
      });
      return;
    }

    await route.fulfill({
      contentType: 'application/json',
      body: JSON.stringify({ jobs: [] }),
    });
  });

  await page.route('**/api/assets', async (route) => {
    await route.fulfill({
      contentType: 'application/json',
      body: JSON.stringify({
        assets: [
          {
            id: 'asset:sample',
            module: 'voice-cloning',
            type: 'voice_sample',
            mime_type: 'audio/wav',
            storage_path: 'samples/ref.wav',
            created_at: '2026-06-14T00:00:00Z',
          },
        ],
      }),
    });
  });

  await page.goto('/voice-cloning');

  await expect(page.getByRole('main').getByRole('heading', { name: 'Voice Cloning', level: 2 })).toBeVisible();
  await page.getByLabel('Provider').selectOption('qwen-voice');
  await page.getByLabel('Sample asset').selectOption('asset:sample');
  await page.getByLabel('Profile name').fill('Narrator');
  await page.getByRole('button', { name: 'Queue voice profile' }).click();

  await expect(page.getByText('Voice profile job queued: job:voice-profile')).toBeVisible();
});

test('rpg module queues a replay-preserving shared turn job', async ({ page }) => {
  await page.route('**/api/replay/persistence/inventory', async (route) => {
    await route.fulfill({
      contentType: 'application/json',
      body: JSON.stringify({
        sessions: [{ session_id: 'rpg-session-1', updated_at: '2026-06-14T00:00:00Z' }],
        diagnostics: [],
      }),
    });
  });

  await page.route('**/api/jobs', async (route) => {
    if (route.request().method() === 'POST') {
      await route.fulfill({
        contentType: 'application/json',
        body: JSON.stringify({
          id: 'job:rpg',
          module: 'rpg',
          type: 'rpg.turn',
          status: 'queued',
          resource_class: 'gpu:llm',
          created_at: '2026-06-14T00:00:01Z',
          updated_at: '2026-06-14T00:00:01Z',
          priority: 0,
        }),
      });
      return;
    }

    await route.fulfill({
      contentType: 'application/json',
      body: JSON.stringify({ jobs: [] }),
    });
  });

  await page.route('**/api/assets', async (route) => {
    await route.fulfill({
      contentType: 'application/json',
      body: JSON.stringify({
        assets: [
          {
            id: 'asset:checkpoint',
            module: 'rpg',
            type: 'rpg_checkpoint',
            mime_type: 'application/json',
            storage_path: 'checkpoints/session.json',
            created_at: '2026-06-14T00:00:00Z',
          },
        ],
      }),
    });
  });

  await page.route('**/api/reports', async (route) => {
    await route.fulfill({
      contentType: 'application/json',
      body: JSON.stringify({
        reports: [{ id: 'rpg/autoplay.json', kind: 'rpg_autoplay', path: 'reports/rpg/autoplay.json', size_bytes: 32 }],
      }),
    });
  });

  await page.goto('/rpg');

  await expect(page.getByRole('main').getByRole('heading', { name: 'RPG', level: 2 })).toBeVisible();
  await page.getByLabel('Session').selectOption('rpg-session-1');
  await page.getByLabel('Command').fill('Look around the tavern.');
  await page.getByRole('button', { name: 'Queue RPG turn' }).click();

  await expect(page.getByText('RPG turn job queued: job:rpg')).toBeVisible();
});
