"""
Parakeet TDT 0.6B STT Server
FastAPI server for speech-to-text using NVIDIA NeMo Parakeet model

This file is placed in the root to avoid import conflicts with the 
local nemo folder in models/stt/parakeet-tdt-0.6b-v2/
"""
# Fix PyTorch DLL loading hang on Windows (PyTorch 2.9+)
import os
import platform

if platform.system() == "Windows":
    import ctypes
    from importlib.util import find_spec
    try:
        if (spec := find_spec("torch")) and spec.origin:
            torch_lib_dir = os.path.join(os.path.dirname(spec.origin), "lib")
            c10_dll = os.path.join(torch_lib_dir, "c10.dll")
            if os.path.exists(c10_dll):
                ctypes.CDLL(os.path.normpath(c10_dll))
    except Exception:
        pass

import asyncio
import base64
import datetime
import gc
import shutil
import tempfile
import traceback
import uuid


# --- WebSocket dependency validation ---
def _validate_websocket_support():
    try:
        import websockets  # noqa
        return "websockets"
    except Exception:
        try:
            import wsproto  # noqa
            return "wsproto"
        except Exception:
            raise RuntimeError(
                "STT WebSocket support missing. Install with: pip install 'uvicorn[standard]' or 'websockets'"
            )
from pathlib import Path
from typing import List, Optional

import numpy as np
import torch
import uvicorn
from fastapi import (
    BackgroundTasks,
    FastAPI,
    File,
    HTTPException,
    UploadFile,
    WebSocket,
    WebSocketDisconnect,
)
from nemo.collections.asr.models import ASRModel
from pydantic import BaseModel, Field
from pydub import AudioSegment
from pydub.silence import detect_nonsilent

# Configuration
device = "cpu"  # Default to CPU to avoid GPU conflicts with LLM
MODEL_NAME = "nvidia/parakeet-tdt-0.6b-v2"

# Global model instance
model = None

# Track if we're in fallback mode
gpu_fallback_to_cpu = False

def safe_cuda_sync():
    """Safely synchronize CUDA device if available"""
    try:
        if torch.cuda.is_available():
            torch.cuda.synchronize()
            torch.cuda.empty_cache()
    except Exception as e:
        print(f"[STT] CUDA sync warning: {e}")

def load_model():
    """Load the ASR model on startup - CPU by default to avoid LLM conflicts"""
    global model, device, gpu_fallback_to_cpu
    
    # Check environment for mode preference
    # Default to CPU because LLM (llama.cpp) typically uses GPU
    # and CUDA context conflicts cause crashes
    force_cpu = os.environ.get('PARAKEET_FORCE_CPU', 'true').lower() == 'true'
    try_gpu = os.environ.get('PARAKEET_TRY_GPU', 'false').lower() == 'true'
    
    print(f"[STT] Environment: PARAKEET_FORCE_CPU={force_cpu}, PARAKEET_TRY_GPU={try_gpu}")
    
    if force_cpu:
        print("[STT] CPU mode (default) - avoiding GPU conflicts with LLM")
        device = "cpu"
    elif try_gpu and torch.cuda.is_available():
        print("[STT] Attempting GPU mode (experimental)")
        device = "cuda"
    else:
        print("[STT] CPU mode - stable operation")
        device = "cpu"
    
    print(f"[STT] Loading model on {device}...")
    
    try:
        # Set CUDA device explicitly if using GPU
        if device == "cuda":
            torch.cuda.set_device(0)
            # Clear any existing CUDA state
            torch.cuda.empty_cache()
            gc.collect()
        
        model = ASRModel.from_pretrained(model_name=MODEL_NAME)
        model.to(device)
        model.eval()
        
        print(f"[STT] Model {MODEL_NAME} loaded successfully on {device}")
        
        # Log GPU info if available
        if torch.cuda.is_available():
            gpu_name = torch.cuda.get_device_name(0)
            gpu_memory = torch.cuda.get_device_properties(0).total_memory / 1024**3
            print(f"[STT] GPU available: {gpu_name} ({gpu_memory:.1f} GB)")
            if device == "cpu":
                print(f"[STT] Running on CPU to avoid GPU conflicts with LLM")
                
    except Exception as e:
        print(f"[STT] Failed to load model on {device}: {e}")
        traceback.print_exc()
        
        # If GPU failed, try CPU fallback
        if device == "cuda":
            print("[STT] GPU failed, falling back to CPU...")
            device = "cpu"
            gpu_fallback_to_cpu = True
            
            try:
                torch.cuda.empty_cache()
                gc.collect()
                
                model = ASRModel.from_pretrained(model_name=MODEL_NAME)
                model.to(device)
                model.eval()
                print(f"[STT] Model loaded on {device} (CPU fallback)")
            except Exception as e2:
                print(f"[STT] CPU fallback also failed: {e2}")
                traceback.print_exc()
                model = None
        else:
            model = None

# Pydantic models for API
class TranscriptionSegment(BaseModel):
    start: float = Field(..., description="Start time in seconds")
    end: float = Field(..., description="End time in seconds") 
    text: str = Field(..., description="Transcribed text segment")

class TranscriptionResponse(BaseModel):
    success: bool = Field(..., description="Whether transcription was successful")
    segments: List[TranscriptionSegment] = Field(default=[], description="List of transcription segments")
    duration: Optional[float] = Field(None, description="Total audio duration in seconds")
    message: Optional[str] = Field(None, description="Status message or error description")

class HealthResponse(BaseModel):
    status: str = Field(..., description="Service health status")
    model_loaded: bool = Field(..., description="Whether the ASR model is loaded")
    device: str = Field(..., description="Device being used (cuda/cpu)")

# Initialize FastAPI app
app = FastAPI(
    title="Speech Transcription API",
    description="A REST API for speech-to-text transcription using NVIDIA's parakeet-tdt-0.6b-v2 model",
    version="1.0.0",
    docs_url="/docs",
    redoc_url="/redoc"
)

# Add CORS middleware to allow cross-origin requests from the main app
from fastapi.middleware.cors import CORSMiddleware

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

def cleanup_session_dir(session_dir: Path):
    """Background task to clean up session directory"""
    try:
        if session_dir.exists():
            shutil.rmtree(session_dir)
            print(f"Cleaned up session directory: {session_dir}")
    except Exception as e:
        print(f"Error cleaning up session directory {session_dir}: {e}")

def process_audio_for_transcription(audio_path: str, session_dir: Path) -> tuple:
    """Process audio file for transcription (resampling, mono conversion)"""
    try:
        print(f"[STT] Loading audio from: {audio_path}")
        
        # Try pydub first, fall back to soundfile/wave if ffprobe not available
        audio = None
        use_pydub = True
        
        try:
            audio = AudioSegment.from_file(audio_path)
        except (FileNotFoundError, OSError) as e:
            # ffprobe not found (Windows Error 2 or similar), try soundfile fallback for WAV files
            print(f"[STT] pydub failed (likely ffprobe missing: {e}), trying soundfile fallback...")
            use_pydub = False
            
            import numpy as np
            import soundfile as sf
            
            # Read audio with soundfile
            data, samplerate = sf.read(audio_path, dtype='float32')
            
            # Convert to mono if stereo
            if len(data.shape) > 1 and data.shape[1] > 1:
                data = np.mean(data, axis=1)
            
            # Resample to 16kHz if needed
            target_sr = 16000
            if samplerate != target_sr:
                from scipy import signal
                num_samples = int(len(data) * target_sr / samplerate)
                data = signal.resample(data, num_samples)
                samplerate = target_sr
            
            # Save processed audio
            audio_name = Path(audio_path).stem
            processed_audio_path = session_dir / f"{audio_name}_processed.wav"
            sf.write(processed_audio_path, data, samplerate, subtype='PCM_16')
            
            print(f"[STT] Audio processed via soundfile: {samplerate}Hz, mono")
            return processed_audio_path.as_posix(), len(data) / samplerate
        
        duration_sec = audio.duration_seconds
        
        print(f"[STT] Audio loaded: duration={duration_sec:.2f}s, channels={audio.channels}, frame_rate={audio.frame_rate}")
        
        resampled = False
        mono = False
        
        # Resample to 16kHz if needed
        target_sr = 16000
        if audio.frame_rate != target_sr:
            print(f"[STT] Resampling from {audio.frame_rate}Hz to {target_sr}Hz")
            audio = audio.set_frame_rate(target_sr)
            resampled = True
            
        # Convert to mono if needed
        if audio.channels == 2:
            print(f"[STT] Converting stereo to mono")
            audio = audio.set_channels(1)
            mono = True
        elif audio.channels > 2:
            raise ValueError(f"Audio has {audio.channels} channels. Only mono (1) or stereo (2) supported.")
            
        # Trim leading/trailing silence for Parakeet TDT models
        # TDT models are sensitive to leading silence and may fail to detect speech
        try:
            nonsilent_chunks = detect_nonsilent(audio, min_silence_len=300, silence_thresh=-40)
            if nonsilent_chunks:
                start, end = nonsilent_chunks[0][0], nonsilent_chunks[-1][1]
                audio = audio[start:end]
                print(f"[STT] Trimmed silence: {start}ms to {end}ms")
            else:
                print(f"[STT] No nonsilent chunks detected, using full audio")
        except Exception as e:
            print(f"[STT] Silence detection failed, using full audio: {e}")
        
        # Export processed audio if changes were made
        if resampled or mono:
            audio_name = Path(audio_path).stem
            processed_audio_path = session_dir / f"{audio_name}_processed.wav"
            print(f"[STT] Exporting processed audio to: {processed_audio_path}")
            audio.export(processed_audio_path, format="wav")
            print(f"[STT] Export complete, file size: {processed_audio_path.stat().st_size} bytes")
            return processed_audio_path.as_posix(), duration_sec
        else:
            print(f"[STT] No processing needed, using original file")
            return audio_path, duration_sec
            
    except Exception as e:
        print(f"[STT] Error processing audio: {e}")
        import traceback
        traceback.print_exc()
        raise RuntimeError(f"Failed to process audio: {e}")

def get_transcripts_and_raw_times(audio_path: str, session_dir: Path) -> TranscriptionResponse:
    """Main transcription function"""
    if not model:
        return TranscriptionResponse(
            success=False,
            message="ASR model is not loaded"
        )
    
    if not audio_path:
        return TranscriptionResponse(
            success=False,
            message="No audio file path provided"
        )
    
    try:
        # Process audio
        transcribe_path, duration_sec = process_audio_for_transcription(audio_path, session_dir)
        
        # Configure model for long audio if needed
        long_audio_settings_applied = False
        try:
            model.to(device)
            
            # Apply settings for long audio (>8 minutes)
            if duration_sec > 480:
                print("Applying long audio settings: Local Attention and Chunking.")
                model.change_attention_model("rel_pos_local_attn", [256, 256])
                model.change_subsampling_conv_chunking_factor(1)
                long_audio_settings_applied = True
            
            # Perform transcription (use paths2audio_files parameter for Parakeet TDT)
            # Remove manual dtype casting - NeMo manages precision internally
            model.to(device)
            
            # Run transcription with improved handling
            try:
                output = model.transcribe(paths2audio_files=[transcribe_path])
            except TypeError:
                # fallback for positional-only models
                try:
                    output = model.transcribe([transcribe_path])
                except Exception as trans_err:
                    print(f"[STT] Positional transcription failed, trying with timestamps: {trans_err}")
                    output = model.transcribe([transcribe_path], timestamps=True)

            print(f"[STT] RAW MODEL OUTPUT: {output}")
            print(f"[STT] Transcription output type: {type(output)}")

            text = None

            # Case 1: Tuple (RNNT models)
            if isinstance(output, tuple):
                print("[STT] Processing tuple output")
                
                if len(output) > 0 and isinstance(output[0], list) and len(output[0]) > 0:
                    text = output[0][0]

            # Case 2: List output
            elif isinstance(output, list) and len(output) > 0:
                if isinstance(output[0], str):
                    text = output[0]
                elif hasattr(output[0], "text"):
                    text = output[0].text

            # Final validation
            if text and text.strip():
                print(f"[STT] Final transcription: {text}")
                transcribed_text = text.strip()
            else:
                print("[STT] No transcription output")
                return TranscriptionResponse(
                    success=False,
                    message="No speech detected in audio"
                )
            
            # Create a single segment with the full text
            segments = [TranscriptionSegment(
                start=0.0,
                end=duration_sec,
                text=transcribed_text
            )]
            
            print(f"[STT] Transcribed text: {transcribed_text}")
            
            return TranscriptionResponse(
                success=True,
                segments=segments,
                duration=duration_sec,
                message="Transcription completed successfully"
            )
            
        finally:
            # Revert model settings if applied
            if long_audio_settings_applied:
                try:
                    print("Reverting long audio settings.")
                    model.change_attention_model("rel_pos")
                    model.change_subsampling_conv_chunking_factor(-1)
                except Exception as e:
                    print(f"Warning: Failed to revert long audio settings: {e}")
            
            # Cleanup
            try:
                if device == 'cuda':
                    model.cpu()
                gc.collect()
                if device == 'cuda':
                    torch.cuda.empty_cache()
            except Exception as e:
                print(f"Error during model cleanup: {e}")
                
    except torch.cuda.OutOfMemoryError as e:
        return TranscriptionResponse(
            success=False,
            message="CUDA out of memory. Please try a shorter audio or reduce GPU load."
        )
    except Exception as e:
        return TranscriptionResponse(
            success=False,
            message=f"Transcription failed: {str(e)}"
        )

# API Endpoints
@app.on_event("startup")
async def startup_event():
    """Load model on startup"""
    load_model()

@app.get("/health")
async def health():
    try:
        import nemo.collections.asr as nemo_asr
        import torch
        return {
            "ok": True,
            "status": "ready",
            "provider": "parakeet_stt",
            "details": {
                "versions": {
                    "torch": getattr(torch, "__version__", ""),
                    "nemo": getattr(nemo_asr, "__version__", ""),
                },
                "cuda_available": bool(torch.cuda.is_available()) if hasattr(torch, "cuda") else False,
                "model_loaded": model is not None,
                "device": device
            },
            "error": "",
        }
    except Exception as exc:
        return JSONResponse(
            {
                "ok": False,
                "status": "not_ready",
                "provider": "parakeet_stt",
                "details": {},
                "error": str(exc),
            },
            status_code=500,
        )

@app.post("/transcribe", response_model=TranscriptionResponse)
async def transcribe_audio(
    background_tasks: BackgroundTasks,
    file: UploadFile = File(..., description="Audio file to transcribe")
):
    """
    Transcribe an audio file to text with timestamps
    
    - **file**: Audio file (supported formats: wav, mp3, flac, etc.)
    
    Returns transcription segments with start/end timestamps and text
    """
    print(f"[STT] Received transcription request: filename={file.filename}, content_type={file.content_type}")
    
    # Validate file type
    allowed_types = ["audio/wav", "audio/mpeg", "audio/flac", "audio/ogg", "audio/mp4", "audio/webm"]
    if file.content_type not in allowed_types:
        # Allow webm and try to process anyway
        if not file.content_type or 'webm' in file.content_type.lower():
            print(f"[STT] Accepting webm content type: {file.content_type}")
            pass  # Accept webm
        else:
            print(f"[STT] Rejecting content type: {file.content_type}")
            raise HTTPException(
                status_code=400,
                detail=f"Unsupported file type: {file.content_type}. Allowed types: {allowed_types}"
            )
    
    # Create session directory
    session_id = str(uuid.uuid4())
    session_dir = Path(tempfile.gettempdir()) / f"transcription_{session_id}"
    session_dir.mkdir(parents=True, exist_ok=True)
    
    # Schedule cleanup
    background_tasks.add_task(cleanup_session_dir, session_dir)
    
    try:
        # Save uploaded file
        file_path = session_dir / (file.filename or "audio.webm")
        content = await file.read()
        file_size = len(content)
        print(f"[STT] Received {file_size} bytes of audio data")
        
        if file_size < 100:
            print(f"[STT] Audio file too small: {file_size} bytes")
            return TranscriptionResponse(
                success=False,
                message=f"Audio file too small ({file_size} bytes). Please record for at least 1 second."
            )
        
        with open(file_path, "wb") as buffer:
            buffer.write(content)
        
        print(f"[STT] Saved audio to: {file_path}")
        
        # Perform transcription
        result = get_transcripts_and_raw_times(file_path.as_posix(), session_dir)
        print(f"[STT] Transcription result: success={result.success}, segments={len(result.segments) if result.segments else 0}")
        return result
        
    except Exception as e:
        print(f"[STT] Error during transcription: {e}")
        import traceback
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=f"Internal server error: {str(e)}")

# WebSocket endpoint for streaming STT
@app.websocket("/ws/transcribe")
async def websocket_transcribe(websocket: WebSocket):
    """
    WebSocket endpoint for streaming speech-to-text.
    
    Client sends:
    - {"type": "audio", "data": "<base64-encoded-audio-chunk>"}
    - {"type": "final"} to signal end of audio
    
    Server sends:
    - {"type": "ready"} when connection is ready
    - {"type": "text", "text": "<partial-transcript>"} during streaming
    - {"type": "done", "text": "<final-transcript>"} when complete
    - {"type": "error", "error": "<error-message>"} on error
    """
    await websocket.accept()
    
    try:
        # Signal ready
        await websocket.send_json({"type": "ready"})
        
        # Collect audio chunks
        audio_chunks = []
        
        while True:
            try:
                # Receive message
                data = await websocket.receive_json()
                msg_type = data.get("type", "")
                
                if msg_type == "audio":
                    # Decode and collect audio chunk
                    audio_b64 = data.get("data", "")
                    if audio_b64:
                        audio_chunk = base64.b64decode(audio_b64)
                        audio_chunks.append(audio_chunk)
                        
                        # For now, we don't send partial results
                        # Real streaming would require a streaming ASR model
                        
                elif msg_type == "final":
                    # Process all collected audio
                    if not audio_chunks:
                        await websocket.send_json({
                            "type": "done",
                            "text": ""
                        })
                        break
                    
                    if not model:
                        await websocket.send_json({
                            "type": "error",
                            "error": "ASR model not loaded"
                        })
                        break
                    
                    # Combine audio chunks
                    combined_audio = b"".join(audio_chunks)
                    
                    # Create temp file for transcription
                    session_id = str(uuid.uuid4())
                    session_dir = Path(tempfile.gettempdir()) / f"ws_transcription_{session_id}"
                    session_dir.mkdir(parents=True, exist_ok=True)
                    
                    try:
                        # Detect audio format and convert if needed
                        # Check for WAV header (RIFF)
                        if len(combined_audio) > 44 and combined_audio[:4] == b'RIFF':
                            # Already WAV format
                            wav_path = session_dir / "audio.wav"
                            with open(wav_path, "wb") as f:
                                f.write(combined_audio)
                            audio_path = wav_path
                        # Check for webm/mp4 header
                        elif len(combined_audio) > 4 and combined_audio[:4] in [b'\x1a\x45\xdf\xa3', b'ftyp']:
                            # WebM format
                            webm_path = session_dir / "audio.webm"
                            with open(webm_path, "wb") as f:
                                f.write(combined_audio)
                            try:
                                audio = AudioSegment.from_file(webm_path, format="webm")
                                wav_path = session_dir / "audio.wav"
                                audio.export(wav_path, format="wav")
                                audio_path = wav_path
                            except Exception as conv_err:
                                print(f"Webm conversion failed: {conv_err}")
                                audio_path = webm_path
                        else:
                            # Assume raw PCM Int16, create WAV container
                            import wave
                            wav_path = session_dir / "audio.wav"
                            with wave.open(str(wav_path), 'wb') as wf:
                                wf.setnchannels(1)
                                wf.setsampwidth(2)  # 16-bit
                                wf.setframerate(16000)  # Default to 16kHz
                                wf.writeframes(combined_audio)
                            audio_path = wav_path
                        
                        # Process and transcribe
                        result = get_transcripts_and_raw_times(str(audio_path), session_dir)
                        
                        if result.success:
                            # Combine all segment texts
                            full_text = " ".join([seg.text for seg in result.segments])
                            await websocket.send_json({
                                "type": "done",
                                "text": full_text,
                                "segments": [{"start": s.start, "end": s.end, "text": s.text} for s in result.segments]
                            })
                        else:
                            await websocket.send_json({
                                "type": "error",
                                "error": result.message or "Transcription failed"
                            })
                            
                    finally:
                        # Cleanup
                        cleanup_session_dir(session_dir)
                    
                    # Clear buffer for next utterance
                    audio_chunks = []
                    break
                    
            except Exception as e:
                import traceback
                print(f"WebSocket transcription error: {e}")
                traceback.print_exc()
                await websocket.send_json({
                    "type": "error",
                    "error": str(e)
                })
                break
                
    except WebSocketDisconnect:
        print("WebSocket client disconnected")
    except Exception as e:
        print(f"WebSocket error: {e}")
        try:
            await websocket.send_json({
                "type": "error",
                "error": str(e)
            })
        except:
            pass

if __name__ == "__main__":
    ws_backend = _validate_websocket_support()
    print(f"[STT] WebSocket backend: {ws_backend}")
    PORT = int(os.environ.get("OMNIX_STT_PORT", "5201"))
    print(f"Starting Parakeet STT Server on http://0.0.0.0:{PORT}")
    print(f"Endpoints:")
    print(f"  - Health:    http://0.0.0.0:{PORT}/health")
    print(f"  - Transcribe: http://0.0.0.0:{PORT}/transcribe (POST)")
    print(f"  - WebSocket:  ws://0.0.0.0:{PORT}/ws/transcribe")
    uvicorn.run(app, host="0.0.0.0", port=PORT)
