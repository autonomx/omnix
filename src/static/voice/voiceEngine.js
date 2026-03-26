import { VoiceState } from './voiceState.js?v=2';
import { AudioInput } from './audioInput.js?v=2';
import { AudioOutput } from './audioOutput.js?v=2';
import { STTClient } from './sttClient.js?v=2';
import { LLMClient } from './llmClient.js?v=2';
import { TTSClient } from './ttsClient.js?v=2';
import { InterruptClassifier } from './interruptClassifier.js?v=2';

export { VoiceState };
export class VoiceEngine {
  constructor(options = {}) {
    this.onStateChange = options.onStateChange || (() => {});
    this.onTranscript = options.onTranscript || (() => {});  // kept for external use
    this._onTranscriptCallback = options.onTranscript || (() => {});
    this.onAIResponse = options.onAIResponse || (() => {});
    this.onUserMessage = options.onUserMessage || (() => {});
    this.onError = options.onError || console.error;

    this.state = VoiceState.IDLE;
    this.speaker = options.speaker || 'default';
    this.sessionId = options.sessionId || null;

    this.audioOutput = new AudioOutput();
    
    this.stt = new STTClient(
      this.onTranscript.bind(this),
      this.onSTTFinal.bind(this)
    );
    
    this.tts = new TTSClient(
      this.onAudioChunk.bind(this),
      this.onTTSDone.bind(this),
      this.onTTSStart.bind(this)
    );
    
    this.llm = new LLMClient(
      this.onLLMToken.bind(this),
      this.onLLMEnd.bind(this),
      this.onLLMStart.bind(this)
    );

    this.audioInput = new AudioInput(
      this.onSpeechStart.bind(this),
      this.onSpeechEnd.bind(this),
      this.onAudioChunkInput.bind(this),
      this.handleUserSpeechStart.bind(this)
    );
    // Wire echo cancellation: let AudioInput compare mic chunks against
    // the most recently played TTS audio to suppress self-echo.
    this.audioInput.setAudioOutput(this.audioOutput);

    this.currentTranscript = '';
    this.accumulatedResponse = '';
    this.textBuffer = '';
    this.responseFinished = false;
    this.awaitingSTT = false;
    this.hasStartedSpeaking = false;
    this.interrupting = false;
    // Guard against stale audio chunks arriving after an interrupt
    this.ignoreAudioChunks = false;
    this.minTranscriptLength = 2;
    // Streaming text buffer flush thresholds
    this.TTS_FLUSH_LENGTH = 80;
    this.TTS_MAX_BUFFER_LENGTH = 300;
    // Minimum buffer length before a comma/semicolon clause is sent to TTS.
    this.TTS_CLAUSE_FLUSH_MIN_LENGTH = 40;
    // Partial-STT early LLM start flag
    this.llmStarted = false;
    // Minimum partial transcript length before early LLM start is triggered
    this.MIN_PARTIAL_TEXT_LENGTH = 4;
    // Minimum word count in partial transcript before early LLM start
    this.MIN_PARTIAL_WORD_COUNT = 1;
    // Minimum text length before shouldFlush() returns true
    this.FLUSH_MIN_LENGTH = 30;
    // Reduced dynamicMinLength when user interrupts frequently (adaptive pacing)
    this.IMPATIENT_MIN_CHUNK_LENGTH = 6;
    // HTTP TTS mode thresholds – fewer, larger chunks because each HTTP round-trip
    // costs 2-4 seconds regardless of text length.
    this.HTTP_FIRST_CHUNK_MIN = 20;
    this.HTTP_MIN_CHUNK_LENGTH = 60;
    // Count of TTS segments sent but not yet completed
    this._ttsInFlight = 0;
    // Ensure audio order when TTS resolves out-of-order
    this.ttsSeq = 0;
    this.expectedSeq = 0;
    this.pendingAudio = new Map();
    // Deferred TTS queue: holds chunks that were backpressured instead of dropped
    this.deferredTTSQueue = [];
    // Early first-chunk flag: send TTS earlier for first chunk
    this.hasSentFirstChunk = false;
    // Max gap before skipping missing TTS sequence numbers
    this.MAX_SEQUENCE_GAP = 5;
    // Track the last spoken text for speech continuity context
    this.lastSpokenText = '';
    // Incremental word counter for the current textBuffer (avoids per-token split)
    this._wordCount = 0;
    // When false, VAD is paused after each turn so the user must type
    this.alwaysListening = options.alwaysListening !== false;
    // Monotonically incrementing counter – bumped on every cancel/interrupt so
    // in-flight HTTP TTS callbacks from the previous turn know they are stale
    // and discard their audio without touching engine state.
    this._ttsRequestId = 0;
    // Monotonically incrementing counter for LLM requests so stale onLLMToken /
    // onLLMEnd callbacks from a cancelled request are silently ignored.
    this._llmRequestId = 0;
    // Priority mode: when set after an interrupt, the next TTS dispatch clears
    // any lingering deferred queue so the new response wins immediately.
    this._priorityMode = false;
    // Per-request AbortControllers for in-flight TTS HTTP requests so they
    // can be hard-cancelled on interrupt instead of just discarded at callback time.
    this._ttsControllers = new Map();
    // Conversational fillers: sent on first LLM token to mask latency
    this._fillers = ["Yeah,", "Okay,", "Right,"];
    // Soft barge-in: pending interrupt flag (cleared if user speech stops quickly)
    this._pendingInterrupt = false;
    // Timer ID for soft barge-in (cleared on cancel to prevent stacked timers)
    this._interruptTimer = null;
    // Track interrupt count for adaptive behavior
    this.interruptCount = 0;
    // Guard: only one filler (speculative or pre-speech) fires per turn
    this._sentFillerThisTurn = false;
    // Filler priority: tracks which type fired ('speculative' | 'prespeech' | null)
    // so pre-speech can upgrade a speculative filler for better context-awareness
    this._fillerType = null;
    // Timestamp of last interrupt for adaptive decay (resets interruptCount after 8s)
    this._lastInterruptTime = 0;
    // Full-duplex interrupt arbitration
    this._interruptCandidate = false;
    this._interruptStartTime = 0;
    this._interruptMinDuration = 350; // ms – minimum speech duration to validate interrupt
    this._interruptMinWords = 2;
    this._interruptEnabledAt = 0;
    this._interruptGracePeriod = 800; // ms – delay before interrupts are accepted after AI starts
    this._isValidInterrupt = false;
    // Semantic interrupt classifier (heuristic + optional LLM fallback)
    this.interruptClassifier = new InterruptClassifier();
    // Confidence threshold: scores above this trigger a real interrupt
    this._interruptScoreThreshold = 0.6;
  }

  setState(newState) {
    if (this.state !== newState) {
      this.state = newState;
      this.onStateChange(newState);
    }
  }

  async start() {
    try {
      console.log('[VoiceEngine] Starting...');
      
      // Reset state for new session (fixes "only works once" bug)
      this.startConversation();

      this.setState(VoiceState.LISTENING);
      this.ttsConnected = false;

      await this.stt.connect();
      
      try {
        await this.tts.connect();
        this.ttsConnected = true;
      } catch (e) {
        console.warn('[VoiceEngine] TTS WebSocket failed, will use HTTP fallback:', e.message);
        this.ttsConnected = false;
      }
      
      await this.audioInput.start();

      this.audioOutput.onPlaybackEnd = this.onPlaybackEnded.bind(this);
      
      console.log('[VoiceEngine] Started successfully, TTS WebSocket:', this.ttsConnected ? 'connected' : 'HTTP fallback');
    } catch (error) {
      console.error('[VoiceEngine] Failed to start:', error);
      this.onError(error);
      this.setState(VoiceState.IDLE);
    }
  }

  stop() {
    console.log('[VoiceEngine] Stopping...');
    
    this.audioInput.stop();
    this.stt.disconnect();
    this.tts.disconnect();
    this._abortAllTTS();
    this.audioOutput.reset();
    this.llm.cancel();

    this.setState(VoiceState.IDLE);
    
    this.currentTranscript = '';
    this.accumulatedResponse = '';
    this.textBuffer = '';
    this.ignoreAudioChunks = false;
    this.responseFinished = false;
    this.llmStarted = false;
    this.hasSentFirstChunk = false;
    this._ttsInFlight = 0;
    // Reset TTS sequencing state
    this.ttsSeq = 0;
    this.expectedSeq = 0;
    this.pendingAudio.clear();
    this.deferredTTSQueue = [];
    this.lastSpokenText = '';
    // Invalidate all in-flight HTTP TTS and LLM callbacks
    this._ttsRequestId++;
    this._llmRequestId++;
  }

  onSpeechStart() {
    // During AI speech, delegate to the full-duplex interrupt arbitration
    // pipeline (candidate → validate → maybe interrupt) instead of cancelling
    // immediately.
    if (this.state === VoiceState.AI_SPEAKING || this.state === VoiceState.THINKING) {
      this.handleUserSpeechStart();
      return;
    }

    // Safe to reset for a normal speech-start
    this.textBuffer = '';
    this.responseFinished = false;
    this.hasStartedSpeaking = false;

    this.setState(VoiceState.USER_SPEAKING);
  }

  onSpeechEnd() {
    // Cancel interrupt candidate if user stopped too quickly (false interrupt)
    if (this._interruptCandidate) {
      this._interruptCandidate = false;
      this._isValidInterrupt = false;
      // Restore volume after ducking
      this.audioOutput.setVolume?.(1.0);
    }

    // Cancel any pending soft barge-in if the user stopped speaking quickly
    this._pendingInterrupt = false;
    if (this._interruptTimer) {
      clearTimeout(this._interruptTimer);
      this._interruptTimer = null;
    }

    // Also handle speech-end coming in from INTERRUPTED state (user spoke after barge-in)
    if (this.state === VoiceState.INTERRUPTED) {
      this.setState(VoiceState.USER_SPEAKING);
    }
    if (this.state === VoiceState.USER_SPEAKING) {
      this.setState(VoiceState.THINKING);
      this.audioInput.pauseVAD();
      
      if (!this.awaitingSTT) {
        this.awaitingSTT = true;
        this.stt.sendFinal();

        // Safety net: if STT never responds within 4s (e.g. connection died),
        // recover the engine from THINKING back to LISTENING so it is not stuck.
        setTimeout(() => {
          if (this.awaitingSTT) {
            console.warn('[VoiceEngine] STT response timeout - recovering to LISTENING');
            this.awaitingSTT = false;
            this.setState(VoiceState.LISTENING);
            this.audioInput.resumeVAD();
          }
        }, 4000);
      }
    }
  }

  onAudioChunkInput(chunk) {
    if (this.state === VoiceState.USER_SPEAKING || this.state === VoiceState.LISTENING || this.state === VoiceState.INTERRUPTED) {
      this.stt.sendAudio(chunk);
    }

    // Full-duplex interrupt validation: if the user is a candidate for
    // interrupting, check whether they have been speaking long enough
    // (duration gate) before allowing the intent check in onTranscript.
    if (this._interruptCandidate && this.state === VoiceState.AI_SPEAKING) {
      const duration = Date.now() - this._interruptStartTime;
      if (duration > this._interruptMinDuration) {
        this._isValidInterrupt = true;
      }
    }
  }

  onTranscript(text) {
    this.currentTranscript = text;
    // Call the external callback passed via options (not this method — that would recurse infinitely)
    if (this._onTranscriptCallback) this._onTranscriptCallback(text);

    // Start LLM early on partial STT when enough text has arrived
    const wordCount = text ? text.trim().split(/\s+/).length : 0;
    if (!this.llmStarted && text &&
        (wordCount >= this.MIN_PARTIAL_WORD_COUNT || text.length > 12) &&
        (this.state === VoiceState.USER_SPEAKING || this.state === VoiceState.LISTENING)) {
      this.llmStarted = true;
      console.log('[VoiceEngine] Starting LLM early on partial transcript:', text);
      this.llm.sendMessage(text, this.sessionId, this.speaker);
      // Speculative response: send a brief filler to eliminate dead air while
      // the LLM generates its first real content.  Guarded by _sentFillerThisTurn
      // so we never double-filler if onLLMToken also fires a pre-speech filler.
      // Only for WebSocket TTS; in HTTP mode fillers waste a 3-4s round-trip.
      if (this.ttsConnected && !this._sentFillerThisTurn) {
        this._sendTTS('Hmm,');
        this._sentFillerThisTurn = true;
        this._fillerType = 'speculative';
      }
    } else if (this.llmStarted && text) {
      // Streaming context update: if LLM is already running, push updated
      // transcript so the model can adapt mid-user-sentence.
      if (typeof this.llm.updateContext === 'function') {
        this.llm.updateContext(text);
      }
    }

    // Interrupt intent validation: use confidence scoring with semantic
    // classification instead of a simple word-count boolean check.
    if (this._interruptCandidate && this.state === VoiceState.AI_SPEAKING) {
      if (this._isNoise(text)) return;

      const duration = Date.now() - this._interruptStartTime;
      const words = text.trim().split(/\s+/).length;

      // Two-stage system: heuristic fast-path runs synchronously for instant
      // response on obvious interrupts; LLM fallback runs async for ambiguous
      // cases.  Both feed into the confidence score.
      const isStrongIntent = this.interruptClassifier.isStrongInterrupt(text);

      const score = this._computeInterruptScore({ duration, words, text, isStrongIntent });

      if (isStrongIntent && this._isValidInterrupt) {
        // Stage 1 — instant: strong heuristic match, interrupt immediately
        this._executeInterrupt();
      } else if (score > this._interruptScoreThreshold && this._isValidInterrupt) {
        // Score already passes threshold (e.g. long duration + multiple words)
        this._executeInterrupt();
      } else if (this._isValidInterrupt && !isStrongIntent) {
        // Stage 2 — async: ambiguous speech, ask the LLM classifier
        this.interruptClassifier.classify(text).then(isIntent => {
          // Re-check guards: the turn may have ended while the LLM was thinking
          if (isIntent && this._interruptCandidate && this.state === VoiceState.AI_SPEAKING) {
            this._executeInterrupt();
          }
        }).catch(() => {
          // Classification errors must not break the voice pipeline
        });
      }
    }
  }

  /**
   * Shared interrupt execution: logs, resets arbitration state, updates
   * adaptive counters, and fires the actual interrupt.
   */
  _executeInterrupt() {
    console.log('[VoiceEngine] Valid interrupt detected');

    this._interruptCandidate = false;
    this._isValidInterrupt = false;

    // Adaptive decay: reset interrupt count if >8s since last interrupt
    const now = typeof performance !== 'undefined' ? performance.now() : Date.now();
    if (now - this._lastInterruptTime > 8000) {
      this.interruptCount = 0;
    }
    this._lastInterruptTime = now;
    this.interruptCount++;

    this.interruptAI();
  }

  /**
   * Compute a 0–1 confidence score for an interrupt candidate.
   *
   * Factors:
   *   • Speech duration (longer = more likely intentional)
   *   • Word count (more words = more likely intentional)
   *   • Semantic intent (strong turn-taking phrases boost score)
   *   • Filler penalty (lone "uh" / "um" / "hmm" reduces score)
   *
   * @param {{duration: number, words: number, text: string, isStrongIntent?: boolean}} params
   * @returns {number} score between 0 and 1
   */
  _computeInterruptScore({ duration, words, text, isStrongIntent }) {
    let score = 0;

    // Duration weight
    if (duration > 300) score += 0.3;
    if (duration > 600) score += 0.2;

    // Word count weight
    if (words >= 2) score += 0.2;
    if (words >= 4) score += 0.1;

    // Semantic intent boost (reuse pre-computed result when available)
    if (isStrongIntent !== undefined ? isStrongIntent : this.interruptClassifier.isStrongInterrupt(text)) {
      score += 0.4;
    }

    // Penalize lone fillers
    if (/^(uh|um|hmm)$/i.test(text.trim())) {
      score -= 0.5;
    }

    return Math.max(0, Math.min(1, score));
  }

  onSTTFinal(text) {
    this.awaitingSTT = false;
    
    if (!text || !text.trim()) {
      console.log('[VoiceEngine] Empty transcript, returning to listening');
      this.setState(VoiceState.LISTENING);
      this.audioInput.resumeVAD();
      return;
    }

    this.currentTranscript = text;
    
    if (text.trim().length < this.minTranscriptLength) {
      console.log('[VoiceEngine] Transcript too short, ignoring');
      this.setState(VoiceState.LISTENING);
      this.audioInput.resumeVAD();
      return;
    }

    console.log('[VoiceEngine] Final transcript:', text);

    this.onUserMessage(text);

    // If LLM was already started on partial STT, skip re-sending
    if (this.llmStarted) {
      console.log('[VoiceEngine] LLM already started on partial – skipping re-send');
      return;
    }

    this.llm.sendMessage(text, this.sessionId, this.speaker);
  }

  /**
   * Send a typed (text) message directly to the LLM, bypassing STT.
   * Interrupts any ongoing AI speech, displays the user message, and starts
   * the LLM/TTS pipeline just like a voice transcript would.
   */
  sendTypedMessage(text) {
    if (!text || !text.trim()) return;

    console.log('[VoiceEngine] Typed message:', text.trim());

    // Interrupt any ongoing AI speech/generation
    if (this.state === VoiceState.AI_SPEAKING || this.state === VoiceState.THINKING) {
      this._cancelOngoingResponse();
    }

    this.onUserMessage(text.trim());
    this.setState(VoiceState.THINKING);
    this.audioInput.pauseVAD();
    // ignoreAudioChunks is set to true by _cancelOngoingResponse above (if called);
    // onLLMStart will reset it to false once the new LLM request begins so that
    // legitimate audio from the new turn is played while any still-in-flight HTTP
    // TTS requests from the old turn are discarded via _ttsRequestId checks.
    this.llm.sendMessage(text.trim(), this.sessionId, this.speaker);
  }

  onLLMStart() {
    // Capture the current generation counter so onLLMToken / onLLMEnd can
    // confirm they belong to this request and not a cancelled predecessor.
    // _llmRequestId itself is only incremented by cancel/interrupt so that
    // stale callbacks from an aborted request always see a mismatch.
    this._activeLLMId = this._llmRequestId;
    console.log(`[VoiceEngine] LLM started (id=${this._activeLLMId})`);
    this.accumulatedResponse = '';
    // Allow audio chunks from this new response; clear any stale-chunk guard
    this.ignoreAudioChunks = false;
    // Reset filler guard so one filler is allowed per turn
    this._sentFillerThisTurn = false;
    this._fillerType = null;
  }

  onLLMToken(token) {
    // Discard tokens from a cancelled/replaced LLM request
    if (this._activeLLMId !== this._llmRequestId) return;

    if (!this.hasStartedSpeaking) {
      this.hasStartedSpeaking = true;
      this.setState(VoiceState.AI_SPEAKING);
      // Pre-speech filler: send a random conversational filler immediately
      // to mask LLM-to-TTS latency — perceived response time drops to ~0ms.
      // Guarded by _sentFillerThisTurn so we never double-filler when a
      // speculative filler was already sent from onTranscript.
      // Priority upgrade: if a speculative filler already fired, we still send
      // a contextual pre-speech filler to override it — feels more natural
      // because intent is clearer by the time the LLM starts responding.
      // Only for WebSocket TTS; in HTTP mode each filler wastes a 3-4s round-trip.
      if (this.ttsConnected && !this._sentFillerThisTurn) {
        const filler = this._fillers[Math.floor(Math.random() * this._fillers.length)];
        this._sendTTS(filler);
        this._sentFillerThisTurn = true;
        this._fillerType = 'prespeech';
      } else if (this.ttsConnected && this._fillerType === 'speculative') {
        // Upgrade speculative → pre-speech filler for better context awareness
        const filler = this._fillers[Math.floor(Math.random() * this._fillers.length)];
        this._sendTTS(filler);
        this._fillerType = 'prespeech';
      }
      // Full duplex: resume VAD so the user can interrupt by speaking.
      // Browser echo-cancellation (echoCancellation: true in getUserMedia)
      // plus hasEnoughAudioForInterrupt() guard prevents false triggers.
      // In HTTP mode, VAD stays paused during AI speech because the delayed
      // audio playback causes echo that triggers false interrupts.
      if (this.ttsConnected) {
        this.audioInput.resumeVAD();
      }
      // Prevent early self-interrupt: enable interrupt validation only after
      // AI audio has had time to start playing back.
      this._interruptEnabledAt = Date.now() + this._interruptGracePeriod;
      console.log(`[VoiceEngine] LLM first token received (id=${this._activeLLMId})`);
    }
    
    this.accumulatedResponse += token;
    this.onAIResponse(this.accumulatedResponse);
    
    this.textBuffer += token;

    // Track word count incrementally (avoids per-token split allocation)
    if (token.includes(' ')) {
      this._wordCount++;
    }

    // Early first chunk: speculative TTS for fastest perceived response
    // Flush as soon as buffer exceeds threshold – even partial words are OK
    // because latency matters more than perfection for the very first chunk.
    // Uses _dispatchTTS directly (bypassing backpressure) to shave ~50ms
    // by firing immediately without queue checks — first chunk is always urgent.
    // In HTTP mode, wait for more text (HTTP_FIRST_CHUNK_MIN) so the first
    // request carries enough content for meaningful audio.
    const firstChunkMin = this.ttsConnected ? 3 : this.HTTP_FIRST_CHUNK_MIN;
    if (!this.hasSentFirstChunk && this.textBuffer.length > firstChunkMin) {
      const text = this.textBuffer;
      this.textBuffer = '';
      this.hasSentFirstChunk = true;
      this._wordCount = 0;
      const cleaned = this._stripMarkdown(text);
      if (cleaned) {
        const seq = this.ttsSeq++;
        this._dispatchTTS(cleaned, seq);
      }
      return;
    }
    
    // Phrase-level flush: flush on word boundary for speech-rhythm chunking
    // This starts TTS while the sentence is still forming, reducing latency.
    // Adaptive chunk sizing: smoothly scale minimum length with in-flight count
    // to avoid overwhelming the TTS pipeline under load while keeping latency
    // low when idle.
    // Adaptive personality: if user has interrupted frequently (> 2 times),
    // use shorter chunks so the AI speaks more concisely and responsively.
    // In HTTP mode, use larger minimums to batch more text per request.
    const dynamicMinLength = !this.ttsConnected
      ? (this.interruptCount > 2 ? 20 : this.HTTP_MIN_CHUNK_LENGTH)
      : this.interruptCount > 2
        ? this.IMPATIENT_MIN_CHUNK_LENGTH
        : Math.min(8 + this._ttsInFlight * 4, 24);
    if (token.endsWith(' ') && this.textBuffer.length > dynamicMinLength && this._wordCount >= 2) {
      const flushText = this.textBuffer;
      this.textBuffer = '';
      this._wordCount = 0;
      this._sendTTS(flushText);
      return;
    }

    if (this.textBuffer.length > this.TTS_MAX_BUFFER_LENGTH) {
      // Hard cap: flush to prevent unbounded buffer growth
      const flushText = this.textBuffer;
      this.textBuffer = '';
      this._wordCount = 0;
      this._sendTTS(flushText);
      return;
    }
    
    if (this.textBuffer.length > this.TTS_FLUSH_LENGTH) {
      // Flush when enough text has accumulated
      const flushText = this.textBuffer;
      this.textBuffer = '';
      this._wordCount = 0;
      this._sendTTS(flushText);
      return;
    }
    
    // Flush on sentence-ending punctuation for natural speech boundaries.
    // Also flush on comma/semicolon when the buffer is long enough.
    if (this.shouldFlush(this.textBuffer)) {
      // In HTTP mode, use greedy match to capture ALL complete sentences in the
      // buffer as one chunk — reduces the number of expensive round-trips.
      // In WebSocket mode, use non-greedy match to stream the first sentence.
      const sentenceRegex = this.ttsConnected
        ? /(.+?[.!?])(\s|$)/
        : /(.+[.!?])(\s|$)/;
      const sentenceMatch = this.textBuffer.match(sentenceRegex);
      if (sentenceMatch) {
        const sentence = sentenceMatch[1];
        this.textBuffer = this.textBuffer.slice(sentenceMatch.index + sentence.length);
        this._wordCount = 0;
        this._sendTTS(sentence);
        return;
      }

      // Clause boundary flush
      const clauseFlushMin = this.ttsConnected
        ? this.TTS_CLAUSE_FLUSH_MIN_LENGTH
        : this.HTTP_MIN_CHUNK_LENGTH;
      if (this.textBuffer.length > clauseFlushMin) {
        const clauseRegex = this.ttsConnected
          ? /(.+?[,;])(\s|$)/
          : /(.+[,;])(\s|$)/;
        const clauseMatch = this.textBuffer.match(clauseRegex);
        if (clauseMatch) {
          const clause = clauseMatch[1];
          this.textBuffer = this.textBuffer.slice(clauseMatch.index + clause.length);
          this._wordCount = 0;
          this._sendTTS(clause);
          return;
        }
      }

      // Fallback: flush the whole buffer if it matches generic flush criteria
      if (this.textBuffer.length > this.FLUSH_MIN_LENGTH || /[.!?,;:]$/.test(this.textBuffer)) {
        const chunk = this.textBuffer;
        this.textBuffer = '';
        this._wordCount = 0;
        this._sendTTS(chunk);
      }
    }
  }

  /** Returns true when the text buffer should be flushed to TTS. */
  shouldFlush(text) {
    // In HTTP TTS mode, require more text before flushing to reduce
    // the number of expensive round-trips (each takes 2-4 seconds).
    if (!this.ttsConnected && text.length < this.HTTP_MIN_CHUNK_LENGTH) {
      return false;
    }
    return (
      text.length > this.FLUSH_MIN_LENGTH ||
      /[.!?]$/.test(text) ||
      /,\s$/.test(text) ||        // pause at commas
      /\band\s$/i.test(text) ||   // natural phrasing
      /\bbut\s$/i.test(text)      // natural phrasing
    );
  }

  /**
   * Strip common markdown formatting so the TTS engine speaks clean prose
   * instead of literal asterisks, hashes, or bracket syntax.
   */
  _stripMarkdown(text) {
    return text
      // Fenced code blocks (multiline)
      .replace(/```[\s\S]*?```/g, '')
      // Inline code
      .replace(/`([^`]+)`/g, '$1')
      // Bold + italic (*** or ___)
      .replace(/\*{3}([^*]+)\*{3}/g, '$1')
      .replace(/_{3}([^_]+)_{3}/g, '$1')
      // Bold (** or __)
      .replace(/\*{2}([^*]+)\*{2}/g, '$1')
      .replace(/_{2}([^_]+)_{2}/g, '$1')
      // Numbered list markers (e.g. "1. " "  2. ") – before italic so "1." dot isn't re-matched
      .replace(/^\s*\d+\.\s+/gm, '')
      // Bullet list markers ("* ", "- ", "+ ") – before italic so lone * isn't re-matched
      .replace(/^\s*[-*+]\s+/gm, '')
      // Headings
      .replace(/^#{1,6}\s+/gm, '')
      // Blockquotes
      .replace(/^\s*>\s*/gm, '')
      // Italic (* or _) – processed after bold/bullets so remaining * and _ are italic markers
      .replace(/\*([^*]+)\*/g, '$1')
      .replace(/_([^_]+)_/g, '$1')
      // Links – keep display text, drop URL
      .replace(/\[([^\]]+)\]\([^)]*\)/g, '$1')
      // HTML entities common in LLM output – decode &amp; last to avoid
      // double-unescaping sequences like &amp;lt; → &lt; → <
      .replace(/&lt;/g, '<')
      .replace(/&gt;/g, '>')
      .replace(/&nbsp;/g, ' ')
      .replace(/&amp;/g, '&')
      // Collapse runs of whitespace / newlines into a single space
      .replace(/\s+/g, ' ')
      .trim();
  }

  /** Send text to TTS immediately (no queue). Handles both WebSocket and HTTP paths. */
  _sendTTS(text) {
    if (!text || !text.trim()) return;
    const cleaned = this._stripMarkdown(text);
    if (!cleaned) return;

    const seq = this.ttsSeq++;

    // Backpressure: defer instead of dropping to avoid content loss
    // Adaptive concurrency: allow more parallelism when buffer is low, throttle when full
    const dynamicLimit = this.audioOutput.bufferedTime < 0.2 ? 16 : 8;
    if (this._ttsInFlight > dynamicLimit || this.audioOutput.bufferedTime > 0.3) {
      this.deferredTTSQueue.push({ text: cleaned, seq });
      // Freshness bias: drop oldest deferred chunks under heavy load
      // to keep speech feeling live rather than lagging behind
      if (this.deferredTTSQueue.length > 5) {
        this.deferredTTSQueue.shift();
      }
      return;
    }

    this._dispatchTTS(cleaned, seq);
  }

  /** Internal: actually dispatch a TTS request (shared by _sendTTS and _drainDeferredTTS). */
  _dispatchTTS(cleaned, seq) {
    // Priority mode: after an interrupt, flush any stale deferred chunks so
    // the new response wins immediately with zero competition.
    if (this._priorityMode) {
      this.deferredTTSQueue = [];
      this._priorityMode = false;
    }

    this._ttsInFlight++;
    const requestId = this._ttsRequestId;
    const preview = cleaned.substring(0, 40);
    console.log(`[VoiceEngine] TTS immediate [req=${requestId}, seq=${seq}]: "${preview}${cleaned.length > 40 ? '…' : ''}"`);

    if (this.ttsConnected && this.tts.ws && this.tts.ws.readyState === WebSocket.OPEN) {
      this.tts.sendText(cleaned, this.speaker);
      // onTTSDone will decrement _ttsInFlight
    } else {
      this._sendTTSHTTP(cleaned, requestId, seq);
    }
  }

  /** Drain deferred TTS queue gradually (one at a time) to avoid burst speech. */
  _drainDeferredTTS() {
    // Rate-limit: don't flood if already busy
    if (this._ttsInFlight > 8) return;

    if (
      this.deferredTTSQueue.length &&
      this.audioOutput.bufferedTime < 0.3
    ) {
      const { text, seq } = this.deferredTTSQueue.shift();
      this._dispatchTTS(text, seq);
    }
  }

  _sendTTSHTTP(text, requestId, seq) {
    const startTime = Date.now();
    const preview = text.trim().substring(0, 40);
    console.log(`[VoiceEngine] TTS HTTP [req=${requestId}, seq=${seq}] starting: "${preview}${text.length > 40 ? '…' : ''}"`);

    // Sentence-boundary detection: don't bleed prosody across sentence starts
    const isNewSentence = /^[A-Z]/.test(text.trim());
    const prevText = isNewSentence ? '' : this.lastSpokenText.slice(-200);

    // Per-request AbortController so interrupt can hard-cancel in-flight requests
    const controller = new AbortController();
    this._ttsControllers.set(seq, controller);

    fetch('/api/tts', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ text: text, speaker: this.speaker, prev_text: prevText }),
      signal: controller.signal
    })
    .then(response => response.json())
    .then(data => {
      if (data.success && data.audio) {
        const elapsed = Date.now() - startTime;
        // Drop stale audio after interrupt
        if (requestId !== this._ttsRequestId) {
          console.log(`[VoiceEngine] TTS HTTP [req=${requestId}] discarding stale audio (${elapsed}ms, current req=${this._ttsRequestId})`);
        } else {
          console.log(`[VoiceEngine] TTS HTTP [req=${requestId}, seq=${seq}] enqueuing audio (${elapsed}ms)`);
          // Accumulate lastSpokenText for prosody context (bounded to 200 chars)
          this.lastSpokenText += text;
          if (this.lastSpokenText.length > 200) {
            this.lastSpokenText = this.lastSpokenText.slice(-200);
          }
          const audioData = this.base64ToArrayBuffer(data.audio);
          this._handleTTSAudio(audioData, seq, text);
        }
      }
    })
    .catch(e => {
      if (e.name === 'AbortError') {
        console.log(`[VoiceEngine] TTS HTTP [req=${requestId}, seq=${seq}] aborted`);
      } else {
        console.error('[VoiceEngine] HTTP TTS failed:', e);
      }
    })
    .finally(() => {
      this._ttsControllers.delete(seq);
      if (requestId === this._ttsRequestId) {
        this._ttsInFlight = Math.max(0, this._ttsInFlight - 1);
        this._drainDeferredTTS();
        this._tryCompleteResponse();
      } else {
        console.log(`[VoiceEngine] TTS HTTP [req=${requestId}] stale finally – skipping state update (current req=${this._ttsRequestId})`);
      }
    });
  }

  /** Ordered playback handler: buffers out-of-order TTS results and plays in sequence. */
  _handleTTSAudio(buffer, seq, text) {
    this.pendingAudio.set(seq, { buffer, text });

    while (this.pendingAudio.has(this.expectedSeq)) {
      const entry = this.pendingAudio.get(this.expectedSeq);
      this.pendingAudio.delete(this.expectedSeq);

      this.audioOutput.enqueue(entry.buffer, entry.text);
      this.expectedSeq++;
    }

    // Timeout fallback: if a seq is lost/skipped, skip ahead to avoid memory leak
    setTimeout(() => {
      if (this.pendingAudio.has(seq) && seq > this.expectedSeq + this.MAX_SEQUENCE_GAP) {
        console.warn(`[VoiceEngine] Skipping missing seqs up to ${seq}`);
        this.expectedSeq = seq;
        // Re-drain from the new expectedSeq
        while (this.pendingAudio.has(this.expectedSeq)) {
          const entry = this.pendingAudio.get(this.expectedSeq);
          this.pendingAudio.delete(this.expectedSeq);
          this.audioOutput.enqueue(entry.buffer, entry.text);
          this.expectedSeq++;
        }
      }
    }, 2000);
  }
  
  base64ToArrayBuffer(base64) {
    const binaryString = atob(base64);
    const bytes = new Uint8Array(binaryString.length);
    for (let i = 0; i < binaryString.length; i++) {
      bytes[i] = binaryString.charCodeAt(i);
    }
    return bytes.buffer;
  }

  onLLMEnd() {
    // Discard completion from a cancelled/replaced LLM request
    if (this._activeLLMId !== this._llmRequestId) {
      console.log(`[VoiceEngine] onLLMEnd ignored – stale LLM id=${this._activeLLMId} (current=${this._llmRequestId})`);
      return;
    }
    console.log(`[VoiceEngine] LLM complete (id=${this._activeLLMId}), flushing ${this.textBuffer.length} chars remaining in text buffer`);
    if (this.textBuffer.trim()) {
      this._sendTTS(this.textBuffer);
      this.textBuffer = '';
      this._wordCount = 0;
    }
    this.responseFinished = true;
    // Check immediately: if TTS/audio already finished before this callback arrived
    this._tryCompleteResponse();
  }

  onTTSStart() {
  }

  onAudioChunk(chunk) {
    // Ignore stale chunks that arrive after an interrupt or stop
    if (this.ignoreAudioChunks) return;
    this.audioOutput.enqueue(chunk);
  }

  onTTSDone() {
    this._ttsInFlight = Math.max(0, this._ttsInFlight - 1);
    this._drainDeferredTTS();
    this._tryCompleteResponse();
  }

  onPlaybackEnded() {
    this._tryCompleteResponse();
  }

  /** Hard-cancel all in-flight HTTP TTS requests to save bandwidth and prevent stale audio. */
  _abortAllTTS() {
    for (const ctrl of this._ttsControllers.values()) {
      ctrl.abort();
    }
    this._ttsControllers.clear();
  }

  /**
   * Cancel any ongoing LLM/TTS pipeline and reset generation state, without
   * changing the VoiceState or touching the microphone.  Shared by
   * sendTypedMessage(), interrupt(), and interruptAI().
   */
  _cancelOngoingResponse() {
    this.llm.cancel();
    this.tts.cancel();
    this._abortAllTTS();
    this.audioOutput.softReset();
    this._ttsInFlight = 0;
    this.ignoreAudioChunks = true;
    this.accumulatedResponse = '';
    this.textBuffer = '';
    this._wordCount = 0;
    this.responseFinished = false;
    this.hasStartedSpeaking = false;
    this.llmStarted = false;
    this.hasSentFirstChunk = false;
    // Reset TTS sequencing state
    this.ttsSeq = 0;
    this.expectedSeq = 0;
    this.pendingAudio.clear();
    this.deferredTTSQueue = [];
    // Invalidate any in-flight HTTP TTS and stale LLM callbacks so they
    // do not enqueue audio or alter state for the upcoming new turn.
    this._ttsRequestId++;
    this._llmRequestId++;
    // Enable priority mode so the next response wins immediately
    this._priorityMode = true;
    // Reset filler guard for the new turn
    this._sentFillerThisTurn = false;
    this._fillerType = null;
    // Reset interrupt arbitration state
    this._interruptCandidate = false;
    this._isValidInterrupt = false;
    console.log(`[VoiceEngine] Cancelled ongoing response (ttsReqId=${this._ttsRequestId}, llmReqId=${this._llmRequestId})`);
  }

  /**
   * Central "are we done?" check.
   * Transitions to LISTENING only when ALL of the following are true:
   *   1. LLM has finished streaming (responseFinished)
   *   2. No TTS segments are in-flight (_ttsInFlight === 0)
   *   3. The audio output has finished playing
   */
  _tryCompleteResponse() {
    if (!this.responseFinished) return;
    // Drain any deferred TTS chunks first
    this._drainDeferredTTS();
    if (this._ttsInFlight > 0) return;
    if (this.deferredTTSQueue.length > 0) return;
    // Flush any audio that was waiting below the minBufferSec threshold
    this.audioOutput.flush();
    if (this.audioOutput.queueLength() > 0 || this.audioOutput.isPlaying()) return;

    console.log('[VoiceEngine] Response fully complete – transitioning to LISTENING');
    this.responseFinished = false;
    this.hasStartedSpeaking = false;
    this.llmStarted = false;
    this.hasSentFirstChunk = false;
    this.setState(VoiceState.LISTENING);
    if (this.alwaysListening) {
      this.audioInput.resumeVAD();
    }
  }

  /**
   * Toggle whether the engine automatically resumes listening after each AI turn.
   * When disabled the microphone VAD is paused and the user must type to send messages.
   */
  setAlwaysListening(enabled) {
    this.alwaysListening = enabled;
    if (this.state === VoiceState.LISTENING) {
      if (enabled) {
        this.audioInput.resumeVAD();
      } else {
        this.audioInput.pauseVAD();
      }
    }
  }

  /**
   * Fetch a greeting from the server and play it as the first AI turn.
   * Transitions through AI_SPEAKING → LISTENING (respecting alwaysListening).
   */
  async playGreeting() {
    try {
      const response = await fetch('/api/conversation/greeting', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ speaker: this.speaker })
      });
      const data = await response.json();

      if (data.success) {
        if (data.text) {
          this.onAIResponse(data.text);
        }

        if (data.audio) {
          this.setState(VoiceState.AI_SPEAKING);
          // Full duplex: keep VAD active so user can interrupt even during greeting
          this.ignoreAudioChunks = false;
          // Mark response finished so _tryCompleteResponse() can fire once playback ends
          this.responseFinished = true;
          const audioData = this.base64ToArrayBuffer(data.audio);
          this.audioOutput.enqueue(audioData);
          // onPlaybackEnded → _tryCompleteResponse → LISTENING (+ resumeVAD if alwaysListening)
        }
      }
    } catch (e) {
      console.warn('[VoiceEngine] Greeting failed:', e.message || e);
    }
  }

  interrupt() {
    if (this.state === VoiceState.AI_SPEAKING || this.state === VoiceState.THINKING) {
      console.log('[VoiceEngine] Interrupt requested');
      this._abortAllTTS();
      this.audioOutput.softReset();
      this.llm.cancel();
      this.tts.cancel();
      this.textBuffer = '';
      this._wordCount = 0;
      this.llmStarted = false;
      this.hasSentFirstChunk = false;
      this._ttsInFlight = 0;
      this._llmRequestId++;
      this._ttsRequestId++;
      this.accumulatedResponse = '';
      this.responseFinished = false;
      this.hasStartedSpeaking = false;
      this.ignoreAudioChunks = true;
      // Reset TTS sequencing state
      this.ttsSeq = 0;
      this.expectedSeq = 0;
      this.pendingAudio.clear();
      this.deferredTTSQueue = [];
      // Enable priority mode so the next response wins immediately
      this._priorityMode = true;
      // Reset filler guard for the new turn
      this._sentFillerThisTurn = false;
      this._fillerType = null;
      this.setState(VoiceState.LISTENING);
      if (this.alwaysListening) {
        this.audioInput.resumeVAD();
      }
    }
  }

  /**
   * Reset state before starting a new conversation.
   * Fixes the "only works once" bug by ensuring AudioContext is fresh.
   */
  startConversation() {
    this.audioOutput.reset();
    this.textBuffer = '';
    this.llmStarted = false;
    this.hasSentFirstChunk = false;
    this._ttsInFlight = 0;
    // Reset TTS sequencing state
    this.ttsSeq = 0;
    this.expectedSeq = 0;
    this.pendingAudio.clear();
    this.deferredTTSQueue = [];
    this._llmRequestId++;
    this._ttsRequestId++;
  }

  handleUserSpeechStart() {
    if (this.state !== VoiceState.AI_SPEAKING) return;
    // In HTTP TTS mode, skip barge-in entirely — the delayed audio playback
    // causes echo that triggers false interrupts, cutting off responses.
    if (!this.ttsConnected) return;

    // Too early → ignore (prevents self-interrupt from AI audio bleed)
    if (Date.now() < this._interruptEnabledAt) return;

    // Start interrupt candidate
    this._interruptCandidate = true;
    this._interruptStartTime = Date.now();

    // Duck audio instead of immediately cancelling
    this.audioOutput.setVolume?.(0.3);
  }

  /**
   * Return true if the text is noise / backchannel that should not trigger
   * an interrupt (e.g. "uh", "um", "hmm", or very short fragments).
   */
  _isNoise(text) {
    if (!text) return true;
    const trimmed = text.trim();
    return trimmed.length < 2 || /^(uh|um|hmm)$/i.test(trimmed);
  }

  interruptAI() {
    if (this.interrupting) return;

    // Restore volume in case ducking was active
    this.audioOutput.setVolume?.(1.0);

    this.interrupting = true;
    this._cancelOngoingResponse();
    this.setState(VoiceState.LISTENING);
    this.audioInput.resumeVAD();
    this.interrupting = false;
  }

  getState() {
    return this.state;
  }

  isSpeaking() {
    return this.state === VoiceState.AI_SPEAKING;
  }

  isListening() {
    return this.state === VoiceState.LISTENING || this.state === VoiceState.USER_SPEAKING;
  }
}

export default VoiceEngine;