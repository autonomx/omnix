import fs from 'node:fs';
import path from 'node:path';
import { fileURLToPath } from 'node:url';
import reactHooks from 'eslint-plugin-react-hooks';
import tseslint from 'typescript-eslint';

const webRoot = path.dirname(fileURLToPath(import.meta.url));
const featureRoot = path.join(webRoot, 'src', 'features');
const featureNames = fs.readdirSync(featureRoot, { withFileTypes: true })
  .filter((entry) => entry.isDirectory() && entry.name !== 'shared')
  .map((entry) => entry.name)
  .sort();

const fetchAssignments = [
  {
    selector: 'AssignmentExpression[left.type="MemberExpression"][left.computed=false][left.property.name="fetch"]',
    message: 'Do not replace a fetch implementation; use the API transport layer.',
  },
  {
    selector: 'AssignmentExpression[left.type="MemberExpression"][left.computed=true][left.property.value="fetch"]',
    message: 'Do not replace a fetch implementation; use the API transport layer.',
  },
];

const omnixApiClientAssignments = [
  {
    selector: 'AssignmentExpression[left.type="MemberExpression"][left.object.name="omnixApiClient"]',
    message: 'Do not patch omnixApiClient members; extend the typed API client.',
  },
  {
    selector: 'AssignmentExpression[left.type="MemberExpression"][left.object.type="MemberExpression"][left.object.object.name="omnixApiClient"]',
    message: 'Do not patch omnixApiClient members; extend the typed API client.',
  },
];

const omnixGlobalAssignments = [
  {
    selector: 'AssignmentExpression[left.type="MemberExpression"][left.object.name="window"][left.property.name=/^__omnix/]',
    message: 'Do not add state to window.__omnix; use an explicit module contract.',
  },
  {
    selector: 'AssignmentExpression[left.type="MemberExpression"][left.computed=true][left.object.name="window"][left.property.value=/^__omnix/]',
    message: 'Do not add state to window.__omnix; use an explicit module contract.',
  },
];

const mutationObserver = [
  {
    selector: 'NewExpression[callee.name="MutationObserver"]',
    message: 'New MutationObserver usage needs an explicit allow-list entry.',
  },
];

const bodyInsertion = [
  {
    selector: 'CallExpression[callee.object.object.name="document"][callee.object.property.name="body"][callee.property.name=/^(appendChild|insertBefore)$/]',
    message: 'Do not mutate document.body directly; render through React or an approved portal.',
  },
];

const innerHtmlAssignment = [
  {
    selector: 'AssignmentExpression[left.type="MemberExpression"][left.computed=false][left.property.name="innerHTML"]',
    message: 'Use the approved markdown renderer instead of assigning innerHTML.',
  },
  {
    selector: 'AssignmentExpression[left.type="MemberExpression"][left.computed=true][left.property.value="innerHTML"]',
    message: 'Use the approved markdown renderer instead of assigning innerHTML.',
  },
];

const restrictedSyntax = [
  ...fetchAssignments,
  ...omnixApiClientAssignments,
  ...omnixGlobalAssignments,
  ...mutationObserver,
  ...bodyInsertion,
  ...innerHtmlAssignment,
];

function restrictedFeatureImports(currentFeature) {
  const patterns = [];
  for (const otherFeature of featureNames) {
    if (otherFeature === currentFeature) continue;

    const relativeRoots = [
      ...Array.from({ length: 8 }, (_, depth) => '../'.repeat(depth + 1)),
      ...Array.from({ length: 8 }, (_, depth) => `${'../'.repeat(depth + 1)}features/`),
      '@/features/',
    ];

    for (const root of relativeRoots) {
      const featurePath = `${root}${otherFeature}`;
      patterns.push({
        group: [
          `${featurePath}/*`,
          `${featurePath}/**`,
          `!${featurePath}/index`,
          `!${featurePath}/index.ts`,
        ],
        message: `Import ${otherFeature} through its public index.ts API.`,
      });
    }
  }
  return patterns;
}

const mutationObserverAllowList = [
  'src/features/assistant-workspace/assistant-context-controller.ts',
  'src/features/assistant-workspace/chat-message-stream-audio-controller.ts',
  'src/features/assistant-workspace/desktop-companion-controls.ts',
  'src/features/assistant-workspace/desktop-companion-text-surface.ts',
  'src/features/assistant-workspace/live-avatar-presence.ts',
  'src/features/assistant-workspace/live-voice-controller.ts',
  'src/features/assistant-workspace/live-voice-transcript-autoscroll.ts',
  'src/features/assistant-workspace/live-voice-websocket-enhancer.ts',
  'src/features/assistant-workspace/live-chat-submission-gateway.ts',
  'src/features/chatbot/chat-response-metrics-controller.ts',
  'src/features/chatbot/chat-sidebar-manager.ts',
  'src/features/chatbot/live-chat-workspace.tsx',
  'src/features/chatbot/liveCharacterAvatarBridge.ts',
  'src/features/chatbot/newChatCoordinator.ts',
  'src/features/chatbot/researchProgressController.ts',
  'src/features/chatbot/voice-session-evaluation-workspace.tsx',
  'src/features/rpg/RpgWorkspaceHeader.tsx',
  'src/features/storyteller/story-audio-enhancer.ts',
];

const bodyInsertionAllowList = [
  'src/features/rpg/RpgWorldBundleTransfer.tsx',
  'src/features/storyteller/StoryAudioPanel.tsx',
  'src/features/storyteller/StorytellerWorkspace.tsx',
];

function featureImportTarget(importer, specifier) {
  if (typeof specifier !== 'string') return null;
  let target;
  if (specifier.startsWith('@/features/')) {
    target = path.resolve(featureRoot, specifier.slice('@/features/'.length));
  } else if (specifier.startsWith('.')) {
    target = path.resolve(path.dirname(importer), specifier);
  } else {
    return null;
  }

  const relative = path.relative(featureRoot, target);
  if (relative === '..' || relative.startsWith(`..${path.sep}`) || path.isAbsolute(relative)) {
    return null;
  }
  const [feature, ...publicPath] = relative.split(path.sep);
  if (!featureNames.includes(feature)) return null;
  return { feature, publicPath };
}

const omnixBoundaryPlugin = {
  rules: {
    'no-cross-feature-dynamic-import': {
      meta: {
        type: 'problem',
        docs: { description: 'require public APIs for cross-feature dynamic imports' },
        schema: [],
        messages: {
          deepImport: 'Import {{feature}} through its public index.ts API.',
        },
      },
      create(context) {
        const filename = context.filename ?? context.getFilename();
        const importer = path.relative(featureRoot, filename);
        const currentFeature = importer.split(path.sep)[0];
        if (!featureNames.includes(currentFeature)) return {};
        return {
          ImportExpression(node) {
            const specifier = node.source.type === 'Literal' ? node.source.value : null;
            const target = featureImportTarget(filename, specifier);
            if (
              target
              && target.feature !== currentFeature
              && !(target.publicPath.length === 0 || target.publicPath.join('/') === 'index.ts')
            ) {
              context.report({
                node,
                messageId: 'deepImport',
                data: { feature: target.feature },
              });
            }
          },
        };
      },
    },
    'no-app-direct-feature-dynamic-import': {
      meta: {
        type: 'problem',
        docs: { description: 'route application feature loading through ModuleWorkspace or manifests' },
        schema: [],
        messages: {
          directImport: 'Application shell modules must load features through ModuleWorkspace or a manifest.',
        },
      },
      create(context) {
        const filename = context.filename ?? context.getFilename();
        if (!filename.includes(`${path.sep}src${path.sep}app${path.sep}`)) return {};
        if (/[/\\](?:modules|[^/\\]*Manifest)\.(?:[cm]?[jt]sx?)$/i.test(filename)) return {};
        return {
          ImportExpression(node) {
            const specifier = node.source.type === 'Literal' ? node.source.value : null;
            if (typeof specifier !== 'string') return;
            const resolved = specifier.startsWith('@/features/')
              ? path.resolve(featureRoot, specifier.slice('@/features/'.length))
              : specifier.startsWith('.')
                ? path.resolve(path.dirname(filename), specifier)
                : null;
            if (!resolved) return;
            const relative = path.relative(featureRoot, resolved).replaceAll('\\', '/');
            const isWorkspace = relative === 'ModuleWorkspace' || relative === 'ModuleWorkspace.tsx';
            const isFeature = featureNames.some((feature) => (
              relative === feature || relative.startsWith(`${feature}/`)
            ));
            if (isFeature && !isWorkspace) {
              context.report({ node, messageId: 'directImport' });
            }
          },
        };
      },
    },
  },
};

function restrictedSyntaxConfig(files, restrictions) {
  return {
    files,
    rules: {
      'no-restricted-syntax': ['error', ...restrictions],
    },
  };
}

const defaultSyntax = restrictedSyntax;
const withoutMutationObserver = restrictedSyntax.filter(
  (restriction) => !mutationObserver.includes(restriction),
);
const withoutBodyInsertion = restrictedSyntax.filter(
  (restriction) => !bodyInsertion.includes(restriction),
);
const withoutInnerHtml = restrictedSyntax.filter(
  (restriction) => !innerHtmlAssignment.includes(restriction),
);

const appImports = {
  patterns: [
    {
      group: [
        '../features/**',
        '../../features/**',
        '@/features/**',
        '!../features/ModuleWorkspace',
        '!../features/ModuleWorkspace.tsx',
        '!../../features/ModuleWorkspace',
        '!../../features/ModuleWorkspace.tsx',
      ],
      message: 'Application shell modules must load features through ModuleWorkspace or a manifest.',
    },
  ],
};

export default [
  {
    ignores: [
      'dist/**',
      'node_modules/**',
      'coverage/**',
      'playwright-report/**',
      'test-results/**',
    ],
  },
  ...tseslint.configs.recommended,
  {
    files: ['**/*.{js,jsx,ts,tsx,mjs,cjs,mts,cts}'],
    plugins: {
      'react-hooks': reactHooks,
      omnix: omnixBoundaryPlugin,
    },
    rules: {
      'react-hooks/rules-of-hooks': 'error',
      'react-hooks/exhaustive-deps': 'warn',
      'no-restricted-syntax': ['error', ...defaultSyntax],
    },
  },
  ...mutationObserverAllowList.map((file) => restrictedSyntaxConfig(
    [file],
    withoutMutationObserver,
  )),
  ...bodyInsertionAllowList.map((file) => restrictedSyntaxConfig(
    [file],
    withoutBodyInsertion,
  )),
  restrictedSyntaxConfig(
    ['src/features/chatbot/markdownRenderer.ts'],
    withoutInnerHtml,
  ),
  ...featureNames.map((feature) => ({
    files: [`src/features/${feature}/**/*.{js,jsx,ts,tsx}`],
    rules: {
      'no-restricted-imports': ['error', {
        patterns: restrictedFeatureImports(feature),
      }],
    },
  })),
  {
    files: ['src/features/**/*.{js,jsx,ts,tsx}'],
    rules: {
      'omnix/no-cross-feature-dynamic-import': 'error',
    },
  },
  {
    files: ['src/app/**/*.{js,jsx,ts,tsx}'],
    ignores: ['src/app/modules.ts', 'src/app/*Manifest.ts'],
    rules: {
      'no-restricted-imports': ['error', appImports],
      'omnix/no-app-direct-feature-dynamic-import': 'error',
    },
  },
];
