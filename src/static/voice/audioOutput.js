export const TIMELINE_GAP_OFFSET = 0.05;

export class AudioOutput {
  constructor() {
    this.ctx = null;
    this.nextTime = 0;
    this.started = false;
    this.bufferedTime = 0;
    this.minBufferSec = 0.15; // tweakable: delay start until small buffer ready
    this.onPlaybackStart = null;
    this.onPlaybackEnd = null;
    this.hasPlayedSomething = false;
    this._pendingBuffers = [];
    this._activeSourceCount = 0;
    this._activeSources = [];
    this._resetGeneration = 0;
    this._lastChunkText = null;
  }

  _ensureContext() {
    if (!this.ctx) {
      this.ctx = new (window.AudioContext || window.webkitAudioContext)({
        sampleRate: 24000,
        latencyHint: 'interactive'
      });
      this.nextTime = this.ctx.currentTime + 0.1;
      this.started = false;
      this.bufferedTime = 0;
    }
    if (this.ctx.state === 'suspended') {
      this.ctx.resume();
    }
  }

  /**
   * Convert a raw chunk (Float32Array, ArrayBuffer/WAV) to a Web Audio
   * AudioBuffer and schedule it on the playback timeline.
   * @param {Float32Array|ArrayBuffer} chunk - Audio data to enqueue
   * @param {string} [text] - Source text for this chunk; used to determine
   *   sentence-ending pauses for natural prosody.
   */
  enqueue(chunk, text) {
    this._ensureContext();

    // Prevent timeline from falling behind (gap protection)
    if (this.nextTime < this.ctx.currentTime + TIMELINE_GAP_OFFSET) {
      this.nextTime = this.ctx.currentTime + TIMELINE_GAP_OFFSET;
    }

    // Track the source text for prosody pauses
    if (text) this._lastChunkText = text;

    let float32;
    let sampleRate;

    if (chunk instanceof Float32Array) {
      float32 = chunk;
      sampleRate = this.ctx.sampleRate;
    } else {
      const uint8arr = new Uint8Array(chunk);

      if (uint8arr.length > 44 &&
          String.fromCharCode(uint8arr[0], uint8arr[1], uint8arr[2], uint8arr[3]) === 'RIFF' &&
          String.fromCharCode(uint8arr[8], uint8arr[9], uint8arr[10], uint8arr[11]) === 'WAVE') {
        const wavData = this.parseWAV(uint8arr);
        float32 = wavData.float32;
        sampleRate = wavData.sampleRate;
      } else {
        let buffer = chunk;
        if (buffer.byteLength % 2 !== 0) {
          const paddedBuffer = new ArrayBuffer(buffer.byteLength + 1);
          new Uint8Array(paddedBuffer).set(new Uint8Array(buffer));
          buffer = paddedBuffer;
        }
        const pcm16 = new Int16Array(buffer);
        float32 = new Float32Array(pcm16.length);
        for (let i = 0; i < pcm16.length; i++) {
          float32[i] = pcm16[i] / 32768.0;
        }
        sampleRate = 24000;
      }
    }

    const audioBuffer = this.ctx.createBuffer(1, float32.length, sampleRate);
    audioBuffer.getChannelData(0).set(float32);

    this.bufferedTime += audioBuffer.duration;

    // Fast-start first audio (don't wait full buffer)
    if (!this.started) {
      this.started = true;
      this.nextTime = this.ctx.currentTime + TIMELINE_GAP_OFFSET;
      this.hasPlayedSomething = true;
      if (this.onPlaybackStart) {
        this.onPlaybackStart();
      }
      // Schedule all pending buffers
      for (const buf of this._pendingBuffers) {
        this._scheduleBuffer(buf);
      }
      this._pendingBuffers = [];
    }

    this._scheduleBuffer(audioBuffer);
  }

  /** Schedule a decoded AudioBuffer on the playback timeline (fire-and-forget). */
  _scheduleBuffer(audioBuffer) {
    this.hasPlayedSomething = true;

    const source = this.ctx.createBufferSource();
    source.buffer = audioBuffer;

    const gain = this.ctx.createGain();
    source.connect(gain).connect(this.ctx.destination);

    // Underrun protection: if timeline has fallen behind, reset to now
    const now = this.ctx.currentTime;
    if (this.nextTime < now) {
      this.nextTime = now + 0.02;
    }

    const t = this.nextTime;

    // Micro fade (prevents clicks between chunks)
    const fadeDuration = Math.min(0.015, audioBuffer.duration / 4);
    gain.gain.setValueAtTime(0, t);
    gain.gain.linearRampToValueAtTime(1, t + fadeDuration);
    if (audioBuffer.duration > fadeDuration * 2) {
      gain.gain.setValueAtTime(1, t + audioBuffer.duration - fadeDuration);
      gain.gain.linearRampToValueAtTime(0, t + audioBuffer.duration);
    }

    source.start(t);

    this._activeSourceCount++;
    this._activeSources.push(source);
    const gen = this._resetGeneration;

    source.onended = () => {
      // Ignore callbacks from sources that belong to a previous (cancelled) session
      if (gen !== this._resetGeneration) return;
      this._activeSourceCount--;
      const idx = this._activeSources.indexOf(source);
      if (idx !== -1) this._activeSources.splice(idx, 1);
      if (this._activeSourceCount === 0 && this.hasPlayedSomething) {
        this.hasPlayedSomething = false;
        if (this.onPlaybackEnd) {
          console.log('[AudioOutput] Timeline empty – firing onPlaybackEnd');
          this.onPlaybackEnd();
        }
      }
    };

    // Semantic pacing: meaning-aware pauses for natural speech rhythm
    let pause = 0.02;
    if (this._lastChunkText) {
      if (/[,.]/.test(this._lastChunkText)) pause += 0.04;
      if (/[!?]/.test(this._lastChunkText)) pause += 0.08;
      if (/\b(and|but|so|because)\b/i.test(this._lastChunkText)) pause += 0.02;
    }
    const jitter = Math.random() * 0.015;
    this.nextTime += audioBuffer.duration + pause + jitter;
  }

  /**
   * Signal that no more chunks will arrive — flush whatever is buffered
   * below the minBufferSec threshold.
   */
  flush() {
    if (!this.started && this._pendingBuffers.length > 0) {
      this._ensureContext();
      this.started = true;
      this.hasPlayedSomething = true;
      if (this.onPlaybackStart) {
        this.onPlaybackStart();
      }
      for (const buf of this._pendingBuffers) {
        this._scheduleBuffer(buf);
      }
      this._pendingBuffers = [];
    }
  }

  parseWAV(wavData) {
    const view = new DataView(wavData.buffer);
    
    let offset = 12;
    let sampleRate = 24000;
    let numChannels = 1;
    let bitsPerSample = 16;
    
    while (offset < wavData.length - 8) {
      const id = String.fromCharCode(
        wavData[offset], wavData[offset + 1], 
        wavData[offset + 2], wavData[offset + 3]
      );
      const size = view.getUint32(offset + 4, true);
      
      if (id === 'fmt ') {
        numChannels = view.getUint16(offset + 10, true);
        sampleRate = view.getUint32(offset + 12, true);  // sampleRate is 4 bytes, not 2
        bitsPerSample = view.getUint16(offset + 22, true);
        offset += 8 + size;
      } else if (id === 'data') {
        const dataOffset = offset + 8;
        const numSamples = Math.floor(size / (bitsPerSample / 8));
        
        const float32 = new Float32Array(numSamples);
        
        if (bitsPerSample === 16) {
          for (let i = 0; i < numSamples; i++) {
            const sample = view.getInt16(dataOffset + i * 2, true);
            float32[i] = sample / 32768.0;
          }
        } else if (bitsPerSample === 32) {
          for (let i = 0; i < numSamples; i++) {
            const sample = view.getInt32(dataOffset + i * 4, true);
            float32[i] = sample / 2147483648.0;
          }
        } else if (bitsPerSample === 8) {
          for (let i = 0; i < numSamples; i++) {
            const sample = wavData[dataOffset + i] - 128;
            float32[i] = sample / 128.0;
          }
        }
        
        return { float32, sampleRate };
      } else {
        offset += 8 + size;
      }
    }
    
    return { float32: new Float32Array(0), sampleRate: 24000 };
  }

  /**
   * Lightweight reset: keep the AudioContext alive, just reset scheduling state.
   * Avoids the latency cost of AudioContext recreation.
   * Falls back to full reset() if the context is in a broken state.
   */
  softReset() {
    this._resetGeneration++;
    // Stop all currently playing sources immediately for instant interrupt
    for (const src of this._activeSources) {
      try { src.stop(); } catch (e) {}
    }
    this._activeSources = [];
    if (this.ctx && this.ctx.state !== 'closed') {
      this.nextTime = this.ctx.currentTime + TIMELINE_GAP_OFFSET;
    } else {
      this.ctx = null;
      this.nextTime = 0;
    }
    this.started = false;
    this.bufferedTime = 0;
    this._pendingBuffers = [];
    this._activeSourceCount = 0;
    this.hasPlayedSomething = false;
    this._lastChunkText = null;
  }

  /** Tear down the AudioContext and reset all scheduling state. */
  reset() {
    this._resetGeneration++;
    // Stop all currently playing sources immediately
    for (const src of this._activeSources) {
      try { src.stop(); } catch (e) {}
    }
    this._activeSources = [];
    if (this.ctx) {
      try { this.ctx.close(); } catch (e) {}
    }
    this.ctx = null;
    this.nextTime = 0;
    this.started = false;
    this.bufferedTime = 0;
    this._pendingBuffers = [];
    this._activeSourceCount = 0;
    this.hasPlayedSomething = false;
    this._lastChunkText = null;
  }

  stop() {
    this.reset();
  }

  isPlaying() {
    if (!this.ctx) return false;
    return this._activeSourceCount > 0;
  }

  queueLength() {
    return this._pendingBuffers.length;
  }

  stopAll() {
    this.softReset();
  }

  clear() {
    this._pendingBuffers = [];
  }
}

export default AudioOutput;
