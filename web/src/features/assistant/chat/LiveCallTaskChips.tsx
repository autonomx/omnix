import {
  cancelLiveCallTask,
  decideProposalQuestion,
  openCallTasks,
  proposalButtonsVisible,
  useLiveCallTasks,
  useProposalQuestion,
  type LiveCallTask,
} from '../workspace';
import './LiveCallTaskChips.css';

/**
 * What the call is working on (live companion roadmap WP 1.4): one chip per open task, each with Cancel. The task's
 * state comes from the server; a finished task leaves the row and the call reports it aloud. While the call asks
 * about an action it proposed (WP 1.5), Confirm and Cancel answer it as a spoken "confirm" or "cancel" would.
 */
export function LiveCallTaskChips({ className }: { className?: string }) {
  const tasks = useLiveCallTasks();
  const open = openCallTasks(tasks);
  const proposal = <LiveCallProposalButtons sessionId={tasks.sessionId} />;
  if (!open.length) return proposal;
  return (
    <>
      {proposal}
      <ul className={['live-call-task-chips', className].filter(Boolean).join(' ')} aria-label="Working on it">
        {open.map((task) => {
          const cancelling = tasks.cancelling.includes(task.task_id);
          const label = taskLabel(task);
          return (
            <li key={task.task_id} className="live-call-task-chip" data-task-state={task.state}>
              <span className="live-call-task-chip-spinner" aria-hidden="true" />
              <span className="live-call-task-chip-label" title={task.query || undefined}>{label}</span>
              <button
                type="button"
                onClick={() => void cancelLiveCallTask(task.task_id)}
                disabled={cancelling}
                aria-label={`Cancel: ${label}`}
              >
                {cancelling ? 'Cancelling…' : 'Cancel'}
              </button>
            </li>
          );
        })}
      </ul>
    </>
  );
}

function LiveCallProposalButtons({ sessionId }: { sessionId: string | null }) {
  const question = useProposalQuestion();
  if (question.outcome && question.question?.sessionId === sessionId) {
    return (
      <p className="live-call-proposal" role="status" data-outcome={question.outcome.status}>
        {question.outcome.text}
      </p>
    );
  }
  if (!sessionId || !proposalButtonsVisible(question, sessionId)) return null;
  return (
    <div className="live-call-proposal" role="group" aria-label="Answer the question">
      <button type="button" onClick={() => void decideProposalQuestion('confirm')} disabled={question.deciding}>
        Confirm
      </button>
      <button type="button" onClick={() => void decideProposalQuestion('cancel')} disabled={question.deciding}>
        Cancel
      </button>
    </div>
  );
}

function taskLabel(task: LiveCallTask): string {
  const kind = task.ability === 'deep_research' || !task.ability ? 'Researching' : `Working on ${task.ability.replace(/_/g, ' ')}`;
  const query = task.query.replace(/\s+/g, ' ').trim();
  if (!query) return kind;
  return `${kind}: ${query.length > 60 ? `${query.slice(0, 59).trimEnd()}…` : query}`;
}
