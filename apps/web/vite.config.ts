import { execFileSync } from 'node:child_process';

import { defineConfig, type PluginOption } from 'vite';
import react from '@vitejs/plugin-react';

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

export default defineConfig(({ command, mode }) => {
  const gitSha = resolveGitSha();
  process.env.VITE_GIT_SHA ??= gitSha;
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
