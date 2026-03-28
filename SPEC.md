# Omnix - Specification

## Project Overview
- **Project Name**: Omnix
- **Company**: Autonomx
- **Type**: AI Voice Platform
- **Core Functionality**: A comprehensive AI voice platform featuring chat, audiobook generation, AI podcasts, live conversation, and voice cloning
- **Target Users**: Users who want to create, converse, and interact with AI through voice and text

## Architecture

### Components
1. **Backend**: Python Flask server with WebSocket support
2. **Frontend**: Modern HTML/CSS/JS web interface
3. **LLM Providers**: Cerebras (fastest), OpenRouter (cloud), LM Studio (local)
4. **TTS Engine**: Qwen3 TTS for natural voice synthesis
5. **STT Engine**: Parakeet for speech-to-text transcription

### Connection Flow
```
User Input → Frontend → Flask Backend → LM Studio API → LLM Model
                                            ↓
                                    Response → Flask → Frontend → Display
```

## Technical Details

### LM Studio API Configuration
- **Base URL**: `http://localhost:1234`
- **Chat Endpoint**: `/api/v1/chat`
- **OpenAI Compatible**: `/v1/chat/completions`
- **Authentication**: Optional (not required by default)
- **Content-Type**: `application/json`

### Request Format (LM Studio REST API)
```json
{
  "model": "model-identifier",
  "input": "user message"
}
```

### Request Format (OpenAI Compatible)
```json
{
  "model": "model-identifier",
  "messages": [
    {"role": "user", "content": "user message"}
  ],
  "stream": false
}
```

## UI/UX Specification

### Layout Structure
- **Header**: App title and connection status indicator
- **Chat Container**: Scrollable message area
- **Input Area**: Text input with send button

### Visual Design
- **Theme**: Dark mode with accent colors
- **Primary Background**: #0f0f0f (near black)
- **Secondary Background**: #1a1a2e (dark blue-gray)
- **User Message**: #2d2d44 (muted purple-gray)
- **AI Message**: #1e1e2e (dark)
- **Accent Color**: #7c3aed (violet)
- **Text Primary**: #e2e8f0 (light gray)
- **Text Secondary**: #94a3b8 (muted gray)
- **Font Family**: 'JetBrains Mono', 'Fira Code', monospace
- **Border Radius**: 12px for messages, 8px for input

### Components
1. **Message Bubbles**
   - User messages: Right-aligned, violet accent border
   - AI messages: Left-aligned, subtle border
   
2. **Input Area**
   - Full-width text input
   - Send button with icon
   - Disabled state during loading

3. **Status Indicator**
   - Green dot: Connected to LM Studio
   - Red dot: Not connected
   - Yellow dot: Loading/Processing

### Animations
- Fade-in for new messages
- Typing indicator animation
- Smooth scroll to bottom on new messages

## Functionality Specification

### Core Features
1. **Send Messages**: User can type and send messages
2. **Receive Responses**: Display AI responses in real-time
3. **Model Selection**: Dropdown to select available models
4. **Connection Status**: Visual indicator of LM Studio connection
5. **Streaming Response**: Support for streaming responses
6. **Message History**: Maintain conversation context

### User Interactions
1. Type message in input field
2. Press Enter or click Send to submit
3. View AI response in chat
4. Select different model from dropdown (if available)

### Error Handling
- Display error message if LM Studio is not running
- Show loading state during model response
- Handle network disconnection gracefully

## File Structure
```
f:\LLM\Chatbot\
├── app.py              # Flask backend
├── templates/
│   └── index.html      # Chat interface
├── static/
│   ├── style.css       # Styling
│   └── script.js       # Frontend logic
└── SPEC.md             # This specification
```

## Acceptance Criteria

### Visual Checkpoints
- [ ] Dark theme with violet accents loads correctly
- [ ] Messages display with proper alignment
- [ ] Input area is functional and styled
- [ ] Status indicator shows connection state
- [ ] Animations play smoothly

### Functional Checkpoints
- [ ] Can connect to LM Studio API
- [ ] Can send messages and receive responses
- [ ] Chat history is maintained during session
- [ ] Error states are handled gracefully
- [ ] Model selection works (if models available)
