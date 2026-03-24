# OpenAI Compatible API Guide

This application provides a drop-in replacement for OpenAI's TTS and Chat APIs, making it compatible with OpenWebUI, SillyTavern, and other clients that expect standard OpenAI endpoints.

## Quick Start

### Start the API Server

**Windows:**
```bash
start_openai_api.bat
```

**Linux/macOS:**
```bash
chmod +x start_openai_api.sh
./start_openai_api.sh
```

**Direct Python:**
```bash
python openai_api.py
```

The API server will start on `http://localhost:8001`

## Available Endpoints

### 1. List Models
```http
GET /v1/models
```

Returns available models for chat completions.

### 2. List Voices
```http
GET /v1/audio/voices
```

Returns available voices for TTS.

### 3. Get Voice Details
```http
GET /v1/audio/voices/{voice_id}
```

Get details about a specific voice.

### 4. Generate Speech (TTS)
```http
POST /v1/audio/speech
Content-Type: application/json

{
  "model": "tts-1",
  "voice": "alloy",
  "input": "Hello, this is a test message.",
  "speed": 1.0,
  "response_format": "mp3",
  "stream": false
}
```

**Parameters:**
- `model`: TTS model (default: "tts-1")
- `voice`: Voice ID (use `/v1/audio/voices` to see available options)
- `input`: Text to convert to speech
- `speed`: Speech speed (default: 1.0)
- `response_format`: Output format - "mp3", "wav", "flac" (default: "mp3")
- `stream`: Whether to stream the response (default: false)

**Response:** Audio file in the specified format.

### 5. Chat Completions
```http
POST /v1/chat/completions
Content-Type: application/json

{
  "model": "mistral-7b-instruct-v0.2",
  "messages": [
    {"role": "user", "content": "Hello, how are you?"}
  ],
  "temperature": 0.7,
  "max_tokens": 100,
  "stream": false
}
```

**Parameters:**
- `model`: LLM model to use
- `messages`: Array of chat messages
- `temperature`: Creativity parameter (0.0 to 1.0)
- `max_tokens`: Maximum tokens to generate
- `stream`: Whether to stream responses (default: false)

**Response:**
```json
{
  "id": "chatcmpl-123",
  "object": "chat.completion",
  "created": 1700000000,
  "model": "mistral-7b-instruct-v0.2",
  "choices": [
    {
      "index": 0,
      "message": {
        "role": "assistant",
        "content": "I'm doing well, thank you for asking!"
      },
      "finish_reason": "stop"
    }
  ],
  "usage": {
    "prompt_tokens": 10,
    "completion_tokens": 20,
    "total_tokens": 30
  }
}
```

### 6. Streaming Chat Completions
Set `"stream": true` in the chat completions request to get real-time responses:

```http
POST /v1/chat/completions
Content-Type: application/json

{
  "model": "mistral-7b-instruct-v0.2",
  "messages": [
    {"role": "user", "content": "Tell me a story."}
  ],
  "stream": true
}
```

**Streaming Response Format:**
```
data: {"id": "chatcmpl-123", "object": "chat.completion.chunk", "choices": [{"index": 0, "delta": {"content": "Once"}, "finish_reason": null}]}

data: {"id": "chatcmpl-123", "object": "chat.completion.chunk", "choices": [{"index": 0, "delta": {"content": " upon"}, "finish_reason": null}]}

data: [DONE]
```

### 7. Audio Transcriptions
```http
POST /v1/audio/transcriptions
Content-Type: multipart/form-data

file: [audio file]
model: whisper-1
```

**Note:** Currently returns placeholder text. Full transcription support coming soon.

### 8. Health Check
```http
GET /health
```

Returns server status and component availability.

## Integration Examples

### OpenWebUI Configuration

1. In OpenWebUI settings, set the API base URL to: `http://localhost:8001/v1`
2. Use any of the available models for chat
3. Use any of the available voices for TTS

### SillyTavern Configuration

1. In SillyTavern settings, set the API URL to: `http://localhost:8001/v1`
2. Select "OpenAI" as the API type
3. Use the available models and voices

### Python Client Example

```python
import openai

# Configure client
client = openai.OpenAI(
    base_url="http://localhost:8001/v1",
    api_key="dummy-key"  # Not required for local server
)

# Chat completion
response = client.chat.completions.create(
    model="mistral-7b-instruct-v0.2",
    messages=[{"role": "user", "content": "Hello!"}]
)
print(response.choices[0].message.content)

# Text-to-speech
speech = client.audio.speech.create(
    model="tts-1",
    voice="alloy",
    input="Hello from your local TTS server!"
)

# Save audio
with open("output.mp3", "wb") as f:
    f.write(speech.content)
```

### cURL Examples

**List models:**
```bash
curl http://localhost:8001/v1/models
```

**Generate speech:**
```bash
curl -X POST http://localhost:8001/v1/audio/speech \
  -H "Content-Type: application/json" \
  -d '{
    "model": "tts-1",
    "voice": "alloy",
    "input": "Hello, this is a test from curl!"
  }' \
  --output output.mp3
```

**Chat completion:**
```bash
curl -X POST http://localhost:8001/v1/chat/completions \
  -H "Content-Type: application/json" \
  -d '{
    "model": "mistral-7b-instruct-v0.2",
    "messages": [{"role": "user", "content": "What is AI?"}]
  }'
```

## Available Models

- `mistral-7b-instruct-v0.2`
- `qwen2.5-coder-7b-instruct`
- `gpt-4`
- `gpt-3.5-turbo`

## Available Voices

### Custom Voices
Any voice files you've uploaded through the web interface will appear here with their original filenames.

### Standard Voices
- `alloy` - Neutral voice
- `echo` - Deep voice
- `fable` - Storytelling voice
- `onyx` - Strong voice
- `nova` - Clear voice
- `shimmer` - Soft voice

## Troubleshooting

### Server Won't Start
1. Ensure Python 3.8+ is installed
2. Check that all requirements are installed: `pip install -r requirements.txt`
3. Verify port 8001 is not in use by another application

### TTS Not Working
1. Ensure you have voice files in the `resources/voice_clones/` directory
2. Check that the TTS models are downloaded
3. Verify the voice ID exists in `/v1/audio/voices`

### Chat Not Working
1. Ensure the LLM server is running
2. Check that the model files are downloaded
3. Verify the model name is correct

### CORS Issues
The API includes CORS headers to allow cross-origin requests. If you're still having issues, ensure your client is making requests to the correct port (8001).

## Performance Notes

- The API server runs on port 8001 by default
- Chat completions use your local LLM server
- TTS uses your local TTS models
- Audio files are saved to the `audio/` directory
- The server supports both streaming and non-streaming responses

## Security

- The API is designed for local use
- No authentication is required for local development
- For production use, consider adding authentication middleware
- The server binds to `0.0.0.0` to allow external connections

## Development

To modify the API endpoints or add new functionality:

1. Edit `openai_api.py`
2. Restart the server
3. Test endpoints using the examples above

The API uses FastAPI, so you can access interactive documentation at `http://localhost:8001/docs` when the server is running.