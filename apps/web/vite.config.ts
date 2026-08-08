import { execFileSync } from 'node:child_process';

import { defineConfig, type PluginOption } from 'vite';
import react from '@vitejs/plugin-react';

const LIVE_VOICE_CRITICAL_PATHS = [
  'src/app/gateway/live_voice_speculative_tts.py',
  'src/app/gateway/live_voice_execution_lane.py',
  'src/app/gateway/live_chat_speculative_tts.py',
  'src/app/gateway/live_chat_speculation.py',
  'src/app/gateway/live_chat_speculation_inline_stream.py',
  'apps/web/src/features/assistant-workspace/live-speculation-controller.ts',
  'apps/web/src/features/assistant-workspace/live-voice-controller.ts',
  'apps/web/src/features/assistant-workspace/live-voice-turn-coordinator.ts',
] as const;

function reactDevtoolsStandalonePlugin(): PluginOption {
  return {
    name: 'omnix-react-devtools-standalone',
    transformIndexHtml: {
      order: 'pre',
      handler(html) {
        return html.replace(
          '</head>',
          '    <script src="http://localhost:8097"></script>\n  </head>',
        );
      },
    },
  };
}

function resolveGitSha(): string {
  const configured = process.env.VITE_GIT_SHA?.trim();
  if (configured) return configured;
  try {
    return execFileSync('git', ['rev-parse', 'HEAD'], { encoding: 'utf8' }).trim();
  } catch {
    return 'unknown';
  }
}

function resolveGitDirty(): string {
  const configured = process.env.VITE_GIT_DIRTY?.trim();
  if (configured) return configured;
  try {
    const status = execFileSync(
      'git',
      ['status', '--porcelain', '--untracked-files=normal'],
      { encoding: 'utf8' },
    ).trim();
    return status ? 'true' : 'false';
  } catch {
    return 'unknown';
  }
}

function resolveLiveVoiceCriticalDirtyFiles(): string {
  const configured = process.env.VITE_LIVE_VOICE_CRITICAL_DIRTY_FILES?.trim();
  if (configured) return configured;
  try {
    const status = execFileSync(
      'git',
      [
        'status',
        '--porcelain=v1',
        '--untracked-files=normal',
        '--',
        ...LIVE_VOICE_CRITICAL_PATHS,
      ],
      { encoding: 'utf8' },
    ).trim();
    if (!status) return '[]';
    const paths = status
      .split(/\r?\n/u)
      .map((line) => line.slice(3).trim())
      .map((path) => {
        const renameIndex = path.lastIndexOf(' -> ');
        return renameIndex >= 0 ? path.slice(renameIndex + 4).trim() : path;
      })
      .filter(Boolean);
    return JSON.stringify([...new Set(paths)]);
  } catch {
    return '[]';
  }
}

export default defineConfig(({ command, mode }) => {
  const gitSha = resolveGitSha();
  process.env.VITE_GIT_SHA ??= gitSha;
  process.env.VITE_GIT_DIRTY ??= resolveGitDirty();
  process.env.VITE_LIVE_VOICE_CRITICAL_DIRTY_FILES ??= resolveLiveVoiceCriticalDirtyFiles();
  process.env.VITE_BUILD_ID ??= `${command}-${mode}-${gitSha.slice(0, 12)}`;
  return ({
  plugins: [
    ...(command === 'serve' && mode === 'devtools'
      ? [reactDevtoolsStandalonePlugin()]
      : []),
    react(),
  ],
  server: {
    port: 5173,
    proxy: {
      '/api': {
        target: 'http://localhost:8000',
        changeOrigin: true,
        ws: true,
      },
      '/events': {
        target: 'http://localhost:8000',
        changeOrigin: true,
      },
    },
  },
  preview: {
    port: 4173,
  },
  });
});
