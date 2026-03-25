"""
API validation/healthcheck tests for FastAPI server.
Run this while the server is running on localhost:5000

Note: Some endpoints are Flask-only and return 404 on FastAPI.
"""

import requests
import json
import sys

BASE_URL = "http://localhost:5000"

passed = 0
failed = 0
skipped = 0


def test_endpoint(method, path, data=None, expected_status=200, timeout=5, note=""):
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


def test_flask_endpoint(method, path, note="(Flask-only)"):
    """Test endpoint that only exists in Flask, not FastAPI"""
    global skipped
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
    test_endpoint("GET", "/")
    test_endpoint("GET", "/health")
    test_endpoint("GET", "/api/health")
    test_flask_endpoint("GET", "/favicon.ico", "(Flask-only)")
    test_flask_endpoint("GET", "/api/providers", "(Flask-only)")
    print()
    
    # Settings
    print("--- Settings ---")
    test_endpoint("GET", "/api/settings")
    test_endpoint("POST", "/api/settings", {"provider": "cerebras"})
    print()
    
    # Models
    print("--- Models ---")
    test_endpoint("GET", "/api/models")
    test_endpoint("GET", "/api/llm/models")
    test_endpoint("GET", "/api/openrouter/models")
    test_flask_endpoint("GET", "/api/huggingface/search", "(Flask-only)")
    test_flask_endpoint("GET", "/api/llamacpp/releases", "(Flask-only)")
    print()
    
    # Sessions
    print("--- Sessions ---")
    test_endpoint("GET", "/api/sessions")
    resp = test_endpoint("POST", "/api/sessions", {})
    if resp and resp.status_code == 200:
        try:
            session_id = resp.json().get("session_id")
            if session_id:
                test_endpoint("GET", f"/api/sessions/{session_id}")
                test_endpoint("PUT", f"/api/sessions/{session_id}", {"title": "Test"})
                test_endpoint("DELETE", f"/api/sessions/{session_id}")
        except:
            pass
    print()
    
    # Chat
    print("--- Chat ---")
    test_flask_endpoint("POST", "/api/chat", "(Flask-only)")
    test_endpoint("POST", "/api/chat/stream", {"message": "hello", "session_id": "test"}, timeout=10)
    test_endpoint("POST", "/api/sessions/generate-title", {"user_message": "hi", "ai_response": "hello"})
    print()
    
    # TTS
    print("--- TTS ---")
    test_endpoint("GET", "/api/tts/speakers")
    test_endpoint("POST", "/api/tts", {"text": "hello"}, timeout=60)
    test_endpoint("POST", "/api/tts/stream", {"text": "hello"}, timeout=60)
    print()
    
    # STT
    print("--- STT ---")
    test_endpoint("POST", "/api/stt", {"audio": ""}, expected_status=400, timeout=30)  # Expect 400 for missing audio
    print()
    
    # Providers
    print("--- Providers ---")
    test_endpoint("GET", "/api/providers/status")
    print()
    
    # Llama.cpp
    print("--- Llama.cpp ---")
    test_endpoint("GET", "/api/llamacpp/server/status")
    print()
    
    # LLM Download
    print("--- LLM Download ---")
    test_flask_endpoint("GET", "/api/llm/download/status", "(Flask-only)")
    print()
    
    # Podcast
    print("--- Podcast ---")
    test_endpoint("GET", "/api/podcast/episodes")
    test_endpoint("GET", "/api/podcast/voice-profiles")
    test_endpoint("POST", "/api/podcast/voice-profiles", {"name": "Test", "voice_id": "default"})
    test_flask_endpoint("POST", "/api/podcast/outline", "(Flask-only)")
    print()
    
    # Voice Clones
    print("--- Voice Clones ---")
    test_endpoint("GET", "/api/voice_clones")
    print()
    
    # Audiobook
    print("--- Audiobook ---")
    test_endpoint("POST", "/api/audiobook/upload", {"text": "Hello world"})
    test_endpoint("POST", "/api/audiobook/speakers/detect", {"text": "\"Hello,\" said Alice."})
    test_endpoint("POST", "/api/audiobook/ai-structure", {"text": ""}, expected_status=400, note="(empty text → 400)")
    test_endpoint("POST", "/api/audiobook/direct", {"script": []}, expected_status=400, note="(empty script → 400)")
    print()
    
    # Services
    print("--- Services ---")
    test_endpoint("GET", "/api/services/status", timeout=30)
    print()
    
    # Clear
    print("--- Clear ---")
    test_endpoint("POST", "/api/clear", {}, expected_status=200)
    print()
    
    # Summary
    print("=" * 60)
    print(f"Results: {passed} passed, {failed} failed, {skipped} skipped (Flask-only)")
    print("=" * 60)
    
    return 0 if failed == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
