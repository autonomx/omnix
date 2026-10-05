"""
API validation/healthcheck tests for FastAPI server.
Run this while the server is running on localhost:5000

Note: Some endpoints are Flask-only and return 404 on FastAPI.
"""

import sys

import requests

BASE_URL = "http://localhost:5000"

passed = 0
failed = 0
skipped = 0


def check_endpoint(method, path, data=None, expected_status=200, timeout=5, note=""):
    global passed, failed, skipped
    url = f"{BASE_URL}{path}"
    try:
        if method == "GET":
            resp = requests.get(url, timeout=timeout)
        elif method == "POST":
            resp = requests.post(url, json=data, timeout=timeout)
        elif method == "PUT":
            resp = requests.put(url, json=data, timeout=timeout)
        elif method == "DELETE":
            resp = requests.delete(url, timeout=timeout)
        
        status_ok = resp.status_code == expected_status
        if status_ok:
            print(f"[PASS] {method} {path}")
            passed += 1
        else:
            print(f"[FAIL] {method} {path} - Expected: {expected_status}, Got: {resp.status_code} {note}")
            if resp.text and len(resp.text) < 200:
                print(f"         Response: {resp.text}")
            failed += 1
        return resp
    except requests.exceptions.Timeout:
        print(f"[TIMEOUT] {method} {path}")
        failed += 1
        return None
    except Exception as e:
        print(f"[ERROR] {method} {path} - {e}")
        failed += 1
        return None


def check_flask_endpoint(method, path, note="(Flask-only)"):
    """Test endpoint that only exists in Flask, not FastAPI"""
    global passed, failed, skipped
    url = f"{BASE_URL}{path}"
    try:
        if method == "GET":
            resp = requests.get(url, timeout=5)
        elif method == "POST":
            resp = requests.post(url, timeout=5)
        
        if resp.status_code == 404:
            print(f"[SKIP] {method} {path} {note}")
            skipped += 1
        elif resp.status_code >= 200 and resp.status_code < 300:
            print(f"[PASS] {method} {path} {note}")
            passed += 1
        else:
            print(f"[FAIL] {method} {path} - Got: {resp.status_code} {note}")
            failed += 1
    except Exception as e:
        print(f"[ERROR] {method} {path} - {e}")


def main():
    global passed, failed, skipped
    print("=" * 60)
    print("API Healthcheck Tests")
    print("=" * 60)
    print()
    
    # Core endpoints
    print("--- Core Endpoints ---")
    check_endpoint("GET", "/")
    check_endpoint("GET", "/health")
    check_endpoint("GET", "/api/health")
    check_flask_endpoint("GET", "/favicon.ico", "(Flask-only)")
    check_flask_endpoint("GET", "/api/providers", "(Flask-only)")
    print()
    
    # Settings
    print("--- Settings ---")
    check_endpoint("GET", "/api/settings")
    check_endpoint("POST", "/api/settings", {"provider": "cerebras"})
    print()
    
    # Models
    print("--- Models ---")
    check_endpoint("GET", "/api/models")
    check_endpoint("GET", "/api/llm/models")
    check_endpoint("GET", "/api/openrouter/models")
    check_flask_endpoint("GET", "/api/huggingface/search", "(Flask-only)")
    check_flask_endpoint("GET", "/api/llamacpp/releases", "(Flask-only)")
    print()
    
    # Sessions
    print("--- Sessions ---")
    check_endpoint("GET", "/api/sessions")
    resp = check_endpoint("POST", "/api/sessions", {})
    if resp and resp.status_code == 200:
        try:
            session_id = resp.json().get("session_id")
            if session_id:
                check_endpoint("GET", f"/api/sessions/{session_id}")
                check_endpoint("PUT", f"/api/sessions/{session_id}", {"title": "Test"})
                check_endpoint("DELETE", f"/api/sessions/{session_id}")
        except:
            pass
    print()
    
    # Chat
    print("--- Chat ---")
    check_flask_endpoint("POST", "/api/chat", "(Flask-only)")
    check_endpoint("POST", "/api/chat/stream", {"message": "hello", "session_id": "test"}, timeout=10)
    check_endpoint("POST", "/api/sessions/generate-title", {"user_message": "hi", "ai_response": "hello"})
    print()
    
    # TTS
    print("--- TTS ---")
    check_endpoint("GET", "/api/tts/speakers")
    check_endpoint("POST", "/api/tts", {"text": "hello"}, timeout=60)
    check_endpoint("POST", "/api/tts/stream", {"text": "hello"}, timeout=60)
    print()
    
    # STT
    print("--- STT ---")
    check_endpoint("POST", "/api/stt", {"audio": ""}, expected_status=400, timeout=30)  # Expect 400 for missing audio
    print()
    
    # Providers
    print("--- Providers ---")
    check_endpoint("GET", "/api/providers/status")
    print()
    
    # Llama.cpp
    print("--- Llama.cpp ---")
    check_endpoint("GET", "/api/llamacpp/server/status")
    print()
    
    # LLM Download
    print("--- LLM Download ---")
    check_flask_endpoint("GET", "/api/llm/download/status", "(Flask-only)")
    print()
    
    # Podcast
    print("--- Podcast ---")
    check_endpoint("GET", "/api/podcast/episodes")
    check_endpoint("GET", "/api/podcast/voice-profiles")
    check_endpoint("POST", "/api/podcast/voice-profiles", {"name": "Test", "voice_id": "default"})
    check_flask_endpoint("POST", "/api/podcast/outline", "(Flask-only)")
    print()
    
    # Voice Clones
    print("--- Voice Clones ---")
    check_endpoint("GET", "/api/voice_clones")
    print()
    
    # Services
    print("--- Services ---")
    check_endpoint("GET", "/api/services/status", timeout=30)
    print()
    
    # Clear
    print("--- Clear ---")
    check_endpoint("POST", "/api/clear", {}, expected_status=200)
    print()
    
    # Summary
    print("=" * 60)
    print(f"Results: {passed} passed, {failed} failed, {skipped} skipped (Flask-only)")
    print("=" * 60)
    
    return 0 if failed == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
