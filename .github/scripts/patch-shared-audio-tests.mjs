import { readFileSync, writeFileSync } from 'node:fs';

const path = 'apps/web/src/features/assistant-workspace/live-voice-unified-audio-controller.test.ts';
let text = readFileSync(path, 'utf8');

function replaceOnce(oldText, newText, label) {
  if (!text.includes(oldText)) {
    throw new Error(`Missing ${label}: ${oldText.slice(0, 120)}`);
  }
  text = text.replace(oldText, newText);
}

function transformSection(startMarker, endMarker, transform) {
  const start = text.indexOf(startMarker);
  if (start < 0) throw new Error(`Missing section start: ${startMarker}`);
  const end = endMarker ? text.indexOf(endMarker, start) : text.length;
  if (end < 0) throw new Error(`Missing section end: ${endMarker}`);
  const block = text.slice(start, end);
  text = text.slice(0, start) + transform(block) + text.slice(end);
}

if (!text.includes('mocks.session.cancelOutputItem.mockReset().mockResolvedValue(undefined);')) {
  replaceOnce(
    '  mocks.session.enqueueCue.mockReset().mockResolvedValue(undefined);\n',
    '  mocks.session.enqueueCue.mockReset().mockResolvedValue(undefined);\n'
      + '  mocks.session.cancelOutputItem.mockReset().mockResolvedValue(undefined);\n'
      + '  mocks.session.waitForOutputItem.mockReset().mockResolvedValue(undefined);\n',
    'ownership mock reset marker',
  );
}

if (!text.includes('afterEach(async () => {')) {
  replaceOnce(
    "afterEach(() => {\n  cleanup?.();\n  cleanup = null;\n  document.body.innerHTML = '';\n  vi.restoreAllMocks();\n  vi.unstubAllGlobals();\n});",
    "afterEach(async () => {\n  const hadSharedSession = mocks.createSession.mock.calls.length > 0;\n  cleanup?.();\n  cleanup = null;\n  if (hadSharedSession) {\n    await waitFor(() => expect(mocks.session.stop).toHaveBeenCalled());\n  }\n  document.body.innerHTML = '';\n  vi.restoreAllMocks();\n  vi.unstubAllGlobals();\n});",
    'asynchronous shared-session cleanup',
  );
}

transformSection(
  "  it('generates one transient greeting only after runtime and microphone connection are ready'",
  "  it('does not generate a greeting when the user speaks before startup is ready'",
  (block) => {
    if (block.includes('expect.objectContaining({ generationEpoch: expect.any(Number), outputOrder: 0 })')) {
      return block;
    }
    const marker = "      0,\n      {},\n    ));";
    if (!block.includes(marker)) throw new Error('Missing greeting ownership expectation marker');
    return block.replace(
      marker,
      "      0,\n      expect.objectContaining({ generationEpoch: expect.any(Number), outputOrder: 0 }),\n      {},\n    ));",
    );
  },
);

transformSection(
  "  it('aborts greeting generation and playback when the user begins speaking'",
  "  it('uses the authoritative live-call voice instead of the chat voice setting'",
  (block) => {
    if (!block.includes('let resolveOutput: () => void')) {
      const opening = "  it('aborts greeting generation and playback when the user begins speaking', async () => {\n";
      if (!block.includes(opening)) throw new Error('Missing greeting interruption opening');
      block = block.replace(
        opening,
        opening
          + '    let resolveOutput: () => void = () => undefined;\n'
          + '    mocks.session.waitForOutputItem.mockImplementationOnce(() => new Promise<void>((resolve) => {\n'
          + '      resolveOutput = resolve;\n'
          + '    }));\n',
      );
    }
    if (!block.includes('    resolveOutput();\n')) {
      const closing = "    expect(document.querySelector<HTMLElement>('.assistant-voice-orb')?.dataset.voiceMode).toBe('listening');\n  });";
      if (!block.includes(closing)) throw new Error('Missing greeting interruption closing');
      block = block.replace(
        closing,
        "    expect(document.querySelector<HTMLElement>('.assistant-voice-orb')?.dataset.voiceMode).toBe('listening');\n"
          + '    resolveOutput();\n'
          + '  });',
      );
    }
    return block;
  },
);

text = text.replace(
  '    expect(mocks.createTraceId).not.toHaveBeenCalled();',
  "    expect(mocks.createTraceId).toHaveBeenCalledWith('s1:audio-session');",
);

transformSection(
  "  it('aborts the active request and stops the persistent session on interruption'",
  null,
  (block) => {
    block = block.replace(
      "  it('aborts the active request and stops the persistent session on interruption'",
      "  it('aborts the active request and cancels owned output on interruption'",
    );
    if (!block.includes('let resolveOutput: () => void')) {
      const opening = "  it('aborts the active request and cancels owned output on interruption', async () => {\n";
      if (!block.includes(opening)) throw new Error('Missing response interruption opening');
      block = block.replace(
        opening,
        opening
          + '    let resolveOutput: () => void = () => undefined;\n'
          + '    mocks.session.waitForOutputItem.mockImplementationOnce(() => new Promise<void>((resolve) => {\n'
          + '      resolveOutput = resolve;\n'
          + '    }));\n',
      );
    }
    if (!block.includes('    resolveOutput();\n')) {
      const closing = "    expect(document.querySelector<HTMLElement>('.assistant-voice-orb')?.dataset.voiceMode).toBe('listening');\n  });\n});";
      if (!block.includes(closing)) throw new Error('Missing response interruption closing');
      block = block.replace(
        closing,
        "    expect(document.querySelector<HTMLElement>('.assistant-voice-orb')?.dataset.voiceMode).toBe('listening');\n"
          + '    resolveOutput();\n'
          + '  });\n'
          + '});',
      );
    }
    return block;
  },
);

const required = [
  'afterEach(async () => {',
  'cancelOutputItem.mockReset()',
  'waitForOutputItem.mockReset()',
  "toHaveBeenCalledWith('s1:audio-session')",
  'aborts the active request and cancels owned output on interruption',
];
const missing = required.filter((marker) => !text.includes(marker));
if (missing.length > 0) throw new Error(`Missing patched markers: ${missing.join(', ')}`);

writeFileSync(path, text, 'utf8');
