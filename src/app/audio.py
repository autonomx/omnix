"""
Audio TTS Module
Handles text-to-speech functionality with streaming support
"""
import base64
import json
import os
import queue
import tempfile
import threading
import time
import wave

import numpy as np
from flask import Blueprint, Response, jsonify, request

import app.shared as shared

audio_bp = Blueprint('audio', __name__)

# Semaphore allows up to 2 concurrent TTS generations (replaces single Lock
# to reduce head-of-line blocking while still limiting CUDA memory pressure)
_generation_semaphore = threading.Semaphore(2)

# Global waiter counter with lock
_waiter_lock = threading.Lock()
_generation_waiters = 0


@audio_bp.route('/api/stt', methods=['POST'])
def stt():
    """STT endpoint for audio transcription."""
    try:
        if 'file' in request.files:
            audio_file = request.files['file']
            language = request.form.get('language', 'en')
            
            with tempfile.NamedTemporaryFile(suffix='.wav', delete=False) as temp_audio:
                audio_file.save(temp_audio.name)
                temp_path = temp_audio.name
            
            try:
                stt_provider = shared.get_stt_provider()
                if not stt_provider:
                    return jsonify({"success": False, "error": "No STT provider available"}), 500
                
                result = stt_provider.transcribe(temp_path, language=language)
                return jsonify(result)
            finally:
                if os.path.exists(temp_path):
                    os.unlink(temp_path)
        else:
            return jsonify({"success": False, "error": "No audio file provided"}), 400
            
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500


@audio_bp.route('/api/stt/float32', methods=['POST'])
def stt_float32():
    """STT endpoint for raw Float32 audio."""
    try:
        audio_data = request.get_data()
        if not audio_data:
            return jsonify({"success": False, "error": "No audio data provided"}), 400
        
        sample_rate = int(request.headers.get('X-Sample-Rate', 24000))
        
        stt_provider = shared.get_stt_provider()
        if not stt_provider:
            return jsonify({"success": False, "error": "No STT provider available"}), 500
        
        if hasattr(stt_provider, 'transcribe_raw'):
            result = stt_provider.transcribe_raw(audio_data, sample_rate=sample_rate)
        else:
            float32_data = np.frombuffer(audio_data, dtype=np.float32)
            int16_data = (float32_data * 32767).astype(np.int16)
            
            with tempfile.NamedTemporaryFile(suffix='.wav', delete=False) as temp_audio:
                with wave.open(temp_audio.name, 'wb') as wf:
                    wf.setnchannels(1)
                    wf.setsampwidth(2)
                    wf.setframerate(sample_rate)
                    wf.writeframes(int16_data.tobytes())
                temp_path = temp_audio.name
            
            try:
                result = stt_provider.transcribe(temp_path)
            finally:
                if os.path.exists(temp_path):
                    os.unlink(temp_path)
        
        return jsonify(result)
        
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500

def resolve_speaker(data):
    """Resolve speaker from request data."""
    speaker = data.get('speaker', 'default')
    language = data.get('language', 'en')
    
    # Handle custom voices
    clean_speaker = speaker.replace(" (Custom)", "").strip()
    voice_clone_id = shared.custom_voices.get(clean_speaker, {}).get("voice_clone_id")
    
    final_speaker = voice_clone_id
    if not final_speaker and clean_speaker and clean_speaker.lower() != 'default':
        final_speaker = clean_speaker
    
    return final_speaker, language

@audio_bp.route('/api/tts', methods=['POST'])
def tts():
    """Standard TTS endpoint - returns complete audio."""
    data = request.get_json()
    text = shared.remove_emojis(data.get('text', ''))
    if not text:
        return jsonify({"success": False, "error": "Text required"}), 400
    
    final_speaker, language = resolve_speaker(data)
    
    tts_provider = shared.get_tts_provider()
    if not tts_provider:
        return jsonify({"success": False, "error": "No TTS provider available"}), 500
    
    try:
        # Use provider's TTS method
        if hasattr(tts_provider, 'generate_tts'):
            result = tts_provider.generate_tts(text=text, speaker=final_speaker, language=language)
        elif hasattr(tts_provider, 'generate_audio'):
            result = tts_provider.generate_audio(text=text, speaker=final_speaker, language=language)
        else:
            return jsonify({"success": False, "error": "Provider missing TTS method"}), 500
        
        if result and result.get('success'):
            return jsonify({
                "success": True,
                "audio": result.get('audio', ''),
                "sample_rate": result.get('sample_rate', 24000)
            })
        else:
            return jsonify({"success": False, "error": result.get('error', 'TTS failed')}), 500
            
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500

@audio_bp.route('/api/tts/stream', methods=['POST'])
def tts_stream():
    """Legacy streaming endpoint - returns raw audio data directly.

    .. deprecated::
        Prefer the ``/ws/audiobook`` WebSocket endpoint for audiobook TTS.
        This HTTP endpoint encodes audio inline and is kept only for backward
        compatibility with the chat subsystem.
    """
    data = request.get_json()
    text = shared.remove_emojis(data.get('text', ''))
    if not text:
        return jsonify({"success": False, "error": "Text required"}), 400
    
    final_speaker, language = resolve_speaker(data)
    
    tts_provider = shared.get_tts_provider()
    if not tts_provider:
        return jsonify({"success": False, "error": "No TTS provider available"}), 500
    
    try:
        # Use provider's streaming method if available
        if hasattr(tts_provider, 'generate_audio_stream'):
            gen = tts_provider.generate_audio_stream(
                text=text,
                speaker=final_speaker,
                language=language,
                chunk_size=12,
                temperature=0.9,
                top_k=50,
                repetition_penalty=1.05
            )
            
            # Stream raw audio data directly
            def generate():
                for audio_chunk, sample_rate, timing in gen:
                    if audio_chunk is None or len(audio_chunk) == 0:
                        continue
                    
                    # Convert float32 to int16 PCM
                    pcm_int16 = (audio_chunk * 32767).astype(np.int16).tobytes()
                    yield pcm_int16
            
            return Response(generate(), mimetype='audio/wav')
        
        else:
            # Fallback to batch TTS
            if hasattr(tts_provider, 'generate_tts'):
                result = tts_provider.generate_tts(text=text, speaker=final_speaker, language=language)
            elif hasattr(tts_provider, 'generate_audio'):
                result = tts_provider.generate_audio(text=text, speaker=final_speaker, language=language)
            else:
                return jsonify({"success": False, "error": "Provider missing TTS method"}), 500
            
            if result and result.get('success'):
                # Return complete audio
                audio_data = base64.b64decode(result.get('audio', ''))
                return Response(audio_data, mimetype='audio/wav')
            else:
                return jsonify({"success": False, "error": result.get('error', 'TTS failed')}), 500
                
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500

@audio_bp.route('/api/tts/stream/server-sent-events', methods=['POST'])
def tts_stream_sse():
    """SSE streaming endpoint with proper JSON format.

    .. deprecated::
        Prefer the ``/ws/audiobook`` WebSocket endpoint for audiobook TTS.
        This SSE endpoint uses base64-encoded audio and is kept only for
        backward compatibility with the chat subsystem.
    """
    global _generation_waiters
    
    # --- Validation (same as /tts) --- 
    try:
        # Try to get JSON data, but be more permissive
        if request.is_json:
            data = request.get_json()
            if not data:
                return jsonify({"success": False, "error": "JSON data required"}), 400
        else:
            # If not JSON, try to get form data or text
            data = request.form.to_dict()
            if not data:
                # Try to get raw data
                try:
                    data = request.get_data(as_text=True)
                    if data:
                        import json as json_module
                        data = json_module.loads(data)
                    else:
                        data = {}
                except:
                    data = {}
        
        # Log what we received for debugging
        print(f"[SSE-DEBUG] Received data: {data}")
        print(f"[SSE-DEBUG] Request headers: {dict(request.headers)}")
        
    except Exception as e:
        print(f"[SSE-DEBUG] Error parsing request: {e}")
        return jsonify({"success": False, "error": f"Invalid request: {str(e)}"}), 400
    
    text = shared.remove_emojis(data.get('text', ''))
    if not text:
        return jsonify({"success": False, "error": "Text required"}), 400
    
    final_speaker, language = resolve_speaker(data)
    
    tts_provider = shared.get_tts_provider()
    if not tts_provider:
        return jsonify({"success": False, "error": "No TTS provider available"}), 500
    
    # --- Per-request state --- 
    q = queue.Queue()
    stop_event = threading.Event()
    
    # --- Report queue position --- 
    with _waiter_lock:
        _generation_waiters += 1
        position = _generation_waiters - 1
    
    def generate():
        t0 = time.time()
        try:
            # Acquire global lock (blocks if another generation is running)
            with _generation_semaphore:
                # Check cancellation before starting
                if stop_event.is_set():
                    return
                
                # Call provider's streaming method
                gen = tts_provider.generate_audio_stream(
                    text=text,
                    speaker=final_speaker,
                    language=language,
                    chunk_size=12,
                    temperature=0.9,
                    top_k=50,
                    repetition_penalty=1.05
                )
                
                total_samples = 0
                sr = 24000
                
                for audio_chunk, sample_rate, timing in gen:
                    if stop_event.is_set():
                        break
                    
                    if audio_chunk is None or len(audio_chunk) == 0:
                        continue
                    
                    total_samples += len(audio_chunk)
                    
                    # Convert float32 PCM to int16 bytes (vectorized!)
                    pcm_int16 = (audio_chunk * 32767).astype(np.int16).tobytes()
                    
                    # Base64 encode
                    audio_b64 = base64.b64encode(pcm_int16).decode('utf-8')
                    
                    # Calculate metrics
                    elapsed = time.time() - t0
                    audio_duration = total_samples / sample_rate
                    rtf = audio_duration / elapsed if elapsed > 0 else 0.0
                    
                    payload = {
                        "type": "chunk",
                        "audio_b64": audio_b64,
                        "sample_rate": sample_rate,
                        "rtf": round(rtf, 3),
                        "elapsed_ms": round(elapsed * 1000, 1)
                    }
                    q.put(json.dumps(payload))
                
                if not stop_event.is_set():
                    q.put(json.dumps({"type": "done"}))
                    
        except Exception as e:
            q.put(json.dumps({"type": "error", "message": str(e)}))
        finally:
            q.put(None)  # Sentinel
    
    # Start generation thread
    thread = threading.Thread(target=generate, daemon=True)
    thread.start()
    
    # --- SSE generator --- 
    def sse():
        global _generation_waiters
        try:
            # Send queue position immediately
            if position > 0:
                yield f"data: {json.dumps({'type': 'queued', 'position': position})}\n\n"
            
            # Stream from queue
            while True:
                item = q.get()
                if item is None:
                    break
                yield f"data: {item}\n\n"
        finally:
            # Cleanup
            with _waiter_lock:
                _generation_waiters -= 1
    
    # Important headers for proxying
    headers = {
        "Cache-Control": "no-cache",
        "X-Accel-Buffering": "no",
        "Content-Type": "text/event-stream"
    }
    
    return Response(sse(), headers=headers)

@audio_bp.route('/api/tts/speakers', methods=['GET'])
def get_tts_speakers():
    """Get available TTS speakers/voices."""
    tts_provider = shared.get_tts_provider()
    if not tts_provider:
        return jsonify({"success": False, "error": "No TTS provider available"}), 500
    
    try:
        # Use provider's method to get speakers
        if hasattr(tts_provider, 'get_speakers'):
            speakers = tts_provider.get_speakers()
        elif hasattr(tts_provider, 'get_voices'):
            speakers = tts_provider.get_voices()
        else:
            # Fallback: return default speakers
            speakers = [
                {"id": "Maya", "name": "Maya"},
                {"id": "en", "name": "English (Default)"},
                {"id": "default", "name": "Default"}
            ]
        
        return jsonify({
            "success": True,
            "speakers": speakers,
            "provider": tts_provider.provider_name
        })
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500

@audio_bp.route('/api/tts/stream/cancel', methods=['POST'])
def cancel_stream():
    """Cancel streaming TTS."""
    # Note: In practice, cancellation is triggered by client aborting the fetch()
    # The stop_event approach works if we store per-request stop_events in a dict
    # But simpler: when client disconnects, Flask will terminate the request
    # and the thread will exit naturally when it tries to yield to dead connection
    return jsonify({"success": True})
