/**
 * Convert a raw 16-bit PCM ArrayBuffer to a normalized Float32Array.
 * Backend TTS streams Int16 samples; the audio pipeline expects Float32 in [-1, 1].
 * Handles odd-length buffers by zero-padding to even alignment instead of dropping.
 */
function pcm16ToFloat32(buffer) {
  let byteLength = buffer.byteLength;

  // Handle odd-length buffers by zero-padding instead of dropping frames
  if (byteLength % 2 !== 0) {
    const padded = new Uint8Array(byteLength + 1);
    padded.set(new Uint8Array(buffer));
    padded[byteLength] = 0;
    buffer = padded.buffer;
  }

  const int16 = new Int16Array(buffer);
  const float32 = new Float32Array(int16.length);
  for (let i = 0; i < int16.length; i++) {
    float32[i] = int16[i] / 32768.0;
  }
  return float32;
}

export class TTSClient {
  constructor(onAudioChunk, onDone, onStart) {
    this.onAudioChunk = onAudioChunk;
    this.onDone = onDone;
    this.onStart = onStart;
    this.onSegment = null;  // optional: called with segment index on each segment
    this.ws = null;
    this.connected = false;
    this.connecting = false;
    // TTS WebSocket is no longer used (TTS runs via HTTP /api/tts)
    this.url = null;
    this.currentAudio = null;
  }

  cancel() {
    if (this.currentAudio) {
      try {
        this.currentAudio.pause();
      } catch (e) {}
      this.currentAudio = null;
    }
  }

  async speak(text) {
    return null;
  }

  connect() {
    return new Promise((resolve, reject) => {
      if (this.ws && this.ws.readyState === WebSocket.OPEN) {
        resolve();
        return;
      }

      if (this.connecting) {
        setTimeout(() => {
          if (this.ws && this.ws.readyState === WebSocket.OPEN) {
            resolve();
          } else {
            reject(new Error('Connection failed'));
          }
        }, 1000);
        return;
      }

      this.connecting = true;

      try {
        this.ws = new WebSocket(this.url);
        this.ws.binaryType = 'arraybuffer';

        this.ws.onopen = () => {
          console.log('[TTSClient] Connected');
          this.connected = true;
          this.connecting = false;
          resolve();
        };

        this.ws.onmessage = (event) => {
          try {
            if (event.data instanceof ArrayBuffer) {
              if (this.onAudioChunk) {
                const floatChunk = pcm16ToFloat32(event.data);
                if (floatChunk && floatChunk.length > 0) {
                  // Validate: warn on potential clipping (sampled ~5% to avoid main-thread load)
                  if (Math.random() < 0.05) {
                    let maxVal = 0;
                    for (let i = 0; i < floatChunk.length; i++) {
                      const abs = Math.abs(floatChunk[i]);
                      if (abs > maxVal) maxVal = abs;
                    }
                    if (maxVal > 1.2) {
                      console.warn('[TTSClient] Clipping detected, max sample:', maxVal);
                    }
                  }
                  this.onAudioChunk(floatChunk);
                }
              }
            } else {
              const data = JSON.parse(event.data);
              
              switch (data.type) {
                case 'ready':
                  console.log('[TTSClient] Server ready');
                  break;
                  
                case 'start':
                  if (this.onStart) {
                    this.onStart();
                  }
                  break;
                  
                case 'done':
                  if (this.onDone) {
                    this.onDone();
                  }
                  break;
                  
                case 'segment':
                  if (this.onSegment) {
                    this.onSegment(data.index);
                  }
                  break;
                  
                case 'error':
                  console.error('[TTSClient] Server error:', data.error);
                  if (this.onDone) {
                    this.onDone();
                  }
                  break;
              }
            }
          } catch (e) {
            console.error('[TTSClient] Parse error:', e);
          }
        };

        this.ws.onerror = (error) => {
          console.error('[TTSClient] WebSocket error:', error);
          this.connected = false;
          this.connecting = false;
        };

        this.ws.onclose = () => {
          console.log('[TTSClient] Disconnected');
          this.connected = false;
          this.connecting = false;
          this.ws = null;
        };

        setTimeout(() => {
          if (!this.connected) {
            this.connecting = false;
            reject(new Error('Connection timeout'));
          }
        }, 5000);

      } catch (e) {
        this.connecting = false;
        reject(e);
      }
    });
  }

  sendText(text, voice = 'default') {
    if (!this.ws || this.ws.readyState !== WebSocket.OPEN) {
      console.warn('[TTSClient] Not connected, cannot send text');
      return;
    }

    this.ws.send(JSON.stringify({
      text: text,
      voice: voice
    }));
  }

  /**
   * Start an audiobook TTS session over WebSocket.
   *
   * Accepts either structured segments or plain text.
   *
   * @param {Object} opts
   * @param {string} [opts.text]            - plain text (for simple mode)
   * @param {Array}  [opts.segments]        - structured audiobook segments
   * @param {Object} [opts.voice_mapping]   - speaker → voice name map
   * @param {Object} [opts.voice_map]       - alternative voice map (takes priority)
   * @param {Object} [opts.default_voices]  - fallback voices per gender
   */
  async speakAudiobook(opts = {}) {
    await this.connect();

    const payload = { type: 'start' };

    if (opts.segments) {
      payload.segments = opts.segments;
    }
    if (opts.text) {
      payload.text = opts.text;
    }
    if (opts.voice_mapping) {
      payload.voice_mapping = opts.voice_mapping;
    }
    if (opts.voice_map) {
      payload.voice_map = opts.voice_map;
    }
    if (opts.default_voices) {
      payload.default_voices = opts.default_voices;
    }

    this.ws.send(JSON.stringify(payload));
  }

  disconnect() {
    if (this.ws) {
      this.ws.close();
      this.ws = null;
      this.connected = false;
    }
  }
}

export default TTSClient;
