export class LLMClient {
  constructor(onToken, onComplete, onStart) {
    this.onToken = onToken;
    this.onComplete = onComplete;
    this.onStart = onStart;
    this.abortController = null;
  }

  async sendMessage(text, sessionId = null, speaker = 'default') {
    this.abortController = new AbortController();

    const body = {
      message: text,
      speaker: speaker
    };

    if (sessionId) {
      body.session_id = sessionId;
    }

    try {
      if (this.onStart) {
        this.onStart();
      }

      const response = await fetch('/api/chat/stream', {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json'
        },
        body: JSON.stringify(body),
        signal: this.abortController.signal
      });

      if (!response.ok) {
        throw new Error(`HTTP error: ${response.status}`);
      }

      const reader = response.body.getReader();
      const decoder = new TextDecoder();
      let buffer = '';

      while (true) {
        const { done, value } = await reader.read();

        if (done) {
          break;
        }

        buffer += decoder.decode(value, { stream: true });
        
        const lines = buffer.split('\n');
        buffer = lines.pop() || '';

        for (const line of lines) {
          if (line.startsWith('data: ')) {
            const data = line.slice(6);
            
            if (data === '[DONE]') {
              if (this.onComplete) {
                this.onComplete();
              }
              return;
            }

            try {
              const parsed = JSON.parse(data);
              if (parsed.content) {
                if (this.onToken) {
                  this.onToken(parsed.content);
                }
              }
              // Also handle OpenAI-style delta format
              const delta = parsed?.choices?.[0]?.delta?.content;
              if (delta && !parsed.content) {
                if (this.onToken) {
                  this.onToken(delta);
                }
              }
            } catch (e) {
              // Silently ignore non-JSON lines (e.g. comments, keep-alives)
              // — do NOT pass raw text to onToken as it pollutes the transcript
            }
          }
        }
      }

      if (this.onComplete) {
        this.onComplete();
      }

    } catch (error) {
      if (error.name === 'AbortError') {
        console.log('[LLMClient] Request aborted (intentional cancel)');
        // Do NOT call onComplete for intentional aborts — the engine already
        // cleaned up via its cancel path (e.g. VoiceEngine._cancelOngoingResponse).
        // Firing onComplete here would set responseFinished=true on the NEW
        // request's state, causing a premature LISTENING transition.
        return;
      }
      console.error('[LLMClient] Error:', error);
      if (this.onComplete) {
        this.onComplete();
      }
    }
  }

  cancel(requestId) {
    if (this.abortController) {
      this.abortController.abort();
      this.abortController = null;
    }
    
    if (requestId) {
      try {
        fetch(`/api/llm/cancel/${requestId}`, {
          method: "POST"
        }).catch(() => {});
      } catch (e) {}
    }
  }
}

export default LLMClient;