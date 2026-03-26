
import os
import time
import json
import queue
import threading
import subprocess
import requests
from flask import Blueprint, request, jsonify
import app.shared as shared

services_bp = Blueprint('services', __name__)

# State
tts_process, stt_process = None, None
tts_log_queue, stt_log_queue = queue.Queue(), queue.Queue()
tts_status = {"running": False, "message": "Not started"}
stt_status = {"running": False, "message": "Not started"}
speculative_cache = {}
cache_lock = threading.Lock()

SPECULATIVE_FILLERS = ["Hmm, let me think about that.", "Sure, I can help with that."]
CONVERSATION_GREETINGS = ["Hello! I'm ready to chat. How can I help you today?", "Hi there! I'm listening."]

def read_logs(process, q, name):
    try:
        import codecs
        for line in codecs.getreader('latin-1')(process.stdout):
            if line.strip(): q.put(f"[{name}] {line.strip()}")
    except Exception as e: 
        q.put(f"[{name}] Log error: {e}")

def check_service_and_add_log(name, base_url, log_queue):
    """Check if service is running and add a log entry"""
    try:
        import requests
        resp = requests.get(f"{base_url}/health", timeout=2)
        if resp.status_code == 200:
            log_queue.put(f"[{name}] Service running on {base_url}")
    except Exception as e:
        pass

def kill_port(port):
    try:
        import subprocess as sp
        r = sp.run(f'netstat -ano | findstr :{port} | findstr LISTENING', shell=True, capture_output=True, text=True)
        for line in r.stdout.strip().split('\n'):
            parts = line.split()
            if len(parts) >= 5:
                sp.run(f'taskkill /F /PID {parts[-1]}', shell=True, capture_output=True)
    except: pass

@services_bp.route('/api/services/tts/start', methods=['POST'])
def start_tts():
    global tts_process, tts_status
    try:
        # TTS now runs in-process via the audio provider system (e.g. faster-qwen3-tts)
        tts_status = {"running": True, "message": "TTS runs in-process via audio provider"}
    except Exception as e: tts_status = {"running": False, "message": str(e)}
    return jsonify({"success": True, "status": tts_status})

@services_bp.route('/api/services/tts/stop', methods=['POST'])
def stop_tts():
    global tts_process, tts_status
    if tts_process:
        try: tts_process.terminate(); tts_process.wait(10)
        except: tts_process.kill()
    tts_process, tts_status = None, {"running": False, "message": "Stopped"}
    return jsonify({"success": True, "status": tts_status})

@services_bp.route('/api/services/stt/start', methods=['POST'])
def start_stt():
    global stt_process, stt_status
    kill_port(8000)
    try:
        stt_dir = os.path.join(shared.MODELS_DIR, 'stt', 'parakeet-tdt-0.6b-v2')
        stt_process = subprocess.Popen(['python', 'app.py'], cwd=stt_dir, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, bufsize=1)
        threading.Thread(target=read_logs, args=(stt_process, stt_log_queue, "STT"), daemon=True).start()
        stt_status = {"running": True, "message": "Starting..."}
    except Exception as e: stt_status = {"running": False, "message": str(e)}
    return jsonify({"success": True, "status": stt_status})

@services_bp.route('/api/services/stt/stop', methods=['POST'])
def stop_stt():
    global stt_process, stt_status
    if stt_process:
        try: stt_process.terminate(); stt_process.wait(10)
        except: stt_process.kill()
    stt_process, stt_status = None, {"running": False, "message": "Stopped"}
    return jsonify({"success": True, "status": stt_status})

@services_bp.route('/api/services/status', methods=['GET'])
def get_status():
    global tts_status, stt_status
    tts_r, stt_r = False, False
    # TTS now runs in-process via audio provider - check if provider is available
    try:
        tts_provider = shared.get_tts_provider()
        tts_r = tts_provider is not None
    except: pass
    try: stt_r = requests.get(f"{shared.STT_BASE_URL}/health", timeout=2).status_code == 200
    except: pass
    
    tts_status['running'], stt_status['running'] = tts_r, stt_r
    return jsonify({"success": True, "tts": {"running": tts_r, "status": tts_status}, "stt": {"running": stt_r, "status": stt_status}})

@services_bp.route('/api/services/xtts/logs', methods=['GET'])
def get_xtts_logs():
    global tts_log_queue
    logs = []
    try:
        while not tts_log_queue.empty():
            logs.append(tts_log_queue.get_nowait())
        
        # If no logs, TTS now runs in-process
        if len(logs) == 0:
            tts_log_queue.put("[TTS] TTS runs in-process via audio provider")
            while not tts_log_queue.empty():
                logs.append(tts_log_queue.get_nowait())
    except: pass
    return jsonify({"success": True, "logs": logs})

@services_bp.route('/api/services/stt/logs', methods=['GET'])
def get_stt_logs():
    global stt_log_queue
    logs = []
    try:
        while not stt_log_queue.empty():
            logs.append(stt_log_queue.get_nowait())
        
        # If no logs, check if service is running and add info
        if len(logs) == 0:
            check_service_and_add_log("STT", shared.STT_BASE_URL, stt_log_queue)
            while not stt_log_queue.empty():
                logs.append(stt_log_queue.get_nowait())
    except: pass
    return jsonify({"success": True, "logs": logs})

def pregen_audio(speaker="default"):
    voice_id = shared.custom_voices.get(speaker.replace(" (Custom)", ""), {}).get("voice_clone_id")
    tts_provider = shared.get_tts_provider()
    if not tts_provider:
        return
    for phrase in SPECULATIVE_FILLERS + CONVERSATION_GREETINGS:
        try:
            result = tts_provider.generate_audio(text=phrase, speaker=speaker, language="en")
            if result.get('success'):
                with cache_lock: speculative_cache[phrase] = (result.get('audio'), result.get('sample_rate'))
        except: pass

@services_bp.route('/api/tts/pregenerate', methods=['POST'])
def pregenerate_route():
    threading.Thread(target=pregen_audio, args=(request.get_json().get('speaker', 'default'),), daemon=True).start()
    return jsonify({"success": True})

@services_bp.route('/api/tts/speculative', methods=['GET'])
def get_speculative():
    import random
    phrase = random.choice(SPECULATIVE_FILLERS)
    with cache_lock: audio = speculative_cache.get(phrase)
    if audio: return jsonify({"success": True, "text": phrase, "audio": audio[0], "sample_rate": audio[1]})
    return jsonify({"success": False, "error": "Not cached"})

@services_bp.route('/api/conversation/greeting', methods=['GET', 'POST'])
def get_greeting():
    import random
    speaker = (request.get_json() if request.method == 'POST' else request.args).get('speaker', 'default')
    phrase = random.choice(CONVERSATION_GREETINGS)
    voice_id = shared.custom_voices.get(speaker.replace(" (Custom)", ""), {}).get("voice_clone_id")
    
    # Try generating fresh audio via in-process TTS provider
    try:
        tts_provider = shared.get_tts_provider()
        if tts_provider:
            result = tts_provider.generate_audio(text=phrase, speaker=speaker, language="en")
            if result.get('success'):
                return jsonify({"success": True, "text": phrase, "audio": result.get('audio'), "sample_rate": result.get('sample_rate')})
    except: pass
    
    # Fallback to cache if generation failed
    with cache_lock: audio = speculative_cache.get(phrase)
    if audio: return jsonify({"success": True, "text": phrase, "audio": audio[0], "sample_rate": audio[1]})
    return jsonify({"success": False, "error": "TTS not available"})