"""Gateway facade for the separately managed Qwen GPU service."""
from __future__ import annotations

import base64
import io
import time
import wave

import numpy as np
import requests

from app.security.service_token import service_headers


class QwenHttpGatewayProvider:
    provider_name = 'faster-qwen3-tts'

    def __init__(self, base_url: str):
        self.base_url = base_url.strip().strip('"').strip("'").replace(' ', '').rstrip('/')

    def start(self):
        health = self._health()
        return {'running': bool(health.get('ok')), 'message': health.get('error', '')}

    def _health(self):
        response = requests.get(self.base_url + '/health', timeout=5)
        response.raise_for_status()
        return response.json()

    def get_runtime_status(self):
        health = self._health()
        return {**health.get('details', {}), 'transport': 'http_buffered_wav',
                'status': health.get('status'), 'error': health.get('error', '')}

    def health_check(self):
        return bool(self._health().get('ok'))

    def stop(self):
        # This facade owns no GPU process. The service launcher owns its lifecycle.
        return True

    def get_speakers(self):
        response = requests.get(self.base_url + '/api/tts/speakers', timeout=10,
                                headers=service_headers(), allow_redirects=False)
        response.raise_for_status()
        return response.json().get('speakers', [])

    def generate_audio(self, text, speaker=None, language=None, **kwargs):
        response = requests.post(self.base_url + '/api/tts/generate_audio',
            json={'text': text, 'speaker': speaker or 'default', 'language': language or 'en'}, timeout=120,
            headers=service_headers(), allow_redirects=False)
        response.raise_for_status()
        result = response.json()
        if not result.get('success') or result.get('is_fallback'):
            raise RuntimeError('Qwen service did not return real synthesized audio')
        return result

    def generate_audio_stream(self, text, speaker=None, language=None, **kwargs):
        started = time.perf_counter()
        allowed = {'chunk_size', 'temperature', 'top_k', 'top_p', 'repetition_penalty', 'append_silence', 'max_new_tokens'}
        payload = {key: value for key, value in kwargs.items() if key in allowed and value is not None}
        payload.update(text=text, speaker=speaker or 'default', language=language or 'en')
        response = requests.post(self.base_url + '/api/tts/generate_stream_audio', json=payload, timeout=120,
            headers=service_headers(), allow_redirects=False)
        response.raise_for_status()
        if 'application/json' in response.headers.get('content-type', ''):
            result = response.json()
            if not result.get('success') or result.get('is_fallback'):
                raise RuntimeError('Qwen service did not return real synthesized audio')
            data = base64.b64decode(result['audio'], validate=True)
        else:
            data = response.content
        with wave.open(io.BytesIO(data), 'rb') as audio:
            if audio.getsampwidth() != 2 or audio.getnchannels() != 1:
                raise ValueError('Qwen service must return mono PCM16 WAV')
            rate = audio.getframerate()
            while pcm := audio.readframes(2400):
                yield np.frombuffer(pcm, dtype='<i2').astype(np.float32) / 32768, rate, {
                    'transport': 'http_buffered_wav', 'elapsed_ms': (time.perf_counter() - started) * 1000}
