/**
 * DEPRECATED — Canonical source: /static/js/audio/pcm-player-worklet.js
 *
 * This file is kept for backwards compatibility only.  All audio worklet
 * consumers should load the canonical module at the path above.  The
 * implementation below is an exact copy so that any code that still
 * references this path continues to work.
 */

// ── Identical copy of js/audio/pcm-player-worklet.js ──────────────────────
const MAX_CORRUPTION_COUNT = 5000;
const MAX_BUFFER_SAMPLES = 24000 * 5; // ~5 seconds at 24 kHz
const CROSSFADE_SAMPLES = 32;

class PCMPlayerProcessor extends AudioWorkletProcessor {
    constructor() {
        super();
        this.buffer = [];
        this.bufferSamples = 0;
        this.currentChunk = null;
        this.chunkOffset = 0;
        this.previousChunk = null;
        this.lastSample = 0;
        this.draining = false;
        this.corruptionCount = 0;

        this.port.onmessage = (event) => {
            const data = event.data;
            if (!data) return;

            if (data.type === 'reset') {
                this.buffer = [];
                this.bufferSamples = 0;
                this.currentChunk = null;
                this.chunkOffset = 0;
                this.previousChunk = null;
                this.lastSample = 0;
                this.draining = false;
                this.corruptionCount = 0;
                return;
            }

            if (data.type === 'stop') {
                this.draining = true;
                return;
            }

            if (!(data instanceof Float32Array)) {
                if (data !== null && typeof data !== 'object') {
                    console.warn('[PCMPlayerProcessor] Invalid audio chunk type — expected Float32Array, got:', typeof data);
                }
                return;
            }

            if (!this.draining && data.length > 0) {
                this.buffer.push(data);
                this.bufferSamples += data.length;

                while (this.bufferSamples > MAX_BUFFER_SAMPLES && this.buffer.length > 1) {
                    const dropped = this.buffer.shift();
                    this.bufferSamples -= dropped.length;
                }
            }
        };
    }

    process(inputs, outputs) {
        const output = outputs[0][0];
        let outputIndex = 0;

        while (outputIndex < output.length) {
            if (!this.currentChunk || this.chunkOffset >= this.currentChunk.length) {
                if (this.buffer.length > 0) {
                    this.previousChunk = this.currentChunk;
                    this.currentChunk = this.buffer.shift();
                    this.chunkOffset = 0;

                    if (this.previousChunk && this.currentChunk.length > 0) {
                        const fadeSamples = Math.min(
                            CROSSFADE_SAMPLES,
                            this.previousChunk.length,
                            this.currentChunk.length
                        );
                        for (let i = 0; i < fadeSamples; i++) {
                            const t = i / fadeSamples;
                            const prev = this.previousChunk[this.previousChunk.length - fadeSamples + i] || 0;
                            this.currentChunk[i] = prev * (1 - t) + this.currentChunk[i] * t;
                        }
                    }
                } else {
                    this.lastSample *= 0.98;
                    output[outputIndex] = this.lastSample;
                    this.lastSample = output[outputIndex];
                    outputIndex++;
                    continue;
                }
            }

            const remainingChunk = this.currentChunk.length - this.chunkOffset;
            const remainingOutput = output.length - outputIndex;
            const copySize = Math.min(remainingChunk, remainingOutput);

            for (let j = 0; j < copySize; j++) {
                let sample = this.currentChunk[this.chunkOffset + j];

                if (!Number.isFinite(sample) || Math.abs(sample) > 5) {
                    sample = 0;
                    this.corruptionCount++;
                }

                sample = Math.max(-1, Math.min(1, sample));
                output[outputIndex + j] = sample;
            }

            if (copySize > 0) {
                this.lastSample = output[outputIndex + copySize - 1];
            }

            this.chunkOffset += copySize;
            this.bufferSamples -= copySize;
            outputIndex += copySize;
        }

        if (this.corruptionCount > MAX_CORRUPTION_COUNT) {
            this.buffer = [];
            this.bufferSamples = 0;
            this.currentChunk = null;
            this.chunkOffset = 0;
            this.previousChunk = null;
            this.lastSample = 0;
            this.corruptionCount = 0;
        }

        if (this.draining && this.buffer.length === 0 &&
            (!this.currentChunk || this.chunkOffset >= this.currentChunk.length)) {
            this.draining = false;
            this.port.postMessage({ type: 'drained' });
        }

        return true;
    }
}

registerProcessor("pcm-player", PCMPlayerProcessor);