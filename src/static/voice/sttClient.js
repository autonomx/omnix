export class STTClient {
  constructor(onTranscript, onFinal) {
    this.onTranscript = onTranscript;
    this.onFinal = onFinal;
    this.ws = null;
    this.connected = false;
    this.connecting = false;
    this.url = 'ws://localhost:8000/ws/transcribe';

    // Audio chunks that arrive while reconnecting are queued and flushed
    // once the connection is re-established.
    this.pendingAudio = [];
    this.autoReconnect = false; // enabled after the first successful connect
    this._reconnectTimer = null;
  }

  connect() {
    return new Promise((resolve, reject) => {
      if (this.ws && this.ws.readyState === WebSocket.OPEN) {
        resolve();
        return;
      }

      if (this.connecting) {
        // Wait for the in-progress connect to settle
        const poll = setInterval(() => {
          if (this.ws && this.ws.readyState === WebSocket.OPEN) {
            clearInterval(poll);
            resolve();
          } else if (!this.connecting) {
            clearInterval(poll);
            reject(new Error('Connection failed'));
          }
        }, 100);
        return;
      }

      this.connecting = true;
      if (this._reconnectTimer) {
        clearTimeout(this._reconnectTimer);
        this._reconnectTimer = null;
      }

      try {
        this.ws = new WebSocket(this.url);

        this.ws.onopen = () => {
          console.log('[STTClient] Connected');
          this.connected = true;
          this.connecting = false;
          this.autoReconnect = true;

          // Flush any audio that arrived while we were reconnecting
          if (this.pendingAudio.length > 0) {
            console.log(`[STTClient] Flushing ${this.pendingAudio.length} buffered chunks`);
            for (const chunk of this.pendingAudio) {
              this._sendEncodedChunk(chunk);
            }
            this.pendingAudio = [];
          }

          resolve();
        };

        this.ws.onmessage = (event) => {
          try {
            const data = JSON.parse(event.data);

            switch (data.type) {
              case 'ready':
                console.log('[STTClient] Server ready');
                break;

              case 'text':
                if (this.onTranscript) this.onTranscript(data.text);
                break;

              case 'done':
                if (this.onFinal) this.onFinal(data.text);
                // Server closes the connection after 'done' — the onclose handler
                // below will schedule a reconnect automatically.
                break;

              case 'error':
                console.error('[STTClient] Server error:', data.error);
                // Still fire onFinal with empty so the engine doesn't hang in THINKING
                if (this.onFinal) this.onFinal('');
                break;
            }
          } catch (e) {
            console.error('[STTClient] Parse error:', e);
          }
        };

        this.ws.onerror = (error) => {
          console.error('[STTClient] WebSocket error:', error);
          this.connected = false;
          this.connecting = false;
        };

        this.ws.onclose = () => {
          console.log('[STTClient] Disconnected');
          this.connected = false;
          this.connecting = false;
          this.ws = null;

          // The STT server closes the socket after every transcription request.
          // Proactively reconnect so the next utterance has a live connection waiting.
          if (this.autoReconnect) {
            this._reconnectTimer = setTimeout(() => {
              console.log('[STTClient] Auto-reconnecting...');
              this.connect().catch(err => {
                console.warn('[STTClient] Auto-reconnect failed:', err.message);
              });
            }, 300);
          }
        };

        setTimeout(() => {
          if (!this.connected && this.connecting) {
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

  /** Encode a Float32 chunk and send it, or buffer it if not yet connected. */
  sendAudio(chunk) {
    if (!this.ws || this.ws.readyState !== WebSocket.OPEN) {
      // Buffer while reconnecting so speech at the start of an utterance isn't lost
      if (this.connecting || this.autoReconnect) {
        this.pendingAudio.push(chunk);
        // Cap buffer to avoid unbounded growth (~2s at 16kHz / 128-sample worklet frames)
        if (this.pendingAudio.length > 250) {
          this.pendingAudio.shift();
        }
      }
      return;
    }

    this._sendEncodedChunk(chunk);
  }

  /** Internal: encode Float32 → Int16 → base64 and send over the WebSocket. */
  _sendEncodedChunk(chunk) {
    try {
      const int16 = new Int16Array(chunk.length);
      for (let i = 0; i < chunk.length; i++) {
        int16[i] = Math.max(-1, Math.min(1, chunk[i])) * 32767;
      }

      // Use a chunked approach for large buffers to avoid call-stack overflow
      // with spread operator on very large TypedArrays
      const uint8 = new Uint8Array(int16.buffer);
      let binary = '';
      const CHUNK = 8192;
      for (let i = 0; i < uint8.length; i += CHUNK) {
        binary += String.fromCharCode(...uint8.subarray(i, i + CHUNK));
      }
      const base64 = btoa(binary);

      this.ws.send(JSON.stringify({ type: 'audio', data: base64 }));
    } catch (e) {
      console.error('[STTClient] Error sending audio:', e);
    }
  }

  sendFinal() {
    // Discard any buffered audio from this utterance — it's about to be transcribed
    this.pendingAudio = [];

    if (this.ws && this.ws.readyState === WebSocket.OPEN) {
      this.ws.send(JSON.stringify({ type: 'final' }));
    } else {
      // Connection dropped mid-utterance — fire onFinal with empty so engine recovers
      console.warn('[STTClient] sendFinal called but not connected');
      if (this.onFinal) this.onFinal('');
    }
  }

  disconnect() {
    this.autoReconnect = false;
    if (this._reconnectTimer) {
      clearTimeout(this._reconnectTimer);
      this._reconnectTimer = null;
    }
    if (this.ws) {
      this.ws.close();
      this.ws = null;
      this.connected = false;
    }
    this.pendingAudio = [];
  }
}

export default STTClient;