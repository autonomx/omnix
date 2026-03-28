#!/usr/bin/env python3
"""
OpenAI Compatible API Server
Provides drop-in replacement for OpenAI TTS and Chat APIs
Compatible with OpenWebUI, SillyTavern, and other clients
"""

import os
import json
import time
import uuid
import asyncio
import logging
import traceback
from typing import Dict, List, Any, Optional
from datetime import datetime
from pathlib import Path

from fastapi import FastAPI, HTTPException, Request, BackgroundTasks
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field
import uvicorn

# Import our existing components
import sys
sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'src'))
import app.shared as shared

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

app = FastAPI(
    title="Omnix OpenAI Compatible API",
    description="Drop-in replacement for OpenAI TTS and Chat APIs",
    version="1.0.0"
)

# Add CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# TTS is handled via the audio provider system (e.g. faster-qwen3-tts)

# Models available
AVAILABLE_MODELS = [
    "mistral-7b-instruct-v0.2",
    "qwen2.5-coder-7b-instruct",
    "gpt-4",
    "gpt-3.5-turbo"
]

class Voice(BaseModel):
    voice_id: str
    name: str
    category: str = "custom"
    preview_url: Optional[str] = None
    labels: Dict[str, str] = Field(default_factory=dict)

class SpeechRequest(BaseModel):
    model: str = "tts-1"
    voice: str
    input: str
    speed: float = 1.0
    response_format: str = "mp3"
    stream: bool = False

class ChatMessage(BaseModel):
    role: str
    content: str

class ChatRequest(BaseModel):
    model: str
    messages: List[ChatMessage]
    temperature: float = 1.0
    top_p: float = 1.0
    n: int = 1
    stream: bool = False
    max_tokens: Optional[int] = None
    stop: Optional[List[str]] = None
    presence_penalty: float = 0.0
    frequency_penalty: float = 0.0

class ChatChoice(BaseModel):
    index: int
    message: ChatMessage
    finish_reason: str

class ChatResponse(BaseModel):
    id: str
    object: str = "chat.completion"
    created: int
    model: str
    choices: List[ChatChoice]
    usage: Dict[str, int]

class ChatStreamChoice(BaseModel):
    index: int
    delta: Dict[str, str]
    finish_reason: Optional[str] = None

class ChatStreamResponse(BaseModel):
    id: str
    object: str = "chat.completion.chunk"
    created: int
    model: str
    choices: List[ChatStreamChoice]

class TranscriptionRequest(BaseModel):
    file: Any
    model: str = "whisper-1"
    language: Optional[str] = None
    prompt: Optional[str] = None
    response_format: str = "json"
    temperature: float = 0.0

class TranscriptionResponse(BaseModel):
    text: str

# Load available voices
def load_voices():
    """Load available voices from custom voice clones"""
    voices = []
    try:
        # Get voices from custom voice clones
        for vid, vdata in shared.custom_voices.items():
            voice_name = vid.replace('_', ' ').title()
            voices.append(Voice(
                voice_id=vid,
                name=voice_name,
                category="custom",
                preview_url=f"/api/v1/audio/voices/{vid}/preview"
            ))
        
        # Add some standard voices for compatibility
        standard_voices = [
            Voice(voice_id="alloy", name="Alloy", category="alloy"),
            Voice(voice_id="echo", name="Echo", category="echo"),
            Voice(voice_id="fable", name="Fable", category="fable"),
            Voice(voice_id="onyx", name="Onyx", category="onyx"),
            Voice(voice_id="nova", name="Nova", category="nova"),
            Voice(voice_id="shimmer", name="Shimmer", category="shimmer"),
        ]
        
        voices.extend(standard_voices)
        
    except Exception as e:
        logger.error(f"Error loading voices: {e}")
        # Return some default voices
        voices = [
            Voice(voice_id="alloy", name="Alloy", category="alloy"),
            Voice(voice_id="echo", name="Echo", category="echo"),
        ]
    
    return voices

AVAILABLE_VOICES = load_voices()

@app.get("/v1/models")
async def list_models():
    """List available models"""
    return {
        "object": "list",
        "data": [
            {
                "id": model,
                "object": "model",
                "created": int(time.time()),
                "owned_by": "omnix"
            }
            for model in AVAILABLE_MODELS
        ]
    }

@app.get("/v1/audio/voices")
async def list_voices():
    """List available voices"""
    return {
        "voices": [voice.dict() for voice in AVAILABLE_VOICES]
    }

@app.get("/v1/audio/voices/{voice_id}")
async def get_voice(voice_id: str):
    """Get voice details"""
    voice = next((v for v in AVAILABLE_VOICES if v.voice_id == voice_id), None)
    if not voice:
        raise HTTPException(status_code=404, detail="Voice not found")
    return voice.dict()

@app.get("/v1/audio/voices/{voice_id}/preview")
async def get_voice_preview(voice_id: str):
    """Get voice preview audio"""
    # For custom voices, we could generate a preview
    # For now, return a placeholder
    return {"message": f"Preview for voice {voice_id}"}

@app.post("/v1/audio/speech")
async def create_speech(request: SpeechRequest, background_tasks: BackgroundTasks):
    """Generate speech from text"""
    try:
        # Generate unique ID for this request
        speech_id = str(uuid.uuid4())
        
        # Use the TTS provider system
        tts_provider = shared.get_tts_provider()
        if not tts_provider:
            raise HTTPException(status_code=503, detail="TTS provider not available")
        
        # Generate speech using the audio provider
        result = tts_provider.generate_audio(
            text=request.input,
            speaker=request.voice,
            language="en"
        )
        
        if not result.get('success'):
            raise HTTPException(status_code=500, detail=result.get('error', 'TTS generation failed'))
        
        # Decode base64 audio to bytes
        import base64 as b64
        audio_bytes = b64.b64decode(result.get('audio', ''))
        
        if not audio_bytes:
            raise HTTPException(status_code=500, detail="No audio generated")
        
        # Return the audio data
        content_type = f"audio/{request.response_format}"
        return StreamingResponse(iter([audio_bytes]), media_type=content_type)
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error generating speech: {e}")
        logger.error(traceback.format_exc())
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/v1/audio/transcriptions")
async def create_transcription(request: TranscriptionRequest):
    """Transcribe audio to text"""
    try:
        # For now, we'll use a simple approach
        # In a real implementation, you'd process the uploaded file
        return TranscriptionResponse(text="This is a transcription placeholder")
        
    except Exception as e:
        logger.error(f"Error transcribing audio: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/v1/chat/completions")
async def create_chat_completion(request: ChatRequest):
    """Create chat completion"""
    try:
        # Generate unique ID
        completion_id = f"chatcmpl-{uuid.uuid4().hex}"
        created_time = int(time.time())
        
        # For streaming responses
        if request.stream:
            return StreamingResponse(
                generate_chat_stream(request, completion_id, created_time),
                media_type="text/event-stream"
            )
        
        # For non-streaming responses
        messages = [msg.dict() for msg in request.messages]
        
        # Here you would integrate with your LLM server
        # For now, return a placeholder response
        response_text = "This is a placeholder response from the local LLM."
        
        choice = ChatChoice(
            index=0,
            message=ChatMessage(role="assistant", content=response_text),
            finish_reason="stop"
        )
        
        response = ChatResponse(
            id=completion_id,
            created=created_time,
            model=request.model,
            choices=[choice],
            usage={"prompt_tokens": 10, "completion_tokens": 20, "total_tokens": 30}
        )
        
        return response
        
    except Exception as e:
        logger.error(f"Error creating chat completion: {e}")
        logger.error(traceback.format_exc())
        raise HTTPException(status_code=500, detail=str(e))

async def generate_chat_stream(request: ChatRequest, completion_id: str, created_time: int):
    """Generate streaming chat completion"""
    try:
        # Placeholder for streaming implementation
        # In a real implementation, you'd stream responses from your LLM
        response_text = "This is a streaming response from the local LLM."
        
        for i, char in enumerate(response_text):
            chunk = ChatStreamResponse(
                id=completion_id,
                created=created_time,
                model=request.model,
                choices=[ChatStreamChoice(
                    index=0,
                    delta={"content": char} if i < len(response_text) - 1 else {"content": char},
                    finish_reason=None if i < len(response_text) - 1 else "stop"
                )]
            )
            
            yield f"data: {chunk.json()}\n\n"
            await asyncio.sleep(0.01)  # Small delay for streaming effect
        
        # Final chunk
        yield "data: [DONE]\n\n"
        
    except Exception as e:
        logger.error(f"Error generating chat stream: {e}")
        yield f"data: {json.dumps({'error': str(e)})}\n\n"

@app.get("/health")
async def health_check():
    """Health check endpoint"""
    return {
        "status": "healthy",
        "tts_available": shared.get_tts_provider() is not None,
        "stt_available": False,  # STT not integrated in this API
        "timestamp": datetime.now().isoformat()
    }

if __name__ == "__main__":
    # Start the OpenAI-compatible API server
    uvicorn.run(
        "openai_api:app",
        host="0.0.0.0",
        port=8001,
        reload=False,
        log_level="info"
    )