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