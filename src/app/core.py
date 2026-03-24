import os
import requests
from datetime import datetime
from flask import Blueprint, render_template, request, jsonify, send_from_directory
import app.shared as shared
from app.providers import get_registry

core_bp = Blueprint('core', __name__)

@core_bp.after_app_request
def no_cache_voice_js(response):
    """Disable browser caching for voice module JS files so updates take effect immediately."""
    if request.path.startswith('/static/voice/') and request.path.endswith('.js'):
        response.headers['Cache-Control'] = 'no-store, no-cache, must-revalidate, max-age=0'
        response.headers['Pragma'] = 'no-cache'
        response.headers['Expires'] = '0'
    return response

@core_bp.route('/')
def index():
    return render_template('index.html')

@core_bp.route('/favicon.ico')
def favicon():
    return send_from_directory(os.path.join(shared.BASE_DIR, 'src', 'static'), 'favicon.ico', mimetype='image/x-icon')

@core_bp.route('/logo/<path:filename>')
def serve_logo(filename):
    return send_from_directory(os.path.join(shared.BASE_DIR, 'resources', 'logo'), filename)

@core_bp.route('/api/settings', methods=['GET'])
def get_settings():
    settings = shared.load_settings()
    for key in ['openrouter', 'cerebras']:
        if settings.get(key, {}).get('api_key'):
            settings[key]['api_key'] = "***" + settings[key]['api_key'][-4:] if len(settings[key]['api_key']) > 4 else "****"
    return jsonify({"success": True, "settings": settings})

@core_bp.route('/api/settings', methods=['POST'])
def save_settings_endpoint():
    data = request.get_json()
    settings = shared.load_settings()
    
    if 'provider' in data:
        settings['provider'] = data['provider']
    if 'global_system_prompt' in data:
        settings['global_system_prompt'] = data['global_system_prompt']
    if 'lmstudio' in data:
        settings['lmstudio'].update(data['lmstudio'])
    
    for key in ['openrouter', 'cerebras']:
        if key in data:
            if key not in settings:
                settings[key] = {}
            if data[key].get('api_key') and not data[key]['api_key'].startswith('***'):
                settings[key]['api_key'] = data[key]['api_key']
            settings[key].update({k: v for k, v in data[key].items() if k != 'api_key'})
            
    if 'llamacpp' in data:
        if 'llamacpp' not in settings:
            settings['llamacpp'] = shared.DEFAULT_SETTINGS['llamacpp'].copy()
        settings['llamacpp'].update(data['llamacpp'])
        
    shared.save_settings(settings)
    return jsonify({"success": True})

@core_bp.route('/api/models', methods=['GET'])
def get_models():
    """Get available models from the current provider."""
    provider = shared.get_provider()
    if not provider:
        return jsonify({"success": False, "error": "Provider not available"}), 500
    
    try:
        models = provider.get_models()
        # Convert ModelInfo objects to dict format expected by frontend
        models_data = [{
            "id": m.id,
            "name": m.name,
            "provider": m.provider,
            "context_length": m.context_length,
            "description": m.description
        } for m in models]
        return jsonify({"success": True, "models": models_data, "provider": provider.provider_name})
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500

@core_bp.route('/api/providers', methods=['GET'])
def list_providers():
    """List all available providers."""
    try:
        registry = get_registry()
        providers = registry.list_providers()
        # Add current provider info
        settings = shared.load_settings()
        current_provider = settings.get('provider', 'lmstudio')
        return jsonify({
            "success": True,
            "providers": providers,
            "current_provider": current_provider
        })
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500

@core_bp.route('/api/providers/<provider_name>/schema', methods=['GET'])
def get_provider_schema(provider_name):
    """Get configuration schema for a specific provider."""
    try:
        registry = get_registry()
        provider_class = registry.get_provider_class(provider_name)
        if not provider_class:
            return jsonify({"success": False, "error": f"Provider '{provider_name}' not found"}), 404
        
        # Create a temporary instance to get schema (with default config)
        from app.providers import ProviderConfig
        provider = provider_class(ProviderConfig(provider_type=provider_name))
        schema = provider.get_config_schema()
        return jsonify({"success": True, "schema": schema})
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500

@core_bp.route('/api/sessions', methods=['GET', 'POST'])
def handle_sessions():
    shared.sessions_data = shared.load_sessions()
    if request.method == 'GET':
        sl = sorted(
            [{'id': k, 'title': v.get('title', 'New Chat'), 'updated_at': v.get('updated_at', '')} 
             for k, v in shared.sessions_data.items()],
            key=lambda x: x['updated_at'],
            reverse=True
        )
        return jsonify({"success": True, "sessions": sl})
        
    import uuid
    sid = str(uuid.uuid4())[:8]
    shared.sessions_data[sid] = {
        'title': 'New Chat',
        'messages': [],
        'system_prompt': shared.get_global_system_prompt(),
        'created_at': datetime.now().isoformat(),
        'updated_at': datetime.now().isoformat()
    }
    shared.save_sessions(shared.sessions_data)
    return jsonify({"success": True, "session_id": sid})

@core_bp.route('/api/sessions/<session_id>', methods=['GET', 'DELETE', 'PUT'])
def handle_session(session_id):
    shared.sessions_data = shared.load_sessions()
    if session_id not in shared.sessions_data:
        return jsonify({"success": False, "error": "Not found"}), 404
    
    if request.method == 'GET':
        return jsonify({"success": True, "session": shared.sessions_data[session_id]})
    elif request.method == 'DELETE':
        del shared.sessions_data[session_id]
        shared.save_sessions(shared.sessions_data)
        return jsonify({"success": True})
    elif request.method == 'PUT':
        data = request.get_json()
        if 'title' in data:
            shared.sessions_data[session_id]['title'] = data['title']
        if 'system_prompt' in data:
            shared.sessions_data[session_id]['system_prompt'] = data['system_prompt']
        shared.sessions_data[session_id]['updated_at'] = datetime.now().isoformat()
        shared.save_sessions(shared.sessions_data)
        return jsonify({"success": True})

@core_bp.route('/api/clear', methods=['POST'])
def clear_session():
    sid = request.get_json().get('session_id', 'default')
    shared.sessions_data = shared.load_sessions()
    if sid in shared.sessions_data:
        shared.sessions_data[sid]['messages'] = []
        shared.sessions_data[sid]['updated_at'] = datetime.now().isoformat()
        shared.save_sessions(shared.sessions_data)
    return jsonify({"success": True})

@core_bp.route('/api/health', methods=['GET'])
def health_check():
    """Check health of current provider."""
    provider = shared.get_provider()
    if not provider:
        return jsonify({"status": "disconnected", "message": "Provider not available", "provider": "unknown"}), 200
    
    try:
        is_healthy = provider.test_connection()
        status = "connected" if is_healthy else "disconnected"
        return jsonify({
            "status": status,
            "provider": provider.provider_name,
            "message": "OK" if is_healthy else "Connection failed"
        })
    except Exception as e:
        # Log the error for debugging
        print(f"[HEALTH CHECK] Error checking {provider.provider_name} connection: {e}")
        return jsonify({
            "status": "disconnected",
            "provider": provider.provider_name,
            "message": str(e)
        }), 200

@core_bp.route('/api/providers/status', methods=['GET'])
def providers_status():
    """Check status of all providers including TTS."""
    try:
        # Check LLM provider status
        llm_provider = shared.get_provider()
        llm_status = {
            "available": False,
            "provider": "unknown",
            "message": "Provider not available"
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
                print(f"[PROVIDERS STATUS] Error checking {llm_provider.provider_name} connection: {e}")
                llm_status = {
                    "available": False,
                    "provider": llm_provider.provider_name,
                    "message": str(e)
                }
        
        # Check TTS provider status using singleton pattern
        tts_status = {
            "available": False,
            "provider": "unknown",
            "message": "TTS provider not available"
        }
        
        try:
            # Use the singleton pattern to get the current TTS provider
            tts_provider = shared.get_tts_provider()
            
            if tts_provider:
                try:
                    is_healthy = tts_provider.test_connection()
                    tts_status = {
                        "available": is_healthy,
                        "provider": tts_provider.provider_name,
                        "message": "OK" if is_healthy else "Connection failed"
                    }
                except Exception as e:
                    print(f"[PROVIDERS STATUS] Error checking {tts_provider.provider_name} connection: {e}")
                    tts_status = {
                        "available": False,
                        "provider": tts_provider.provider_name,
                        "message": str(e)
                    }
        except Exception as e:
            print(f"[PROVIDERS STATUS] Error checking TTS provider: {e}")
        
        return jsonify({
            "success": True,
            "llm": llm_status,
            "tts": tts_status
        })
    except Exception as e:
        print(f"[PROVIDERS STATUS] Error checking providers status: {e}")
        return jsonify({
            "success": False,
            "error": str(e),
            "llm": {"available": False, "provider": "unknown", "message": "Error checking status"},
            "tts": {"available": False, "provider": "unknown", "message": "Error checking status"}
        }), 500