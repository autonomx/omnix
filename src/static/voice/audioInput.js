export class AudioInput {
  constructor(onSpeechStart, onSpeechEnd, onAudioChunk, onUserSpeechStart) {
    this.onSpeechStart = onSpeechStart || (() => {});
    this.onSpeechEnd = onSpeechEnd || (() => {});
    this.onAudioChunk = onAudioChunk || (() => {});
    this.onUserSpeechStart = onUserSpeechStart || (() => {});

    this.stream = null;
    this.audioContext = null;
    this.source = null;
    this.processor = null;

    this.vadPaused = false;
    this.isSpeaking = false;
    this.silenceTimer = null;
    this.speechStartTime = null;
    this.audioChunksSinceStart = 0;

    // VAD thresholds
    this.VAD_THRESHOLD = 0.008;
    this.VAD_SILENCE_TIMEOUT = 500;
    this.MIN_SPEECH_CHUNKS = 3; // minimum chunks of audio needed to count as a real interrupt

    // Echo cancellation: reference to the AudioOutput instance whose
    // lastPlayedSamples are compared against incoming mic data.
    this._audioOutput = null;
    /** Correlation threshold above which a mic chunk is considered echo. */
    this.ECHO_SIMILARITY_THRESHOLD = 0.8;

    // SpeakerFilter: multi-signal echo/user classification (replaces basic
    // echo-only check when wired up via setSpeakerFilter).
    this.speakerFilter = null;
  }

  async start() {
    if (this.audioContext) return;

    this.stream = await navigator.mediaDevices.getUserMedia({
      audio: {
        echoCancellation: true,
        noiseSuppression: true,
        autoGainControl: true
      }
    });

    this.audioContext = new (window.AudioContext || window.webkitAudioContext)({
      latencyHint: 'interactive'
    });

    if (this.audioContext.state === 'suspended') {
      await this.audioContext.resume();
    }

    this.source = this.audioContext.createMediaStreamSource(this.stream);

    try {
      await this.audioContext.audioWorklet.addModule('/static/js/audio/vad-recorder-worklet.js');
      this.processor = new AudioWorkletNode(this.audioContext, 'vad-recorder');

      this.processor.port.onmessage = (e) => {
        const samples = e.data;
        if (!samples || samples.length === 0) return;
        this._processAudioChunk(samples);
      };

      this.source.connect(this.processor);
      this.processor.connect(this.audioContext.destination);
    } catch (workletError) {
      console.warn('[AudioInput] AudioWorklet unavailable, falling back to ScriptProcessor:', workletError.message);

      this.processor = this.audioContext.createScriptProcessor(4096, 1, 1);
      this.processor.onaudioprocess = (event) => {
        const samples = event.inputBuffer.getChannelData(0);
        this._processAudioChunk(new Float32Array(samples));
      };

      this.source.connect(this.processor);
      this.processor.connect(this.audioContext.destination);
    }

    console.log('[AudioInput] Started, sampleRate:', this.audioContext.sampleRate);
  }

  _processAudioChunk(samples) {
    if (this.vadPaused) return;

    // Speaker classification: use multi-signal SpeakerFilter when available,
    // falling back to the simpler correlation-based isEcho() check.
    if (this.speakerFilter) {
      const type = this.speakerFilter.classify(samples);
      if (type === 'echo') return;           // AI voice — ignore entirely
      if (type === 'uncertain') {
        samples = this._attenuate(samples, 0.5); // ambiguous — attenuate
      }
    } else if (this.isEcho(samples)) {
      samples = this._attenuate(samples, 0.3);
    }

    // Always forward audio to STT when the user is speaking
    if (this.isSpeaking) {
      this.audioChunksSinceStart++;
      this.onAudioChunk(samples);
    }

    // Compute RMS energy for VAD
    let sum = 0;
    for (let i = 0; i < samples.length; i++) {
      sum += samples[i] * samples[i];
    }
    const rms = Math.sqrt(sum / samples.length);

    if (rms > this.VAD_THRESHOLD) {
      // Voice detected
      if (this.silenceTimer) {
        clearTimeout(this.silenceTimer);
        this.silenceTimer = null;
      }

      if (!this.isSpeaking) {
        this.isSpeaking = true;
        this.speechStartTime = Date.now();
        this.audioChunksSinceStart = 0;
        console.log('[AudioInput] Speech start detected');
        this.onUserSpeechStart();
        this.onSpeechStart();
        // Send the triggering chunk immediately and count it
        this.audioChunksSinceStart++;
        this.onAudioChunk(samples);
      }
    } else if (this.isSpeaking && !this.silenceTimer) {
      // Silence detected while speaking — start silence timeout
      this.silenceTimer = setTimeout(() => {
        this.silenceTimer = null;
        if (this.isSpeaking) {
          this.isSpeaking = false;
          console.log('[AudioInput] Speech end detected');
          this.onSpeechEnd();
        }
      }, this.VAD_SILENCE_TIMEOUT);
    }
  }

  pauseVAD() {
    this.vadPaused = true;
    if (this.silenceTimer) {
      clearTimeout(this.silenceTimer);
      this.silenceTimer = null;
    }
    if (this.isSpeaking) {
      this.isSpeaking = false;
    }
  }

  resumeVAD() {
    this.vadPaused = false;
  }

  /**
   * Link an AudioOutput instance so that echo cancellation can compare
   * incoming mic audio against the most recently played TTS output.
   * @param {import('./audioOutput.js').AudioOutput} audioOutput
   */
  setAudioOutput(audioOutput) {
    this._audioOutput = audioOutput;
  }

  /**
   * Attach a SpeakerFilter for multi-signal echo/user classification.
   * When set, _processAudioChunk uses the filter instead of the basic
   * isEcho() correlation check.
   * @param {import('./speakerFilter.js').SpeakerFilter} filter
   */
  setSpeakerFilter(filter) {
    this.speakerFilter = filter;
  }

  /**
   * Return true if `inputChunk` closely matches the audio we recently
   * played through AudioOutput, indicating the mic is hearing its own echo.
   *
   * Uses a lightweight normalised dot-product correlation — not perfect
   * but a significant improvement over no echo detection at all.
   *
   * @param {Float32Array} inputChunk
   * @returns {boolean}
   */
  isEcho(inputChunk) {
    if (!this._audioOutput) return false;
    const ref = this._audioOutput.lastPlayedSamples;
    if (!ref) return false;

    const similarity = AudioInput._correlate(inputChunk, ref);
    return similarity > this.ECHO_SIMILARITY_THRESHOLD;
  }

  /**
   * Normalised dot-product correlation between two audio buffers.
   * Returns a value in [-1, 1] where 1 means identical and -1 means
   * perfectly anti-correlated.  For echo detection only the magnitude
   * matters; the caller compares the result against a positive threshold.
   *
   * To keep this lightweight, at most MAX_CORRELATE_SAMPLES are compared
   * (roughly 1 second at 24 kHz).
   *
   * @param {Float32Array} a
   * @param {Float32Array} b
   * @returns {number}
   */
  static _correlate(a, b) {
    // Cap the comparison window to ~1 s at 24 kHz to avoid expensive
    // correlations on long buffers.
    const MAX_CORRELATE_SAMPLES = 24000;
    const len = Math.min(a.length, b.length, MAX_CORRELATE_SAMPLES);
    if (len === 0) return 0;

    let dot = 0;
    let normA = 0;
    let normB = 0;
    for (let i = 0; i < len; i++) {
      dot += a[i] * b[i];
      normA += a[i] * a[i];
      normB += b[i] * b[i];
    }

    const denom = Math.sqrt(normA) * Math.sqrt(normB);
    return denom === 0 ? 0 : dot / denom;
  }

  /**
   * Return a new Float32Array with every sample scaled by `factor`.
   * Used for echo attenuation: reduces echo energy without dropping
   * the chunk entirely so overlapping real speech is preserved.
   *
   * @param {Float32Array} samples
   * @param {number} factor - Scaling factor (0–1)
   * @returns {Float32Array}
   */
  _attenuate(samples, factor) {
    const out = new Float32Array(samples.length);
    for (let i = 0; i < samples.length; i++) {
      out[i] = samples[i] * factor;
    }
    return out;
  }

  hasEnoughAudioForInterrupt() {
    return this.audioChunksSinceStart >= this.MIN_SPEECH_CHUNKS;
  }

  stop() {
    this.vadPaused = false;
    this.isSpeaking = false;

    if (this.silenceTimer) {
      clearTimeout(this.silenceTimer);
      this.silenceTimer = null;
    }

    if (this.processor) {
      try {
        if (this.processor instanceof AudioWorkletNode) {
          this.processor.port.postMessage({ type: 'stop' });
        }
        this.processor.disconnect();
      } catch (e) {}
      this.processor = null;
    }

    if (this.source) {
      try {
        this.source.disconnect();
      } catch (e) {}
      this.source = null;
    }

    if (this.stream) {
      this.stream.getTracks().forEach(t => t.stop());
      this.stream = null;
    }

    if (this.audioContext) {
      this.audioContext.close().catch(() => {});
      this.audioContext = null;
    }

    console.log('[AudioInput] Stopped');
  }
}

export default AudioInput;