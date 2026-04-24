import hashlib
import json
import os
import re
from typing import Any, Dict, Optional

# Base paths - project root (parent of src/)
BASE_DIR = os.path.dirname(os.path.dirname(os.path.dirname(__file__)))
RESOURCES_DIR = os.path.join(BASE_DIR, 'resources')
DATA_DIR = os.path.join(RESOURCES_DIR, 'data')
MODELS_DIR = os.path.join(RESOURCES_DIR, 'models')
VOICE_CLONES_DIR = os.path.join(RESOURCES_DIR, 'voice_clones')
LOGO_DIR = os.path.join(RESOURCES_DIR, 'logo')
LOGS_DIR = os.path.join(RESOURCES_DIR, 'logs')
os.makedirs(DATA_DIR, exist_ok=True)
os.makedirs(LOGS_DIR, exist_ok=True)

SESSIONS_FILE = os.path.join(DATA_DIR, 'sessions.json')
SETTINGS_FILE = os.path.join(DATA_DIR, 'settings.json')
VOICE_CLONES_FILE = os.path.join(VOICE_CLONES_DIR, 'voice_clones.json')

# Create necessary directories
os.makedirs(os.path.join(MODELS_DIR, 'llm'), exist_ok=True)
os.makedirs(os.path.join(MODELS_DIR, 'server'), exist_ok=True)
os.makedirs(VOICE_CLONES_DIR, exist_ok=True)

# Shared Service Constants
TTS_SAMPLE_RATE = 24000
TARGET_SR = TTS_SAMPLE_RATE  # canonical playback sample-rate for the whole pipeline
STT_BASE_URL = "http://localhost:8000"

# Secrets file path
SECRETS_FILE = os.path.join(DATA_DIR, 'secrets.json')

# Global Shared States
sessions_data = {}
custom_voices = {}
downloads = {}
llamacpp_server_downloads = {}

# Singleton Provider Instances
_tts_provider_instance = None
_tts_provider_name = None
_stt_provider_instance = None
_stt_provider_name = None

# LLM provider cache — avoids repeated construction in hot loops (RPG turns).
_PROVIDER_CACHE: Dict[str, Any] = {
    "key": None,
    "instance": None,
}

# Provider system
from app.providers import BaseProvider, ProviderConfig, get_registry
from app.providers.audio_registry import (
    get_audio_registry,
    get_stt_provider,
    get_tts_provider,
)

DEFAULT_SETTINGS = {
    "provider": "lmstudio",
    "audio_provider_tts": "faster-qwen3-tts",
    "audio_provider_stt": "parakeet",
    "global_system_prompt": """You are Maya, a warm, friendly, emotionally aware AI. Keep responses short (1-3 sentences for voice, 5 for text), match the user's emotional tone, avoid filler and tangents. Be clear and concise, admit uncertainty when needed, and maintain a natural, human-like presence.""",
    "lmstudio": {"base_url": "http://localhost:1234", "direct": False},
    "openrouter": {"api_key": "", "model": "openai/gpt-4o-mini", "context_size": 128000, "thinking_budget": 0},
    "cerebras": {"api_key": "", "model": "llama-3.3-70b-versatile"},
    "llamacpp": {"base_url": "http://localhost:8080", "model": "", "download_location": "server", "auto_start": False},
    "faster-qwen3-tts": {
        "model_name": "Qwen/Qwen3-TTS-12Hz-0.6B-Base",
        "model_dir": "",
        "device": "cuda",
        "dtype": "bfloat16",
        "max_seq_len": 2048,
        "chunk_size": 12,
        "temperature": 0.9,
        "top_k": 50,
        "top_p": 1.0,
        "do_sample": True,
        "repetition_penalty": 1.05,
        "xvec_only": True,
        "non_streaming_mode": True,
        "append_silence": True
    },
    "parakeet": {"base_url": "http://localhost:8000"},
    "image": {
        "enabled": False,
        "provider": "flux_klein",
        "auto_unload_on_disable": True,
        "chat": {
            "auto_generate_images": False,
            "style": "",
        },
        "story": {
            "auto_generate_scene_images": False,
            "auto_generate_cover_images": False,
            "style": "story",
        },
        "mock": {
            "enabled": True,
        },
        "flux_klein": {
            "enabled": False,
            "repo_id": "black-forest-labs/FLUX.2-klein-4B",
            "variant": "distilled",
            "base_repo_id": "black-forest-labs/FLUX.2-klein-base-4B",
            "download_dir": "image",
            "local_dir": "",
            "device": "cuda",
            "torch_dtype": "bfloat16",
            "enable_cpu_offload": False,
            "prefer_local_files": True,
            "allow_repo_fallback": False,
            "num_inference_steps": 3,
            "guidance_scale": 1.0,
            "cuda_empty_cache_after_generate": False,
            "width": 768,
            "height": 768,
            "portrait_width": 512,
            "portrait_height": 768,
            "scene_width": 768,
            "scene_height": 512,
        },
    },
    "rpg_visual": {
        "enabled": False,
        "provider": "mock",
        "auto_unload_on_disable": True,
        "flux_klein": {
            "enabled": False,
            "repo_id": "black-forest-labs/FLUX.2-klein-4B",
            "variant": "distilled",  # distilled | base
            "base_repo_id": "black-forest-labs/FLUX.2-klein-base-4B",
            "download_dir": "image",
            "local_dir": "",
            "device": "cuda",
            "torch_dtype": "bfloat16",
            "enable_cpu_offload": False,
            "prefer_local_files": True,
            "allow_repo_fallback": False,
            "num_inference_steps": 3,
            "guidance_scale": 1.0,
            "portrait_width": 512,
            "portrait_height": 768,
            "scene_width": 768,
            "scene_height": 512,
            "item_width": 1024,
            "item_height": 1024
        }
    },
}

DEFAULT_SYSTEM_PROMPT = "You are a helpful AI assistant."

def migrate_settings(settings: Dict[str, Any]) -> Dict[str, Any]:
    """
    Migrate old settings format to new provider-based format.
    
    Args:
        settings: Old settings dictionary
        
    Returns:
        Migrated settings dictionary
    """
    # Check if already migrated (has provider-specific configs at top level)
    if 'provider' in settings and any(key in settings for key in ['lmstudio', 'openrouter', 'cerebras', 'llamacpp']):
        # Already in new format or mixed - ensure all provider configs exist
        for key in ['cerebras', 'openrouter', 'lmstudio', 'llamacpp']:
            if key not in settings:
                settings[key] = DEFAULT_SETTINGS[key].copy()
        # Ensure audio provider settings exist
        if 'audio_provider_tts' not in settings:
            settings['audio_provider_tts'] = DEFAULT_SETTINGS['audio_provider_tts']
        if 'audio_provider_stt' not in settings:
            settings['audio_provider_stt'] = DEFAULT_SETTINGS['audio_provider_stt']
        if 'parakeet' not in settings:
            settings['parakeet'] = DEFAULT_SETTINGS['parakeet']
        if 'image' not in settings:
            settings['image'] = json.loads(json.dumps(DEFAULT_SETTINGS['image']))
        else:
            image = dict(settings.get('image') or {})
            flux = dict(image.get('flux_klein') or {})
            merged_image = json.loads(json.dumps(DEFAULT_SETTINGS['image']))
            merged_image.update(image)
            merged_mock = dict(merged_image.get('mock') or {})
            merged_mock.update(dict(image.get('mock') or {}))
            merged_image['mock'] = merged_mock
            merged_flux = dict(merged_image.get('flux_klein') or {})
            merged_flux.update(flux)
            merged_image['flux_klein'] = merged_flux
            settings['image'] = merged_image
        if 'rpg_visual' not in settings:
            settings['rpg_visual'] = json.loads(json.dumps(DEFAULT_SETTINGS['rpg_visual']))
        else:
            visual = dict(settings.get('rpg_visual') or {})
            flux = dict(visual.get('flux_klein') or {})
            merged_visual = json.loads(json.dumps(DEFAULT_SETTINGS['rpg_visual']))
            merged_visual.update(visual)
            merged_flux = dict(merged_visual.get('flux_klein') or {})
            merged_flux.update(flux)
            merged_visual['flux_klein'] = merged_flux
            settings['rpg_visual'] = merged_visual
        return settings
    
    # Old format - migrate
    migrated = settings.copy()
    
    # Ensure provider key exists
    if 'provider' not in migrated:
        migrated['provider'] = 'lmstudio'
    
    # Initialize provider configs if not present
    for key in ['cerebras', 'openrouter', 'lmstudio', 'llamacpp']:
        if key not in migrated:
            migrated[key] = DEFAULT_SETTINGS[key].copy()
    
    # Initialize audio provider configs if not present
    if 'audio_provider_tts' not in migrated:
        migrated['audio_provider_tts'] = DEFAULT_SETTINGS['audio_provider_tts']
    if 'audio_provider_stt' not in migrated:
        migrated['audio_provider_stt'] = DEFAULT_SETTINGS['audio_provider_stt']
    if 'parakeet' not in migrated:
        migrated['parakeet'] = DEFAULT_SETTINGS['parakeet']
    if 'rpg_visual' not in migrated:
        migrated['rpg_visual'] = json.loads(json.dumps(DEFAULT_SETTINGS['rpg_visual']))
    
    # Migrate old base_url to lmstudio config
    if 'base_url' in migrated:
        migrated['lmstudio']['base_url'] = migrated.pop('base_url')
    
    return migrated

def load_secrets():
    """Load API keys and sensitive configuration from secrets file."""
    if os.path.exists(SECRETS_FILE):
        try:
            with open(SECRETS_FILE, 'r') as f:
                return json.load(f)
        except Exception as e:
            print(f"Error loading secrets: {e}")
    return {"api_keys": {}}


def _llm_provider_cache_inputs_from_settings(settings: Dict[str, Any]) -> Dict[str, Any]:
    """Extract only the settings fields that affect LLM provider construction."""
    settings = migrate_settings(dict(settings or {}))
    return {
        "provider": settings.get("provider", DEFAULT_SETTINGS["provider"]),
        "lmstudio": dict(settings.get("lmstudio", {})),
        "openrouter": dict(settings.get("openrouter", {})),
        "cerebras": dict(settings.get("cerebras", {})),
        "llamacpp": dict(settings.get("llamacpp", {})),
    }


def _llm_provider_cache_inputs_from_secrets(secrets: Dict[str, Any]) -> Dict[str, Any]:
    """Extract only the secret fields that affect LLM provider construction."""
    api_keys = dict((secrets or {}).get("api_keys", {}) or {})
    return {
        "api_keys": {
            "openrouter": api_keys.get("openrouter", ""),
            "cerebras": api_keys.get("cerebras", ""),
        }
    }


def save_secrets(secrets):
    """Save API keys and sensitive configuration to secrets file."""
    previous_inputs = _llm_provider_cache_inputs_from_secrets(load_secrets())
    next_inputs = _llm_provider_cache_inputs_from_secrets(secrets)

    with open(SECRETS_FILE, 'w') as f:
        json.dump(secrets, f, indent=2)

    if previous_inputs != next_inputs:
        invalidate_provider_cache()

def load_settings():
    if os.path.exists(SETTINGS_FILE):
        try:
            with open(SETTINGS_FILE, 'r') as f:
                settings = json.load(f)
                # Migrate old settings format
                settings = migrate_settings(settings)
                # Ensure all provider configs exist
                for key in ['cerebras', 'openrouter', 'lmstudio', 'llamacpp']:
                    if key not in settings:
                        settings[key] = DEFAULT_SETTINGS[key].copy()
                return settings
        except Exception as e:
            print(f"Error loading settings: {e}, using defaults")
    return DEFAULT_SETTINGS.copy()

def save_settings(settings):
    settings = migrate_settings(dict(settings or {}))
    previous_inputs = _llm_provider_cache_inputs_from_settings(load_settings())
    next_inputs = _llm_provider_cache_inputs_from_settings(settings)
    previous_settings = load_settings()

    with open(SETTINGS_FILE, 'w') as f:
        json.dump(settings, f, indent=2)

    if previous_inputs != next_inputs:
        invalidate_provider_cache()

    try:
        prev_visual = dict(previous_settings.get("rpg_visual") or {})
        next_visual = dict(settings.get("rpg_visual") or {})
        prev_enabled = bool(prev_visual.get("enabled"))
        next_enabled = bool(next_visual.get("enabled"))
        prev_provider = str(prev_visual.get("provider") or "mock").strip().lower()
        next_provider = str(next_visual.get("provider") or "mock").strip().lower()
        should_unload = (
            (prev_enabled and not next_enabled and bool(next_visual.get("auto_unload_on_disable", True)))
            or (prev_provider != next_provider)
            or (prev_enabled and next_enabled and prev_provider == "flux_klein" and next_provider == "flux_klein" and prev_visual != next_visual)
        )
        if should_unload:
            from app.rpg.visual.providers import unload_image_provider_cache
            unload_image_provider_cache()
    except Exception:
        pass

def load_sessions():
    if os.path.exists(SESSIONS_FILE):
        try:
            with open(SESSIONS_FILE, 'r') as f:
                return json.load(f)
        except: pass
    return {}

def save_sessions(sessions):
    with open(SESSIONS_FILE, 'w') as f:
        json.dump(sessions, f, indent=2)

def extract_thinking(content):
    """Extract thinking/analysis from content."""
    if not content:
        return "", content
    
    lines = content.split('\n')
    thinking_lines, answer_lines = [], []
    found_thinking = False
    
    for i, line in enumerate(lines):
        stripped = line.strip()
        # Check for numbered list indicators (1., 2., etc.)
        if stripped and all(stripped.startswith(f"{n}.") for n in range(1, 10) if stripped.startswith(f"{n}.")):
            if not found_thinking and i > 0 and any(m in '\n'.join(lines[:i]).lower() for m in ['analyze', 'identify', 'determine']):
                thinking_lines, answer_lines = lines[:i], lines[i:]
                found_thinking = True
                continue
        # Check for thinking-indicator phrases
        if not found_thinking and any(m in stripped.lower() for m in ['analyze', 'identify the intent', 'determine the answer', 'formulate', 'final output']):
            thinking_lines, answer_lines = lines[:i], lines[i:]
            found_thinking = True
    
    if thinking_lines and answer_lines:
        t_text = '\n'.join(thinking_lines).strip()
        a_text = '\n'.join(answer_lines).strip()
        if len(t_text) > 20:
            return t_text, a_text
    
    # Fallback: check for  tags (simple approach)
    if '思考过程' in content or 'thinking' in content.lower():
        # This is a placeholder - could be enhanced
        pass
    
    return "", content

def _build_provider_cache_key(provider_name: str, provider_config: "ProviderConfig") -> str:
    """Build a stable cache key from provider configuration.

    Uses a SHA-256 hash of the API key rather than the raw secret so that
    sensitive material is not held in a general-purpose cache key string.
    """
    raw_key = getattr(provider_config, "api_key", "") or ""
    key_hash = hashlib.sha256(raw_key.encode("utf-8")).hexdigest()[:16] if raw_key else ""
    parts = [
        provider_name,
        getattr(provider_config, "base_url", "") or "",
        getattr(provider_config, "model", "") or "",
        key_hash,
    ]
    return "|".join(parts)


def invalidate_provider_cache() -> None:
    """Clear the cached LLM provider so the next get_provider() builds fresh."""
    _PROVIDER_CACHE["key"] = None
    _PROVIDER_CACHE["instance"] = None


def get_provider(provider_name: Optional[str] = None) -> Optional[BaseProvider]:
    """
    Get a provider instance based on settings.

    Uses a lightweight cache keyed on (provider, base_url, model, api_key)
    so that repeated calls within the same process (e.g. multiple RPG turn
    phases) return the same instance instead of rebuilding from scratch.

    Args:
        provider_name: Optional provider name override, otherwise uses settings

    Returns:
        BaseProvider instance or None if not available
    """
    settings = load_settings()
    secrets = load_secrets()
    provider = provider_name or settings.get('provider', 'lmstudio')
    
    # Build provider config from settings
    provider_config = None
    try:
        if provider == 'openrouter':
            or_settings = settings.get('openrouter', {})
            # Get API key from secrets file first, fallback to settings
            api_key = secrets.get('api_keys', {}).get('openrouter', '') or or_settings.get('api_key', '')
            provider_config = ProviderConfig(
                provider_type='openrouter',
                api_key=api_key,
                base_url='https://openrouter.ai/api/v1',
                model=or_settings.get('model', 'openai/gpt-4o-mini'),
                extra_params={
                    'thinking_budget': or_settings.get('thinking_budget', 0),
                    'context_size': or_settings.get('context_size', 128000)
                }
            )
        elif provider == 'cerebras':
            cb_settings = settings.get('cerebras', {})
            # Get API key from secrets file first, fallback to settings
            api_key = secrets.get('api_keys', {}).get('cerebras', '') or cb_settings.get('api_key', '')
            provider_config = ProviderConfig(
                provider_type='cerebras',
                api_key=api_key,
                base_url='https://api.cerebras.ai',
                model=cb_settings.get('model', 'llama-3.3-70b-versatile')
            )
        elif provider == 'llamacpp':
            lp_settings = settings.get('llamacpp', {})
            dl_loc = lp_settings.get('download_location', 'server')
            model_dir = os.path.join(MODELS_DIR, dl_loc)
            provider_config = ProviderConfig(
                provider_type='llamacpp',
                base_url=lp_settings.get('base_url', 'http://localhost:8080'),
                model=lp_settings.get('model', ''),
                extra_params={
                    'download_location': dl_loc,
                    'model_dir': model_dir,
                    'auto_start': lp_settings.get('auto_start', False)
                }
            )
        else:  # lmstudio (default)
            ls_settings = settings.get('lmstudio', {})
            provider_config = ProviderConfig(
                provider_type='lmstudio',
                base_url=ls_settings.get('base_url', 'http://localhost:1234'),
                model=ls_settings.get('model', '')
            )

        # Check cache before creating a new provider instance
        cache_key = _build_provider_cache_key(provider, provider_config)
        if _PROVIDER_CACHE["key"] == cache_key and _PROVIDER_CACHE["instance"] is not None:
            return _PROVIDER_CACHE["instance"]

        # Create provider instance using registry
        registry = get_registry()
        provider_instance = registry.create_provider(provider, provider_config=provider_config)

        # Store in cache
        _PROVIDER_CACHE["key"] = cache_key
        _PROVIDER_CACHE["instance"] = provider_instance
        return provider_instance
        
    except Exception as e:
        print(f"Error creating provider '{provider}': {e}")
        return None

def get_provider_config():
    """
    Legacy function for backward compatibility.
    Returns provider config dict in old format.
    New code should use get_provider() instead.
    """
    settings = load_settings()
    provider = settings.get('provider', 'lmstudio')
    
    if provider == 'openrouter':
        return {'provider': 'openrouter', 'api_key': settings['openrouter'].get('api_key', ''), 'model': settings['openrouter'].get('model', 'openai/gpt-4o-mini'), 'base_url': 'https://openrouter.ai/api/v1', 'context_size': settings['openrouter'].get('context_size', 128000), 'thinking_budget': settings['openrouter'].get('thinking_budget', 0)}
    elif provider == 'cerebras':
        return {'provider': 'cerebras', 'api_key': settings['cerebras'].get('api_key', ''), 'model': settings['cerebras'].get('model', 'llama-3.3-70b-versatile'), 'base_url': 'https://api.cerebras.ai'}
    elif provider == 'llamacpp':
        l_settings = settings.get('llamacpp', {})
        dl_loc = l_settings.get('download_location', 'server')
        model_dir = os.path.join(MODELS_DIR, dl_loc)
        return {'provider': 'llamacpp', 'base_url': l_settings.get('base_url', 'http://localhost:8080'), 'model': l_settings.get('model', ''), 'download_location': dl_loc, 'model_dir': model_dir}
    return {'provider': 'lmstudio', 'base_url': settings['lmstudio'].get('base_url', 'http://localhost:1234')}

def get_global_system_prompt():
    return load_settings().get('global_system_prompt', DEFAULT_SYSTEM_PROMPT)

def get_tts_provider(provider_name: Optional[str] = None) -> Optional[Any]:
    """
    Get a TTS provider instance based on settings using singleton pattern.
    
    Args:
        provider_name: Optional provider name override, otherwise uses settings
        
    Returns:
        TTS provider instance or None if not available
    """
    global _tts_provider_instance, _tts_provider_name
    
    settings = load_settings()
    provider = provider_name or settings.get('audio_provider_tts', 'faster-qwen3-tts')
    
    # Check if we already have the correct provider cached
    if _tts_provider_instance is not None and _tts_provider_name == provider:
        return _tts_provider_instance
    
    # If we have a different provider cached, stop it first
    if _tts_provider_instance is not None:
        try:
            _tts_provider_instance.stop()
        except Exception as e:
            print(f"Error stopping previous TTS provider: {e}")
        _tts_provider_instance = None
        _tts_provider_name = None
    
    # Build provider config from settings
    provider_config = None
    try:
        provider_settings = settings.get(provider, {})
        
        if provider == 'faster-qwen3-tts':
            # For faster-qwen3-tts, use the full settings as config
            provider_config = provider_settings
        else:
            # For other providers, use the base URL approach
            base_url = provider_settings.get("base_url")
            if not base_url:
                # Fallback to default base URL if not configured
                if provider == 'parakeet':
                    base_url = "http://localhost:8000"
                else:
                    base_url = None
            
            provider_config = {
                "base_url": base_url,
                "timeout": provider_settings.get("timeout", 300),
                "max_retries": provider_settings.get("max_retries", 3),
                "extra_params": provider_settings.get("extra_params", {})
            }
        
        # Create provider instance using audio registry
        registry = get_audio_registry()
        provider_instance = registry.create_tts_provider(provider, config=provider_config)
        
        # Start the provider if it has a start method
        if provider_instance and hasattr(provider_instance, 'start'):
            try:
                start_result = provider_instance.start()
                if not start_result.get('running', False):
                    print(f"Failed to start TTS provider '{provider}': {start_result.get('message', 'Unknown error')}")
                    return None
            except Exception as e:
                print(f"Error starting TTS provider '{provider}': {e}")
                return None
        
        # Cache the successful instance
        _tts_provider_instance = provider_instance
        _tts_provider_name = provider
        
        return provider_instance
        
    except Exception as e:
        print(f"Error creating TTS provider '{provider}': {e}")
        return None

def get_stt_provider(provider_name: Optional[str] = None) -> Optional[Any]:
    """
    Get an STT provider instance based on settings using singleton pattern.
    
    Args:
        provider_name: Optional provider name override, otherwise uses settings
        
    Returns:
        STT provider instance or None if not available
    """
    global _stt_provider_instance, _stt_provider_name
    
    settings = load_settings()
    provider = provider_name or settings.get('audio_provider_stt', 'parakeet')
    
    # Check if we already have the correct provider cached
    if _stt_provider_instance is not None and _stt_provider_name == provider:
        return _stt_provider_instance
    
    # If we have a different provider cached, stop it first
    if _stt_provider_instance is not None:
        try:
            _stt_provider_instance.stop()
        except Exception as e:
            print(f"Error stopping previous STT provider: {e}")
        _stt_provider_instance = None
        _stt_provider_name = None
    
    # Build provider config from settings
    provider_config = None
    try:
        provider_settings = settings.get(provider, {})
        provider_config = {
            "base_url": provider_settings.get("base_url"),
            "timeout": provider_settings.get("timeout", 300),
            "max_retries": provider_settings.get("max_retries", 3),
            "extra_params": provider_settings.get("extra_params", {})
        }
        
        # Create provider instance using audio registry
        registry = get_audio_registry()
        provider_instance = registry.create_stt_provider(provider, config=provider_config)
        
        # Start the provider if it has a start method
        if provider_instance and hasattr(provider_instance, 'start'):
            try:
                start_result = provider_instance.start()
                if not start_result.get('running', False):
                    print(f"Failed to start STT provider '{provider}': {start_result.get('message', 'Unknown error')}")
                    return None
            except Exception as e:
                print(f"Error starting STT provider '{provider}': {e}")
                return None
        
        # Cache the successful instance
        _stt_provider_instance = provider_instance
        _stt_provider_name = provider
        
        return provider_instance
        
    except Exception as e:
        print(f"Error creating STT provider '{provider}': {e}")
        return None

def remove_emojis(text):
    if not text: return text
    emoji_pattern = re.compile(u"[\U0001F600-\U0001F64F\U0001F300-\U0001F5FF\U0001F680-\U0001F6FF\U0001F1E0-\U0001F1FF\u2702-\u27B0\u24C2-\U0001F251]+", flags=re.UNICODE)
    return emoji_pattern.sub(r'', text)

def format_size(bytes_size):
    for unit in ['B', 'KB', 'MB', 'GB', 'TB']:
        if bytes_size < 1024.0: return f"{bytes_size:.1f} {unit}"
        bytes_size /= 1024.0
    return f"{bytes_size:.1f} PB"

# Startup Initializations
def _init_custom_voices():
    if os.path.exists(VOICE_CLONES_FILE):
        try:
            with open(VOICE_CLONES_FILE, 'r') as f:
                custom_voices.update(json.load(f))
        except: pass
    
    clones_dir = VOICE_CLONES_DIR
    if os.path.exists(clones_dir):
        for w in os.listdir(clones_dir):
            if w.lower().endswith('.wav'):
                vid = os.path.splitext(w)[0]
                if vid not in custom_voices:
                    custom_voices[vid] = {"speaker": "default", "language": "en", "voice_clone_id": vid, "has_audio": True, "is_preloaded": True, "gender": "neutral"}

    # Ensure all existing entries have the gender field
    for vid, vdata in custom_voices.items():
        if "gender" not in vdata:
            vdata["gender"] = "neutral"

    with open(VOICE_CLONES_FILE, 'w') as f:
        json.dump(custom_voices, f, indent=2)

_init_custom_voices()