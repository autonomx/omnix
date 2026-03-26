/**
 * SpeakerFilter — real-time speaker classification for echo suppression.
 *
 * Uses four signals to distinguish user speech from AI echo picked up
 * by the microphone:
 *
 *   1. Correlation  — dot-product similarity against the last played TTS audio
 *   2. Timing       — whether the AI is currently playing audio
 *   3. Energy       — RMS energy of the incoming chunk (is it real speech?)
 *   4. Persistence  — temporal smoothing across consecutive frames to prevent
 *                     flicker decisions
 *
 * Returns one of three labels:
 *   • 'echo'      — high confidence the chunk is AI playback heard by the mic
 *   • 'user'      — high confidence this is genuine user speech
 *   • 'uncertain' — not enough signal to decide; caller may attenuate
 */
export class SpeakerFilter {
  /**
   * @param {import('./audioOutput.js').AudioOutput} audioOutput
   */
  constructor(audioOutput) {
    this.audioOutput = audioOutput;

    /** Correlation above this value (combined with timing) → echo. */
    this.similarityThreshold = 0.75;
    /** RMS energy below this value → silence / not speech. */
    this.energyThreshold = 0.01;

    // Temporal smoothing frame counters
    this.echoFrames = 0;
    this.userFrames = 0;

    /** Consecutive echo frames required before labelling 'echo'. */
    this.minEchoFrames = 3;
    /** Consecutive user frames required before labelling 'user'. */
    this.minUserFrames = 3;
  }

  /**
   * Classify an incoming audio chunk.
   *
   * @param {Float32Array} samples — raw mic audio
   * @returns {'echo' | 'user' | 'uncertain'}
   */
  classify(samples) {
    const ref = this.audioOutput.lastPlayedSamples;
    const isAIPlaying = this.audioOutput.isPlaying();

    const similarity = ref ? SpeakerFilter._correlate(samples, ref) : 0;
    const energy = SpeakerFilter._energy(samples);

    // --- SIGNALS ---
    const looksLikeEcho = similarity > this.similarityThreshold && isAIPlaying;
    const looksLikeSpeech = energy > this.energyThreshold;

    // Timing constraint: if the last playback ended very recently the mic
    // may still carry residual echo even though isPlaying() is already false.
    const timeSincePlayback = (typeof performance !== 'undefined' ? performance.now() : Date.now())
      - (this.audioOutput._lastPlaybackTime || 0);
    if (similarity > this.similarityThreshold && timeSincePlayback < 200) {
      this.echoFrames++;
      this.userFrames = 0;
      if (this.echoFrames >= this.minEchoFrames) return 'echo';
      return 'uncertain';
    }

    // --- TEMPORAL SMOOTHING ---
    if (looksLikeEcho) {
      this.echoFrames++;
      this.userFrames = 0;
    } else if (looksLikeSpeech) {
      this.userFrames++;
      this.echoFrames = 0;
    } else {
      this.echoFrames = 0;
      this.userFrames = 0;
    }

    // --- FINAL DECISION ---
    if (this.echoFrames >= this.minEchoFrames) return 'echo';
    if (this.userFrames >= this.minUserFrames) return 'user';

    return 'uncertain';
  }

  /**
   * RMS energy of an audio buffer.
   * @param {Float32Array} samples
   * @returns {number}
   */
  static _energy(samples) {
    let sum = 0;
    for (let i = 0; i < samples.length; i++) {
      sum += samples[i] * samples[i];
    }
    return Math.sqrt(sum / samples.length);
  }

  /**
   * Normalised dot-product correlation between two audio buffers.
   * Returns a value in [-1, 1].  Capped at 24 000 samples (~1 s at 24 kHz).
   *
   * @param {Float32Array} a
   * @param {Float32Array} b
   * @returns {number}
   */
  static _correlate(a, b) {
    const len = Math.min(a.length, b.length, 24000);
    if (len === 0) return 0;

    let dot = 0, na = 0, nb = 0;
    for (let i = 0; i < len; i++) {
      dot += a[i] * b[i];
      na += a[i] * a[i];
      nb += b[i] * b[i];
    }

    if (na === 0 || nb === 0) return 0;
    return dot / Math.sqrt(na * nb);
  }
}

export default SpeakerFilter;
