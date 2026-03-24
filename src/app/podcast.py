import os
import json
import time
import base64
import requests
import io
import struct
from datetime import datetime
from flask import Blueprint, request, jsonify, Response, send_file
import app.shared as shared

podcast_bp = Blueprint('podcast', __name__)

EP_FILE = os.path.join(shared.DATA_DIR, 'podcasts', 'episodes.json')
VP_FILE = os.path.join(shared.DATA_DIR, 'podcasts', 'voice_profiles.json')
os.makedirs(os.path.dirname(EP_FILE), exist_ok=True)

def load_data(path, default):
    try:
        if os.path.exists(path): return json.load(open(path, 'r'))
    except: pass
    return default

def save_data(path, data):
    with open(path, 'w') as f: json.dump(data, f, indent=2)

@podcast_bp.route('/api/podcast/voice-profiles', methods=['GET', 'POST'])
def profiles():
    profiles = load_data(VP_FILE, [])
    if request.method == 'GET': return jsonify({"success": True, "profiles": profiles})
    
    data = request.get_json()
    data['id'] = data.get('id', f"vp_{int(time.time())}")
    data['created_at'] = datetime.now().isoformat()
    profiles.append(data)
    save_data(VP_FILE, profiles)
    return jsonify({"success": True, "profile": data})

@podcast_bp.route('/api/podcast/episodes', methods=['GET'])
def get_episodes():
    eps = load_data(EP_FILE, {})
    return jsonify({"success": True, "episodes": sorted(eps.values(), key=lambda x: x.get('created_at', ''), reverse=True)})

@podcast_bp.route('/api/podcast/episodes/<ep_id>', methods=['GET', 'DELETE'])
def manage_episode(ep_id):
    eps = load_data(EP_FILE, {})
    if ep_id not in eps: return jsonify({"success": False, "error": "Not found"}), 404
    
    if request.method == 'GET':
        ep = eps[ep_id]
        if os.path.exists(os.path.join(shared.DATA_DIR, 'podcasts', f"{ep_id}.wav")): ep['audio_url'] = f"/api/podcast/episodes/{ep_id}/audio"
        return jsonify({"success": True, "episode": ep})
        
    del eps[ep_id]
    save_data(EP_FILE, eps)
    try: os.remove(os.path.join(shared.DATA_DIR, 'podcasts', f"{ep_id}.wav"))
    except: pass
    return jsonify({"success": True})

@podcast_bp.route('/api/podcast/episodes/<ep_id>/audio', methods=['GET'])
def get_audio(ep_id):
    path = os.path.join(shared.DATA_DIR, 'podcasts', f"{ep_id}.wav")
    return send_file(path, mimetype='audio/wav') if os.path.exists(path) else (jsonify({"error": "No audio"}), 404)

def llm_generate(prompt):
    cfg = shared.get_provider_config()
    payload = {"model": cfg.get('model', 'local-model'), "messages": [{"role": "user", "content": prompt}]}
    headers = {"Content-Type": "application/json"}
    if cfg['provider'] in ['openrouter', 'cerebras']: headers["Authorization"] = f"Bearer {cfg['api_key']}"
    url = f"{cfg['base_url']}/chat/completions" if cfg['provider'] == 'openrouter' else f"{cfg['base_url']}/v1/chat/completions"
    r = requests.post(url, json=payload, headers=headers, timeout=120)
    return r.json()['choices'][0]['message']['content'] if r.status_code == 200 else ""

@podcast_bp.route('/api/podcast/outline', methods=['POST'])
def gen_outline():
    data = request.get_json()
    p = f"Create a podcast outline JSON for Topic: {data.get('topic')}. Format: {{'outline': '...', 'sections': [{{'title': '...', 'description': '...'}}]}}"
    try:
        res = llm_generate(p)
        import re
        match = re.search(r'\{[\s\S]*\}', res)
        return jsonify({"success": True, **json.loads(match.group() if match else res)})
    except Exception as e: return jsonify({"success": False, "error": str(e)}), 500

@podcast_bp.route('/api/podcast/generate', methods=['POST'])
def generate_ep():
    data = request.get_json()
    ep_id = data.get('id', f"ep_{int(time.time())}")
    
    def gen():
        try:
            yield f"data: {json.dumps({'type': 'phase', 'phase': 'script', 'message': 'Generating...'})}\n\n"
            script = llm_generate(f"Write a podcast dialogue script for: {data.get('topic')}. Format lines exactly as 'SpeakerName: Text'")
            
            segments = []
            for line in script.split('\n'):
                if ':' in line and len(line.split(':', 1)) == 2:
                    sp, txt = line.split(':', 1)
                    segments.append({"speaker": sp.strip(), "text": txt.strip()})
            
            transcript, audios = [], []
            for i, seg in enumerate(segments):
                vid = next((s.get('voice_id') for s in data.get('speakers', []) if s.get('name', '').lower() == seg['speaker'].lower()), None)
                v_clone = shared.custom_voices.get(vid.replace(" (Custom)", "") if vid else "", {}).get('voice_clone_id', vid)
                
                req = {"text": shared.remove_emojis(seg['text']), "language": "en"}
                if v_clone: req["voice_clone_id"] = v_clone
                
                try:
                    r = requests.post(f"{shared.TTS_BASE_URL}/tts", json=req, timeout=60)
                    if r.status_code == 200 and r.json().get('success'):
                        adata, sr = r.json().get('audio'), r.json().get('sample_rate')
                        yield f"data: {json.dumps({'type': 'audio', 'audio': adata, 'sample_rate': sr, 'segment_index': i})}\n\n"
                        transcript.append({"speaker": seg['speaker'], "text": seg['text']})
                        audios.append(base64.b64decode(adata))
                except: pass
                
            if audios:
                wav_io = io.BytesIO()
                wav_io.write(b'RIFF'); wav_io.write(struct.pack('<I', 36 + sum(len(a) for a in audios))); wav_io.write(b'WAVEfmt ')
                wav_io.write(struct.pack('<IHHIIHH', 16, 1, 1, shared.TTS_SAMPLE_RATE, shared.TTS_SAMPLE_RATE*2, 2, 16))
                wav_io.write(b'data'); wav_io.write(struct.pack('<I', sum(len(a) for a in audios)))
                for a in audios: wav_io.write(a)
                with open(os.path.join(shared.DATA_DIR, 'podcasts', f"{ep_id}.wav"), 'wb') as f: f.write(wav_io.getvalue())
            
            eps = load_data(EP_FILE, {})
            eps[ep_id] = {**data, "transcript": transcript, "status": "complete", "created_at": datetime.now().isoformat()}
            save_data(EP_FILE, eps)
            yield f"data: {json.dumps({'type': 'done'})}\n\n"
            
        except Exception as e: yield f"data: {json.dumps({'type': 'error', 'error': str(e)})}\n\n"
    return Response(gen(), mimetype='text/event-stream')