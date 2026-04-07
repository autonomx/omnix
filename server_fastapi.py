#!/usr/bin/env python3
"""
FastAPI Server for Ultra-Low-Latency Voice Conversation
Replaces Flask for streaming endpoints to achieve sub-500ms latency

Key optimizations:
- WebSocket instead of HTTP SSE
- Binary PCM instead of base64
- Predictive TTS (start after 25 chars)
- Pre-loaded TTS model
"""

import asyncio
import base64
import json
import queue

# Import existing infrastructure
import sys
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from contextlib import asynccontextmanager
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional

import numpy as np
import requests
import uvicorn
from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

sys.path.insert(0, str(Path(__file__).parent / 'src'))

import app.shared as shared
from app.providers.base import ChatMessage
from app.providers.faster_qwen3_tts_provider import (
    apply_fade,
    find_best_offset,
    soft_clip,
)

# RPG imports
from app.rpg.models import GameSession
from app.rpg.persistence import CURRENT_RPG_SCHEMA_VERSION, migrate_package_to_current
from app.rpg.pipeline import create_new_game, delete_game, execute_turn, list_games, load_game, replay_turn
from app.rpg.api.rpg_adventure_routes import rpg_adventure_bp
from app.rpg.api.rpg_presentation_routes import rpg_presentation_bp
from app.rpg.api.rpg_game_routes import rpg_game_bp

# ============== CONFIG ==============
HOST = "0.0.0.0"
PORT = 5000
TTS_CHUNK_SIZE = 6  # ~0.5s (12000 samples at 24kHz) for stable streaming
TTS_MIN_CHARS = 25  # Start TTS after this many chars
TTS_MAX_CHARS = 80  # Max chars per TTS chunk
LLM_MAX_TOKENS = 60  # Max tokens before forcing TTS


# ============== GLOBAL STATE ==============
@dataclass
class ConversationSession:
    """State for each conversation session"""
    websocket: WebSocket
    session_id: str
    speaker: str = "default"
    buffer: str = ""
    tts_queue: queue.Queue = field(default_factory=queue.Queue)
    last_tts_time: float = 0
    stop_requested: bool = False
    tts_active: bool = False
    tts_chunks_pending: int = 0
    tts_abort: bool = False  # abort current TTS generation without ending the session
    loop: Optional[asyncio.AbstractEventLoop] = None


# Global session management
sessions: Dict[str, ConversationSession] = {}
sessions_lock = threading.Lock()

# TTS worker
tts_worker_thread: Optional[threading.Thread] = None
tts_provider = None
llm_provider = None
executor = ThreadPoolExecutor(max_workers=2)


# ============== APP LIFECYCLE ==============
@asynccontextmanager
async def lifespan(app: FastAPI):
    """Initialize providers on startup"""
    global tts_provider, llm_provider
    
    print("[FASTAPI] Starting up...")
    
    # Initialize TTS provider
    try:
        tts_provider = shared.get_tts_provider()
        if tts_provider:
            print(f"[FASTAPI] TTS provider loaded: {tts_provider.provider_name}")
            # Warm up the model
            _warmup_tts()
        else:
            print("[FASTAPI] WARNING: No TTS provider available")
    except Exception as e:
        print(f"[FASTAPI] ERROR loading TTS: {e}")
    
    # Initialize LLM provider
    try:
        llm_provider = shared.get_provider()
        if llm_provider:
            print(f"[FASTAPI] LLM provider loaded: {llm_provider.config.model}")
        else:
            print("[FASTAPI] WARNING: No LLM provider available")
    except Exception as e:
        print(f"[FASTAPI] ERROR loading LLM: {e}")
    
    # Start TTS worker thread
    start_tts_worker()
    
    yield
    
    print("[FASTAPI] Shutting down...")


def _warmup_tts():
    """Warm up TTS model with a test generation"""
    if not tts_provider:
        return
    
    try:
        print("[FASTAPI] Warming up TTS...")
        # Try to get a reference audio path
        ref_audio_path = None
        voice_clones_dir = Path(shared.VOICE_CLONES_DIR)
        if voice_clones_dir.exists():
            wav_files = list(voice_clones_dir.glob('*.wav'))
            if wav_files:
                ref_audio_path = str(wav_files[0])
        
        # If no voice clone, try to generate without reference (will use default voice)
        if hasattr(tts_provider, 'generate_audio_stream'):
            try:
                # Warmup with streaming - may fail if no ref audio
                for _ in tts_provider.generate_audio_stream(
                    text="hello",
                    speaker="default",
                    language="English",
                    chunk_size=TTS_CHUNK_SIZE,
                    non_streaming_mode=False,
                    temperature=0.6,
                    top_k=20,
                    append_silence=False,
                    max_new_tokens=30
                ):
                    break
            except Exception as warmup_err:
                print(f"[FASTAPI] TTS warmup stream error (may be OK): {warmup_err}")
                
        print("[FASTAPI] TTS warmup complete!")
    except Exception as e:
        print(f"[FASTAPI] TTS warmup error: {e}")


def start_tts_worker():
    """Start background worker for TTS generation"""
    global tts_worker_thread
    
    def worker():
        """Background thread that processes TTS requests"""
        while True:
            try:
                # Get next request from any session
                with sessions_lock:
                    active_sessions = [s for s in sessions.values() if not s.stop_requested]
                
                if not active_sessions:
                    time.sleep(0.01)
                    continue
                
                # Check each session's queue
                for session in active_sessions:
                    try:
                        text = session.tts_queue.get_nowait()
                        if text and len(text.strip()) >= 3:
                            _generate_tts_stream(session, text.strip())
                        else:
                            # Chunk is too short to speak (e.g. a bare emoji).
                            # Still decrement the pending counter so the drain
                            # loop in _process_conversation doesn't hang until
                            # the 60-second timeout waiting for it to reach zero.
                            if session.tts_chunks_pending > 0:
                                session.tts_chunks_pending -= 1
                    except queue.Empty:
                        continue
                    except Exception as e:
                        print(f"[TTS WORKER] Error: {e}")
                        
            except Exception as e:
                print(f"[TTS WORKER] Fatal error: {e}")
                time.sleep(0.1)
    
    tts_worker_thread = threading.Thread(target=worker, daemon=True)
    tts_worker_thread.start()
    print("[FASTAPI] TTS worker started")


FRAME_SIZE = 2400  # 100ms at 24kHz — smaller frames for smoother streaming
TTS_GAIN = 0.85    # fixed pre-limiter gain (< 1.0 to leave headroom)
XFADE_SAMPLES = 512  # crossfade overlap between consecutive model chunks

def _generate_tts_stream(session: ConversationSession, text: str):
    """Generate TTS and send directly via WebSocket with proper chunking"""
    print(f"[TTS] _generate_tts_stream called with text: '{text[:30]}...' loop={id(session.loop)}")
    
    if not tts_provider:
        print("[TTS] ERROR: No tts_provider available")
        return
    
    if session.stop_requested:
        print("[TTS] Stop requested, skipping")
        return
    
    if not hasattr(tts_provider, 'generate_audio_stream'):
        print(f"[TTS] ERROR: tts_provider doesn't have generate_audio_stream. Has: {[x for x in dir(tts_provider) if not x.startswith('_')]}")
        return
    
    session.tts_active = True
    buffer = np.array([], dtype=np.float32)
    buffer_chunks: list = []          # collect chunks, concat periodically (O(n) vs O(n²))
    frames_sent = 0
    
    def _ws_send_json(data):
        """Send JSON on the WebSocket's event loop and wait for completion."""
        if session.loop is None:
            print(f"[TTS] ERROR: session.loop is None, cannot send JSON: {data}")
            raise RuntimeError("session.loop is None — WebSocket event loop was not captured at connect time")
        asyncio.run_coroutine_threadsafe(
            session.websocket.send_json(data), session.loop
        ).result()

    def _ws_send_bytes(data):
        """Send bytes on the WebSocket's event loop and wait for completion."""
        if session.loop is None:
            print(f"[TTS] ERROR: session.loop is None, cannot send {len(data)} bytes")
            raise RuntimeError("session.loop is None — WebSocket event loop was not captured at connect time")
        asyncio.run_coroutine_threadsafe(
            session.websocket.send_bytes(data), session.loop
        ).result()

    start_time = time.time()
    try:
        
        if hasattr(tts_provider, 'generate_audio_stream'):
            first_sent = False
            raw_chunks_received = 0
            prev_audio = None  # tail held back for crossfade stitching
            
            # generate_audio_stream is a regular (synchronous) generator.
            # Run TTS generation entirely in this worker thread; dispatch
            # each WebSocket send to the main event loop via
            # run_coroutine_threadsafe so we use the loop that owns the socket.
            for audio_chunk, sr, timing in tts_provider.generate_audio_stream(
                text=text,
                speaker=session.speaker,
                language="English",
                chunk_size=TTS_CHUNK_SIZE,
                non_streaming_mode=False,
                temperature=0.6,
                top_k=20,
                top_p=0.85,
                repetition_penalty=1.0,
                append_silence=False,
                max_new_tokens=180
            ):
                if session.stop_requested or session.tts_abort:
                    print(f"[TTS] Stop requested mid-stream after {raw_chunks_received} raw chunks")
                    break
                    
                if audio_chunk is not None and len(audio_chunk) > 0:
                    raw_chunks_received += 1
                    audio = np.asarray(audio_chunk, dtype=np.float32)
                    
                    if audio.ndim > 1:
                        audio = audio.mean(axis=1)
                    
                    # 1. DC offset correction – remove any bias the TTS
                    # model may have introduced (prevents low-freq hum /
                    # clicks).  Guard against unstable mean on tiny or
                    # near-silent chunks.
                    if len(audio) > 128:
                        mean = np.mean(audio)
                        if abs(mean) > 1e-4:
                            audio = audio - mean

                    # 2. Only apply fade-in/out on the very first chunk
                    # (edge protection).  For subsequent chunks the
                    # tail-buffer crossfade handles smooth transitions —
                    # stacking both causes over-attenuation ("pulsing").
                    if prev_audio is None:
                        audio = apply_fade(audio, fade_samples=128)

                    # 3. Tail-buffer crossfade (single strategy) -------
                    # Blend the held-back tail of the previous chunk with
                    # the head of this chunk using a raised-cosine ramp.
                    # Energy-based alignment reduces phase-mismatch
                    # artifacts between arbitrary TTS chunk boundaries.
                    if prev_audio is not None:
                        # Phase-align: shift curr to best-match prev tail
                        offset = find_best_offset(prev_audio, audio)
                        if offset > 0:
                            audio = audio[offset:]

                        overlap = min(len(prev_audio), len(audio), XFADE_SAMPLES)
                        if overlap > 0:
                            t = np.linspace(0.0, 1.0, overlap, dtype=np.float32)
                            fade_in = 0.5 * (1.0 - np.cos(np.pi * t))
                            fade_out = 1.0 - fade_in
                            audio[:overlap] = (
                                prev_audio[-overlap:] * fade_out
                                + audio[:overlap] * fade_in
                            )

                    # 4. Soft limiter AFTER crossfade — crossfade can
                    # push amplitude >1.0 even if both inputs were
                    # limited, so we limit the final stitched waveform.
                    audio = soft_clip(audio * TTS_GAIN)

                    # Split tail for next iteration's crossfade
                    if len(audio) > XFADE_SAMPLES:
                        prev_audio = audio[-XFADE_SAMPLES:].copy()
                        audio = audio[:-XFADE_SAMPLES]
                    else:
                        prev_audio = audio.copy()
                        audio = np.array([], dtype=np.float32)

                    # Accumulate into list buffer (O(n) total)
                    if len(audio) > 0:
                        buffer_chunks.append(audio)
                    
                    # Flatten accumulated chunks into working buffer
                    if buffer_chunks:
                        if len(buffer) > 0:
                            buffer_chunks.insert(0, buffer)
                        buffer = np.concatenate(buffer_chunks)
                        buffer_chunks.clear()

                    while len(buffer) >= FRAME_SIZE:
                        frame = buffer[:FRAME_SIZE]
                        buffer = buffer[FRAME_SIZE:]
                        
                        try:
                            if not first_sent:
                                elapsed = (time.time() - start_time) * 1000
                                print(f"[TTS] First chunk for '{text[:20]}...' in {elapsed:.0f}ms, sent {len(frame)} samples")
                                _ws_send_json({
                                    "type": "tts_start",
                                    "time": elapsed
                                })
                                first_sent = True
                            
                            _ws_send_bytes(frame.tobytes())
                            frames_sent += 1
                        except Exception as e:
                            print(f"[TTS] Send error (frame {frames_sent}): {e}")
                            break
            
            print(f"[TTS] Generator done for '{text[:20]}...': raw_chunks={raw_chunks_received}, frames_sent={frames_sent}, remainder={len(buffer)}")
            
            # Flush the crossfade tail that was held back for stitching
            if prev_audio is not None and len(prev_audio) > 0:
                buffer_chunks.append(prev_audio)
                prev_audio = None
            if buffer_chunks:
                if len(buffer) > 0:
                    buffer_chunks.insert(0, buffer)
                buffer = np.concatenate(buffer_chunks)
                buffer_chunks.clear()

            if len(buffer) > 0:
                try:
                    fade_len = min(len(buffer), 256)
                    fade = np.linspace(1.0, 0.0, fade_len, dtype=np.float32)
                    buffer[-fade_len:] *= fade
                    if len(buffer) < FRAME_SIZE:
                        buffer = np.pad(buffer, (0, FRAME_SIZE - len(buffer)))
                    _ws_send_bytes(buffer.tobytes())
                    frames_sent += 1
                    print(f"[TTS] Flushed remainder frame, total frames_sent={frames_sent}")
                except Exception as e:
                    print(f"[TTS] Final send error: {e}")
                        
    except Exception as e:
        print(f"[TTS] Generation error: {e}")
    finally:
        elapsed_total = (time.time() - start_time) * 1000
        print(f"[TTS] Finished '{text[:20]}...': frames_sent={frames_sent}, total_time={elapsed_total:.0f}ms, tts_chunks_pending={session.tts_chunks_pending}")
        session.tts_active = False
        if session.tts_chunks_pending > 0:
            session.tts_chunks_pending -= 1


# ============== FASTAPI APP ==============
app = FastAPI(title="Omnix FastAPI", lifespan=lifespan)

# Serve static files directly
from pathlib import Path

from fastapi.responses import FileResponse, HTMLResponse, Response

BASE_DIR = Path(__file__).parent
static_dir = BASE_DIR / 'src' / 'static'
templates_dir = BASE_DIR / 'src' / 'templates'
index_file = templates_dir / 'index.html'

# Cache for processed index.html
_index_html_cache = None

def get_index_html():
    """Get index.html with Flask url_for replaced"""
    global _index_html_cache
    if _index_html_cache is not None:
        return _index_html_cache
    
    if index_file.exists():
        content = index_file.read_text(encoding='utf-8')
        # Replace Flask url_for with static paths
        content = content.replace("{{ url_for('static', filename='", '/static/')
        content = content.replace("') }}", '')
        # Also handle variable replacements
        content = content.replace("{{ ", "").replace(" }}", "")
        _index_html_cache = content
        return content
    return None

@app.get("/")
async def root():
    """Serve the main HTML page"""
    content = get_index_html()
    if content:
        return HTMLResponse(content)
    return HTMLResponse("<h1>Omnix</h1><p>Static files not found</p>")

@app.get("/static/{path:path}")
async def serve_static(path: str):
    """Serve static files"""
    file_path = static_dir / path
    if file_path.exists() and file_path.is_file():
        return FileResponse(file_path)
    return HTMLResponse("Not Found", status_code=404)

@app.get("/logo/{path:path}")
async def serve_logo(path: str):
    """Serve logo files"""
    logo_dir = Path(shared.BASE_DIR) / 'resources' / 'logo'
    file_path = logo_dir / path
    if file_path.exists() and file_path.is_file():
        return FileResponse(file_path)
    return HTMLResponse("Not Found", status_code=404)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

# Register RPG adventure routes
app.include_router(rpg_adventure_bp)

# Register RPG presentation routes
app.include_router(rpg_presentation_bp)

# Register RPG game routes
app.include_router(rpg_game_bp)


@app.get("/health")
async def health():
    return {"status": "ok", "server": "fastapi"}


# ============== WEBSOCKET ENDPOINT ==============
@app.websocket("/ws/conversation")
async def websocket_conversation(websocket: WebSocket):
    """Main WebSocket endpoint for voice conversation"""
    await websocket.accept()
    
    session_id = None
    session = None
    
    try:
        # Wait for initial config message
        config_data = await asyncio.wait_for(websocket.receive_json(), timeout=10.0)
        session_id = config_data.get("session_id", "default")
        speaker = config_data.get("speaker", "default")
        
        print(f"[WS] New session: {session_id}, speaker: {speaker}")
        
        # Create session, capturing the running event loop so the TTS
        # worker thread can schedule WebSocket sends on the correct loop.
        current_loop = asyncio.get_event_loop()
        print(f"[WS] Capturing event loop id={id(current_loop)} for session {session_id}")
        with sessions_lock:
            session = ConversationSession(
                websocket=websocket,
                session_id=session_id,
                speaker=speaker,
                loop=current_loop
            )
            sessions[session_id] = session
        
        # Send ready signal
        await websocket.send_json({"type": "ready"})
        
        # Main message loop
        while not session.stop_requested:
            try:
                # Wait for user input with timeout
                data = await asyncio.wait_for(websocket.receive_text(), timeout=30.0)
                message = json.loads(data)
                
                msg_type = message.get("type")
                
                if msg_type == "stop":
                    session.stop_requested = True
                    await websocket.send_json({"type": "stopped"})
                    break
                    
                elif msg_type == "text":
                    user_text = message.get("text", "")
                    await _process_conversation(session, user_text)
                    
                elif msg_type == "chat_stream":
                    user_text = message.get("message") if "message" in message else message.get("text", "")
                    await _process_conversation(session, user_text)
                    
                elif msg_type == "config":
                    # Update config
                    if "speaker" in message:
                        session.speaker = message["speaker"]
                    
            except asyncio.TimeoutError:
                continue
            except WebSocketDisconnect:
                break
            except Exception as e:
                print(f"[WS] Error: {e}")
                try:
                    await websocket.send_json({"type": "error", "error": str(e)})
                except:
                    break
                
    except Exception as e:
        print(f"[WS] Connection error: {e}")
        
    finally:
        # Cleanup
        if session_id and session_id in sessions:
            with sessions_lock:
                del sessions[session_id]
        print(f"[WS] Session ended: {session_id}")


async def _process_conversation(session: ConversationSession, user_text: str):
    """Process conversation and stream response"""
    # Reload provider from settings on each request to pick up changes
    provider = shared.get_provider()
    if not provider:
        await session.websocket.send_json({"type": "error", "error": "No LLM provider"})
        return
    
    # Reset per-turn abort flag so a previous drain timeout doesn't block the
    # TTS worker for this new turn.
    session.tts_abort = False
    
    try:
        # Get conversation history
        messages = []
        if session.session_id in shared.sessions_data:
            raw_messages = shared.sessions_data[session.session_id].get('messages', [])
            for msg in raw_messages:
                if isinstance(msg, dict):
                    messages.append(ChatMessage(role=msg.get('role', 'user'), content=msg.get('content', '')))
                elif hasattr(msg, 'role') and hasattr(msg, 'content'):
                    messages.append(msg)
        
        # Add user message
        messages.append(ChatMessage(role="user", content=user_text))
        
        # Prepare for streaming
        buffer = ""
        sentence_buffer = ""
        done_sent = False  # guard: ensure 'done' is sent exactly once per turn
        
        start_time = time.time()
        
        # Stream from LLM
        stream_generator = provider.chat_completion(
            messages=messages,
            model=provider.config.model,
            stream=True
        )
        
        first_token_time = None
        
        for response_chunk in stream_generator:
            if session.stop_requested:
                break
                
            content = response_chunk.content if hasattr(response_chunk, 'content') else str(response_chunk)
            
            if content:
                if first_token_time is None:
                    first_token_time = time.time()
                    elapsed = (first_token_time - start_time) * 1000
                    print(f"[LLM] First token: {elapsed:.0f}ms")
                    await session.websocket.send_json({
                        "type": "token",
                        "time": elapsed
                    })
                
                buffer += content
                sentence_buffer += content
                
                # Send token to client for display
                await session.websocket.send_json({
                    "type": "content",
                    "content": content
                })
                
                # PREDICTIVE TTS: Send to worker after minimum chars
                if len(sentence_buffer) >= TTS_MIN_CHARS:
                    # Check for sentence end or punctuation
                    should_send = False
                    for punct in '.!?,':
                        if punct in sentence_buffer:
                            should_send = True
                            break
                    
                    if should_send or len(sentence_buffer) >= TTS_MAX_CHARS:
                        # Find the split point FIRST, then queue only up to it.
                        # The old order (queue full buffer, then split) caused the
                        # tail of the sentence to appear in both the queued chunk
                        # AND the next sentence_buffer, making it spoken twice.
                        last_punct = -1
                        for i, c in enumerate(sentence_buffer):
                            if c in '.!?,':
                                last_punct = i
                        
                        if last_punct >= 0:
                            # Queue only up to and including the punctuation mark
                            text_to_speak = sentence_buffer[:last_punct + 1].strip()
                            sentence_buffer = sentence_buffer[last_punct + 1:]
                        else:
                            # No punctuation found — queue the entire buffer
                            text_to_speak = sentence_buffer.strip()
                            sentence_buffer = ""
                        
                        if text_to_speak:
                            try:
                                session.tts_queue.put_nowait(text_to_speak)
                                session.tts_chunks_pending += 1
                                print(f"[CONV] Queued TTS chunk ({len(text_to_speak)} chars, pending={session.tts_chunks_pending}): '{text_to_speak[:40]}'")
                            except:
                                pass
        
        # Process remaining buffer
        if sentence_buffer.strip() and not session.stop_requested:
            try:
                session.tts_queue.put_nowait(sentence_buffer.strip())
                session.tts_chunks_pending += 1
                print(f"[CONV] Queued final TTS chunk (pending={session.tts_chunks_pending}): '{sentence_buffer.strip()[:40]}'")
            except:
                pass
        
        # Wait until both conditions are true:
        # 1. tts_queue is empty (no more text items waiting to be picked up)
        # 2. tts_active is False (the TTS worker has finished sending all audio frames)
        # 3. tts_chunks_pending is 0 (all queued chunks have been processed)
        # Checking only tts_queue.empty() is insufficient because the worker
        # dequeues the text item before it starts generating/sending audio.
        drain_timeout = time.time() + 60.0  # max 60s wait for long responses
        drain_polls = 0
        while not session.stop_requested:
            if time.time() > drain_timeout:
                print("[CONV] TTS drain timeout — sending done anyway")
                # Signal the TTS worker to abort the current generation so it
                # stops sending audio frames after we send 'done'. Without this
                # the worker continues to stream audio to the WebSocket while
                # the client has already moved on, wasting bandwidth.
                session.tts_abort = True
                # Drain the pending queue so no further chunks are picked up.
                try:
                    while not session.tts_queue.empty():
                        session.tts_queue.get_nowait()
                except queue.Empty:
                    pass
                session.tts_chunks_pending = 0
                break
            queue_empty = session.tts_queue.empty()
            tts_done = not session.tts_active
            chunks_done = session.tts_chunks_pending <= 0
            if queue_empty and tts_done and chunks_done:
                print(f"[CONV] TTS drain complete after {drain_polls} polls ({(time.time() - start_time)*1000:.0f}ms total)")
                break
            drain_polls += 1
            await asyncio.sleep(0.05)
        
        # One additional render-cycle wait to ensure the final send_bytes
        # call has been flushed through the WebSocket send buffer
        if not session.stop_requested:
            await asyncio.sleep(0.1)
        
        if not done_sent:
            done_sent = True
            total_ms = (time.time() - start_time) * 1000
            print(f"[CONV] Sending 'done' at {total_ms:.0f}ms, response_length={len(buffer)} chars")
            await session.websocket.send_json({
                "type": "done",
                "total_time": total_ms
            })
        
        # Save to history
        if session.session_id in shared.sessions_data:
            # Save user message
            shared.sessions_data[session.session_id]['messages'].append({
                "role": "user", 
                "content": user_text
            })
            # Save assistant message
            shared.sessions_data[session.session_id]['messages'].append({
                "role": "assistant", 
                "content": buffer
            })
            shared.save_sessions(shared.sessions_data)
            
    except Exception as e:
        import traceback
        print(f"[CONV] Error: {e}\n{traceback.format_exc()}")
        try:
            await session.websocket.send_json({
                "type": "error", 
                "error": str(e)
            })
        except:
            pass


# ============== REST API ENDPOINTS ==============
import uuid
from datetime import datetime

from fastapi import HTTPException, Request


@app.get("/api/settings")
async def get_settings():
    """Get settings"""
    settings = shared.load_settings()
    secrets = shared.load_secrets()
    
    # Add API keys from secrets to settings (for internal use)
    if 'api_keys' in secrets:
        for key in ['openrouter', 'cerebras']:
            if key in secrets['api_keys'] and secrets['api_keys'][key]:
                if key not in settings:
                    settings[key] = {}
                settings[key]['api_key'] = secrets['api_keys'][key]
    
    # Mask API keys in response to frontend
    for key in ['openrouter', 'cerebras']:
        if settings.get(key, {}).get('api_key'):
            api_key = settings[key]['api_key']
            settings[key]['api_key'] = "***" + api_key[-4:] if len(api_key) > 4 else "****"
    
    return {"success": True, "settings": settings}


@app.post("/api/settings")
async def save_settings(request: Request):
    """Save settings"""
    data = await request.json()
    settings = shared.load_settings()
    secrets = shared.load_secrets()
    
    if 'provider' in data:
        settings['provider'] = data['provider']
    if 'global_system_prompt' in data:
        settings['global_system_prompt'] = data['global_system_prompt']
    if 'lmstudio' in data:
        settings['lmstudio'].update(data['lmstudio'])
    
    # Save API keys to secrets.json
    if 'openrouter' in data:
        if data['openrouter'].get('api_key') and not data['openrouter']['api_key'].startswith('***'):
            if 'api_keys' not in secrets:
                secrets['api_keys'] = {}
            secrets['api_keys']['openrouter'] = data['openrouter']['api_key']
        if 'openrouter' not in settings:
            settings['openrouter'] = {}
        settings['openrouter'].update({k: v for k, v in data['openrouter'].items() if k != 'api_key'})
    
    if 'cerebras' in data:
        if data['cerebras'].get('api_key') and not data['cerebras']['api_key'].startswith('***'):
            if 'api_keys' not in secrets:
                secrets['api_keys'] = {}
            secrets['api_keys']['cerebras'] = data['cerebras']['api_key']
        if 'cerebras' not in settings:
            settings['cerebras'] = {}
        settings['cerebras'].update({k: v for k, v in data['cerebras'].items() if k != 'api_key'})
            
    if 'llamacpp' in data:
        if 'llamacpp' not in settings:
            settings['llamacpp'] = shared.DEFAULT_SETTINGS['llamacpp'].copy()
        settings['llamacpp'].update(data['llamacpp'])
    
    # Save secrets (API keys)
    shared.save_secrets(secrets)
    
    # Save settings
    shared.save_settings(settings)
    return {"success": True}


@app.get("/api/openrouter/models")
async def get_openrouter_models():
    """Get available models from OpenRouter API"""
    import requests
    
    settings = shared.load_settings()
    api_key = settings.get('openrouter', {}).get('api_key', '')
    
    if not api_key:
        return {"success": False, "error": "No API key configured"}
    
    try:
        response = requests.get(
            "https://openrouter.ai/api/v1/models",
            headers={"Authorization": f"Bearer {api_key}"},
            timeout=10
        )
        
        if response.status_code == 200:
            data = response.json()
            models = [{"id": m.get("id"), "name": m.get("name", m.get("id"))} for m in data.get("data", [])]
            return {"success": True, "models": models}
        else:
            return {"success": False, "error": f"API error: {response.status_code}"}
    except Exception as e:
        return {"success": False, "error": str(e)}


@app.get("/api/sessions")
async def get_sessions():
    """Get all sessions"""
    shared.sessions_data = shared.load_sessions()
    sl = sorted(
        [{'id': k, 'title': v.get('title', 'New Chat'), 'updated_at': v.get('updated_at', '')} 
         for k, v in shared.sessions_data.items()],
        key=lambda x: x['updated_at'],
        reverse=True
    )
    return {"success": True, "sessions": sl}


@app.post("/api/sessions")
async def create_session():
    """Create new session"""
    shared.sessions_data = shared.load_sessions()
    sid = str(uuid.uuid4())[:8]
    shared.sessions_data[sid] = {
        'title': 'New Chat',
        'messages': [],
        'system_prompt': shared.get_global_system_prompt(),
        'created_at': datetime.now().isoformat(),
        'updated_at': datetime.now().isoformat()
    }
    shared.save_sessions(shared.sessions_data)
    return {"success": True, "session_id": sid}


@app.get("/api/sessions/{session_id}")
async def get_session(session_id: str):
    """Get session by ID"""
    shared.sessions_data = shared.load_sessions()
    if session_id not in shared.sessions_data:
        raise HTTPException(status_code=404, detail="Not found")
    return {"success": True, "session": shared.sessions_data[session_id]}


@app.delete("/api/sessions/{session_id}")
async def delete_session(session_id: str):
    """Delete session"""
    shared.sessions_data = shared.load_sessions()
    if session_id not in shared.sessions_data:
        raise HTTPException(status_code=404, detail="Not found")
    del shared.sessions_data[session_id]
    shared.save_sessions(shared.sessions_data)
    return {"success": True}


@app.put("/api/sessions/{session_id}")
async def update_session(session_id: str, request: Request):
    """Update session"""
    shared.sessions_data = shared.load_sessions()
    if session_id not in shared.sessions_data:
        raise HTTPException(status_code=404, detail="Not found")
    
    data = await request.json()
    if 'title' in data:
        shared.sessions_data[session_id]['title'] = data['title']
    if 'system_prompt' in data:
        shared.sessions_data[session_id]['system_prompt'] = data['system_prompt']
    shared.sessions_data[session_id]['updated_at'] = datetime.now().isoformat()
    shared.save_sessions(shared.sessions_data)
    return {"success": True}


@app.post("/api/sessions/generate-title")
async def generate_session_title(request: Request):
    """Generate a smart title for a session based on the conversation"""
    data = await request.json()
    user_message = data.get('user_message', '')
    ai_response = data.get('ai_response', '')
    
    # Reload provider from settings on each request to pick up changes
    provider = shared.get_provider()
    if not provider:
        return JSONResponse({"success": False, "error": "No LLM provider"}, status_code=500)
    
    try:
        # Create a prompt to generate a short title
        title_prompt = f"""Given this conversation:
User: {user_message[:200]}
AI: {ai_response[:300]}

Generate a short, descriptive title (max 5 words) for this conversation. 
The title should capture the main topic or question. 
Just return the title, nothing else."""

        messages = [ChatMessage(role="user", content=title_prompt)]
        
        response = await provider.chat_completion(
            messages=messages,
            model=provider.config.model,
            stream=False
        )
        
        title = ""
        if hasattr(response, 'content'):
            title = response.content.strip()
        elif isinstance(response, dict):
            title = response.get('content', '').strip()
        
        # Clean up the title - remove quotes if present
        title = title.strip('"\'')
        
        # Fallback to first message if title is empty or too long
        if not title or len(title) > 50:
            # Use first line of user message as fallback
            first_line = user_message.split('\n')[0].strip()
            title = first_line[:50] if first_line else "New Chat"
        
        return {"success": True, "title": title}
        
    except Exception as e:
        print(f"[TITLE] Error generating title: {e}")
        # Fallback
        first_line = user_message.split('\n')[0].strip() if user_message else "New Chat"
        return {"success": True, "title": first_line[:50]}


@app.get("/api/tts/speakers")
async def get_tts_speakers():
    """Get available TTS speakers/voices"""
    tts = shared.get_tts_provider()
    if not tts:
        return JSONResponse({"success": False, "error": "No TTS provider available"}, status_code=500)
    
    try:
        if hasattr(tts, 'get_speakers'):
            speakers = tts.get_speakers()
        elif hasattr(tts, 'get_voices'):
            speakers = tts.get_voices()
        else:
            speakers = [
                {"id": "Maya", "name": "Maya"},
                {"id": "en", "name": "English (Default)"},
                {"id": "default", "name": "Default"}
            ]
        
        return {
            "success": True,
            "speakers": speakers,
            "provider": tts.provider_name
        }
    except Exception as e:
        return JSONResponse({"success": False, "error": str(e)}, status_code=500)


@app.get("/api/health")
async def health_check():
    """Check health of current provider"""
    provider = shared.get_provider()
    if not provider:
        return {"status": "disconnected", "message": "Provider not available", "provider": "unknown"}
    
    try:
        is_healthy = provider.test_connection()
        status = "connected" if is_healthy else "disconnected"
        return {
            "status": status,
            "provider": provider.provider_name,
            "message": "OK" if is_healthy else "Connection failed"
        }
    except Exception as e:
        return {
            "status": "disconnected",
            "provider": provider.provider_name,
            "message": str(e)
        }


@app.get("/api/providers/status")
async def providers_status():
    """Check status of all providers"""
    try:
        llm_provider = shared.get_provider()
        llm_status = {
            "available": False,
            "provider": "unknown",
            "message": ""
        }
        
        if llm_provider:
            try:
                is_healthy = llm_provider.test_connection()
                llm_status = {
                    "available": is_healthy,
                    "provider": llm_provider.provider_name,
                    "message": "OK" if is_healthy else "Connection failed"
                }
            except Exception as e:
                llm_status = {
                    "available": False,
                    "provider": llm_provider.provider_name,
                    "message": str(e)
                }
        
        tts_p = shared.get_tts_provider()
        tts_status = {
            "available": tts_p is not None,
            "provider": tts_p.provider_name if tts_p else "none",
            "message": "Ready" if tts_p else "Not loaded"
        }
        
        return {
            "success": True,
            "llm": llm_status,
            "tts": tts_status
        }
    except Exception as e:
        return JSONResponse({"success": False, "error": str(e)}, status_code=500)


@app.get("/api/voice_clones")
async def get_voice_clones():
    """Get list of saved voice clones"""
    try:
        voices = []
        for voice_id, voice_data in shared.custom_voices.items():
            voices.append({
                "id": voice_id,
                "name": voice_id,
                "gender": voice_data.get("gender", "neutral"),
                **voice_data
            })
        return {"success": True, "voices": voices}
    except Exception as e:
        return JSONResponse({"success": False, "error": str(e)}, status_code=500)


@app.put("/api/voice_clones/{voice_id}")
async def update_voice_clone(voice_id: str, request: Request):
    """Update a voice clone's metadata (e.g. gender)."""
    try:
        voice_id = voice_id.replace("_", " ")
        if voice_id not in shared.custom_voices:
            return JSONResponse({"success": False, "error": "Voice not found"}, status_code=404)

        data = await request.json()
        if "gender" in data and data["gender"] in ("male", "female", "neutral"):
            shared.custom_voices[voice_id]["gender"] = data["gender"]

        with open(shared.VOICE_CLONES_FILE, 'w') as f:
            json.dump(shared.custom_voices, f, indent=2)

        return {"success": True, "voice": shared.custom_voices[voice_id]}
    except Exception as e:
        return JSONResponse({"success": False, "error": str(e)}, status_code=500)


@app.delete("/api/voice_clones/{voice_id}")
async def delete_voice_clone(voice_id: str):
    """Delete a voice clone"""
    try:
        voice_id = voice_id.replace("_", " ")
        if voice_id in shared.custom_voices:
            del shared.custom_voices[voice_id]
            
            clones_dir = Path(shared.VOICE_CLONES_DIR)
            wav_file = clones_dir / f"{voice_id}.wav"
            if wav_file.exists():
                wav_file.unlink()
            
            with open(shared.VOICE_CLONES_FILE, 'w') as f:
                json.dump(shared.custom_voices, f, indent=2)
            
            return {"success": True}
        return JSONResponse({"success": False, "error": "Voice not found"}, status_code=404)
    except Exception as e:
        return JSONResponse({"success": False, "error": str(e)}, status_code=500)


@app.post("/api/voice_clone")
async def create_voice_clone(request: Request):
    """Create a new voice clone from uploaded audio."""
    try:
        content_type = request.headers.get("content-type", "")

        if "multipart/form-data" in content_type:
            form = await request.form()
            voice_id = form.get("voice_id") or form.get("name")
            gender = form.get("gender", "neutral")
            language = form.get("language", "en")
            ref_text = form.get("ref_text", "")
            audio_file = form.get("file")
        else:
            data = await request.json()
            voice_id = data.get("voice_id") or data.get("name")
            gender = data.get("gender", "neutral")
            language = data.get("language", "en")
            ref_text = data.get("ref_text", "")
            audio_file = None

        if not voice_id:
            return JSONResponse({"success": False, "error": "Voice name is required"}, status_code=400)

        if gender not in ("male", "female", "neutral"):
            gender = "neutral"

        voice_id_clean = voice_id.strip()

        # Save audio file if provided
        clones_dir = Path(shared.VOICE_CLONES_DIR)
        clones_dir.mkdir(parents=True, exist_ok=True)

        if audio_file and hasattr(audio_file, "read"):
            audio_bytes = await audio_file.read()
            if audio_bytes:
                wav_path = clones_dir / f"{voice_id_clean}.wav"
                wav_path.write_bytes(audio_bytes)

                # Try voice cloning via provider
                tts_provider = shared.get_tts_provider()
                if tts_provider and hasattr(tts_provider, "voice_clone"):
                    tts_provider.voice_clone(voice_id_clean, audio_bytes, ref_text)

        # Register in custom_voices
        shared.custom_voices[voice_id_clean] = {
            "speaker": "default",
            "language": language,
            "voice_clone_id": voice_id_clean,
            "has_audio": True,
            "is_preloaded": True,
            "gender": gender,
        }

        with open(shared.VOICE_CLONES_FILE, "w") as f:
            json.dump(shared.custom_voices, f, indent=2)

        return {"success": True, "voice_id": voice_id_clean}
    except Exception as e:
        return JSONResponse({"success": False, "error": str(e)}, status_code=500)


# ----- Voice Studio endpoints -----

VOICE_STUDIO_EMOTION_MAP = {
    "neutral": {"speed": 1.0, "pitch": 0},
    "calm": {"speed": 0.9, "pitch": -1},
    "happy": {"speed": 1.1, "pitch": 2},
    "sad": {"speed": 0.85, "pitch": -2},
    "angry": {"speed": 1.2, "pitch": 1},
    "dramatic": {"speed": 0.95, "pitch": -1},
}

VS_MAX_TEXT = 2000
VS_SPEED_MIN, VS_SPEED_MAX = 0.7, 1.5
VS_PITCH_MIN, VS_PITCH_MAX = -5, 5


@app.post("/api/voice_studio/generate")
async def voice_studio_generate(request: Request):
    """Generate TTS audio with emotion controls for Voice Studio."""
    try:
        data = await request.json()
    except Exception:
        return JSONResponse({"success": False, "error": "Invalid JSON"}, status_code=400)

    text = (data.get("text") or "").strip()
    voice_id = data.get("voice_id")
    emotion = data.get("emotion", "neutral")

    if not text:
        return JSONResponse({"success": False, "error": "Text is required"}, status_code=400)
    if len(text) > VS_MAX_TEXT:
        return JSONResponse({"success": False, "error": f"Text must be {VS_MAX_TEXT} characters or fewer"}, status_code=400)
    if not voice_id:
        return JSONResponse({"success": False, "error": "Voice is required"}, status_code=400)

    try:
        speed = float(data.get("speed", 1.0))
        pitch = float(data.get("pitch", 0))
    except (ValueError, TypeError):
        return JSONResponse({"success": False, "error": "Speed and pitch must be numbers"}, status_code=400)

    if not (VS_SPEED_MIN <= speed <= VS_SPEED_MAX):
        return JSONResponse({"success": False, "error": f"Speed must be between {VS_SPEED_MIN} and {VS_SPEED_MAX}"}, status_code=400)
    if not (VS_PITCH_MIN <= pitch <= VS_PITCH_MAX):
        return JSONResponse({"success": False, "error": f"Pitch must be between {VS_PITCH_MIN} and {VS_PITCH_MAX}"}, status_code=400)

    if emotion in VOICE_STUDIO_EMOTION_MAP:
        emo = VOICE_STUDIO_EMOTION_MAP[emotion]
        if speed == 1.0:
            speed = emo["speed"]
        if pitch == 0:
            pitch = emo["pitch"]

    try:
        clean_speaker = voice_id.replace(" (Custom)", "").strip()
        voice_clone_id = shared.custom_voices.get(clean_speaker, {}).get("voice_clone_id")
        final_speaker = voice_clone_id if voice_clone_id else clean_speaker

        tts_provider = shared.get_tts_provider()
        if not tts_provider:
            return JSONResponse({"success": False, "error": "No TTS provider available"}, status_code=500)

        gen_kwargs = {"text": text, "speaker": final_speaker, "language": "en",
                      "speed": speed, "pitch": pitch, "emotion": emotion}

        if hasattr(tts_provider, "generate_tts"):
            result = tts_provider.generate_tts(**gen_kwargs)
        elif hasattr(tts_provider, "generate_audio"):
            result = tts_provider.generate_audio(**gen_kwargs)
        else:
            return JSONResponse({"success": False, "error": "TTS provider missing generation method"}, status_code=500)

        if not result or not result.get("success"):
            err = result.get("error", "TTS generation failed") if result else "TTS generation failed"
            return JSONResponse({"success": False, "error": err}, status_code=500)

        return {"success": True, "audio_base64": result.get("audio", "")}
    except Exception as e:
        return JSONResponse({"success": False, "error": str(e)}, status_code=500)


@app.get("/api/voice_studio/voices")
async def voice_studio_voices():
    """Return available voices for the Voice Studio dropdown."""
    voices = []

    for vid, vdata in shared.custom_voices.items():
        voices.append({
            "id": vid,
            "name": vid,
            "gender": vdata.get("gender", "neutral"),
        })

    tts_provider = shared.get_tts_provider()
    if tts_provider:
        try:
            if hasattr(tts_provider, "get_speakers"):
                for s in tts_provider.get_speakers():
                    sid = s.get("id", s.get("name", ""))
                    if sid and not any(v["id"] == sid for v in voices):
                        voices.append({"id": sid, "name": s.get("name", sid), "gender": "neutral"})
            elif hasattr(tts_provider, "get_voices"):
                for s in tts_provider.get_voices():
                    sid = s.get("id", s.get("name", ""))
                    if sid and not any(v["id"] == sid for v in voices):
                        voices.append({"id": sid, "name": s.get("name", sid), "gender": "neutral"})
        except Exception:
            pass

    if not voices:
        voices.append({"id": "default", "name": "Default", "gender": "neutral"})

    return {"success": True, "voices": voices}


@app.post("/api/clear")
async def clear_session(request: Request):
    """Clear session messages"""
    data = await request.json()
    sid = data.get('session_id', 'default')
    shared.sessions_data = shared.load_sessions()
    if sid in shared.sessions_data:
        shared.sessions_data[sid]['messages'] = []
        shared.sessions_data[sid]['updated_at'] = datetime.now().isoformat()
        shared.save_sessions(shared.sessions_data)
    return {"success": True}


# ============== PODCAST ENDPOINTS ==============
import io as _io
import os as _os
import re as _re_podcast
import struct as _struct
import time as _time
from pathlib import Path

VP_FILE = Path(shared.DATA_DIR) / 'podcast_voice_profiles.json'
EP_FILE = Path(shared.DATA_DIR) / 'podcast_episodes.json'

def _load_json(path, default):
    try:
        if _os.path.exists(path): 
            return json.loads(open(path, 'r').read())
    except: 
        pass
    return default

def _save_json(path, data):
    with open(path, 'w') as f: 
        json.dump(data, f, indent=2)

@app.get("/api/podcast/voice-profiles")
async def get_voice_profiles():
    """Get podcast voice profiles"""
    profiles = _load_json(VP_FILE, [])
    return {"success": True, "profiles": profiles}

@app.post("/api/podcast/voice-profiles")
async def create_voice_profile(request: Request):
    """Create podcast voice profile"""
    profiles = _load_json(VP_FILE, [])
    data = await request.json()
    data['id'] = data.get('id', f"vp_{int(_time.time())}")
    data['created_at'] = datetime.now().isoformat()
    profiles.append(data)
    _save_json(VP_FILE, profiles)
    return {"success": True, "profile": data}


@app.get("/api/podcast/episodes")
async def get_podcast_episodes():
    """Get podcast episodes"""
    eps = _load_json(EP_FILE, {})
    episodes = sorted(eps.values(), key=lambda x: x.get('created_at', ''), reverse=True)
    return {"success": True, "episodes": episodes}


@app.get("/api/podcast/episodes/{ep_id}")
async def get_podcast_episode(ep_id: str):
    """Get a specific podcast episode"""
    eps = _load_json(EP_FILE, {})
    if ep_id not in eps:
        return JSONResponse({"success": False, "error": "Not found"}, status_code=404)
    ep = eps[ep_id]
    audio_path = Path(shared.DATA_DIR) / 'podcasts' / f"{ep_id}.wav"
    if audio_path.exists():
        ep['audio_url'] = f"/api/podcast/episodes/{ep_id}/audio"
    return {"success": True, "episode": ep}


@app.put("/api/podcast/episodes/{ep_id}")
async def update_podcast_episode(ep_id: str, request: Request):
    """Update a podcast episode"""
    eps = _load_json(EP_FILE, {})
    if ep_id not in eps:
        return JSONResponse({"success": False, "error": "Not found"}, status_code=404)
    data = await request.json()
    if data:
        allowed = {'title', 'topic', 'transcript', 'speakers', 'duration', 'format', 'length', 'status', 'points', 'outline'}
        filtered = {k: v for k, v in data.items() if k in allowed}
        eps[ep_id].update(filtered)
        _save_json(EP_FILE, eps)
    return {"success": True, "episode": eps[ep_id]}


@app.delete("/api/podcast/episodes/{ep_id}")
async def delete_podcast_episode(ep_id: str):
    """Delete a podcast episode"""
    eps = _load_json(EP_FILE, {})
    if ep_id not in eps:
        return JSONResponse({"success": False, "error": "Not found"}, status_code=404)
    del eps[ep_id]
    _save_json(EP_FILE, eps)
    audio_path = Path(shared.DATA_DIR) / 'podcasts' / f"{ep_id}.wav"
    if audio_path.exists():
        audio_path.unlink()
    return {"success": True}


@app.get("/api/podcast/episodes/{ep_id}/audio")
async def get_podcast_episode_audio(ep_id: str):
    """Stream podcast episode audio"""
    audio_path = Path(shared.DATA_DIR) / 'podcasts' / f"{ep_id}.wav"
    if not audio_path.exists():
        return JSONResponse({"error": "No audio"}, status_code=404)
    return FileResponse(str(audio_path), media_type='audio/wav')


@app.post("/api/podcast/generate-outline")
async def generate_podcast_outline(request: Request):
    """Generate a podcast outline for a topic"""
    data = await request.json()
    prompt = (
        f"Create a podcast outline JSON for Topic: {data.get('topic')}. "
        f"Format: {{\"outline\": \"...\", \"sections\": [{{\"title\": \"...\", \"description\": \"...\"}}]}}"
    )
    try:
        res = await asyncio.to_thread(_llm_generate_audiobook, prompt)
        match = _re_podcast.search(r'\{[\s\S]*\}', res)
        parsed = json.loads(match.group() if match else res)
        return {"success": True, **parsed}
    except Exception as e:
        return JSONResponse({"success": False, "error": str(e)}, status_code=500)


@app.post("/api/podcast/generate")
async def generate_podcast_episode(request: Request):
    """Generate a podcast episode with SSE streaming"""
    from fastapi.responses import StreamingResponse

    data = await request.json()
    ep_id = data.get('id', f"ep_{int(_time.time())}")

    async def gen():
        try:
            yield f"data: {json.dumps({'type': 'phase', 'phase': 'script', 'percent': 5, 'message': 'Generating script...'})}\n\n"
            speaker_names = [s.get('name', f'Speaker {i+1}') for i, s in enumerate(data.get('speakers', []))]
            if not speaker_names:
                speaker_names = ['Host', 'Guest']
            speakers_str = ', '.join(speaker_names)

            # Map requested length to approximate duration and dialogue guidance
            length = data.get('length', 'medium')
            length_map = {
                'short': ('5 minutes', '20-30 exchanges'),
                'medium': ('15 minutes', '60-80 exchanges'),
                'long': ('30 minutes', '120-160 exchanges'),
                'extended': ('60 minutes', '240-320 exchanges'),
            }
            duration_str, exchanges_str = length_map.get(length, ('15 minutes', '60-80 exchanges'))

            script = await asyncio.to_thread(
                _llm_generate_audiobook,
                f"Write a podcast dialogue script for: {data.get('topic')}. "
                f"Use exactly these speaker names: {speakers_str}. "
                f"The podcast should be approximately {duration_str} long with {exchanges_str} between the speakers. "
                f"Write enough dialogue to fill the full {duration_str} duration. "
                f"Format lines exactly as 'SpeakerName: Text'"
            )

            segments = []
            for line in script.split('\n'):
                if ':' in line:
                    sp, txt = line.split(':', 1)
                    segments.append({"speaker": sp.strip(), "text": txt.strip()})

            # Build speaker-to-voice mapping by name (case-insensitive)
            input_speakers = data.get('speakers', [])
            voice_by_name = {s.get('name', '').lower(): s.get('voice_id') for s in input_speakers}

            total_segments = len(segments)
            yield f"data: {json.dumps({'type': 'phase', 'phase': 'audio', 'percent': 10, 'message': f'Generating audio for {total_segments} segments...'})}\n\n"

            transcript, audios = [], []
            for i, seg in enumerate(segments):
                # Match by name first, fall back to round-robin by index
                vid = voice_by_name.get(seg['speaker'].lower())
                if vid is None and input_speakers:
                    vid = input_speakers[i % len(input_speakers)].get('voice_id')
                v_clone = shared.custom_voices.get(
                    vid.replace(" (Custom)", "") if vid else "", {}
                ).get('voice_clone_id', vid)

                try:
                    tts_provider = shared.get_tts_provider()
                    if tts_provider:
                        result = await asyncio.to_thread(
                            tts_provider.generate_audio,
                            text=shared.remove_emojis(seg['text']),
                            speaker=v_clone,
                            language="en"
                        )
                        if result.get('success'):
                            adata, sr = result.get('audio'), result.get('sample_rate')
                            pct = round(10 + (i + 1) / total_segments * 85) if total_segments else 95
                            yield f"data: {json.dumps({'type': 'audio', 'audio': adata, 'sample_rate': sr, 'segment_index': i, 'total_segments': total_segments, 'percent': pct, 'speaker': seg['speaker'], 'text': seg['text']})}\n\n"
                            transcript.append({"speaker": seg['speaker'], "text": seg['text']})
                            audios.append(base64.b64decode(adata))
                except Exception:
                    pass

            duration = 0
            if audios:
                podcasts_dir = Path(shared.DATA_DIR) / 'podcasts'
                podcasts_dir.mkdir(exist_ok=True)
                wav_io = _io.BytesIO()
                total = sum(len(a) for a in audios)
                wav_io.write(b'RIFF')
                wav_io.write(_struct.pack('<I', 36 + total))
                wav_io.write(b'WAVEfmt ')
                wav_io.write(_struct.pack('<IHHIIHH', 16, 1, 1, shared.TTS_SAMPLE_RATE, shared.TTS_SAMPLE_RATE * 2, 2, 16))
                wav_io.write(b'data')
                wav_io.write(_struct.pack('<I', total))
                for a in audios:
                    wav_io.write(a)
                with open(podcasts_dir / f"{ep_id}.wav", 'wb') as f:
                    f.write(wav_io.getvalue())
                duration = total / 2 / shared.TTS_SAMPLE_RATE

            eps = _load_json(EP_FILE, {})
            eps[ep_id] = {**data, "transcript": transcript, "status": "complete", "duration": duration, "created_at": datetime.now().isoformat()}
            _save_json(EP_FILE, eps)
            yield f"data: {json.dumps({'type': 'done', 'duration': duration})}\n\n"

        except Exception as e:
            yield f"data: {json.dumps({'type': 'error', 'error': str(e)})}\n\n"

    return StreamingResponse(gen(), media_type="text/event-stream")


# ============== AUDIOBOOK ENDPOINTS ==============
import re as _re

# ---------------------------------------------------------------------------
# Inline dialogue parsing helpers (mirrors app/audiobook.py but avoids a
# Flask import so server_fastapi.py can run without the Flask dependency).
# ---------------------------------------------------------------------------
_FEMALE_NAMES = {'sofia', 'emma', 'olivia', 'ava', 'mia', 'charlotte', 'amelia', 'harper', 'evelyn', 'sarah', 'laura', 'kate', 'jessica', 'ciri', 'her', 'anaka'}
_MALE_NAMES = {'morgan', 'james', 'john', 'robert', 'michael', 'david', 'richard', 'joseph', 'thomas', 'charles', 'nate', 'inigo', 'jinx'}


def _detect_gender(name):
    if not name:
        return 'neutral'
    nl = name.lower().strip()
    if any(w in nl for w in ['ms.', 'mrs.', 'she', 'her', 'woman']):
        return 'female'
    if any(w in nl for w in ['mr.', 'he', 'him', 'man']):
        return 'male'
    if any(f in nl for f in _FEMALE_NAMES):
        return 'female'
    if any(m in nl for m in _MALE_NAMES):
        return 'male'
    return 'neutral'


def _parse_dialogue(text):
    segments = []
    speech_verbs = r'(?:said|asked|replied|whispered|shouted|murmured|answered|added|insisted|demanded|muttered|sighed|groaned|exclaimed|called|declared|continued|suggested|offered|responded)'
    thought_pattern = _re.compile(r'([A-Z][A-Za-z\'\-]+)\s+(?:thought|wondered)\s*[,:]*\s*["\']([^"\']+)["\']', _re.IGNORECASE)

    paragraphs = _re.split(r'\n\s*\n', text)
    if len(paragraphs) <= 2 and '\n' in text:
        paragraphs = [p for p in text.split('\n') if p.strip()]

    last_speaker = None
    for para in paragraphs:
        para = para.strip()
        if not para:
            continue

        para_dialogues = []
        thoughts = [t[1] for t in thought_pattern.findall(para)]

        for m in _re.finditer(r'([A-Z][A-Za-z\'\-]+)\s*:\s*(.+)$', para, _re.MULTILINE):
            if m.group(2).strip() and not any(t in m.group(2) for t in thoughts):
                para_dialogues.append({'speaker': m.group(1).strip(), 'text': m.group(2).strip(), 'start': m.start(), 'end': m.end()})
                last_speaker = m.group(1).strip()

        if not para_dialogues:
            matched_spans = []
            # Pattern: "dialogue," verb Speaker  (e.g. "Heartless," said Tom)
            for m in _re.finditer(r'["\u201c]([^"\u201d]+)["\u201d]\s*,?\s*(?:' + speech_verbs + r')\s+([A-Z][A-Za-z\'\-]+)', para, _re.IGNORECASE):
                if m.group(1).strip() and not any(t in m.group(1) for t in thoughts):
                    para_dialogues.append({'speaker': m.group(2).strip(), 'text': m.group(1).strip(), 'start': m.start(), 'end': m.end()})
                    last_speaker = m.group(2).strip()
                    matched_spans.append((m.start(), m.end()))

            # Pattern: "dialogue," Speaker verb  (e.g. "I'm serious," Maya insisted)
            for m in _re.finditer(r'["\u201c]([^"\u201d]+)["\u201d]\s*,?\s*([A-Z][A-Za-z\'\-]+)\s+(?:' + speech_verbs + r')', para, _re.IGNORECASE):
                if any(s <= m.start() < e for s, e in matched_spans):
                    continue
                if m.group(1).strip() and not any(t in m.group(1) for t in thoughts):
                    para_dialogues.append({'speaker': m.group(2).strip(), 'text': m.group(1).strip(), 'start': m.start(), 'end': m.end()})
                    last_speaker = m.group(2).strip()
                    matched_spans.append((m.start(), m.end()))

            # Also find remaining quoted segments not captured by speech-verb patterns
            if para_dialogues:
                for m in _re.finditer(r'["\u201c]([^"\u201d]+)["\u201d]', para):
                    if any(s <= m.start() < e for s, e in matched_spans):
                        continue
                    if m.group(1).strip() and not any(t in m.group(1) for t in thoughts):
                        para_dialogues.append({'speaker': last_speaker or 'Narrator', 'text': m.group(1).strip(), 'start': m.start(), 'end': m.end()})

        if not para_dialogues:
            for m in _re.finditer(r'["\u201c]([^"\u201d]+)["\u201d]', para):
                if m.group(1).strip() and not any(t in m.group(1) for t in thoughts):
                    para_dialogues.append({'speaker': last_speaker or 'Narrator', 'text': m.group(1).strip(), 'start': m.start(), 'end': m.end()})

        if para_dialogues:
            para_dialogues.sort(key=lambda x: x.get('start', 0))

            # Collect matched spans for gap extraction
            spans = [(d['start'], d.get('end', d['start'] + len(d['text']) + 2)) for d in para_dialogues]

            # Narration before first dialogue
            if spans[0][0] > 0:
                pre = _re.sub(r'["\u201c].*?["\u201d]', '', para[:spans[0][0]]).strip()
                if pre:
                    segments.append({'speaker': 'Narrator', 'text': pre})

            for i, d in enumerate(para_dialogues):
                segments.append({'speaker': d['speaker'], 'text': d['text']})
                # Narration gap between this dialogue and the next
                if i < len(para_dialogues) - 1:
                    gap_text = para[spans[i][1]:spans[i + 1][0]]
                    gap_text = _re.sub(r'["\u201c].*?["\u201d]', '', gap_text).strip('.,;: \t\n')
                    if gap_text:
                        segments.append({'speaker': 'Narrator', 'text': gap_text})

            # Narration after last dialogue
            if spans[-1][1] < len(para):
                post = _re.sub(r'["\u201c].*?["\u201d]', '', para[spans[-1][1]:]).strip('.,;: \t\n')
                if post:
                    segments.append({'speaker': 'Narrator', 'text': post})
        else:
            if '"' not in para and '\u201c' not in para:
                segments.append({'speaker': 'Narrator', 'text': para})

    return segments


def _llm_generate_audiobook(prompt: str) -> str:
    """Call the configured LLM and return its text response (audiobook helper)."""
    cfg = shared.get_provider_config()
    payload = {
        "model": cfg.get("model", "local-model"),
        "messages": [{"role": "user", "content": prompt}],
    }
    headers = {"Content-Type": "application/json"}
    if cfg["provider"] in ("openrouter", "cerebras"):
        headers["Authorization"] = f"Bearer {cfg['api_key']}"
    url = (
        f"{cfg['base_url']}/chat/completions"
        if cfg["provider"] == "openrouter"
        else f"{cfg['base_url']}/v1/chat/completions"
    )
    r = requests.post(url, json=payload, headers=headers, timeout=120)
    if r.status_code == 200:
        return r.json()["choices"][0]["message"]["content"]
    return ""


# ---------------------------------------------------------------------------
# PDF page filtering helpers (mirrors app/audiobook.py)
# ---------------------------------------------------------------------------

_MAX_INITIAL_PAGES = 5
_MIN_WORDS_THRESHOLD = 30

# Server-side session storage for remaining pages
_upload_sessions: dict = {}


def _is_title_page(text):
    words = text.split()
    if len(words) < 50 and "chapter" not in text.lower():
        return True
    keywords = ["by", "author", "published"]
    if any(k in text.lower() for k in keywords) and len(words) < 100:
        return True
    return False


def _is_table_of_contents(text):
    t = text.lower()
    if "contents" in t:
        return True
    lines = text.splitlines()
    toc_like = sum(1 for line in lines if _re.search(r'\d+\s*$', line))
    if toc_like >= 5:
        return True
    if "...." in text:
        return True
    return False


def _is_story_page(text):
    if len(text.split()) < _MIN_WORDS_THRESHOLD:
        return False
    if '"' in text:
        return True
    sentences = text.split('.')
    if len(sentences) > 5:
        return True
    return False


def _extract_valid_pages(reader):
    valid_pages = []
    for page in reader.pages:
        text = page.extract_text() or ""
        if _is_table_of_contents(text):
            continue
        if _is_title_page(text):
            continue
        if not _is_story_page(text):
            continue
        valid_pages.append(text)
    return valid_pages


def _extract_characters_and_gender(text):
    characters = {}
    for m in _re.finditer(
        r'([A-Z][a-z]+)\s+(said|says|replied|replies|asked|asks|whispered|whispers|shouted|shouts|murmured|murmurs|exclaimed|exclaims)',
        text,
    ):
        name = m.group(1)
        if name not in characters:
            characters[name] = {"male": 0, "female": 0}
        # Local window: ±100 chars around the match
        start = max(0, m.start() - 100)
        end = min(len(text), m.end() + 100)
        window = text[start:end].lower()
        if " he " in window or " his " in window or " him " in window:
            characters[name]["male"] += 2
        if " she " in window or " her " in window or " hers " in window:
            characters[name]["female"] += 2
    return characters


@app.post("/api/audiobook/upload")
async def audiobook_upload(request: Request):
    """Parse uploaded text or file into dialogue segments."""
    content_type = request.headers.get("content-type", "")
    text = None

    if "multipart/form-data" in content_type:
        form = await request.form()
        file = form.get("file")
        if file:
            raw = await file.read()
            if file.filename and file.filename.lower().endswith(".pdf"):
                try:
                    import io
                    import uuid as _uuid

                    import PyPDF2
                    reader = PyPDF2.PdfReader(io.BytesIO(raw))
                    valid_pages = _extract_valid_pages(reader)
                except Exception as e:
                    return JSONResponse(
                        {"success": False, "error": f"Failed to read PDF: {e}"},
                        status_code=400,
                    )

                if not valid_pages:
                    return JSONResponse(
                        {"success": False, "error": "No readable story content found"},
                        status_code=400,
                    )

                initial_pages = valid_pages[:_MAX_INITIAL_PAGES]
                remaining_pages = valid_pages[_MAX_INITIAL_PAGES:]
                initial_text = "\n".join(initial_pages)

                characters = _extract_characters_and_gender(initial_text)

                segs = _parse_dialogue(initial_text)

                available_voices = []
                for vid, vdata in shared.custom_voices.items():
                    available_voices.append({
                        "id": vid,
                        "gender": vdata.get("gender", "neutral"),
                    })

                # Store remaining pages server-side
                session_id = None
                if remaining_pages:
                    session_id = str(_uuid.uuid4())
                    _upload_sessions[session_id] = remaining_pages

                return {
                    "success": True,
                    "initial_text": initial_text,
                    "session_id": session_id,
                    "characters": characters,
                    "total_pages": len(valid_pages),
                    "remaining_count": len(remaining_pages),
                    "segments": segs,
                    "speakers": list({s["speaker"] for s in segs}),
                    "available_voices": available_voices,
                }
            else:
                text = raw.decode("utf-8")
        if not text:
            text = form.get("text", "")
    else:
        data = await request.json()
        text = data.get("text", "")

    if not text:
        return JSONResponse({"success": False, "error": "No text"}, status_code=400)

    segs = _parse_dialogue(text)
    return {
        "success": True,
        "segments": segs,
        "speakers": list({s["speaker"] for s in segs}),
    }


@app.get("/api/audiobook/pages")
async def audiobook_get_remaining_pages(request: Request):
    """Lazily fetch remaining pages stored during PDF upload."""
    session_id = request.query_params.get("session_id", "")
    if not session_id or not _re.match(r'^[A-Za-z0-9\-]+$', session_id):
        return JSONResponse({"success": False, "error": "Invalid session_id"}, status_code=400)

    pages = _upload_sessions.pop(session_id, None)
    if pages is None:
        return JSONResponse(
            {"success": False, "error": "Session not found or already consumed"},
            status_code=404,
        )

    return {"success": True, "pages": pages}


@app.post("/api/audiobook/generate")
async def audiobook_generate(request: Request):
    """Generate audiobook audio via SSE stream."""
    from fastapi.responses import StreamingResponse

    data = await request.json()
    segments = data.get("segments", [])
    v_map = data.get("voice_mapping", {})
    def_v = data.get("default_voices", {})
    avail = set(shared.custom_voices.keys())

    async def gen():
        # Use the configured TTS provider (same as /api/tts endpoint)
        tts_provider = shared.get_tts_provider()
        if not tts_provider:
            yield f"data: {json.dumps({'type': 'error', 'error': 'No TTS provider available. Please check your TTS settings.', 'code': 'TTS_UNAVAILABLE'})}\n\n"
            yield f"data: {json.dumps({'type': 'done'})}\n\n"
            return

        for i, seg in enumerate(segments):
            speaker = seg.get("speaker")
            text = seg.get("text", "")
            if not text.strip():
                continue

            v_name = v_map.get(speaker)
            if not v_name:
                g = _detect_gender(speaker)
                if g == "female":
                    v_name = def_v.get("female")
                elif g == "male":
                    v_name = def_v.get("male")
                else:
                    v_name = def_v.get("narrator")

            vid = (
                shared.custom_voices.get(v_name, {}).get("voice_clone_id")
                if v_name
                else None
            )

            final_speaker = vid if vid else v_name

            try:
                if hasattr(tts_provider, 'generate_tts'):
                    result = tts_provider.generate_tts(text=shared.remove_emojis(text), speaker=final_speaker, language="en")
                elif hasattr(tts_provider, 'generate_audio'):
                    result = tts_provider.generate_audio(text=shared.remove_emojis(text), speaker=final_speaker, language="en")
                else:
                    yield f"data: {json.dumps({'type': 'error', 'error': 'TTS provider missing generate method.'})}\n\n"
                    break

                if result and result.get("success"):
                    yield (
                        f"data: {json.dumps({'type': 'audio', 'audio': result.get('audio', ''), 'sample_rate': result.get('sample_rate', 24000), 'segment_index': i, 'text': text[:100], 'voice_used': v_name})}\n\n"
                    )
                else:
                    yield f"data: {json.dumps({'type': 'error', 'error': result.get('error', 'TTS generation failed')})}\n\n"
            except (requests.exceptions.ConnectionError, requests.exceptions.Timeout):
                yield f"data: {json.dumps({'type': 'error', 'error': 'TTS server is not running. Please start the TTS server and try again.', 'code': 'TTS_UNAVAILABLE'})}\n\n"
                break
            except Exception as e:
                yield f"data: {json.dumps({'type': 'error', 'error': str(e)})}\n\n"

            await asyncio.sleep(0.1)

        yield f"data: {json.dumps({'type': 'done'})}\n\n"

    return StreamingResponse(gen(), media_type="text/event-stream")


@app.post("/api/audiobook/speakers/detect")
async def audiobook_speakers_detect(request: Request):
    """Detect speakers in text."""
    data = await request.json()
    segs = _parse_dialogue(data.get("text", ""))
    speakers: dict = {}
    for s in segs:
        sp = s.get("speaker")
        if sp and sp not in speakers:
            speakers[sp] = {
                "name": sp,
                "gender": _detect_gender(sp),
                "segment_count": 1,
            }
        elif sp:
            speakers[sp]["segment_count"] += 1

    avail = list(shared.custom_voices.keys())
    for sp, info in speakers.items():
        match = next(
            (v for v in avail if sp.lower() in v.lower() or v.lower() in sp.lower()),
            None,
        )
        if match:
            info["suggested_voice"] = match
        else:
            info["suggested_voice"] = next(
                (v for v in avail if info["gender"] in v.lower()),
                avail[0] if avail else None,
            )

    return {"success": True, "speakers": speakers, "available_voices": avail}


@app.post("/api/audiobook/ai-structure")
async def audiobook_ai_structure(request: Request):
    """Structure raw text into a directed audiobook script using the LLM."""
    data = await request.json()
    text = data.get("text", "")
    title = data.get("title", "")
    book_id = data.get("book_id", "default")

    if not text.strip():
        return JSONResponse(
            {"success": False, "error": "No text provided"}, status_code=400
        )

    try:
        from audiobook.ai.ai_structuring_service import AIStructuringService
        from audiobook.voice.character_normalizer import CharacterNormalizer
        from audiobook.voice.character_voice_memory import CharacterVoiceMemory
        from audiobook.voice.voice_assignment import VoiceAssignment

        normalizer = CharacterNormalizer()
        memory = CharacterVoiceMemory(
            book_id,
            base_dir=_os.path.join(shared.DATA_DIR, "audiobooks"),
        )
        avail_voices = list(shared.custom_voices.keys())

        loop = asyncio.get_event_loop()
        service = AIStructuringService(llm_fn=_llm_generate_audiobook)
        structured = await loop.run_in_executor(
            None, lambda: service.structure(text, title=title)
        )

        assignment = VoiceAssignment(
            available_voices=avail_voices,
            memory=memory,
            normalizer=normalizer,
        )
        for seg in structured.get("segments", []):
            for line in seg.get("script", []):
                line["speaker"] = normalizer.normalize(line.get("speaker", ""))
                line["voice"] = assignment.get_voice(line["speaker"])

        all_speakers = list(
            {
                line["speaker"]
                for seg in structured.get("segments", [])
                for line in seg.get("script", [])
            }
        )
        structured["characters"] = [
            {"id": _re.sub(r"\W+", "_", s.lower()), "name": s} for s in all_speakers
        ]

        return {"success": True, "structured_script": structured}

    except Exception as e:
        return JSONResponse({"success": False, "error": str(e)}, status_code=500)


@app.post("/api/audiobook/direct")
async def audiobook_direct(request: Request):
    """Apply AI narration direction (pacing, emotion, emphasis) to a script."""
    data = await request.json()
    script = data.get("script", [])
    book_id = data.get("book_id", "default")

    if not script:
        return JSONResponse(
            {"success": False, "error": "No script provided"}, status_code=400
        )

    try:
        from audiobook.director.audiobook_director import AudiobookDirector
        from audiobook.voice.character_normalizer import CharacterNormalizer
        from audiobook.voice.character_voice_memory import CharacterVoiceMemory
        from audiobook.voice.voice_assignment import VoiceAssignment

        normalizer = CharacterNormalizer()
        memory = CharacterVoiceMemory(
            book_id,
            base_dir=_os.path.join(shared.DATA_DIR, "audiobooks"),
        )
        avail_voices = list(shared.custom_voices.keys())
        assignment = VoiceAssignment(
            available_voices=avail_voices,
            memory=memory,
            normalizer=normalizer,
        )

        director = AudiobookDirector(llm_fn=_llm_generate_audiobook)

        normalised_script = [
            {**line, "speaker": normalizer.normalize(line.get("speaker", ""))}
            for line in script
        ]

        loop = asyncio.get_event_loop()
        directed = await loop.run_in_executor(
            None, lambda: director.direct(normalised_script)
        )

        for line in directed:
            line["voice"] = assignment.get_voice(line["speaker"])

        return {"success": True, "directed_script": directed}

    except Exception as e:
        return JSONResponse({"success": False, "error": str(e)}, status_code=500)


@app.get("/api/audiobook/books/{book_id}/voices")
async def audiobook_get_voice_profiles(book_id: str):
    """Return all stored voice profiles for a book."""
    try:
        from audiobook.voice.character_voice_memory import CharacterVoiceMemory

        memory = CharacterVoiceMemory(
            book_id,
            base_dir=_os.path.join(shared.DATA_DIR, "audiobooks"),
        )
        return {
            "success": True,
            "book_id": book_id,
            "voices": memory.all_profiles(),
            "available_voices": list(shared.custom_voices.keys()),
        }
    except Exception as e:
        return JSONResponse({"success": False, "error": str(e)}, status_code=500)


@app.put("/api/audiobook/books/{book_id}/voices")
async def audiobook_update_voice_profiles(book_id: str, request: Request):
    """Bulk-update voice profiles for a book (used by the Voice Panel UI)."""
    data = await request.json()
    voices = data.get("voices", {})

    if not isinstance(voices, dict):
        return JSONResponse(
            {"success": False, "error": "voices must be an object"}, status_code=400
        )

    try:
        from audiobook.voice.character_voice_memory import CharacterVoiceMemory

        memory = CharacterVoiceMemory(
            book_id,
            base_dir=_os.path.join(shared.DATA_DIR, "audiobooks"),
        )
        for character, profile in voices.items():
            if isinstance(profile, str):
                memory.set_voice(character, profile)
            elif isinstance(profile, dict):
                memory.update_profile(character, profile)
        return {"success": True, "voices": memory.all_profiles()}
    except Exception as e:
        return JSONResponse({"success": False, "error": str(e)}, status_code=500)


# ---------- Audiobook library (list files in resources/data/audiobooks) -----
_AUDIOBOOK_LIBRARY_DIR = _os.path.join(shared.DATA_DIR, "audiobooks")
_ALLOWED_BOOK_EXTENSIONS = {'.mp3', '.wav', '.ogg', '.m4a', '.flac', '.aac', '.wma'}
_AUDIO_MIME_TYPES = {
    '.mp3': 'audio/mpeg',
    '.wav': 'audio/wav',
    '.ogg': 'audio/ogg',
    '.m4a': 'audio/mp4',
    '.flac': 'audio/flac',
    '.aac': 'audio/aac',
    '.wma': 'audio/x-ms-wma',
}

@app.get("/api/audiobook/library")
async def audiobook_list_library():
    """Return a list of audiobook files available in the library directory."""
    _os.makedirs(_AUDIOBOOK_LIBRARY_DIR, exist_ok=True)
    books = []
    try:
        for entry in sorted(_os.listdir(_AUDIOBOOK_LIBRARY_DIR)):
            ext = _os.path.splitext(entry)[1].lower()
            if ext not in _ALLOWED_BOOK_EXTENSIONS:
                continue
            full_path = _os.path.join(_AUDIOBOOK_LIBRARY_DIR, entry)
            if not _os.path.isfile(full_path):
                continue
            name_without_ext = _os.path.splitext(entry)[0]
            books.append({
                "filename": entry,
                "title": name_without_ext.replace('_', ' ').replace('-', ' '),
                "type": ext.lstrip('.'),
                "size": _os.path.getsize(full_path),
            })
    except OSError:
        pass
    return {"success": True, "books": books}


@app.get("/api/audiobook/library/{filename:path}")
async def audiobook_get_library_book(filename: str):
    """Return an audiobook file from the library."""
    basename = _os.path.basename(filename)
    if basename != filename:
        return JSONResponse({"success": False, "error": "Invalid filename"}, status_code=400)
    ext = _os.path.splitext(basename)[1].lower()
    if ext not in _ALLOWED_BOOK_EXTENSIONS:
        return JSONResponse({"success": False, "error": "Unsupported file type"}, status_code=400)

    full_path = _os.path.join(_AUDIOBOOK_LIBRARY_DIR, basename)
    if not _os.path.isfile(full_path):
        return JSONResponse({"success": False, "error": "File not found"}, status_code=404)

    media_type = _AUDIO_MIME_TYPES.get(ext, 'application/octet-stream')
    return FileResponse(full_path, media_type=media_type)


# ============== STORY TELLER ENDPOINTS ==============

_STORY_GENRES = {"fantasy", "horror", "sci-fi", "kids", "romance", "custom"}
_STORY_TONES = {"dark", "funny", "emotional", "epic", "calm", "mysterious"}
_STORY_LENGTHS = {
    "short":  ("~2 minutes",  "15–25 lines"),
    "medium": ("~5 minutes",  "40–60 lines"),
    "long":   ("~10 minutes", "80–120 lines"),
}

# Maximum allowed characters in a speaker name (guards against mis-parsed lines).
_MAX_SPEAKER_NAME_LEN = 50

_STORY_PROMPT_TEMPLATE = """You are a professional storyteller.

Write a complete story in the following STRICT format:

Speaker: text

Rules:
- Use "Narrator" for narration.
- Every line must start with a speaker name followed by a colon.
- Do NOT use quotes around dialogue.
- Do NOT include explanations or formatting outside the story.
- Do NOT summarize.
- Keep all storytelling rich and detailed.
- Each line should be a natural spoken segment.
- No multi-line segments.

Characters:
{character_list}

Story type: {genre}
Tone: {tone}
Length: approximately {length_desc} ({length_lines})

Output ONLY the story, nothing else."""


def _parse_story_format(text: str) -> list:
    """Parse Speaker: text format into list of segment dicts.

    Splits on the FIRST colon only so that content such as
    "Narrator: The time was 10:30 AM" is correctly handled –
    speaker = "Narrator", text = "The time was 10:30 AM".
    """
    segments = []
    for line in text.splitlines():
        line = line.strip()
        if not line or ":" not in line:
            continue
        speaker, content = line.split(":", 1)
        speaker = speaker.strip()
        content = content.strip()
        # Validate: speaker must be a simple word/name (not a URL, timestamp, etc.)
        if (
            speaker
            and content
            and len(speaker) <= _MAX_SPEAKER_NAME_LEN
            and not _re.search(r'[/\\<>]', speaker)
        ):
            segments.append({"speaker": speaker, "text": content})
    return segments


@app.post("/api/story/generate")
async def story_generate(request: Request):
    """Generate a structured story using the configured LLM."""
    data = await request.json()
    genre = data.get("genre", "fantasy")
    tone = data.get("tone", "epic")
    length = data.get("length", "short")
    custom_prompt = data.get("custom_prompt", "")
    characters = data.get("characters", [])

    # Build character list string
    if characters:
        char_lines = []
        for c in characters:
            name = str(c.get("name", "")).strip()
            traits = str(c.get("traits", "")).strip()
            if name:
                char_lines.append(f"- {name}" + (f" ({traits})" if traits else ""))
        character_list = "\n".join(char_lines) if char_lines else "Auto-generate interesting characters"
    else:
        character_list = "Auto-generate 2–3 interesting characters with distinct personalities"

    length_desc, length_lines = _STORY_LENGTHS.get(length, _STORY_LENGTHS["short"])

    # Handle custom prompt by appending it to the genre description
    genre_str = custom_prompt.strip() if genre == "custom" and custom_prompt else genre

    prompt = _STORY_PROMPT_TEMPLATE.format(
        character_list=character_list,
        genre=genre_str,
        tone=tone,
        length_desc=length_desc,
        length_lines=length_lines,
    )

    try:
        story_text = await asyncio.to_thread(_llm_generate_audiobook, prompt)
    except Exception as e:
        return JSONResponse({"success": False, "error": str(e)}, status_code=500)

    if not story_text or not story_text.strip():
        return JSONResponse({"success": False, "error": "LLM returned an empty story. Check your LLM provider settings."}, status_code=500)

    segments = _parse_story_format(story_text)
    if not segments:
        return JSONResponse({"success": False, "error": "LLM output could not be parsed. Ensure the LLM is connected and responding correctly."}, status_code=500)

    return {"success": True, "story": story_text, "segments": segments}


@app.post("/api/story/parse")
async def story_parse(request: Request):
    """Parse a story text (Speaker: text format) and detect speakers with voice suggestions."""
    data = await request.json()
    text = data.get("text", "")

    segments = _parse_story_format(text)

    speakers: dict = {}
    for seg in segments:
        sp = seg.get("speaker")
        if not sp:
            continue
        if sp not in speakers:
            speakers[sp] = {
                "name": sp,
                "gender": _detect_gender(sp),
                "segment_count": 1,
            }
        else:
            speakers[sp]["segment_count"] += 1

    avail = list(shared.custom_voices.keys())
    for sp, info in speakers.items():
        match = next(
            (v for v in avail if sp.lower() in v.lower() or v.lower() in sp.lower()),
            None,
        )
        if match:
            info["suggested_voice"] = match
        else:
            info["suggested_voice"] = next(
                (v for v in avail if info["gender"] in v.lower()),
                avail[0] if avail else None,
            )

    return {"success": True, "segments": segments, "speakers": speakers, "available_voices": avail}


# ============== LLAMACPP ENDPOINTS ==============
@app.get("/api/llamacpp/server/status")
async def llamacpp_status():
    """Get llama.cpp server status"""
    server_dir = Path(shared.BASE_DIR) / 'models' / 'server'
    binary = None
    for n in ["llama-server.exe", "llama-server", "llama.exe", "llama"]:
        if (server_dir / n).exists():
            binary = n
            break
    
    cuda_available = False
    try:
        import subprocess as sp
        result = sp.run(["nvidia-smi", "--query-gpu=name", "--format=csv,noheader"], capture_output=True, text=True, timeout=5)
        cuda_available = result.returncode == 0 and result.stdout.strip() != ""
        gpu_name = result.stdout.strip() if cuda_available else None
    except:
        gpu_name = None
    
    # Check if server is actually running by trying to connect
    server_running = False
    try:
        import requests
        resp = requests.get("http://localhost:8080/v1/models", timeout=2)
        server_running = resp.status_code == 200
    except:
        pass
    
    return {
        "success": True, 
        "server_dir": str(server_dir), 
        "binary_found": bool(binary), 
        "binary_name": binary,
        "cuda_available": cuda_available,
        "gpu_name": gpu_name,
        "running": server_running
    }

@app.post("/api/llamacpp/server/start")
async def llamacpp_start(request: Request):
    """Start llama.cpp server"""
    data = await request.json()
    model = data.get('model', '')
    if not model:
        return JSONResponse({"success": False, "error": "Model required"}, status_code=400)
    
    server_dir = Path(shared.BASE_DIR) / 'models' / 'server'
    binary = None
    for n in ["llama-server.exe", "llama-server", "llama.exe", "llama"]:
        if (server_dir / n).exists():
            binary = n
            break
    if not binary:
        return JSONResponse({"success": False, "error": "Binary not found"}, status_code=400)
    
    m_path = model if _os.path.isabs(model) else None
    if not m_path:
        for p in [Path(shared.BASE_DIR) / 'models' / 'llm' / model, server_dir / model]:
            if p.exists():
                m_path = str(p)
                break
    
    if not m_path:
        return JSONResponse({"success": False, "error": "Model file not found"}, status_code=400)
    
    try:
        port = 8080
        try: 
            port = int(shared.load_settings().get('llamacpp', {}).get('base_url', '').split(':')[-1])
        except: pass
        
        import subprocess as sp
        # Use higher GPU layers for better performance (99 = use all available)
        cmd = [
            str(server_dir / binary), "-m", m_path, 
            "-c", "4096", 
            "-ngl", "99", 
            "--host", "0.0.0.0", 
            "--port", str(port),
            "--log-disable"
        ]
        
        proc = sp.Popen(
            cmd,
            cwd=str(server_dir), 
            stdout=sp.PIPE, 
            stderr=sp.STDOUT,
            text=True,
            bufsize=1
        )
        
        # Start thread to read and log server output to file
        import logging
        import threading
        
        log_file = Path(shared.BASE_DIR) / "logs" / "llama-server.log"
        log_file.parent.mkdir(parents=True, exist_ok=True)
        
        def log_server_output():
            try:
                with open(log_file, "w") as f:
                    f.write(f"=== Server started at {time.strftime('%Y-%m-%d %H:%M:%S')} ===\n")
                    f.flush()
                    for line in iter(proc.stdout.readline, ''):
                        if line:
                            msg = line.rstrip()
                            print(f"[LLAMA-SERVER] {msg}")
                            f.write(msg + "\n")
                            f.flush()
            except Exception as e:
                print(f"[LLAMA-SERVER] Log error: {e}")
        
        threading.Thread(target=log_server_output, daemon=True).start()
        
        return {"success": True, "message": f"Started on port {port}", "pid": proc.pid}
    except Exception as e:
        return JSONResponse({"success": False, "error": str(e)}, status_code=500)

@app.post("/api/llamacpp/server/stop")
async def llamacpp_stop():
    """Stop llama.cpp server"""
    try:
        import subprocess as sp
        port = 8080
        try: 
            port = int(shared.load_settings().get('llamacpp', {}).get('base_url', '').split(':')[-1])
        except: pass
        return {"success": True, "message": f"Stopped port {port}"}
    except Exception as e:
        return JSONResponse({"success": False, "error": str(e)}, status_code=500)

@app.post("/api/llamacpp/server/download")
async def llamacpp_download(request: Request):
    """Download and install llama.cpp server binary"""
    import uuid

    from app.llamacpp_installer import get_installer
    
    data = await request.json()
    release_id = data.get('release_id', 'default')
    
    download_id = str(uuid.uuid4())[:8]
    
    async def progress_callback(status):
        shared.llamacpp_server_downloads[download_id] = {
            "id": download_id,
            "status": status.get("type", "downloading"),
            "progress": status.get("progress", 0),
            "message": status.get("message", "")
        }
    
    try:
        installer = get_installer()
        
        result = installer.download_and_extract_server(progress_callback=progress_callback)
        
        if result.get("success"):
            shared.llamacpp_server_downloads[download_id] = {
                "id": download_id,
                "status": "completed",
                "progress": 100,
                "message": "Download and extraction complete"
            }
        else:
            shared.llamacpp_server_downloads[download_id] = {
                "id": download_id,
                "status": "error",
                "error": result.get("error", "Unknown error")
            }
        
        return {"success": result.get("success", False), "download_id": download_id, "message": result.get("message", result.get("error", ""))}
    except Exception as e:
        shared.llamacpp_server_downloads[download_id] = {
            "id": download_id,
            "status": "error",
            "error": str(e)
        }
        return JSONResponse({"success": False, "error": str(e)}, status_code=500)

@app.get("/api/llamacpp/server/download/status")
async def llamacpp_download_status(id: str = None):
    """Get download status"""
    if not id:
        return JSONResponse({"success": False, "error": "Download ID required"}, status_code=400)
    
    download = shared.llamacpp_server_downloads.get(id)
    if not download:
        return JSONResponse({"success": False, "error": "Download not found"}, status_code=404)
    
    return {"success": True, "download": download}

@app.post("/api/llamacpp/server/download/stop")
async def llamacpp_download_stop():
    """Stop current download (placeholder)"""
    return {"success": True, "message": "Download cancellation not implemented"}


# ============== SERVICES ENDPOINTS ==============
@app.get("/api/services/status")
async def services_status():
    """Get services status"""
    import requests
    tts_r, stt_r = False, False
    try: 
        tts_r = requests.get(f"{shared.TTS_BASE_URL}/health", timeout=2).status_code == 200
    except: 
        pass
    try: 
        stt_r = requests.get(f"{shared.STT_BASE_URL}/health", timeout=2).status_code == 200
    except: 
        pass
    
    return {"success": True, "tts": {"running": tts_r}, "stt": {"running": stt_r}}

@app.get("/api/services/xtts/logs")
async def get_xtts_logs():
    """Get XTTS service logs"""
    import requests
    logs = []
    try:
        # Try Flask first
        response = requests.get(f"http://127.0.0.1:5001/api/services/xtts/logs", timeout=5)
        if response.ok:
            data = response.json()
            if data.get("logs"):
                return data
    except:
        pass
    
    # Check service directly
    try:
        resp = requests.get(f"{shared.TTS_BASE_URL}/health", timeout=2)
        if resp.status_code == 200:
            logs.append(f"[TTS] Service running on {shared.TTS_BASE_URL}")
    except Exception as e:
        logs.append(f"[TTS] Service not running: {e}")
    
    return {"success": True, "logs": logs}

@app.get("/api/services/stt/logs")
async def get_stt_logs():
    """Get STT service logs"""
    import requests
    logs = []
    try:
        # Try Flask first
        response = requests.get(f"http://127.0.0.1:5001/api/services/stt/logs", timeout=5)
        if response.ok:
            data = response.json()
            if data.get("logs"):
                return data
    except:
        pass
    
    # Check service directly
    try:
        resp = requests.get(f"{shared.STT_BASE_URL}/health", timeout=2)
        if resp.status_code == 200:
            logs.append(f"[STT] Service running on {shared.STT_BASE_URL}")
    except Exception as e:
        logs.append(f"[STT] Service not running: {e}")
    
    return {"success": True, "logs": logs}


# ============== MODELS ENDPOINTS ==============
@app.get("/api/models")
async def get_models():
    """Get available models"""
    provider = shared.get_provider()
    if not provider:
        return JSONResponse({"success": False, "error": "Provider not available"}, status_code=500)
    
    try:
        models = provider.get_models()
        models_data = [{
            "id": m.id,
            "name": m.name,
            "provider": m.provider,
            "context_length": m.context_length,
            "description": m.description
        } for m in models]
        return {"success": True, "models": models_data, "provider": provider.provider_name}
    except Exception as e:
        return JSONResponse({"success": False, "error": str(e)}, status_code=500)


@app.get("/api/llm/models")
async def get_llm_models():
    """Get available local LLM models (for llama.cpp)"""
    import os
    models = []
    llm_dir = os.path.join(shared.BASE_DIR, 'models', 'llm')
    if os.path.exists(llm_dir):
        for f in os.listdir(llm_dir):
            if f.lower().endswith('.gguf'):
                size = os.path.getsize(os.path.join(llm_dir, f))
                models.append({"name": f, "size": size, "size_formatted": shared.format_size(size)})
    return {"success": True, "models": models}


@app.delete("/api/llm/models/{filename}")
async def delete_llm_model(filename):
    """Delete a local LLM model file"""
    import os

    # URL decode the filename
    from urllib.parse import unquote
    filename = unquote(filename)
    p = os.path.join(shared.BASE_DIR, 'models', 'llm', filename)
    if os.path.exists(p):
        os.remove(p)
        return {"success": True}
    return JSONResponse({"success": False, "error": "File not found"}, status_code=404)


# ============== HTTP FALLBACK ENDPOINTS ==============
@app.post("/api/chat/stream")
async def chat_stream(request: Request):
    """Streaming chat endpoint (HTTP fallback for Flask compatibility)."""
    import asyncio
    import json

    from fastapi.responses import StreamingResponse
    
    data = await request.json()
    user_message = data.get('message', '')
    session_id = data.get('session_id', 'default')
    model = data.get('model')
    system_prompt = data.get('system_prompt', '')
    speaker = data.get('speaker', 'default')
    
    # Reload provider from settings on each request to pick up changes
    provider = shared.get_provider()
    if not provider:
        return JSONResponse({"success": False, "error": "Provider not available"}, status_code=500)
    
    if not provider.supports_streaming():
        return JSONResponse({"success": False, "error": "Provider does not support streaming"}, status_code=400)
    
    try:
        messages = []
        if session_id in shared.sessions_data:
            raw_messages = shared.sessions_data[session_id].get('messages', [])
            for msg in raw_messages:
                if isinstance(msg, dict):
                    messages.append(ChatMessage(role=msg.get('role', 'user'), content=msg.get('content', '')))
                elif hasattr(msg, 'role') and hasattr(msg, 'content'):
                    messages.append(msg)
        
        if system_prompt:
            messages.insert(0, ChatMessage(role="system", content=system_prompt))
        
        messages.append(ChatMessage(role="user", content=user_message))
        
        async def generate():
            try:
                ai_message = ""
                thinking = ""
                
                # Run the blocking stream generator in a thread pool to avoid blocking the event loop
                loop = asyncio.get_event_loop()
                
                # Use async iteration pattern for non-blocking streaming
                def get_chunks():
                    return provider.chat_completion(
                        messages=messages,
                        model=model or provider.config.model,
                        stream=True
                    )
                
                # Run in executor to prevent blocking
                stream_generator = await loop.run_in_executor(None, get_chunks)
                
                for response_chunk in stream_generator:
                    if response_chunk.content:
                        ai_message += response_chunk.content
                        yield f"data: {json.dumps({'type': 'content', 'content': response_chunk.content})}\n\n"
                    
                    if response_chunk.thinking or response_chunk.reasoning:
                        thinking += response_chunk.thinking or response_chunk.reasoning
                
                if session_id in shared.sessions_data:
                    # Save user message
                    shared.sessions_data[session_id]['messages'].append({
                        "role": "user",
                        "content": user_message
                    })
                    # Save assistant message
                    shared.sessions_data[session_id]['messages'].append({
                        "role": "assistant",
                        "content": ai_message,
                        "thinking": thinking
                    })
                    shared.save_sessions(shared.sessions_data)
                
                yield f"data: {json.dumps({'type': 'done', 'thinking': thinking, 'session_id': session_id})}\n\n"
                
            except Exception as e:
                yield f"data: {json.dumps({'type': 'error', 'error': str(e)})}\n\n"
        
        return StreamingResponse(generate(), media_type="text/event-stream")
    
    except Exception as e:
        return JSONResponse({"success": False, "error": str(e)}, status_code=500)
@app.post("/api/conversation/greeting")
async def greeting(request: Request):
    """HTTP fallback for greeting"""
    if not tts_provider:
        return JSONResponse({"success": False, "error": "No TTS"})
    
    try:
        data = await request.json()
        speaker = data.get('speaker', 'default')
        greeting_text = "Hello! I'm listening. How can I help you today?"
        
        if hasattr(tts_provider, 'generate_tts'):
            result = tts_provider.generate_tts(text=greeting_text, speaker=speaker, language="en")
        else:
            result = tts_provider.generate_audio(text=greeting_text, speaker=speaker, language="en")
        
        if result and result.get('success'):
            return {
                "success": True,
                "text": greeting_text,
                "audio": result.get('audio', ''),
                "sample_rate": result.get('sample_rate', 24000)
            }
    except Exception as e:
        return JSONResponse({"success": False, "error": str(e)})


# ============== TTS ENDPOINTS ==============
def resolve_speaker_tts(data: dict):
    """Resolve speaker and language from request data."""
    speaker = data.get('speaker', 'default')
    language = data.get('language', 'en')
    
    if not speaker or speaker.lower() == 'default':
        speaker = 'default'
    
    return speaker, language


@app.post("/api/stt/float32")
async def stt_float32(request: Request):
    """STT endpoint for Float32 audio - proxies to STT service."""
    try:
        content_type = request.headers.get('content-type', '')
        
        audio_bytes = None
        sample_rate = request.headers.get('X-Sample-Rate', '24000')
        
        if 'multipart/form-data' in content_type:
            form = await request.form()
            file = form.get('file')
            if file:
                audio_bytes = await file.read()
        else:
            audio_bytes = await request.body()
        
        if not audio_bytes:
            return JSONResponse({"detail": "No audio data provided"}, status_code=400)
        
        # Convert raw Float32 PCM bytes to WAV so the STT service accepts it
        import io
        import wave
        float32_data = np.frombuffer(audio_bytes, dtype=np.float32)
        int16_data = (np.clip(float32_data, -1.0, 1.0) * 32767).astype(np.int16)
        wav_buf = io.BytesIO()
        with wave.open(wav_buf, 'wb') as wf:
            wf.setnchannels(1)
            wf.setsampwidth(2)
            wf.setframerate(int(sample_rate))
            wf.writeframes(int16_data.tobytes())
        wav_bytes = wav_buf.getvalue()

        # Forward to STT service as multipart — the STT service requires a 'file' field
        stt_url = f"{shared.STT_BASE_URL}/transcribe"
        response = requests.post(
            stt_url,
            files={'file': ('audio.wav', wav_bytes, 'audio/wav')},
            data={'sample_rate': sample_rate},
            timeout=30
        )
        
        if response.status_code == 200:
            stt_data = response.json()
            # Normalize response: ensure top-level 'text' field exists
            if 'text' not in stt_data or not stt_data.get('text'):
                segments = stt_data.get('segments', [])
                if segments:
                    # segments may be dicts with 'text' or Hypothesis-like objects
                    texts = []
                    for seg in segments:
                        if isinstance(seg, dict):
                            texts.append(seg.get('text', ''))
                        elif isinstance(seg, str):
                            texts.append(seg)
                    combined = ' '.join(t for t in texts if t).strip()
                    stt_data['text'] = combined
            return JSONResponse(stt_data)
        else:
            return JSONResponse({
                "detail": f"STT service error: {response.status_code}",
                "stt_response": response.text[:500] if response.text else "Empty response"
            }, status_code=response.status_code)
    except requests.exceptions.ConnectionError as e:
        return JSONResponse({"detail": f"STT service unavailable at {shared.STT_BASE_URL}: {str(e)}"}, status_code=503)
    except Exception as e:
        return JSONResponse({"detail": str(e)}, status_code=500)


@app.post("/api/stt")
async def stt_endpoint(request: Request):
    """Standard STT endpoint for file uploads."""
    try:
        # Handle multipart form data
        form = await request.form()
        audio_file = form.get('audio')
        
        if not audio_file:
            return JSONResponse({"detail": "No audio file provided"}, status_code=400)
        
        audio_bytes = await audio_file.read()
        
        # Forward to STT service
        stt_url = f"{shared.STT_BASE_URL}/transcribe"
        files = {'audio': (audio_file.filename, audio_bytes, audio_file.content_type)}
        response = requests.post(stt_url, files=files, timeout=30)
        
        if response.status_code == 200:
            return response.json()
        else:
            return JSONResponse({"detail": f"STT service error: {response.status_code}"}, status_code=response.status_code)
    except Exception as e:
        return JSONResponse({"detail": str(e)}, status_code=500)


@app.post("/api/tts")
async def tts_endpoint(request: Request):
    """Standard TTS endpoint - returns complete audio."""
    if not tts_provider:
        return JSONResponse({"success": False, "error": "No TTS provider available"}, status_code=500)
    
    try:
        data = await request.json()
        text = shared.remove_emojis(data.get('text', ''))
        if not text:
            return JSONResponse({"success": False, "error": "Text required"}, status_code=400)
        
        final_speaker, language = resolve_speaker_tts(data)
        
        if hasattr(tts_provider, 'generate_tts'):
            result = tts_provider.generate_tts(text=text, speaker=final_speaker, language=language)
        elif hasattr(tts_provider, 'generate_audio'):
            result = tts_provider.generate_audio(text=text, speaker=final_speaker, language=language)
        else:
            return JSONResponse({"success": False, "error": "Provider missing TTS method"}, status_code=500)
        
        if result and result.get('success'):
            return {
                "success": True,
                "audio": result.get('audio', ''),
                "sample_rate": result.get('sample_rate', 24000)
            }
        else:
            return JSONResponse({"success": False, "error": result.get('error', 'TTS failed')}, status_code=500)
            
    except Exception as e:
        return JSONResponse({"success": False, "error": str(e)}, status_code=500)


@app.post("/api/tts/stream")
async def tts_stream_endpoint(request: Request):
    """Streaming TTS endpoint."""
    if not tts_provider:
        return JSONResponse({"success": False, "error": "No TTS provider available"}, status_code=500)
    
    try:
        data = await request.json()
        text = shared.remove_emojis(data.get('text', ''))
        if not text:
            return JSONResponse({"success": False, "error": "Text required"}, status_code=400)
        
        final_speaker, language = resolve_speaker_tts(data)
        
        if not hasattr(tts_provider, 'generate_audio_stream'):
            return JSONResponse({"success": False, "error": "Provider doesn't support streaming"}, status_code=500)
        
        import io

        from fastapi.responses import StreamingResponse
        
        async def generate():
            try:
                for audio_chunk, sr, timing in tts_provider.generate_audio_stream(
                    text=text,
                    speaker=final_speaker,
                    language=language,
                    chunk_size=12,
                    temperature=0.9,
                    top_k=50,
                    repetition_penalty=1.05,
                    top_p=0.95,
                    append_silence=False,
                    max_new_tokens=1024
                ):
                    if audio_chunk is not None and len(audio_chunk) > 0:
                        pcm_int16 = (audio_chunk * 32767).astype(np.int16).tobytes()
                        yield pcm_int16
            except Exception as e:
                print(f"[TTS STREAM] Error: {e}")
        
        return StreamingResponse(generate(), media_type="audio/wav")
    
    except Exception as e:
        return JSONResponse({"success": False, "error": str(e)}, status_code=500)


@app.post("/api/tts/stream/server-sent-events")
async def tts_stream_sse_endpoint(request: Request):
    """SSE streaming TTS endpoint."""
    import asyncio

    from fastapi.responses import StreamingResponse
    
    print(f"[TTS SSE] Request received")
    
    if not tts_provider:
        print(f"[TTS SSE] No TTS provider")
        return JSONResponse({"success": False, "error": "No TTS provider available"}, status_code=500)
    
    try:
        content_type = request.headers.get('content-type', '')
        
        if 'application/json' in content_type:
            data = await request.json()
        elif 'multipart/form-data' in content_type or 'application/x-www-form-urlencoded' in content_type:
            form = await request.form()
            data = {}
            for key, value in form.items():
                if hasattr(value, 'file'):
                    data[key] = value
                else:
                    data[key] = value
        else:
            try:
                body = await request.body()
                import json as json_module
                data = json_module.loads(body)
            except:
                data = {}
        
        text = data.get('text', '')
        if isinstance(text, list):
            text = ' '.join(text)
        text = shared.remove_emojis(str(text))
        print(f"[TTS SSE] Text: {text[:50]}...")
        
        if not text:
            return JSONResponse({"success": False, "error": "Text required"}, status_code=400)
        
        final_speaker = data.get('speaker', 'default')
        language = data.get('language', 'en')
        
        if not final_speaker or final_speaker.lower() == 'default':
            final_speaker = 'default'
        
        print(f"[TTS SSE] Speaker: {final_speaker}, Language: {language}")
        
        if not hasattr(tts_provider, 'generate_audio_stream'):
            print(f"[TTS SSE] No generate_audio_stream method")
            return JSONResponse({"success": False, "error": "Provider doesn't support streaming"}, status_code=500)
        
        def generate_tts():
            try:
                print(f"[TTS SSE] Starting generation")
                for audio_chunk, sr, timing in tts_provider.generate_audio_stream(
                    text=text,
                    speaker=final_speaker,
                    language=language,
                    chunk_size=12,
                    temperature=0.9,
                    top_k=50,
                    repetition_penalty=1.05,
                    top_p=0.95,
                    append_silence=False,
                    max_new_tokens=1024
                ):
                    if audio_chunk is not None and len(audio_chunk) > 0:
                        pcm_int16 = (audio_chunk * 32767).astype(np.int16)
                        audio_b64 = base64.b64encode(pcm_int16.tobytes()).decode('utf-8')
                        yield f"data: {json.dumps({'type': 'chunk', 'audio_b64': audio_b64, 'sample_rate': sr})}\n\n"
                print(f"[TTS SSE] Generation complete")
            except Exception as e:
                print(f"[TTS SSE] Generation error: {e}")
                yield f"data: {json.dumps({'type': 'error', 'error': str(e)})}\n\n"
        
        async def generate():
            try:
                loop = asyncio.get_event_loop()
                for chunk in await loop.run_in_executor(None, generate_tts):
                    yield chunk
                yield f"data: {json.dumps({'type': 'done'})}\n\n"
            except Exception as e:
                print(f"[TTS SSE] Async error: {e}")
                yield f"data: {json.dumps({'type': 'error', 'error': str(e)})}\n\n"
        
        return StreamingResponse(generate(), media_type="text/event-stream")
    
    except Exception as e:
        print(f"[TTS SSE] Outer error: {e}")
        return JSONResponse({"success": False, "error": str(e)}, status_code=500)


@app.post("/api/tts/stream/cancel")
async def tts_stream_cancel():
    """Cancel ongoing TTS stream."""
    # This is a simple endpoint - actual cancellation is handled client-side via AbortController
    # The server doesn't keep track of streams, so we just return success
    return {"success": True, "message": "TTS stream cancellation requested"}


# ============== STANDALONE TTS WEBSOCKET ==============
#
# /ws/tts — a dedicated WebSocket endpoint that accepts individual text
# chunks and streams back int16 PCM audio at 24 kHz.  This gives the
# VoiceEngine real-time streaming with sub-second first-chunk latency
# instead of the 2-4 s round-trip of the batch HTTP /api/tts endpoint.
#
# Protocol:
#   Client → Server  (JSON):
#     {"text": "Hello", "voice": "default"}   — synthesise text
#     {"type": "cancel"}                       — abort current generation
#
#   Server → Client:
#     {"type": "start"}                        — first audio about to arrive
#     binary frame  (int16 PCM @ 24 kHz)       — audio data
#     {"type": "done"}                         — generation complete
#     {"type": "error", "error": "..."}        — on failure
#     {"type": "ready"}                        — sent once after connection

# Semaphore limits concurrent /ws/tts generations (protects GPU)
_ws_tts_semaphore = threading.Semaphore(2)


def _generate_ws_tts(text: str, speaker: str, ws: WebSocket,
                     loop: asyncio.AbstractEventLoop, abort_flag: list):
    """Synchronous TTS generator — runs in a worker thread.

    Streams int16 PCM frames to the WebSocket via ``run_coroutine_threadsafe``.
    """
    if not tts_provider or not hasattr(tts_provider, 'generate_audio_stream'):
        err = "TTS streaming not supported by current provider" if tts_provider else "No TTS provider loaded"
        asyncio.run_coroutine_threadsafe(
            ws.send_json({"type": "error", "error": err}),
            loop,
        ).result()
        return

    first_sent = False
    frames_sent = 0
    buffer = np.array([], dtype=np.float32)
    buffer_chunks: list = []
    prev_audio = None
    start_time = time.time()

    try:
        for audio_chunk, sr, timing in tts_provider.generate_audio_stream(
            text=text,
            speaker=speaker,
            language="English",
            chunk_size=TTS_CHUNK_SIZE,
            non_streaming_mode=False,
            temperature=0.6,
            top_k=20,
            top_p=0.85,
            repetition_penalty=1.0,
            append_silence=False,
            max_new_tokens=180,
        ):
            if abort_flag[0]:
                break

            if audio_chunk is None or len(audio_chunk) == 0:
                continue

            audio = np.asarray(audio_chunk, dtype=np.float32)
            if audio.ndim > 1:
                audio = audio.mean(axis=1)

            # DC offset correction
            if len(audio) > 128:
                mean = np.mean(audio)
                if abs(mean) > 1e-4:
                    audio = audio - mean

            # Fade-in/out on the very first chunk
            if prev_audio is None:
                audio = apply_fade(audio, fade_samples=128)

            # Cross-fade stitching with previous tail
            if prev_audio is not None:
                offset = find_best_offset(prev_audio, audio)
                if offset > 0:
                    audio = audio[offset:]
                overlap = min(len(prev_audio), len(audio), XFADE_SAMPLES)
                if overlap > 0:
                    t = np.linspace(0.0, 1.0, overlap, dtype=np.float32)
                    fade_in = 0.5 * (1.0 - np.cos(np.pi * t))
                    fade_out = 1.0 - fade_in
                    audio[:overlap] = (
                        prev_audio[-overlap:] * fade_out + audio[:overlap] * fade_in
                    )

            # Soft-limit after crossfade
            audio = soft_clip(audio * TTS_GAIN)

            # Hold back tail for next crossfade
            if len(audio) > XFADE_SAMPLES:
                prev_audio = audio[-XFADE_SAMPLES:].copy()
                audio = audio[:-XFADE_SAMPLES]
            else:
                prev_audio = audio.copy()
                audio = np.array([], dtype=np.float32)

            if len(audio) > 0:
                buffer_chunks.append(audio)

            # Flatten accumulated chunks
            if buffer_chunks:
                if len(buffer) > 0:
                    buffer_chunks.insert(0, buffer)
                buffer = np.concatenate(buffer_chunks)
                buffer_chunks.clear()

            # Send fixed-size frames for smooth playback
            while len(buffer) >= FRAME_SIZE:
                frame = buffer[:FRAME_SIZE]
                buffer = buffer[FRAME_SIZE:]

                if not first_sent:
                    elapsed = (time.time() - start_time) * 1000
                    asyncio.run_coroutine_threadsafe(
                        ws.send_json({"type": "start"}), loop
                    ).result()
                    first_sent = True
                    print(f"[WS-TTS] First chunk in {elapsed:.0f}ms for '{text[:25]}...'")

                # Convert float32 → int16 PCM and send as binary
                pcm = (np.clip(frame, -1.0, 1.0) * 32767).astype(np.int16)
                asyncio.run_coroutine_threadsafe(
                    ws.send_bytes(pcm.tobytes()), loop
                ).result()
                frames_sent += 1

        # Flush crossfade tail + remaining buffer
        if prev_audio is not None and len(prev_audio) > 0:
            buffer_chunks.append(prev_audio)
        if buffer_chunks:
            if len(buffer) > 0:
                buffer_chunks.insert(0, buffer)
            buffer = np.concatenate(buffer_chunks)
            buffer_chunks.clear()

        if len(buffer) > 0:
            fade_len = min(len(buffer), 256)
            fade = np.linspace(1.0, 0.0, fade_len, dtype=np.float32)
            buffer[-fade_len:] *= fade
            if len(buffer) < FRAME_SIZE:
                buffer = np.pad(buffer, (0, FRAME_SIZE - len(buffer)))
            pcm = (np.clip(buffer, -1.0, 1.0) * 32767).astype(np.int16)
            asyncio.run_coroutine_threadsafe(
                ws.send_bytes(pcm.tobytes()), loop
            ).result()
            frames_sent += 1

    except Exception as e:
        print(f"[WS-TTS] Generation error: {e}")
        try:
            asyncio.run_coroutine_threadsafe(
                ws.send_json({"type": "error", "error": str(e)}), loop
            ).result()
        except Exception:
            pass
    finally:
        elapsed_total = (time.time() - start_time) * 1000
        print(f"[WS-TTS] Done '{text[:25]}...': frames={frames_sent}, time={elapsed_total:.0f}ms")
        try:
            asyncio.run_coroutine_threadsafe(
                ws.send_json({"type": "done"}), loop
            ).result()
        except Exception:
            pass


@app.websocket("/ws/tts")
async def websocket_tts(websocket: WebSocket):
    """Standalone TTS WebSocket — send text, receive streaming PCM audio."""
    await websocket.accept()
    loop = asyncio.get_event_loop()
    abort_flag = [False]

    try:
        await websocket.send_json({"type": "ready"})

        while True:
            try:
                raw = await asyncio.wait_for(websocket.receive_text(), timeout=60.0)
            except asyncio.TimeoutError:
                continue

            try:
                msg = json.loads(raw)
            except json.JSONDecodeError:
                await websocket.send_json({"type": "error", "error": "Invalid JSON"})
                continue

            # Cancel in-flight generation
            if msg.get("type") == "cancel":
                abort_flag[0] = True
                continue

            text = msg.get("text", "").strip()
            voice = msg.get("voice", "default")
            if not text:
                await websocket.send_json({"type": "done"})
                continue

            # Reset abort flag for the new request
            abort_flag[0] = False

            # Run TTS generation in a thread so we don't block the event loop
            acquired = _ws_tts_semaphore.acquire(timeout=5)
            if not acquired:
                await websocket.send_json({"type": "error", "error": "TTS busy"})
                continue

            try:
                await asyncio.get_event_loop().run_in_executor(
                    executor,
                    _generate_ws_tts,
                    text, voice, websocket, loop, abort_flag,
                )
            finally:
                _ws_tts_semaphore.release()

    except WebSocketDisconnect:
        print("[WS-TTS] Client disconnected")
    except Exception as e:
        print(f"[WS-TTS] Error: {e}")
        try:
            await websocket.send_json({"type": "error", "error": str(e)})
        except Exception:
            pass


# ============== AUDIOBOOK WEBSOCKET ==============

# Semaphore allows up to 2 concurrent TTS generations (instead of a single Lock)
_audiobook_tts_semaphore = threading.Semaphore(2)

AUDIOBOOK_FRAME_SIZE = 2400  # 100ms at 24kHz


def _generate_audiobook_tts_pcm(text: str, speaker: str = "default",
                                 language: str = "en"):
    """Yield raw PCM int16 bytes for *text*.

    CRITICAL contract:
      - NO base64
      - NO WAV header
      - RAW PCM int16 bytes ONLY
      - Consistent sample rate (24000)
    """
    provider = shared.get_tts_provider()
    if not provider:
        return

    with _audiobook_tts_semaphore:
        if hasattr(provider, 'generate_audio_stream'):
            buffer = np.array([], dtype=np.float32)

            for audio_chunk, sample_rate, _ in provider.generate_audio_stream(
                text=text,
                speaker=speaker,
                language=language,
                chunk_size=1024,
            ):
                if audio_chunk is None or len(audio_chunk) == 0:
                    continue

                audio = np.asarray(audio_chunk, dtype=np.float32)
                if audio.ndim > 1:
                    audio = audio.mean(axis=1)

                audio = np.clip(audio * 0.85, -1.0, 1.0)
                buffer = np.concatenate([buffer, audio])

                # Emit fixed-size frames
                while len(buffer) >= AUDIOBOOK_FRAME_SIZE:
                    frame = buffer[:AUDIOBOOK_FRAME_SIZE]
                    buffer = buffer[AUDIOBOOK_FRAME_SIZE:]
                    pcm_int16 = (frame * 32767).astype(np.int16).tobytes()
                    yield pcm_int16

            # Flush remainder with fade-out to prevent click at boundary
            if len(buffer) > 0:
                fade_len = min(len(buffer), 256)
                fade = np.linspace(1.0, 0.0, fade_len, dtype=np.float32)
                buffer[-fade_len:] *= fade
                if len(buffer) < AUDIOBOOK_FRAME_SIZE:
                    buffer = np.pad(buffer, (0, AUDIOBOOK_FRAME_SIZE - len(buffer)))
                pcm_int16 = (buffer * 32767).astype(np.int16).tobytes()
                yield pcm_int16

        else:
            # Fallback: batch generation → single PCM blob
            if hasattr(provider, 'generate_tts'):
                result = provider.generate_tts(text=text, speaker=speaker, language=language)
            elif hasattr(provider, 'generate_audio'):
                result = provider.generate_audio(text=text, speaker=speaker, language=language)
            else:
                return

            if result and result.get('success'):
                raw = base64.b64decode(result.get('audio', ''))
                yield raw


def _split_into_paragraphs(text: str, max_chars: int = 500) -> list:
    """Split long text into manageable paragraphs for TTS streaming.

    Uses the existing ``chunk_text`` utility when available, otherwise
    falls back to simple paragraph splitting.
    """
    try:
        from audiobook.segmentation.chunk_text import chunk_text
        return chunk_text(text, max_chars=max_chars)
    except ImportError:
        # Simple fallback: split on blank lines, then hard-limit
        paragraphs = [p.strip() for p in text.split('\n\n') if p.strip()]
        if not paragraphs:
            paragraphs = [text]
        result = []
        for p in paragraphs:
            while len(p) > max_chars:
                split_at = p.rfind('. ', 0, max_chars)
                if split_at == -1:
                    split_at = max_chars
                else:
                    split_at += 1  # include the period
                result.append(p[:split_at].strip())
                p = p[split_at:].strip()
            if p:
                result.append(p)
        return result if result else [text]


MAX_SENTENCE_CHARS = 500  # Max chars per sentence before further splitting


def _split_into_sentences(text: str) -> list:
    """Split text into individual sentences for sentence-level TTS streaming.

    Each sentence becomes its own segment so that subtitle transitions
    happen at natural sentence boundaries rather than mid-sentence.
    Falls back to ``_split_into_paragraphs`` if import fails.
    """
    try:
        from audiobook.segmentation.chunk_text import split_sentences
        sentences = split_sentences(text)
        # Safety: if a single sentence is very long, further chunk it
        result = []
        for s in sentences:
            if len(s) > MAX_SENTENCE_CHARS:
                result.extend(_split_into_paragraphs(s, max_chars=MAX_SENTENCE_CHARS))
            else:
                result.append(s)
        return result if result else [text]
    except ImportError:
        return _split_into_paragraphs(text)


@app.websocket("/ws/audiobook")
async def websocket_audiobook(websocket: WebSocket):
    """WebSocket endpoint for audiobook TTS streaming.

    Protocol
    --------
    Client → Server  (JSON):
        {"type": "start", "segments": [...], "voice_mapping": {...},
         "default_voices": {...}, "job_id": "..."}
        *or*  {"type": "start", "text": "plain text"}
        {"type": "stop"}

    Server → Client  (JSON):
        {"type": "start"}
        {"type": "segment", "index": i, "text": "...", "speaker": "..."}
        {"type": "done", "job_id": "..."}
        {"type": "error", "message": "..."}

    Server → Client  (binary):
        Raw PCM int16 bytes at 24 000 Hz, mono
    """
    await websocket.accept()
    loop = asyncio.get_event_loop()

    try:
        while True:
            raw = await websocket.receive_text()
            if not raw:
                break

            data = json.loads(raw)
            msg_type = data.get("type", "")

            if msg_type == "stop":
                await websocket.send_json({"type": "stopped"})
                break

            if msg_type == "start":
                segments = data.get("segments")
                voice_mapping = data.get("voice_mapping", {})
                voice_map = data.get("voice_map", {})
                # Normalise keys so UI voice changes (lower-cased) always win
                merged_map = {
                    k.lower().strip(): v
                    for k, v in {**voice_mapping, **voice_map}.items()
                }
                default_voices = data.get("default_voices", {})
                plain_text = data.get("text")
                job_id = data.get("job_id", f"ws_{int(time.time())}")

                # Accumulate all PCM bytes so we can save the final WAV
                all_pcm_bytes: list = []

                # Pre-compute sentence-level segments so we can send
                # total_segments upfront for accurate progress.
                sentence_segments: list = []

                if segments:
                    for seg in segments:
                        speaker_name = seg.get("speaker", "Narrator")
                        seg_text = seg.get("text", "")
                        if not seg_text.strip():
                            continue

                        # Resolve voice (normalise speaker name for lookup)
                        v_name = merged_map.get(
                            speaker_name.lower().strip() if speaker_name else ''
                        )
                        if not v_name:
                            g = _detect_gender(speaker_name)
                            if g == "female":
                                v_name = default_voices.get("female")
                            elif g == "male":
                                v_name = default_voices.get("male")
                            else:
                                v_name = default_voices.get("narrator")

                        vid = (
                            shared.custom_voices.get(v_name, {}).get("voice_clone_id")
                            if v_name else None
                        )
                        final_speaker = vid if vid else (v_name or "default")

                        # Split into sentences for smooth transitions
                        sentences = _split_into_sentences(
                            shared.remove_emojis(seg_text)
                        )
                        for sent in sentences:
                            sentence_segments.append({
                                "text": sent,
                                "speaker": speaker_name,
                                "voice": final_speaker,
                            })

                elif plain_text:
                    sentences = _split_into_sentences(
                        shared.remove_emojis(plain_text)
                    )
                    for sent in sentences:
                        sentence_segments.append({
                            "text": sent,
                            "speaker": "Narrator",
                            "voice": "default",
                        })

                await websocket.send_json({
                    "type": "start",
                    "total_segments": len(sentence_segments),
                })

                # Generate TTS for each sentence-level segment
                for idx, ss in enumerate(sentence_segments):
                    await websocket.send_json({
                        "type": "segment",
                        "index": idx,
                        "text": ss["text"][:200],
                        "speaker": ss["speaker"],
                    })

                    def _gen_sentence(p=ss["text"], s=ss["voice"]):
                        return list(
                            _generate_audiobook_tts_pcm(p, speaker=s)
                        )

                    chunks = await loop.run_in_executor(
                        None, _gen_sentence
                    )
                    for chunk in chunks:
                        all_pcm_bytes.append(chunk)
                        await websocket.send_bytes(chunk)

                # Save accumulated PCM as a WAV file for the download endpoint
                if all_pcm_bytes:
                    try:
                        _save_audiobook_wav(job_id, all_pcm_bytes)
                    except Exception as _e:
                        print(f"[WS-AUDIOBOOK] WAV save error: {_e}")

                await websocket.send_json({"type": "done", "job_id": job_id})

    except WebSocketDisconnect:
        print("[WS-AUDIOBOOK] Client disconnected")
    except Exception as e:
        print(f"[WS-AUDIOBOOK] Error: {e}")
        try:
            await websocket.send_json({"type": "error", "message": str(e)})
        except Exception:
            pass


def _save_audiobook_wav(job_id: str, pcm_chunks: list, sample_rate: int = 24000) -> None:
    """Concatenate raw PCM int16 chunks and write a WAV file to /tmp."""
    import struct

    raw = b"".join(pcm_chunks)
    num_samples = len(raw) // 2
    num_channels = 1
    bits_per_sample = 16
    byte_rate = sample_rate * num_channels * bits_per_sample // 8
    block_align = num_channels * bits_per_sample // 8
    data_size = len(raw)
    riff_size = 36 + data_size

    header = struct.pack(
        "<4sI4s4sIHHIIHH4sI",
        b"RIFF", riff_size, b"WAVE",
        b"fmt ", 16, 1, num_channels, sample_rate, byte_rate,
        block_align, bits_per_sample,
        b"data", data_size,
    )

    path = f"/tmp/audiobook_{job_id}.wav"
    with open(path, "wb") as fh:
        fh.write(header + raw)


@app.get("/api/audiobook/{job_id}/download")
async def download_audiobook_ws(job_id: str):
    """Download the accumulated WAV file for a completed audiobook job."""
    # Sanitize job_id: allow alphanumeric, underscore, hyphen only
    if not re.match(r"^[A-Za-z0-9_\-]+$", job_id):
        return JSONResponse({"error": "Invalid job_id"}, status_code=400)
    path = f"/tmp/audiobook_{job_id}.wav"
    if not os.path.exists(path):
        return JSONResponse({"error": "Audio file not found"}, status_code=404)
    return FileResponse(path, media_type="audio/wav", filename="audiobook.wav")


if __name__ == "__main__":
    print("\n" + "=" * 50)
    print("Omnix FastAPI Server - Ultra Low Latency")
    print("=" * 50)
    print(f"WebSocket: ws://{HOST}:{PORT}/ws/conversation")
    print(f"WebSocket: ws://{HOST}:{PORT}/ws/tts")
    print(f"WebSocket: ws://{HOST}:{PORT}/ws/audiobook")
    print("=" * 50 + "\n")
    
    uvicorn.run(
        app,
        host=HOST,
        port=PORT,
        log_level="info"
    )
