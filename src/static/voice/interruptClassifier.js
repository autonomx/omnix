/**
 * InterruptClassifier — semantic interrupt detection for voice barge-in.
 *
 * Two-stage system:
 *   1. Heuristic fast-path (instant) — catches obvious turn-taking signals.
 *   2. Async LLM fallback (slower)   — handles ambiguous cases.
 *
 * The heuristic path covers ~90 % of real interrupts with zero latency.
 * The LLM path is only invoked when the heuristic is inconclusive and is
 * rate-limited to at most one request per `minInterval` ms.
 */
export class InterruptClassifier {
  constructor() {
    /** Timestamp of the last LLM-based classification request. */
    this.lastCheck = 0;
    /** Minimum interval (ms) between consecutive LLM intent checks. */
    this.minInterval = 300;
  }

  /**
   * Classify whether `text` expresses interrupt intent.
   * Returns `true` when the user is trying to take the conversational turn.
   *
   * @param {string} text - partial or full transcript from STT
   * @returns {Promise<boolean>}
   */
  async classify(text) {
    if (!text || text.length < 4) return false;

    // Stage 1 — heuristic (instant)
    if (this.isStrongInterrupt(text)) return true;

    // Stage 2 — lightweight LLM check (rate-limited)
    return this.llmCheck(text);
  }

  /**
   * Heuristic fast-path: returns `true` when the transcript contains
   * well-known turn-taking phrases that almost always indicate a real
   * interrupt rather than back-channel noise.
   *
   * @param {string} text
   * @returns {boolean}
   */
  isStrongInterrupt(text) {
    const t = text.toLowerCase();

    return (
      t.startsWith('wait') ||
      t.startsWith('no') ||
      t.startsWith('stop') ||
      t.includes('hold on') ||
      t.includes('let me') ||
      t.includes('actually')
    );
  }

  /**
   * Lightweight LLM-based intent check.  Calls a small server-side model to
   * determine whether the user's speech constitutes a turn-taking attempt.
   *
   * Rate-limited by `minInterval` to avoid flooding the backend.
   *
   * @param {string} text
   * @returns {Promise<boolean>}
   */
  async llmCheck(text) {
    const now = Date.now();
    if (now - this.lastCheck < this.minInterval) return false;
    this.lastCheck = now;

    try {
      const res = await fetch('/api/interrupt-intent', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ text })
      });

      if (!res.ok) return false;

      const data = await res.json();
      return data.interrupt === true;
    } catch {
      // Network errors should never block the voice pipeline.
      return false;
    }
  }
}

export default InterruptClassifier;
