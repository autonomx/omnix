/**
 * AudioWorklet processor for continuous streaming audio playback.
 *
 * Uses a ring buffer to decouple the main-thread push rate from the
 * audio-thread consumption rate, eliminating gaps, clicks and drift
 * that occur with per-chunk AudioBufferSourceNode scheduling.
 *
 * Main thread sends { type: "push", samples: Float32Array } messages
 * to feed audio data into the buffer.
 */
class StreamProcessor extends AudioWorkletProcessor {
  static UNDERRUN_DECAY_FACTOR = 0.995;
  static UNDERRUN_RECOVERY_LEN = 64; // ~2.7ms crossfade on recovery

  constructor(options) {
    super();

    const sr = (options && options.processorOptions && options.processorOptions.sampleRate)
      ? options.processorOptions.sampleRate
      : sampleRate;
    this.buffer = new Float32Array(sr * 10); // 10 sec ring buffer
    this.writeIndex = 0;
    this.readIndex = 0;
    this.availableSamples = 0;
    this.totalSamplesPlayed = 0;
    this.frameCount = 0;
    this.lastSample = 0;
    this.underrunDecayFactor = StreamProcessor.UNDERRUN_DECAY_FACTOR;

    // Underrun recovery state: smoothly blend from decayed silence to
    // new buffer data when audio resumes after a buffer underrun.
    this.wasUnderrun = false;
    this.recoveryRemaining = 0;
    this.recoveryBaseSample = 0;

    this.port.onmessage = (event) => {
      if (event.data.type === "push") {
        this.pushData(event.data.samples);
      }
    };
  }

  pushData(samples) {
    for (let i = 0; i < samples.length; i++) {
      if (this.availableSamples >= this.buffer.length) {
        // buffer full — drop oldest (backpressure safety)
        this.readIndex = (this.readIndex + 1) % this.buffer.length;
        this.availableSamples--;
      }

      this.buffer[this.writeIndex] = samples[i];
      this.writeIndex = (this.writeIndex + 1) % this.buffer.length;
      this.availableSamples++;
    }
  }

  process(inputs, outputs) {
    const output = outputs[0][0];

    for (let i = 0; i < output.length; i++) {
      if (this.availableSamples > 0) {
        const sample = this.buffer[this.readIndex];
        this.readIndex = (this.readIndex + 1) % this.buffer.length;
        this.availableSamples--;
        this.totalSamplesPlayed++;

        // Detect transition from underrun back to data and start recovery
        if (this.wasUnderrun) {
          this.wasUnderrun = false;
          this.recoveryBaseSample = this.lastSample;
          this.recoveryRemaining = StreamProcessor.UNDERRUN_RECOVERY_LEN;
        }

        if (this.recoveryRemaining > 0) {
          // Raised-cosine blend from decayed lastSample to buffer data
          const t = 1.0 - this.recoveryRemaining / StreamProcessor.UNDERRUN_RECOVERY_LEN;
          const w = 0.5 * (1.0 - Math.cos(Math.PI * t));
          output[i] = this.recoveryBaseSample * (1.0 - w) + sample * w;
          this.recoveryRemaining--;
        } else {
          output[i] = sample;
        }
        this.lastSample = output[i];
      } else {
        // underrun — smooth to silence to avoid hard-edge clicks
        this.wasUnderrun = true;
        this.lastSample *= this.underrunDecayFactor;
        output[i] = this.lastSample;
      }
    }

    // Report playback progress and buffer level to main thread (~16-32ms typical;
    // exact interval depends on runtime sample rate and render quantum)
    this.frameCount++;
    if (this.frameCount >= 6) {
      this.frameCount = 0;
      this.port.postMessage({
        type: "progress",
        samplesPlayed: this.totalSamplesPlayed,
        availableSamples: this.availableSamples,
      });
    }

    return true;
  }
}

registerProcessor("stream-processor", StreamProcessor);
