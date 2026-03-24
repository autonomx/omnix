class VADRecorderProcessor extends AudioWorkletProcessor {
    constructor() {
        super();
        this._active = true;
        this.port.onmessage = (e) => {
            if (e.data?.type === 'stop') this._active = false;
        };
    }

    process(inputs) {
        if (!this._active) return false;
        const input = inputs[0]?.[0];
        if (input && input.length > 0) {
            const copy = new Float32Array(input);
            this.port.postMessage(copy, [copy.buffer]);
        }
        return true;
    }
}

registerProcessor('vad-recorder', VADRecorderProcessor);
