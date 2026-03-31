import os
import threading
import time

from flask import Blueprint, jsonify, request

import app.shared as shared

llm_bp = Blueprint('llm', __name__)

@llm_bp.route('/api/llm/models', methods=['GET'])
def get_llm_models():
    models = []
    llm_dir = os.path.join(shared.MODELS_DIR, 'llm')
    if os.path.exists(llm_dir):
        for f in os.listdir(llm_dir):
            if f.lower().endswith('.gguf'):
                size = os.path.getsize(os.path.join(llm_dir, f))
                models.append({"name": f, "size": size, "size_formatted": shared.format_size(size)})
    return jsonify({"success": True, "models": models})

@llm_bp.route('/api/llm/models/<path:filename>', methods=['DELETE'])
def delete_llm_model(filename):
    p = os.path.join(shared.MODELS_DIR, 'llm', filename)
    if os.path.exists(p):
        os.remove(p)
        return jsonify({"success": True})
    return jsonify({"success": False, "error": "Not found"}), 404

@llm_bp.route('/api/huggingface/search', methods=['GET'])
def hf_search():
    try:
        from huggingface_hub import list_models
        models = [{'id': m.id, 'name': m.id.replace('/', ' - '), 'source': 'huggingface'} for m in list_models(search=request.args.get('q', ''), limit=20)]
        return jsonify({"success": True, "models": models})
    except Exception as e: return jsonify({"success": False, "error": str(e)}), 500

@llm_bp.route('/api/huggingface/models/<path:model_id>', methods=['GET'])
def hf_files(model_id):
    try:
        from huggingface_hub import list_repo_files
        files = [{'name': f, 'size': 0, 'size_mb': 0} for f in list_repo_files(model_id, repo_type="model") if f.lower().endswith('.gguf')]
        return jsonify({"success": True, "files": files})
    except Exception as e: return jsonify({"success": False, "error": str(e)}), 400

@llm_bp.route('/api/llm/download', methods=['POST'])
def llm_download():
    url = request.get_json().get('url', '')
    if not url: return jsonify({"success": False}), 400
    
    import uuid
    did = str(uuid.uuid4())[:8]
    fname = url.split('/')[-1].split('?')[0]
    
    shared.downloads[did] = {"id": did, "url": url, "filename": fname, "status": "starting", "progress": 0, "total": 0, "downloaded": 0}
    
    def dl():
        try:
            import ssl
            import urllib.request
            ctx = ssl.create_default_context(); ctx.check_hostname = False; ctx.verify_mode = ssl.CERT_NONE
            req = urllib.request.Request(url, headers={'User-Agent': 'Omnix/1.0'})
            
            with urllib.request.urlopen(urllib.request.Request(url, method='HEAD'), context=ctx) as r:
                shared.downloads[did]['total'] = int(r.headers.get('Content-Length', 0))
                
            shared.downloads[did]['status'] = "downloading"
            start_time, d_bytes = time.time(), 0
            
            with urllib.request.urlopen(req, context=ctx) as r, open(os.path.join(shared.MODELS_DIR, 'llm', fname), 'wb') as f:
                while True:
                    if shared.downloads[did]['status'] == 'cancelled': break
                    chunk = r.read(1024 * 1024)
                    if not chunk: break
                    f.write(chunk); d_bytes += len(chunk)
                    elapsed = time.time() - start_time
                    shared.downloads[did].update({'downloaded': d_bytes, 'progress': (d_bytes / shared.downloads[did]['total'] * 100) if shared.downloads[did]['total'] else 0})
            
            if shared.downloads[did]['status'] != 'cancelled': shared.downloads[did]['status'] = "completed"
        except Exception as e: shared.downloads[did].update({"status": "error", "error": str(e)})
        
    threading.Thread(target=dl, daemon=True).start()
    return jsonify({"success": True, "download_id": did})

@llm_bp.route('/api/llm/download/status', methods=['GET'])
def dl_status():
    d = shared.downloads.get(request.args.get('id'))
    return jsonify({"success": True, "download": d}) if d else (jsonify({"success": False}), 404)

@llm_bp.route('/api/llm/download/stop', methods=['POST'])
def stop_dl():
    did = request.get_json().get('download_id')
    if did in shared.downloads:
        shared.downloads[did]['status'] = 'cancelled'
        try: os.remove(os.path.join(shared.MODELS_DIR, 'llm', shared.downloads[did]['filename']))
        except: pass
        return jsonify({"success": True})
    return jsonify({"success": False}), 404