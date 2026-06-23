# Omnix Assistant Workspace Phase 5

Phase 5 adds the context assembly layer.

## Scope

- ContextAssembly contract.
- ContextSource provenance contract.
- Instruction, memory, knowledge, identity, and tool context inputs.
- Pure assembly helper.

## Acceptance Criteria

- Conversation projection is only one context input.
- Instructions, memories, knowledge, identity, tools, provider, and model can be assembled together.
- Sources record why each context item was included.
- Context assembly remains UI independent.

## Files

- `apps/web/src/features/assistant-workspace/context.ts`
- `apps/web/src/features/assistant-workspace/context.test.ts`
