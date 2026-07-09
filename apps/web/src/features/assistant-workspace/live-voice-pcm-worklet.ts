export const LIVE_VOICE_PCM_WORKLET_NAME = 'omnix-live-voice-pcm-stream';

export function liveVoicePcmWorkletSource(): string {
  return `
class OmnixLiveVoicePcmStreamProcessor extends AudioWorkletProcessor {
  constructor(options) {
    super();
    const settings = options.processorOptions || {};
    this.startBufferSamples = Math.max(1, Number(settings.startBufferSamples) || sampleRate * 0.4);
    this.rebufferSamples = Math.max(1, Number(settings.rebufferSamples) || sampleRate * 0.75);
    this.maxRebufferSamples = Math.max(
      this.rebufferSamples,
      Number(settings.maxRebufferSamples) || sampleRate * 1.5,
    );
    this.currentRebufferSamples = this.rebufferSamples;
    this.transitionFadeSamples = Math.max(
      1,
      Number(settings.transitionFadeSamples) || Math.round(sampleRate * 0.008),
    );
    this.progressIntervalSamples = Math.max(128, Math.round(sampleRate * 0.5));
    this.queue = [];
    this.endedPhrases = new Set();
    this.headOffset = 0;
    this.queuedSamples = 0;
    this.started = false;
    this.waitingForBuffer = false;
    this.inputEnded = false;
    this.stopped = false;
    this.drained = false;
    this.fadeInRemaining = 0;
    this.underrunCount = 0;
    this.renderClockSamples = 0;
    this.playedSamples = 0;
    this.lastProgressSamples = 0;
    this.currentPhraseIndex = null;
    this.currentPhrasePlayedSamples = 0;
    this.port.onmessage = (event) => {
      const message = event.data || {};
      if (message.type === 'push' && message.samples) {
        const samples = message.samples instanceof Float32Array
          ? message.samples
          : new Float32Array(message.samples);
        const phraseIndex = Number.isInteger(message.phraseIndex) ? message.phraseIndex : -1;
        if (samples.length > 0) {
          this.queue.push({ phraseIndex, samples });
          this.queuedSamples += samples.length;
          this.port.postMessage({
            type: 'buffered',
            phrase_index: phraseIndex,
            buffered_samples: this.queuedSamples,
            incoming_samples: samples.length,
            target_samples: this.waitingForBuffer ? this.currentRebufferSamples : this.startBufferSamples,
            waiting_for_buffer: this.waitingForBuffer,
            input_ended: this.inputEnded,
            underrun_count: this.underrunCount,
            render_clock_samples: this.renderClockSamples,
            played_samples: this.playedSamples,
          });
          this.maybeStartOrResume();
        }
        return;
      }
      if (message.type === 'phrase_end' && Number.isInteger(message.phraseIndex)) {
        this.endedPhrases.add(message.phraseIndex);
        this.maybeCompleteCurrentPhrase();
        return;
      }
      if (message.type === 'end') {
        this.inputEnded = true;
        this.port.postMessage({
          type: 'input_ended',
          buffered_samples: this.queuedSamples,
          waiting_for_buffer: this.waitingForBuffer,
          underrun_count: this.underrunCount,
          render_clock_samples: this.renderClockSamples,
          played_samples: this.playedSamples,
        });
        this.maybeStartOrResume();
        return;
      }
      if (message.type === 'stop') {
        this.signalPhraseInterrupted();
        this.stopped = true;
        this.port.postMessage({
          type: 'stopped',
          buffered_samples: this.queuedSamples,
          render_clock_samples: this.renderClockSamples,
          played_samples: this.playedSamples,
          underrun_count: this.underrunCount,
        });
      }
    };
  }

  beginFadeIn() {
    this.fadeInRemaining = this.transitionFadeSamples;
  }

  maybeStartOrResume() {
    if (!this.started && (this.queuedSamples >= this.startBufferSamples || (this.inputEnded && this.queuedSamples > 0))) {
      this.started = true;
      this.waitingForBuffer = false;
      this.beginFadeIn();
      this.port.postMessage({
        type: 'started',
        buffered_samples: this.queuedSamples,
        render_clock_samples: this.renderClockSamples,
        played_samples: this.playedSamples,
      });
      return;
    }
    if (
      this.started
      && this.waitingForBuffer
      && (this.queuedSamples >= this.currentRebufferSamples || this.inputEnded)
    ) {
      this.waitingForBuffer = false;
      this.beginFadeIn();
      this.port.postMessage({
        type: 'resumed',
        buffered_samples: this.queuedSamples,
        target_samples: this.currentRebufferSamples,
        underrun_count: this.underrunCount,
        render_clock_samples: this.renderClockSamples,
        played_samples: this.playedSamples,
      });
    }
  }

  beginPhrase(phraseIndex) {
    if (this.currentPhraseIndex === phraseIndex) return;
    this.maybeCompleteCurrentPhrase();
    this.currentPhraseIndex = phraseIndex;
    this.currentPhrasePlayedSamples = 0;
    this.port.postMessage({
      type: 'phrase_started',
      phrase_index: phraseIndex,
      render_clock_samples: this.renderClockSamples,
      played_samples: this.playedSamples,
    });
  }

  maybeCompleteCurrentPhrase() {
    if (this.currentPhraseIndex === null) return;
    const hasQueuedSamples = this.queue.some((item) => item.phraseIndex === this.currentPhraseIndex);
    if (hasQueuedSamples || !this.endedPhrases.has(this.currentPhraseIndex)) return;
    this.port.postMessage({
      type: 'phrase_completed',
      phrase_index: this.currentPhraseIndex,
      phrase_played_samples: this.currentPhrasePlayedSamples,
      render_clock_samples: this.renderClockSamples,
      played_samples: this.playedSamples,
    });
    this.endedPhrases.delete(this.currentPhraseIndex);
    this.currentPhraseIndex = null;
    this.currentPhrasePlayedSamples = 0;
  }

  signalPhraseInterrupted() {
    if (this.currentPhraseIndex === null) return;
    this.port.postMessage({
      type: 'phrase_interrupted',
      phrase_index: this.currentPhraseIndex,
      phrase_played_samples: this.currentPhrasePlayedSamples,
      render_clock_samples: this.renderClockSamples,
      played_samples: this.playedSamples,
    });
    this.currentPhraseIndex = null;
    this.currentPhrasePlayedSamples = 0;
  }

  applyFadeIn(channel, written) {
    let index = 0;
    while (index < written && this.fadeInRemaining > 0) {
      const elapsed = this.transitionFadeSamples - this.fadeInRemaining + 1;
      const progress = Math.min(1, elapsed / this.transitionFadeSamples);
      channel[index] *= 0.5 * (1 - Math.cos(Math.PI * progress));
      this.fadeInRemaining -= 1;
      index += 1;
    }
  }

  applyFadeOut(channel, written) {
    const fadeSamples = Math.min(written, this.transitionFadeSamples);
    const start = written - fadeSamples;
    for (let index = 0; index < fadeSamples; index += 1) {
      const progress = (index + 1) / fadeSamples;
      channel[start + index] *= 0.5 * (1 + Math.cos(Math.PI * progress));
    }
  }

  beginRebuffering() {
    this.waitingForBuffer = true;
    this.underrunCount += 1;
    const multiplier = 1 + (Math.max(0, this.underrunCount - 1) * 0.5);
    this.currentRebufferSamples = Math.min(
      this.maxRebufferSamples,
      Math.round(this.rebufferSamples * multiplier),
    );
    this.port.postMessage({
      type: 'underrun',
      buffered_samples: this.queuedSamples,
      target_samples: this.currentRebufferSamples,
      underrun_count: this.underrunCount,
      render_clock_samples: this.renderClockSamples,
      played_samples: this.playedSamples,
      input_ended: this.inputEnded,
    });
  }

  signalDrained() {
    this.maybeCompleteCurrentPhrase();
    if (!this.drained) {
      this.drained = true;
      this.port.postMessage({
        type: 'drained',
        buffered_samples: this.queuedSamples,
        underrun_count: this.underrunCount,
        render_clock_samples: this.renderClockSamples,
        played_samples: this.playedSamples,
      });
    }
    return false;
  }

  maybeReportProgress() {
    if (this.renderClockSamples - this.lastProgressSamples < this.progressIntervalSamples) return;
    this.lastProgressSamples = this.renderClockSamples;
    this.port.postMessage({
      type: 'render_progress',
      phrase_index: this.currentPhraseIndex,
      phrase_played_samples: this.currentPhrasePlayedSamples,
      buffered_samples: this.queuedSamples,
      target_samples: this.waitingForBuffer ? this.currentRebufferSamples : 0,
      waiting_for_buffer: this.waitingForBuffer,
      input_ended: this.inputEnded,
      underrun_count: this.underrunCount,
      current_rebuffer_samples: this.currentRebufferSamples,
      render_clock_samples: this.renderClockSamples,
      played_samples: this.playedSamples,
    });
  }

  process(_inputs, outputs) {
    const channel = outputs[0] && outputs[0][0];
    if (!channel) return !this.stopped;
    channel.fill(0);
    this.renderClockSamples += channel.length;
    if (this.stopped) return false;

    this.maybeStartOrResume();
    if (!this.started || this.waitingForBuffer) {
      this.maybeReportProgress();
      if (this.inputEnded && this.queuedSamples === 0) return this.signalDrained();
      return true;
    }

    let written = 0;
    while (written < channel.length && this.queue.length > 0) {
      const head = this.queue[0];
      this.beginPhrase(head.phraseIndex);
      const available = head.samples.length - this.headOffset;
      const take = Math.min(available, channel.length - written);
      channel.set(head.samples.subarray(this.headOffset, this.headOffset + take), written);
      written += take;
      this.headOffset += take;
      this.queuedSamples -= take;
      this.currentPhrasePlayedSamples += take;
      if (this.headOffset >= head.samples.length) {
        this.queue.shift();
        this.headOffset = 0;
        this.maybeCompleteCurrentPhrase();
      }
    }

    this.playedSamples += written;
    this.applyFadeIn(channel, written);
    if (this.queuedSamples === 0) {
      this.applyFadeOut(channel, written);
      this.maybeCompleteCurrentPhrase();
      if (this.inputEnded) return this.signalDrained();
      this.beginRebuffering();
    }
    this.maybeReportProgress();
    return true;
  }
}
registerProcessor('${LIVE_VOICE_PCM_WORKLET_NAME}', OmnixLiveVoicePcmStreamProcessor);
`;
}
