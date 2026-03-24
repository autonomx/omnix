import { VoiceState } from './voiceState.js?v=2';
import { AudioInput } from './audioInput.js?v=2';
import { AudioOutput } from './audioOutput.js?v=2';
import { STTClient } from './sttClient.js?v=2';
import { LLMClient } from './llmClient.js?v=2';
import { TTSClient } from './ttsClient.js?v=2';

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
    this.MIN_PARTIAL_TEXT_LENGTH = 20;
    // Minimum text length before shouldFlush() returns true
    this.FLUSH_MIN_LENGTH = 30;
    // Count of TTS segments sent but not yet completed
    this._ttsInFlight = 0;
    // When false, VAD is paused after each turn so the user must type
    this.alwaysListening = options.alwaysListening !== false;
    // Monotonically incrementing counter – bumped on every cancel/interrupt so
    // in-flight HTTP TTS callbacks from the previous turn know they are stale
    // and discard their audio without touching engine state.
    this._ttsRequestId = 0;
    // Monotonically incrementing counter for LLM requests so stale onLLMToken /
    // onLLMEnd callbacks from a cancelled request are silently ignored.
    this._llmRequestId = 0;
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
    this.audioOutput.reset();
    this.llm.cancel();

    this.setState(VoiceState.IDLE);
    
    this.currentTranscript = '';
    this.accumulatedResponse = '';
    this.textBuffer = '';
    this.ignoreAudioChunks = false;
    this.responseFinished = false;
    this.llmStarted = false;
    this._ttsInFlight = 0;
    // Invalidate all in-flight HTTP TTS and LLM callbacks
    this._ttsRequestId++;
    this._llmRequestId++;
  }

  onSpeechStart() {
    const isInterrupt = (this.state === VoiceState.AI_SPEAKING || this.state === VoiceState.THINKING) 
                        && this.audioInput.hasEnoughAudioForInterrupt();
    
    this.textBuffer = '';
    this.responseFinished = false;
    this.hasStartedSpeaking = false;
    
    if (isInterrupt) {
      console.log('[VoiceEngine] User interrupted AI');
      
      this._ttsInFlight = 0;
      this.ignoreAudioChunks = true;
      this.audioOutput.reset();
      this.llm.cancel();
      this.audioInput.resumeVAD();
      // Invalidate any in-flight HTTP TTS / stale LLM callbacks
      this._ttsRequestId++;
      this._llmRequestId++;
      this.llmStarted = false;
      
      this.setState(VoiceState.INTERRUPTED);
      this.accumulatedResponse = '';
      this.textBuffer = '';
    } else if (this.state === VoiceState.AI_SPEAKING || this.state === VoiceState.THINKING) {
      return;
    }

    if (this.state !== VoiceState.INTERRUPTED) {
      this.setState(VoiceState.USER_SPEAKING);
    }
  }

  onSpeechEnd() {
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
    if (this.state === VoiceState.USER_SPEAKING || this.state === VoiceState.LISTENING) {
      this.stt.sendAudio(chunk);
    }
  }

  onTranscript(text) {
    this.currentTranscript = text;
    // Call the external callback passed via options (not this method — that would recurse infinitely)
    if (this._onTranscriptCallback) this._onTranscriptCallback(text);

    // Start LLM early on partial STT when enough text has arrived
    if (!this.llmStarted && text && text.length > this.MIN_PARTIAL_TEXT_LENGTH &&
        (this.state === VoiceState.USER_SPEAKING || this.state === VoiceState.LISTENING)) {
      this.llmStarted = true;
      console.log('[VoiceEngine] Starting LLM early on partial transcript:', text);
      this.llm.sendMessage(text, this.sessionId, this.speaker);
    }
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
  }

  onLLMToken(token) {
    // Discard tokens from a cancelled/replaced LLM request
    if (this._activeLLMId !== this._llmRequestId) return;

    if (!this.hasStartedSpeaking) {
      this.hasStartedSpeaking = true;
      this.setState(VoiceState.AI_SPEAKING);
      this.audioInput.pauseVAD();
      console.log(`[VoiceEngine] LLM first token received (id=${this._activeLLMId})`);
    }
    
    this.accumulatedResponse += token;
    this.onAIResponse(this.accumulatedResponse);
    
    this.textBuffer += token;
    
    if (this.textBuffer.length > this.TTS_MAX_BUFFER_LENGTH) {
      // Hard cap: flush to prevent unbounded buffer growth
      const flushText = this.textBuffer;
      this.textBuffer = '';
      this._sendTTS(flushText);
      return;
    }
    
    if (this.textBuffer.length > this.TTS_FLUSH_LENGTH) {
      // Flush when enough text has accumulated
      const flushText = this.textBuffer;
      this.textBuffer = '';
      this._sendTTS(flushText);
      return;
    }
    
    // Flush on sentence-ending punctuation for natural speech boundaries.
    // Also flush on comma/semicolon when the buffer is long enough.
    if (this.shouldFlush(this.textBuffer)) {
      const sentenceMatch = this.textBuffer.match(/(.+?[.!?])(\s|$)/);
      if (sentenceMatch) {
        const sentence = sentenceMatch[1];
        this.textBuffer = this.textBuffer.slice(sentenceMatch.index + sentence.length);
        this._sendTTS(sentence);
        return;
      }

      // Clause boundary flush
      if (this.textBuffer.length > this.TTS_CLAUSE_FLUSH_MIN_LENGTH) {
        const clauseMatch = this.textBuffer.match(/(.+?[,;])(\s|$)/);
        if (clauseMatch) {
          const clause = clauseMatch[1];
          this.textBuffer = this.textBuffer.slice(clauseMatch.index + clause.length);
          this._sendTTS(clause);
          return;
        }
      }

      // Fallback: flush the whole buffer if it matches generic flush criteria
      if (this.textBuffer.length > this.FLUSH_MIN_LENGTH || /[.,!?]$/.test(this.textBuffer)) {
        const chunk = this.textBuffer;
        this.textBuffer = '';
        this._sendTTS(chunk);
      }
    }
  }

  /** Returns true when the text buffer should be flushed to TTS. */
  shouldFlush(text) {
    return (
      text.length > this.FLUSH_MIN_LENGTH ||
      /[.!?,;]/.test(text)
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

    this._ttsInFlight++;
    const requestId = this._ttsRequestId;
    const preview = cleaned.substring(0, 40);
    console.log(`[VoiceEngine] TTS immediate [req=${requestId}]: "${preview}${cleaned.length > 40 ? '…' : ''}"`);

    if (this.ttsConnected && this.tts.ws && this.tts.ws.readyState === WebSocket.OPEN) {
      this.tts.sendText(cleaned, this.speaker);
      // onTTSDone will decrement _ttsInFlight
    } else {
      this._sendTTSHTTP(cleaned, requestId);
    }
  }

  _sendTTSHTTP(text, requestId) {
    const startTime = Date.now();
    const preview = text.trim().substring(0, 40);
    console.log(`[VoiceEngine] TTS HTTP [req=${requestId}] starting: "${preview}${text.length > 40 ? '…' : ''}"`);

    fetch('/api/tts', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ text: text, speaker: this.speaker })
    })
    .then(response => response.json())
    .then(data => {
      if (data.success && data.audio) {
        const elapsed = Date.now() - startTime;
        if (requestId !== this._ttsRequestId) {
          console.log(`[VoiceEngine] TTS HTTP [req=${requestId}] discarding stale audio (${elapsed}ms, current req=${this._ttsRequestId})`);
        } else {
          console.log(`[VoiceEngine] TTS HTTP [req=${requestId}] enqueuing audio (${elapsed}ms)`);
          const audioData = this.base64ToArrayBuffer(data.audio);
          this.audioOutput.enqueue(audioData);
        }
      }
    })
    .catch(e => {
      console.error('[VoiceEngine] HTTP TTS failed:', e);
    })
    .finally(() => {
      if (requestId === this._ttsRequestId) {
        if (this._ttsInFlight > 0) this._ttsInFlight--;
        this._tryCompleteResponse();
      } else {
        console.log(`[VoiceEngine] TTS HTTP [req=${requestId}] stale finally – skipping state update (current req=${this._ttsRequestId})`);
      }
    });
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
    if (this._ttsInFlight > 0) this._ttsInFlight--;
    this._tryCompleteResponse();
  }

  onPlaybackEnded() {
    this._tryCompleteResponse();
  }

  /**
   * Cancel any ongoing LLM/TTS pipeline and reset generation state, without
   * changing the VoiceState or touching the microphone.  Shared by
   * sendTypedMessage(), interrupt(), and interruptAI().
   */
  _cancelOngoingResponse() {
    this.llm.cancel();
    this.tts.cancel();
    this.audioOutput.reset();
    this._ttsInFlight = 0;
    this.ignoreAudioChunks = true;
    this.accumulatedResponse = '';
    this.textBuffer = '';
    this.responseFinished = false;
    this.hasStartedSpeaking = false;
    this.llmStarted = false;
    // Invalidate any in-flight HTTP TTS and stale LLM callbacks so they
    // do not enqueue audio or alter state for the upcoming new turn.
    this._ttsRequestId++;
    this._llmRequestId++;
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
    if (this._ttsInFlight > 0) return;
    // Flush any audio that was waiting below the minBufferSec threshold
    this.audioOutput.flush();
    if (this.audioOutput.queueLength() > 0 || this.audioOutput.isPlaying()) return;

    console.log('[VoiceEngine] Response fully complete – transitioning to LISTENING');
    this.responseFinished = false;
    this.hasStartedSpeaking = false;
    this.llmStarted = false;
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
          this.audioInput.pauseVAD();
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
      this.audioOutput.reset();
      this.llm.cancel();
      this.tts.cancel();
      this.textBuffer = '';
      this.llmStarted = false;
      this._ttsInFlight = 0;
      this._llmRequestId++;
      this._ttsRequestId++;
      this.accumulatedResponse = '';
      this.responseFinished = false;
      this.hasStartedSpeaking = false;
      this.ignoreAudioChunks = true;
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
    this._ttsInFlight = 0;
    this._llmRequestId++;
    this._ttsRequestId++;
  }

  handleUserSpeechStart() {
    if (this.state === VoiceState.AI_SPEAKING) {
      this.interruptAI();
    }
  }

  interruptAI() {
    if (this.interrupting) return;
    
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