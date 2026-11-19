import type { ProviderFacadePayload } from '../../api/client';
import { TaskModelSection } from './TaskModelSection';

/** The routing override memory reads (backend ``assistant_memory.model_route.MEMORY_ROUTE_KEY``). */
export const MEMORY_ROUTE_KEY = 'assistant-memory';

/**
 * Which provider and model memory uses: reading chats for what to remember and what each character knows about the
 * person. Unset, it follows the default provider (on the Claude CLI, chats are read with Sonnet).
 */
export function MemoryModelSection({ payload }: { payload?: ProviderFacadePayload }) {
  return (
    <TaskModelSection
      payload={payload}
      routeKey={MEMORY_ROUTE_KEY}
      title="Memory model"
      description="Reads your chats after each turn for what to remember and what each character knows about you. It runs in the background, so a slower, smarter model costs no reply time."
      providerLabel="Memory provider"
      modelLabel="Memory model"
      modelHelp={(provider, modelChosen) => (!modelChosen && provider === 'claude_cli' ? 'Provider default: Sonnet reads chats; the Claude CLI model picks memories.' : undefined)}
    />
  );
}
