import {
  omnixApiClient,
  type ChatSession,
  type JobRecord,
  type SendChatMessageRequest,
  type SendChatMessageResponse,
} from '../../api/client';
import { renderAssistantMessageHtml } from './markdownRenderer';

const INSTALLED_KEY = '__omnix_research_progress_controller__';
const PANEL_ATTRIBUTE = 'data-omnix-research-progress';
const MESSAGE_DETAILS_ATTRIBUTE = 'data-omnix-research-message-details';
const MESSAGE_CONTENT_ATTRIBUTE = 'data-omnix-message-content';
const INJECTED_MESSAGE_ATTRIBUTE = 'data-omnix-research-message-id';
const RESEARCH_JOB_TYPE = 'assistant.deep_research';
const POLL_INTERVAL_MS = 1_500;
const ACTIVE_STATUSES = new Set(['queued', 'leased', 'running', 'waiting', 'retrying', 'cancel_requested']);
const TERMINAL_STATUSES = new Set(['completed', 'failed', 'canceled', 'stale']);

type AnyWindow = Window & Record<string, unknown>;
type ChatMessage = NonNullable<ChatSession['messages']>[number];
type ClientPatch = {
  getChatSession: (sessionId: string) => Promise<ChatSession>;
  sendChatMessage: (sessionId: string, request: SendChatMessageRequest) => Promise<SendChatMessageResponse>;
};

let activeSession: ChatSession | null = null;
let activeJob: JobRecord | null = null;
let pollTimer: number | null = null;
let pollingJobId: string | null = null;
let currentSessionId: string | null = null;
let recoveringSessionId: string | null = null;
let originalGetChatSession: ClientPatch['getChatSession'] | null = null;
const dismissedJobIds = new Set<string>();

export function installResearchProgressController(): void {
  if (typeof window === 'undefined' || typeof document === 'undefined') return;
  const runtimeWindow = window as unknown as AnyWindow;
  if (runtimeWindow[INSTALLED_KEY]) return;
  runtimeWindow[INSTALLED_KEY] = true;
  patchApiClient();
  const mount = () => renderResearchUi();
  if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', mount, { once: true });
  else mount();
  const observer = new MutationObserver(mount);
  observer.observe(document.body, { childList: true, subtree: true });
  document.addEventListener('click', handleResearchReportAction);
  window.addEventListener('beforeunload', stopPolling, { once: true });
}

function patchApiClient(): void {
  const client = omnixApiClient as unknown as ClientPatch;
  originalGetChatSession = client.getChatSession.bind(omnixApiClient);
  const originalSendChatMessage = client.sendChatMessage.bind(omnixApiClient);

  client.getChatSession = async (sessionId: string) => {
    const session = await originalGetChatSession?.(sessionId);
    if (!session) throw new Error('Chat session could not be loaded.');
    captureSession(session);
    return session;
  };

  client.sendChatMessage = async (sessionId: string, request: SendChatMessageRequest) => {
    const result = await originalSendChatMessage(sessionId, request);
    captureSession(result.session);
    if (result.job?.type === RESEARCH_JOB_TYPE) {
      activeJob = result.job;
      currentSessionId = sessionId;
      renderResearchUi();
      startPolling(result.job.id);
    }
    return result;
  };
}

function captureSession(session: ChatSession): void {
  const sessionChanged = currentSessionId !== null && currentSessionId !== session.id;
  if (sessionChanged) {
    activeJob = null;
    stopPolling();
  }
  activeSession = session;
  currentSessionId = session.id;
  enhanceResearchMessages(session);
  const jobId = preferredResearchJobId(session.messages ?? [], activeJob);
  if (!jobId) {
    if (!isActiveResearchJob(activeJob)) stopPolling();
    void recoverLatestResearchJob(session.id);
    renderResearchUi();
    return;
  }
  if (!isActiveResearchJob(activeJob)) void recoverLatestResearchJob(session.id, jobId);
  if (activeJob?.id !== jobId || isActiveResearchJob(activeJob)) startPolling(jobId);
  renderResearchUi();
}

function startPolling(jobId: string): void {
  if (pollingJobId === jobId && pollTimer !== null) return;
  stopPolling();
  pollingJobId = jobId;
  void pollResearchJob(jobId);
  pollTimer = window.setInterval(() => void pollResearchJob(jobId), POLL_INTERVAL_MS);
}

function stopPolling(): void {
  if (pollTimer !== null) window.clearInterval(pollTimer);
  pollTimer = null;
  pollingJobId = null;
}

function handleResearchReportAction(event: Event): void {
  const target = event.target instanceof Element
    ? event.target.closest<HTMLButtonElement>('[data-omnix-research-report-download], [data-omnix-research-report-expand]')
    : null;
  const report = target?.closest<HTMLElement>('.assistant-research-report');
  if (!target || !report) return;

  if (target.hasAttribute('data-omnix-research-report-download')) {
    downloadResearchReport(report);
    return;
  }

  const expanded = report.classList.toggle('is-expanded');
  report.closest<HTMLElement>('.assistant-chat-message')?.classList.toggle('assistant-chat-message-report-expanded', expanded);
  target.setAttribute('aria-pressed', String(expanded));
  target.setAttribute('aria-label', expanded ? 'Collapse research report' : 'Expand research report');
  target.setAttribute('title', expanded ? 'Collapse report' : 'Expand report');
  target.textContent = expanded ? '×' : '⛶';
  if (expanded) report.scrollIntoView({ block: 'nearest' });
}

function downloadResearchReport(report: HTMLElement): void {
  const host = report.closest<HTMLElement>('[data-raw-content]');
  const content = host?.dataset.rawContent || report.querySelector<HTMLElement>('.assistant-research-report-body')?.innerText || '';
  const blob = new Blob([content], { type: 'text/markdown;charset=utf-8' });
  const url = URL.createObjectURL(blob);
  const link = document.createElement('a');
  link.href = url;
  link.download = 'omnix-research-report.md';
  document.body.append(link);
  link.click();
  link.remove();
  window.setTimeout(() => URL.revokeObjectURL(url), 0);
}

async function pollResearchJob(jobId: string): Promise<void> {
  try {
    const job = await omnixApiClient.getJob(jobId);
    if (pollingJobId !== jobId) return;
    activeJob = job;
    renderResearchUi();
    if (!TERMINAL_STATUSES.has(String(job.status))) return;
    if (currentSessionId && await recoverLatestResearchJob(currentSessionId, job.id)) return;
    stopPolling();
    if (currentSessionId && originalGetChatSession) {
      const refreshed = await originalGetChatSession(currentSessionId);
      activeSession = refreshed;
      enhanceResearchMessages(refreshed);
      injectCompletedResearchMessage(refreshed, job.id);
      dispatchRefreshSignal();
      renderResearchUi();
    }
  } catch {
    renderResearchUi('Research progress could not be refreshed.');
  }
}

function renderResearchUi(errorMessage?: string): void {
  reconcileInjectedMessages();
  if (activeSession) enhanceResearchMessages(activeSession);
  const messages = document.querySelector<HTMLElement>('.assistant-chat-messages');
  if (!messages) return;
  let panel = document.querySelector<HTMLElement>(`[${PANEL_ATTRIBUTE}]`);
  const jobId = preferredResearchJobId(activeSession?.messages ?? [], activeJob);
  if (!jobId) {
    panel?.remove();
    return;
  }
  if (dismissedJobIds.has(jobId) && (!activeJob || !isActiveResearchJob(activeJob))) {
    panel?.remove();
    return;
  }
  if (activeJob?.id === jobId && String(activeJob.status) === 'completed') {
    panel?.remove();
    return;
  }
  if (!panel) {
    panel = document.createElement('section');
    panel.setAttribute(PANEL_ATTRIBUTE, 'true');
    panel.className = 'assistant-research-progress';
    messages.insertAdjacentElement('afterend', panel);
  }
  if (errorMessage && !activeJob) {
    setPanelHtml(panel, `<p role="status">${escapeHtml(errorMessage)}</p>`, `error:${errorMessage}`);
    return;
  }
  if (!activeJob || activeJob.id !== jobId) {
    if (panel.dataset.renderKey === `restoring:${jobId}`) {
      startPolling(jobId);
      return;
    }
    panel.dataset.renderKey = `restoring:${jobId}`;
    panel.innerHTML = '<p role="status">Restoring research progress…</p>';
    startPolling(jobId);
    return;
  }
  renderJobPanel(panel, activeJob);
}

export function renderJobPanel(panel: HTMLElement, job: JobRecord): void {
  if (awaitingResearchPlanApproval(job)) {
    renderResearchPlanReview(panel, job);
    return;
  }
  if (isActiveResearchJob(job) && hasSavedResearchPlan(job)) {
    renderResearchPlanProgress(panel, job);
    return;
  }
  if (isStalledResearchJob(job)) {
    renderStalledResearchJob(panel, job);
    return;
  }
  const announcement = researchStageAnnouncement(job);
  const previousAnnouncement = panel.dataset.announcement;
  const details = researchJobOutput(job);
  const active = isActiveResearchJob(job);
  panel.className = `assistant-research-progress status-${String(job.status)}`;
  const html = `
    <header>
      <div><p class="eyebrow">Deep research</p><h3>${escapeHtml(researchStageLabel(job))}</h3></div>
      <div class="assistant-research-header-actions">
        <span class="assistant-research-status">${escapeHtml(humanizeCode(String(job.status)))}</span>
        ${active ? '' : '<button type="button" class="assistant-research-close" data-omnix-research-close aria-label="Close research progress">&times;</button>'}
      </div>
    </header>
    <div class="assistant-research-progress-track" aria-hidden="true"><span style="width:${researchProgressPercent(job)}%"></span></div>
    <p class="assistant-research-announcement" aria-live="polite" aria-atomic="true">${escapeHtml(announcement)}</p>
    <div class="assistant-research-progress-actions">
      ${active ? `<button type="button" data-omnix-research-cancel ${String(job.status) === 'cancel_requested' ? 'disabled' : ''}>${String(job.status) === 'cancel_requested' ? 'Cancellation requested' : 'Cancel research'}</button>` : ''}
      <small>${completedStageCount(job)} of ${job.stages?.length ?? 0} stages complete</small>
    </div>
    ${details ? renderJobDetails(details) : ''}
  `;
  if (!setPanelHtml(panel, html, researchPanelRenderKey(job, announcement, details))) return;
  panel.dataset.announcement = announcement;
  if (previousAnnouncement === announcement) {
    const live = panel.querySelector<HTMLElement>('.assistant-research-announcement');
    live?.removeAttribute('aria-live');
  }
  panel.querySelector<HTMLButtonElement>('[data-omnix-research-close]')?.addEventListener('click', () => {
    dismissedJobIds.add(job.id);
    panel.remove();
  });
  panel.querySelector<HTMLButtonElement>('[data-omnix-research-cancel]')?.addEventListener('click', (event) => {
    const button = event.currentTarget as HTMLButtonElement;
    button.disabled = true;
    button.textContent = 'Canceling…';
    void omnixApiClient.cancelJob(job.id, 'Canceled by the user from the research progress panel.')
      .then((updated) => {
        activeJob = updated;
        renderResearchUi();
      })
      .catch(() => {
        button.disabled = false;
        button.textContent = 'Cancel research';
        button.insertAdjacentHTML('afterend', '<span role="alert">Cancellation failed.</span>');
      });
  });
}

function hasSavedResearchPlan(job: JobRecord): boolean {
  const plan = asRecord(asRecord(job.input_payload).research_plan);
  return Boolean(stringValue(plan.title) || stringList(plan.steps).length);
}

function renderResearchPlanProgress(panel: HTMLElement, job: JobRecord): void {
  const input = asRecord(job.input_payload);
  const plan = researchPlanSteps(job);
  const completedCount = Math.min(plan.length, completedStageCount(job));
  const maxPages = researchMaxPages(job);
  const announcement = researchStageAnnouncement(job);
  const html = `
    <header>
      <div><p class="eyebrow">Deep research</p><h3>${escapeHtml(researchPlanTitle(job))}</h3></div>
      <span class="assistant-research-status">${escapeHtml(humanizeCode(String(job.status)))}</span>
    </header>
    <div class="assistant-research-progress-track" aria-hidden="true"><span style="width:${researchProgressPercent(job)}%"></span></div>
    <p class="assistant-research-plan-intro" role="status">${escapeHtml(announcement)} The completed outline areas are marked below.</p>
    <ol class="assistant-research-plan-list" aria-label="Research outline progress">
      ${plan.map((step, index) => `<li class="${index < completedCount ? 'is-completed' : ''}"><i aria-hidden="true">${index < completedCount ? '✓' : ''}</i><span>${escapeHtml(step)}</span></li>`).join('')}
    </ol>
    <div class="assistant-research-plan-controls">
      <label>Max pages to search<input type="number" min="1" max="100" value="${maxPages}" readonly aria-label="Research maximum pages"></label>
      <small>A hard cap on unique pages searched for this run.</small>
    </div>
    <div class="assistant-research-progress-actions assistant-research-plan-actions">
      <small>${completedCount} of ${plan.length} outline areas complete</small>
      <button type="button" data-omnix-research-cancel ${String(job.status) === 'cancel_requested' ? 'disabled' : ''}>${String(job.status) === 'cancel_requested' ? 'Cancellation requested' : 'Cancel research'}</button>
    </div>
  `;
  panel.className = `assistant-research-progress status-${String(job.status)} status-plan-progress`;
  if (!setPanelHtml(panel, html, `plan-progress:${job.id}:${JSON.stringify({ input, stages: job.stages, progress: job.progress })}`)) return;
  panel.querySelector<HTMLButtonElement>('[data-omnix-research-cancel]')?.addEventListener('click', (event) => {
    const button = event.currentTarget as HTMLButtonElement;
    button.disabled = true;
    button.textContent = 'Canceling…';
    void omnixApiClient.cancelJob(job.id, 'Canceled by the user from the research progress panel.')
      .then((updated) => {
        activeJob = updated;
        renderResearchUi();
      })
      .catch(() => {
        button.disabled = false;
        button.textContent = 'Cancel research';
      });
  });
}

async function recoverLatestResearchJob(sessionId: string, excludeJobId?: string): Promise<boolean> {
  if (recoveringSessionId === sessionId) return false;
  recoveringSessionId = sessionId;
  try {
    const response = await omnixApiClient.listJobs({ limit: 100, full: true });
    if (currentSessionId !== sessionId) return false;
    const recovered = latestActiveResearchJobForSession(response.jobs ?? [], sessionId, excludeJobId);
    if (!recovered) return false;
    if (activeJob && isActiveResearchJob(activeJob)) {
      const activeCreatedAt = Date.parse(String(activeJob.created_at ?? '')) || 0;
      const recoveredCreatedAt = Date.parse(String(recovered.created_at ?? '')) || 0;
      if (activeCreatedAt >= recoveredCreatedAt) return false;
    }
    activeJob = recovered;
    renderResearchUi();
    startPolling(recovered.id);
    return true;
  } catch {
    return false;
  } finally {
    if (recoveringSessionId === sessionId) recoveringSessionId = null;
  }
}

function renderStalledResearchJob(panel: HTMLElement, job: JobRecord): void {
  const maxPages = researchMaxPages(job);
  const html = `
    <header>
      <div><p class="eyebrow">Deep research</p><h3>Research needs restarting</h3></div>
      <span class="assistant-research-status">Paused</span>
    </header>
    <p class="assistant-research-announcement" role="status">The research worker stopped before it began. Restarting preserves this plan and its ${maxPages}-page limit.</p>
    <div class="assistant-research-progress-actions assistant-research-plan-actions">
      <small>No pages have been searched yet.</small>
      <button type="button" class="assistant-research-start" data-omnix-research-restart>Restart research</button>
    </div>
  `;
  panel.className = 'assistant-research-progress status-stalled';
  if (!setPanelHtml(panel, html, `stalled:${job.id}:${JSON.stringify(job.input_payload ?? {})}`)) return;
  panel.querySelector<HTMLButtonElement>('[data-omnix-research-restart]')?.addEventListener('click', () => {
    const button = panel.querySelector<HTMLButtonElement>('[data-omnix-research-restart]');
    if (!button) return;
    button.disabled = true;
    button.textContent = 'Restartingâ€¦';
    void omnixApiClient.startDeepResearchPlan(job.id)
      .then((updated) => {
        activeJob = updated;
        startPolling(updated.id);
        renderResearchUi();
      })
      .catch(() => renderResearchPlanActionError(panel, button, 'The research worker could not be restarted.'));
  });
}

function renderResearchPlanReview(panel: HTMLElement, job: JobRecord): void {
  const input = asRecord(job.input_payload);
  const title = researchPlanTitle(job);
  const plan = researchPlanSteps(job);
  const maxPages = researchMaxPages(job);
  const plannerBackend = stringValue(input.planner_backend);
  const outlineStatus = ['provider', 'hermes'].includes(plannerBackend) ? 'AI outline ready' : 'Outline ready';
  const html = `
    <header>
      <div><p class="eyebrow">Deep research</p><h3>${escapeHtml(title)}</h3></div>
      <span class="assistant-research-status">${outlineStatus}</span>
    </header>
    <p class="assistant-research-plan-intro" role="status">Here’s the AI-generated research outline I’ll follow before writing the answer. No web pages have been searched yet.</p>
    <ol class="assistant-research-plan-list" aria-label="Research outline">
      ${plan.map((step) => `<li><i aria-hidden="true"></i><span>${escapeHtml(step)}</span></li>`).join('')}
    </ol>
    <div class="assistant-research-plan-controls">
      <label>Max pages to search<input type="number" min="1" max="100" step="1" value="${maxPages}" readonly aria-label="Research plan maximum pages" aria-describedby="omnix-research-plan-page-help"></label>
      <small id="omnix-research-plan-page-help">A hard cap on unique pages searched for this run.</small>
    </div>
    <div class="assistant-research-progress-actions assistant-research-plan-actions">
      <button type="button" data-omnix-research-plan-update>Edit</button>
      <span>
        <button type="button" data-omnix-research-plan-cancel>Cancel</button>
        <button type="button" class="assistant-research-start" data-omnix-research-plan-start>Start research</button>
      </span>
    </div>
  `;
  panel.className = 'assistant-research-progress status-plan-review';
  if (!setPanelHtml(panel, html, `plan:${job.id}:${JSON.stringify(job.input_payload ?? {})}`)) return;

  const pageInput = panel.querySelector<HTMLInputElement>('[aria-label="Research plan maximum pages"]');
  const updateButton = panel.querySelector<HTMLButtonElement>('[data-omnix-research-plan-update]');
  let editing = false;
  const persistPageLimit = async (): Promise<JobRecord> => {
    const selectedPages = normalizedPageLimit(pageInput?.value);
    if (selectedPages === null) throw new Error('Choose a page limit from 1 to 100.');
    if (selectedPages === maxPages) return job;
    return omnixApiClient.updateDeepResearchPlan(job.id, { max_pages: selectedPages });
  };
  const resetPageLimitEditor = (): void => {
    editing = false;
    if (pageInput) pageInput.readOnly = true;
    if (updateButton) {
      updateButton.disabled = false;
      updateButton.textContent = 'Edit';
    }
  };

  updateButton?.addEventListener('click', () => {
    if (!pageInput || !updateButton) return;
    if (!editing) {
      editing = true;
      pageInput.readOnly = false;
      pageInput.focus();
      pageInput.select();
      updateButton.textContent = 'Save';
      return;
    }
    updateButton.disabled = true;
    updateButton.textContent = 'Saving…';
    void persistPageLimit()
      .then((updated) => {
        if (updated === job) {
          resetPageLimitEditor();
          return;
        }
        activeJob = updated;
        renderResearchUi();
      })
      .catch((error: unknown) => {
        updateButton.disabled = false;
        updateButton.textContent = 'Save';
        renderResearchPlanActionError(
          panel,
          updateButton,
          error instanceof Error ? error.message : 'The research plan could not be updated.',
        );
        updateButton.textContent = 'Save';
      });
  });
  pageInput?.addEventListener('keydown', (event) => {
    if (event.key !== 'Enter' || !editing) return;
    updateButton?.click();
  });
  panel.querySelector<HTMLButtonElement>('[data-omnix-research-plan-start]')?.addEventListener('click', () => {
    const button = panel.querySelector<HTMLButtonElement>('[data-omnix-research-plan-start]');
    if (!button) return;
    button.disabled = true;
    if (updateButton) updateButton.disabled = true;
    button.textContent = 'Starting…';
    void persistPageLimit()
      .then((updated) => omnixApiClient.startDeepResearchPlan(updated.id))
      .then((updated) => {
        activeJob = updated;
        startPolling(updated.id);
        renderResearchUi();
      })
      .catch((error: unknown) => {
        if (updateButton) {
          updateButton.disabled = false;
          updateButton.textContent = editing ? 'Save' : 'Edit';
        }
        renderResearchPlanActionError(
          panel,
          button,
          error instanceof Error ? error.message : 'The research plan could not be started.',
        );
      });
  });
  panel.querySelector<HTMLButtonElement>('[data-omnix-research-plan-cancel]')?.addEventListener('click', () => {
    const button = panel.querySelector<HTMLButtonElement>('[data-omnix-research-plan-cancel]');
    if (!button) return;
    button.disabled = true;
    button.textContent = 'Canceling…';
    void omnixApiClient.cancelJob(job.id, 'Canceled before deep research started.')
      .then((updated) => {
        activeJob = updated;
        stopPolling();
        renderResearchUi();
      })
      .catch(() => renderResearchPlanActionError(panel, button, 'The research plan could not be canceled.'));
  });
}

function renderResearchPlanActionError(
  panel: HTMLElement,
  button: HTMLButtonElement,
  message: string,
): void {
  button.disabled = false;
  button.textContent = button.dataset.omnixResearchPlanStart !== undefined
    ? 'Start research'
    : button.dataset.omnixResearchPlanCancel !== undefined
      ? 'Cancel'
      : 'Edit';
  const existing = panel.querySelector<HTMLElement>('[data-omnix-research-plan-error]');
  if (existing) {
    existing.textContent = message;
    return;
  }
  button.insertAdjacentHTML('afterend', `<span data-omnix-research-plan-error role="alert">${escapeHtml(message)}</span>`);
}

function setPanelHtml(panel: HTMLElement, html: string, renderKey: string): boolean {
  if (panel.dataset.renderKey === renderKey) return false;
  panel.dataset.renderKey = renderKey;
  panel.innerHTML = html;
  return true;
}

function researchPanelRenderKey(job: JobRecord, announcement: string, details: JobOutput | null): string {
  return JSON.stringify({
    id: job.id,
    status: job.status,
    announcement,
    progress: researchProgressPercent(job),
    stages: (job.stages ?? []).map((stage) => [stage.id, stage.status, stage.label]),
    details,
  });
}

function enhanceResearchMessages(session: ChatSession): void {
  const assistantMessages = (session.messages ?? []).filter((message) => message.role === 'assistant');
  const bubbles = [...document.querySelectorAll<HTMLElement>('.assistant-chat-message.assistant .assistant-chat-bubble')];
  for (const message of assistantMessages) {
    const metadata = asRecord(message.metadata);
    const mode = stringValue(metadata.research_mode);
    if (mode !== 'quick' && mode !== 'deep') continue;
    const bubble = bubbles.find((candidate) => {
      const content = candidate.querySelector<HTMLElement>(`[${MESSAGE_CONTENT_ATTRIBUTE}]`);
      return content?.dataset.rawContent === message.content
        || content?.textContent?.trim() === message.content.trim()
        || candidate.querySelector('p')?.textContent?.trim() === message.content.trim();
    });
    if (!bubble || bubble.querySelector(`[${MESSAGE_DETAILS_ATTRIBUTE}]`)) continue;
    bubble.insertAdjacentHTML('beforeend', renderMessageDetails(message));
  }
}

function injectCompletedResearchMessage(session: ChatSession, jobId: string): void {
  const message = [...(session.messages ?? [])].reverse().find((candidate) => {
    const metadata = asRecord(candidate.metadata);
    return candidate.role === 'assistant' && stringValue(metadata.research_job_id) === jobId;
  });
  if (!message) return;
  const existingText = [...document.querySelectorAll<HTMLElement>('.assistant-chat-message.assistant .assistant-chat-bubble')]
    .some((bubble) => {
      const content = bubble.querySelector<HTMLElement>(`[${MESSAGE_CONTENT_ATTRIBUTE}]`);
      return content?.dataset.rawContent === message.content
        || content?.textContent?.trim() === message.content.trim()
        || bubble.querySelector('p')?.textContent?.trim() === message.content.trim();
    });
  if (existingText || document.querySelector(`[${INJECTED_MESSAGE_ATTRIBUTE}="${cssEscape(message.id)}"]`)) return;
  const container = document.querySelector<HTMLElement>('.assistant-chat-messages');
  if (!container) return;
  const article = document.createElement('article');
  article.className = 'assistant-chat-message assistant omnix-research-injected-message';
  article.setAttribute(INJECTED_MESSAGE_ATTRIBUTE, message.id);
  article.innerHTML = `
    <span class="assistant-chat-avatar" aria-hidden="true"></span>
    <div class="assistant-chat-bubble">
      <header><strong>Omnix Assistant</strong><time datetime="${escapeHtml(message.created_at)}">Research complete</time></header>
      ${renderAssistantMessageHtml(message.content, message.metadata, message.id)}
      ${renderMessageDetails(message)}
    </div>
  `;
  container.querySelector('[aria-hidden="true"]:last-child')?.insertAdjacentElement('beforebegin', article)
    ?? container.append(article);
}

function reconcileInjectedMessages(): void {
  document.querySelectorAll<HTMLElement>(`[${INJECTED_MESSAGE_ATTRIBUTE}]`).forEach((injected) => {
    const content = injected.querySelector<HTMLElement>(`[${MESSAGE_CONTENT_ATTRIBUTE}]`);
    const text = content?.dataset.rawContent ?? content?.textContent?.trim();
    if (!text) return;
    const duplicate = [...document.querySelectorAll<HTMLElement>('.assistant-chat-message.assistant:not(.omnix-research-injected-message) .assistant-chat-bubble')]
      .some((bubble) => {
        const candidate = bubble.querySelector<HTMLElement>(`[${MESSAGE_CONTENT_ATTRIBUTE}]`);
        return candidate?.dataset.rawContent === text
          || candidate?.textContent?.trim() === text
          || bubble.querySelector('p')?.textContent?.trim() === text;
      });
    if (duplicate) injected.remove();
  });
}

export function latestResearchJobId(messages: ChatMessage[]): string | null {
  for (const message of [...messages].reverse()) {
    const jobId = stringValue(asRecord(message.metadata).research_job_id);
    if (jobId) return jobId;
  }
  return null;
}

export function isActiveResearchJob(job: JobRecord | null | undefined): boolean {
  return Boolean(job?.type === RESEARCH_JOB_TYPE && ACTIVE_STATUSES.has(String(job.status)));
}

export function researchStageLabel(job: JobRecord): string {
  const stage = activeStage(job);
  if (stage?.label) return stage.label;
  if (String(job.status) === 'completed') return 'Research complete';
  if (String(job.status) === 'failed') return 'Research failed';
  return 'Research job';
}

export function researchStageAnnouncement(job: JobRecord): string {
  const status = String(job.status);
  if (status === 'completed') {
    const details = researchJobOutput(job);
    if (details?.researchStatus === 'partial' || details?.stopReason === 'no_reliable_sources') {
      return 'Research completed with limited evidence. Review the warnings and search diagnostics before relying on the answer.';
    }
    return 'Research complete. The answer and source details are available in the conversation.';
  }
  if (status === 'failed') {
    const error = stringValue(asRecord(job.error).message);
    return error ? `Research failed: ${error}` : 'Research failed. Review the recorded error before retrying.';
  }
  if (status === 'canceled') return 'Research canceled.';
  if (status === 'cancel_requested') return 'Cancellation requested. The current operation will stop at the next safe boundary.';
  const stage = activeStage(job);
  return stringValue(stage?.progress?.message) || stage?.label || 'Research is queued.';
}

export function researchProgressPercent(job: JobRecord): number {
  if (String(job.status) === 'completed') return 100;
  const total = Math.max(1, job.stages?.length ?? 1);
  return Math.max(0, Math.min(99, Math.round((completedStageCount(job) / total) * 100)));
}

function activeStage(job: JobRecord) {
  const stages = job.stages ?? [];
  return stages.find((stage) => ['running', 'leased', 'cancel_requested'].includes(String(stage.status)))
    ?? stages.find((stage) => !['completed', 'failed', 'canceled', 'stale'].includes(String(stage.status)))
    ?? stages.at(-1);
}

function completedStageCount(job: JobRecord): number {
  return (job.stages ?? []).filter((stage) => String(stage.status) === 'completed').length;
}

type JobOutput = {
  researchStatus?: string;
  researchProvider?: string;
  plannerBackend?: string;
  synthesisBackend?: string;
  stopReason?: string;
  logicalQueries?: number;
  extractedPages?: number;
  searchDiagnostics: Array<{ query?: string; provider?: string; status?: string; results?: number; coverage?: string; error?: string; extractionFailures?: number }>;
  sources: Array<{ id: string; title: string; url?: string; citation?: string; extractionStatus?: string }>;
  conflicts: Array<{ id: string; summary: string }>;
  warnings: string[];
};

function awaitingResearchPlanApproval(job: JobRecord): boolean {
  return asRecord(job.input_payload).awaiting_plan_approval === true
    && String(job.status) === 'queued';
}

export function preferredResearchJobId(
  messages: ChatMessage[],
  currentJob: JobRecord | null,
): string | null {
  if (currentJob && isActiveResearchJob(currentJob)) return currentJob.id;
  return latestResearchJobId(messages) ?? currentJob?.id ?? null;
}

export function latestActiveResearchJobForSession(
  jobs: JobRecord[],
  sessionId: string,
  excludeJobId?: string,
): JobRecord | null {
  return jobs
    .filter((job) => job.id !== excludeJobId
      && job.type === RESEARCH_JOB_TYPE
      && isActiveResearchJob(job)
      && stringValue(asRecord(job.input_payload).session_id) === sessionId)
    .sort((left, right) => Date.parse(String(right.created_at)) - Date.parse(String(left.created_at)))[0] ?? null;
}

export function isStalledResearchJob(job: JobRecord): boolean {
  const stages = job.stages ?? [];
  return String(job.status) === 'running'
    && stages.length > 0
    && stages.every((stage) => String(stage.status) === 'queued');
}

function researchMaxPages(job: JobRecord): number {
  const maxSources = numberValue(asRecord(job.input_payload).max_sources);
  return Math.max(1, Math.min(100, maxSources ?? 12));
}

export function researchPlanTitle(job: JobRecord): string {
  const input = asRecord(job.input_payload);
  const plan = asRecord(input.research_plan);
  const explicitTitle = stringValue(plan.title);
  if (explicitTitle) return explicitTitle;
  const subject = researchPlanSubject(stringValue(input.question) || stringValue(plan.objective));
  return subject ? `${subject} Deep Research` : 'Deep Research Plan';
}

function researchPlanSteps(job: JobRecord): string[] {
  const plan = asRecord(asRecord(job.input_payload).research_plan);
  const generatedSteps = stringList(plan.steps).slice(0, 8);
  if (generatedSteps.length) return generatedSteps;
  const input = asRecord(job.input_payload);
  const subject = researchPlanSubject(stringValue(input.question) || stringValue(plan.objective));
  if (isMarketResearchQuestion(stringValue(input.question) || stringValue(plan.objective))) {
    const topic = subject || 'the company';
    return [
      `Collect recent news and filings on ${topic} from primary financial sources.`,
      `Gather market data and price history for ${topic} over the relevant time horizon.`,
      `Analyze fundamentals, earnings, guidance, and analyst revisions for ${topic}.`,
      `Assess market sentiment, valuation, and other risk indicators for ${topic}.`,
      'Synthesize findings into an actionable outlook and risk-based approach.',
    ];
  }
  return [
    `Collect recent, authoritative sources relevant to ${subject || 'the question'}.`,
    'Gather the key data and context needed to answer it.',
    'Analyze the strongest evidence, including uncertainty and opposing signals.',
    'Cross-check sources and identify conflicts or information gaps.',
    'Synthesize a cited answer with clear conclusions and limitations.',
  ];
}

function researchPlanSubject(value: string): string {
  const clean = value.replace(/\s+/g, ' ').trim();
  if (!clean) return '';
  const withoutLead = clean.replace(/^(?:analy[sz]e|research|investigate|review|summari[sz]e|compare|look into)\s+/i, '');
  const subject = withoutLead
    .split(/\b(?:and how|and whether|how should|is it|over the next|for the next|what should)\b/i, 1)[0]
    .split(/[?.!]/, 1)[0]
    .trim()
    .replace(/[,:;]+$/, '');
  if (!subject || /^(?:this|that|it|the topic)$/i.test(subject)) return '';
  return subject.charAt(0).toUpperCase() + subject.slice(1);
}

function isMarketResearchQuestion(value: string): boolean {
  return /\b(?:stock|stocks|share|shares|equity|ticker|invest|investment|buy|sell|portfolio|market|valuation|earnings|options|short interest)\b/i.test(value);
}

function normalizedPageLimit(value: unknown): number | null {
  const numeric = Number(value);
  if (!Number.isFinite(numeric)) return null;
  return Math.max(1, Math.min(100, Math.trunc(numeric)));
}

function researchJobOutput(job: JobRecord): JobOutput | null {
  const output = asRecord(job.output_refs?.[0]);
  if (!Object.keys(output).length) return null;
  const snapshots = arrayRecords(output.snapshots);
  const snapshotBySource = new Map(snapshots.map((snapshot) => [stringValue(snapshot.source_record_id), snapshot]));
  const sources = arrayRecords(output.sources).map((source, index) => {
    const id = stringValue(source.source_record_id) || `source-${index + 1}`;
    const snapshot = snapshotBySource.get(id);
    return {
      id,
      title: stringValue(source.title) || `Source ${index + 1}`,
      url: stringValue(source.canonical_url ?? source.original_url) || undefined,
      citation: stringValue(snapshot?.citation_label) || undefined,
      extractionStatus: stringValue(snapshot?.extraction_status) || undefined,
    };
  });
  return {
    researchStatus: stringValue(output.research_status) || undefined,
    researchProvider: stringValue(output.research_provider) || undefined,
    plannerBackend: stringValue(output.planner_backend) || undefined,
    synthesisBackend: stringValue(output.synthesis_backend) || undefined,
    stopReason: stringValue(output.stop_reason) || undefined,
    logicalQueries: numberValue(output.logical_queries) ?? undefined,
    extractedPages: numberValue(output.extracted_pages) ?? undefined,
    searchDiagnostics: arrayRecords(output.search_diagnostics).map((diagnostic) => ({
      query: stringValue(diagnostic.query) || undefined,
      provider: stringValue(diagnostic.provider) || undefined,
      status: stringValue(diagnostic.status) || undefined,
      results: numberValue(diagnostic.results) ?? undefined,
      coverage: stringValue(diagnostic.coverage) || undefined,
      error: stringValue(diagnostic.error) || undefined,
      extractionFailures: numberValue(diagnostic.extraction_failures) ?? undefined,
    })),
    sources,
    conflicts: arrayRecords(output.conflicts).map((conflict, index) => ({
      id: stringValue(conflict.conflict_id) || `conflict-${index + 1}`,
      summary: stringValue(conflict.summary) || 'Unresolved source conflict.',
    })),
    warnings: stringList(output.warnings),
  };
}

function renderJobDetails(details: JobOutput): string {
  const searchHits = details.searchDiagnostics.reduce((total, diagnostic) => total + (diagnostic.results ?? 0), 0);
  const extractionFailures = details.searchDiagnostics.reduce(
    (total, diagnostic) => total + (numberValue((diagnostic as Record<string, unknown>).extractionFailures) ?? 0),
    0,
  );
  const rows = [
    details.researchStatus ? `<div><dt>Result</dt><dd>${escapeHtml(humanizeCode(details.researchStatus))}</dd></div>` : '',
    details.researchProvider ? `<div><dt>Search provider</dt><dd>${escapeHtml(humanizeCode(details.researchProvider))}</dd></div>` : '',
    details.plannerBackend ? `<div><dt>Planner</dt><dd>${escapeHtml(details.plannerBackend)}</dd></div>` : '',
    details.synthesisBackend ? `<div><dt>Synthesis</dt><dd>${escapeHtml(details.synthesisBackend)}</dd></div>` : '',
    details.logicalQueries !== undefined ? `<div><dt>Queries</dt><dd>${details.logicalQueries}</dd></div>` : '',
    `<div><dt>Search hits</dt><dd>${searchHits}</dd></div>`,
    details.extractedPages !== undefined ? `<div><dt>Pages reviewed</dt><dd>${details.extractedPages}${details.sources.length ? ` of ${details.sources.length}` : ''}</dd></div>` : '',
    extractionFailures ? `<div><dt>Extraction failures</dt><dd>${extractionFailures}</dd></div>` : '',
    details.stopReason ? `<div><dt>Stop reason</dt><dd>${escapeHtml(humanizeCode(details.stopReason))}</dd></div>` : '',
  ].join('');
  const sources = details.sources.length ? `<section><h4>Sources</h4><ol class="assistant-research-source-list">${details.sources.map((source) => `<li><span>${source.citation ? `[${escapeHtml(source.citation)}] ` : ''}${escapeHtml(source.title)}</span>${source.url ? `<a href="${escapeHtml(source.url)}" target="_blank" rel="noreferrer">Open source</a>` : ''}${source.extractionStatus ? `<small>${escapeHtml(humanizeCode(source.extractionStatus))}</small>` : ''}</li>`).join('')}</ol></section>` : '';
  const diagnostics = details.searchDiagnostics.length ? `<section><h4>Search diagnostics</h4><ol>${details.searchDiagnostics.map((diagnostic) => `<li><span>${escapeHtml(diagnostic.query || 'Search query')}</span><small>${escapeHtml([diagnostic.provider, diagnostic.status, diagnostic.results !== undefined ? `${diagnostic.results} results` : '', diagnostic.coverage, diagnostic.error].filter(Boolean).join(' · '))}</small></li>`).join('')}</ol></section>` : '';
  const conflicts = details.conflicts.length ? `<section><h4>Unresolved conflicts</h4><ul>${details.conflicts.map((conflict) => `<li>${escapeHtml(conflict.summary)}</li>`).join('')}</ul></section>` : '';
  const warnings = details.warnings.length ? `<section><h4>Warnings</h4><ul>${details.warnings.map((warning) => `<li>${escapeHtml(humanizeCode(warning))}</li>`).join('')}</ul></section>` : '';
  return `<details class="assistant-research-job-details"><summary>Research details</summary><dl>${rows}</dl>${sources}${diagnostics}${conflicts}${warnings}</details>`;
}

function renderMessageDetails(message: ChatMessage): string {
  const metadata = asRecord(message.metadata);
  const mode = stringValue(metadata.research_mode);
  const status = stringValue(metadata.research_status) || 'completed';
  const validation = asRecord(metadata.citation_validation ?? metadata.synthesis_validation);
  const diagnostics = arrayRecords(metadata.search_diagnostics);
  const searchHits = diagnostics.reduce((total, diagnostic) => total + (numberValue(diagnostic.results) ?? 0), 0);
  const extractionFailures = diagnostics.reduce((total, diagnostic) => total + (numberValue(diagnostic.extraction_failures) ?? 0), 0);
  const budget = asRecord(metadata.research_budget);
  const pageLimit = numberValue(budget.max_sources) ?? numberValue(metadata.max_sources);
  const provider = stringValue(metadata.research_provider) || stringValue(metadata.web_search_provider);
  const providerChain = stringList(metadata.research_provider_chain);
  const stopReason = stringValue(metadata.research_stop_reason);
  const sourceCount = numberValue(metadata.web_search_source_count) ?? searchHits;
  const rows = [
    `<div><dt>Mode</dt><dd>${mode === 'quick' ? 'Quick search' : 'Deep research'}</dd></div>`,
    provider ? `<div><dt>Search provider</dt><dd>${escapeHtml(humanizeCode(provider))}</dd></div>` : '',
    providerChain.length ? `<div><dt>Provider route</dt><dd>${escapeHtml(providerChain.map(humanizeCode).join(' -> '))}</dd></div>` : '',
    stringValue(metadata.source_manifest_id) ? '<div><dt>Sources</dt><dd>Manifest saved</dd></div>' : '',
    stringValue(metadata.planner_backend) ? `<div><dt>Planner</dt><dd>${escapeHtml(stringValue(metadata.planner_backend))}</dd></div>` : '',
    stringValue(metadata.synthesis_backend) ? `<div><dt>Synthesis</dt><dd>${escapeHtml(stringValue(metadata.synthesis_backend))}</dd></div>` : '',
    numberValue(metadata.logical_queries) !== null ? `<div><dt>Queries</dt><dd>${numberValue(metadata.logical_queries)}</dd></div>` : '',
    `<div><dt>Search hits</dt><dd>${sourceCount}</dd></div>`,
    numberValue(metadata.extracted_pages) !== null ? `<div><dt>Pages reviewed</dt><dd>${numberValue(metadata.extracted_pages)}${pageLimit !== null ? ` of ${pageLimit}` : ''}</dd></div>` : '',
    extractionFailures ? `<div><dt>Extraction failures</dt><dd>${extractionFailures}</dd></div>` : '',
    numberValue(metadata.conflict_count) !== null ? `<div><dt>Conflicts</dt><dd>${numberValue(metadata.conflict_count)}</dd></div>` : '',
    typeof validation.valid === 'boolean' ? `<div><dt>Citations</dt><dd>${validation.valid ? 'Validated' : 'Validation warning'}</dd></div>` : '',
    stopReason ? `<div><dt>Stop reason</dt><dd>${escapeHtml(humanizeCode(stopReason))}</dd></div>` : '',
    diagnostics.length ? `<div><dt>Searches performed</dt><dd>${escapeHtml(diagnostics.map((diagnostic) => stringValue(diagnostic.query)).filter(Boolean).join(' | '))}</dd></div>` : '',
  ].join('');
  const warnings = stringList(metadata.research_warnings);
  return `<details ${MESSAGE_DETAILS_ATTRIBUTE}="true" class="assistant-research-message-details"><summary>${mode === 'quick' ? 'Quick search details' : 'Research details'} · ${escapeHtml(status)}</summary><dl>${rows}</dl>${warnings.length ? `<ul>${warnings.map((warning) => `<li>${escapeHtml(humanizeCode(warning))}</li>`).join('')}</ul>` : ''}</details>`;
}

function dispatchRefreshSignal(): void {
  window.dispatchEvent(new Event('focus'));
  document.dispatchEvent(new Event('visibilitychange'));
  window.dispatchEvent(new CustomEvent('omnix:research-job-settled', { detail: { jobId: activeJob?.id } }));
}

function asRecord(value: unknown): Record<string, unknown> {
  return value && typeof value === 'object' && !Array.isArray(value) ? value as Record<string, unknown> : {};
}

function arrayRecords(value: unknown): Record<string, unknown>[] {
  return Array.isArray(value) ? value.map(asRecord) : [];
}

function stringValue(value: unknown): string {
  return typeof value === 'string' ? value.trim() : '';
}

function stringList(value: unknown): string[] {
  return Array.isArray(value) ? value.map(stringValue).filter(Boolean) : [];
}

function numberValue(value: unknown): number | null {
  return typeof value === 'number' && Number.isFinite(value) ? value : null;
}

function humanizeCode(value: string): string {
  const text = value.replace(/[_-]+/g, ' ').trim();
  return text ? text.charAt(0).toUpperCase() + text.slice(1) : 'Unknown';
}

function escapeHtml(value: unknown): string {
  return String(value ?? '')
    .replaceAll('&', '&amp;')
    .replaceAll('<', '&lt;')
    .replaceAll('>', '&gt;')
    .replaceAll('"', '&quot;')
    .replaceAll("'", '&#039;');
}

function cssEscape(value: string): string {
  return typeof CSS !== 'undefined' && typeof CSS.escape === 'function' ? CSS.escape(value) : value.replace(/[^a-zA-Z0-9_-]/g, '_');
}

installResearchProgressController();
