from __future__ import annotations

from pathlib import Path


def replace_exact(path: str, old: str, new: str, *, count: int = 1) -> None:
    target = Path(path)
    text = target.read_text(encoding="utf-8")
    found = text.count(old)
    if found != count:
        raise SystemExit(f"{path}: expected {count} occurrence(s), found {found}: {old[:120]!r}")
    target.write_text(text.replace(old, new, count), encoding="utf-8")


replace_exact(
    "src/apps/web/src/app/modules.test.ts",
    "  'image-generation',\n  'providers',",
    "  'image-generation',\n  'trading',\n  'providers',",
)

replace_exact(
    "src/apps/web/src/features/image-generation/latestImageResult.spec.ts",
    "    expect(imageAssetUrl('image:test')).toBe('/api/assets/image%3Atest/file');",
    "    expect(imageAssetUrl('image:test')).toBe('/api/assets/image%3Atest/file?preview=true');",
)

replace_exact(
    "src/apps/web/src/features/image-generation/ImageLatestResult.spec.tsx",
    "'/api/assets/image%3Anight/file'",
    "'/api/assets/image%3Anight/file?preview=true'",
    count=3,
)

replace_exact(
    "src/apps/web/src/features/assistant-workspace/live-speech-synthesis-options.test.ts",
    "        maximum_additional_delay_ms: 350,",
    "        maximum_additional_delay_ms: 120,",
)

unified = "src/apps/web/src/features/assistant-workspace/live-voice-unified-audio-controller.test.ts"
replace_exact(
    unified,
    "    await waitFor(() => expect(mocks.session.enqueueOutputPhrase).toHaveBeenCalledTimes(2));\n    expect(mocks.session.setStartPolicy).toHaveBeenCalledTimes(1);",
    "    await waitFor(() => expect(mocks.session.enqueueOutputPhrase).toHaveBeenCalledTimes(3));\n    expect(mocks.session.setStartPolicy).toHaveBeenCalledTimes(1);",
)
replace_exact(
    unified,
    """    expect(mocks.session.enqueueOutputPhrase).toHaveBeenNthCalledWith(
      1,
      'Hello there. This first phrase is ready for speech.',
      0,
      expect.objectContaining({ generationEpoch: expect.any(Number), outputOrder: 0 }),
      {},
    );
    expect(mocks.session.enqueueOutputPhrase).toHaveBeenNthCalledWith(
      2,
      'The second phrase should enter the same continuous queue.',
      1,
      expect.objectContaining({ generationEpoch: expect.any(Number), outputOrder: 1 }),
      {},
    );""",
    """    expect(mocks.session.enqueueOutputPhrase).toHaveBeenNthCalledWith(
      1,
      'Hello there.',
      0,
      expect.objectContaining({ generationEpoch: expect.any(Number), outputOrder: 0 }),
      {},
    );
    expect(mocks.session.enqueueOutputPhrase).toHaveBeenNthCalledWith(
      2,
      'This first phrase is ready for speech.',
      1,
      expect.objectContaining({ generationEpoch: expect.any(Number), outputOrder: 1 }),
      {},
    );
    expect(mocks.session.enqueueOutputPhrase).toHaveBeenNthCalledWith(
      3,
      'The second phrase should enter the same continuous queue.',
      2,
      expect.objectContaining({ generationEpoch: expect.any(Number), outputOrder: 2 }),
      {},
    );""",
)
replace_exact(
    unified,
    "    await waitFor(() => expect(mocks.session.waitForOutputItem).toHaveBeenCalledTimes(2));",
    "    await waitFor(() => expect(mocks.session.waitForOutputItem).toHaveBeenCalledTimes(3));",
)
replace_exact(
    unified,
    "      expect.objectContaining({ phrases: 2, text_chunks: 2, assistant_turn_id: 'assistant-turn:t1', turn_kind: 'response' }),",
    "      expect.objectContaining({ phrases: 3, text_chunks: 2, assistant_turn_id: 'assistant-turn:t1', turn_kind: 'response' }),",
)
replace_exact(
    unified,
    """    await waitFor(() => expect(mocks.session.enqueueOutputPhrase).toHaveBeenCalledWith(
      'Hey there! How is your day going?',
      0,
      expect.objectContaining({ generationEpoch: expect.any(Number), outputOrder: 0 }),
      {},
    ));""",
    """    await waitFor(() => expect(mocks.session.enqueueOutputPhrase).toHaveBeenCalledTimes(2));
    expect(mocks.session.enqueueOutputPhrase).toHaveBeenNthCalledWith(
      1,
      'Hey there!',
      0,
      expect.objectContaining({ generationEpoch: expect.any(Number), outputOrder: 0 }),
      {},
    );
    expect(mocks.session.enqueueOutputPhrase).toHaveBeenNthCalledWith(
      2,
      'How is your day going?',
      1,
      expect.objectContaining({ generationEpoch: expect.any(Number), outputOrder: 1 }),
      {},
    );""",
)
replace_exact(
    unified,
    """    window.dispatchEvent(new CustomEvent('omnix:assistant-live-voice-call-connected'));

    await waitFor(() => expect(mocks.session.enqueueOutputPhrase).toHaveBeenCalledTimes(1));
    const greetingCall = fetchMock.mock.calls.find(([input]) => requestPath(input).endsWith('/live-call/greeting/stream'));""",
    """    window.dispatchEvent(new CustomEvent('omnix:assistant-live-voice-call-connected'));

    await waitFor(() => expect(mocks.session.enqueueOutputPhrase).toHaveBeenCalledTimes(2));
    const greetingCall = fetchMock.mock.calls.find(([input]) => requestPath(input).endsWith('/live-call/greeting/stream'));""",
)

ordering = "src/apps/web/src/features/assistant-workspace/live-voice-unified-audio-ordering-regression.test.ts"
replace_exact(
    ordering,
    """  const reporter = {
    traceId: 'live-call:s1:ordering-regression',
    record: vi.fn(),""",
    """  const recordSpy = vi.fn();
  const reporter = {
    traceId: 'live-call:s1:ordering-regression',
    record: recordSpy,""",
)
replace_exact(
    ordering,
    """    reporter,
    createSession:""",
    """    reporter,
    recordSpy,
    createSession:""",
)
replace_exact(
    ordering,
    "  mocks.reporter.record.mockReset();",
    "  mocks.recordSpy.mockReset();\n  mocks.reporter.record = mocks.recordSpy;",
)
replace_exact(
    ordering,
    "    await waitFor(() => expect(mocks.reporter.record).toHaveBeenCalledWith(",
    "    await waitFor(() => expect(mocks.recordSpy).toHaveBeenCalledWith(",
)

replace_exact(
    "src/apps/web/src/features/chatbot/CharacterManagementPanel.test.tsx",
    "      if (path === '/api/characters/character%3Amaya/avatar-pack') return Response.json(pack);",
    "      if (path === '/api/characters/character%3Amaya/avatar-pack/optional') return Response.json(pack);",
)

print("PR #1494 web CI completion patch applied")
