from pathlib import Path

path = Path("apps/web/src/features/chatbot/MemoryManagementPanel.tsx")
text = path.read_text(encoding="utf-8")
old = """  const candidateMutation = useMutation({
    mutationFn: (input: { id: string; action: 'approve' | 'reject' }) => input.action === 'approve'
      ? memoryClient.approve(sessionId ?? '', input.id)
      : memoryClient.reject(sessionId ?? '', input.id),
"""
new = """  const candidateMutation = useMutation({
    mutationFn: async (input: { id: string; action: 'approve' | 'reject' }) => {
      if (input.action === 'approve') return await memoryClient.approve(sessionId ?? '', input.id);
      return await memoryClient.reject(sessionId ?? '', input.id);
    },
"""
if text.count(old) != 1:
    raise SystemExit("candidate mutation pattern not found exactly once")
path.write_text(text.replace(old, new, 1), encoding="utf-8")
