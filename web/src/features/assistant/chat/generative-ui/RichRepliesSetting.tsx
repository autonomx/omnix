import { useMutation, useQueryClient } from '@tanstack/react-query';
import { assistantApiClient, type ChatRichReplies } from '../../api/assistantClient';

type Choice = 'default' | 'on' | 'off';

/**
 * The current chat's rich-replies setting (GUI-3.1). It is stored on the session, so what the
 * model sees in history does not depend on the browser; models that have not passed the
 * evaluation gate never get blocks, whatever this says.
 */
export function RichRepliesSetting({ sessionId, value }: { sessionId: string | null; value: ChatRichReplies | undefined }) {
  const queryClient = useQueryClient();
  const mutation = useMutation({
    mutationFn: (richReplies: ChatRichReplies) => assistantApiClient.setChatRichReplies(sessionId ?? '', richReplies),
    onSuccess: () => Promise.all([
      queryClient.invalidateQueries({ queryKey: ['feature', 'chatbot', 'session', sessionId] }),
      queryClient.invalidateQueries({ queryKey: ['feature', 'chatbot', 'sessions'] }),
    ]),
  });
  const current: Choice = value === 'on' || value === 'off' ? value : 'default';
  return (
    <div>
      <label htmlFor="assistant-rich-replies">Rich replies in this chat</label>
      <select
        id="assistant-rich-replies"
        aria-label="Rich replies in this chat"
        value={current}
        disabled={!sessionId || mutation.isPending}
        onChange={(event) => {
          const choice = event.currentTarget.value as Choice;
          mutation.mutate(choice === 'default' ? null : choice);
        }}
      >
        <option value="default">Default (off)</option>
        <option value="on">On</option>
        <option value="off">Off</option>
      </select>
      <small>
        {sessionId
          ? 'Headline numbers, charts, sources and suggested replies, for models that passed the rich-reply evaluation.'
          : 'Open a chat to change its setting.'}
        {mutation.isError ? ' The setting could not be saved.' : ''}
      </small>
    </div>
  );
}
