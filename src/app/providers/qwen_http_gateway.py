"""Gateway facade for the separately managed Qwen GPU service."""
from __future__ import annotations

import time

import numpy as np

from app.runtime.http_client import shared_http_client
from app.security.service_token import service_headers


class TtsServiceSaturated(RuntimeError):
    """The shared TTS service has no realtime capacity available yet."""

    def __init__(self, retry_after: str) -> None:
        super().__init__("tts_capacity_saturated")
        self.retry_after = retry_after


class QwenHttpGatewayProvider:
    provider_name = 'faster-qwen3-tts'

    def __init__(self, base_url: str):
        self.base_url = base_url.strip().strip('"').strip("'").replace(' ', '').rstrip('/')
        # Shares the TTS service's connection pool with app.tts_http_client.
        self.http = shared_http_client("tts-service")

    def start(self):
        health = self._health()
        return {'running': bool(health.get('ok')), 'message': health.get('error', '')}

    def _health(self):
        response = self.http.get(self.base_url + '/health', timeout=5, retry=False)
        response.raise_for_status()
        return response.json()

    def get_runtime_status(self):
        health = self._health()
        return {**health.get('details', {}), 'transport': 'http_streaming_pcm16',
                'status': health.get('status'), 'error': health.get('error', '')}

    def health_check(self):
        return bool(self._health().get('ok'))

    def stop(self):
        # This facade owns no GPU process. The service launcher owns its lifecycle.
        return True

    def get_speakers(self):
        response = self.http.get(self.base_url + '/api/tts/speakers', timeout=10, headers=service_headers())
        response.raise_for_status()
        return response.json().get('speakers', [])

    def generate_audio(self, text, speaker=None, language=None, **kwargs):
        response = self.http.post(self.base_url + '/api/tts/generate_audio',
            json={'text': text, 'speaker': speaker or 'default', 'language': language or 'en'}, timeout=120,
            headers=service_headers())
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
        # Realtime: a saturated service is reported at once (no retry); the
        # caller decides whether to wait for Retry-After.
        response = self.http.open_stream(
            'POST',
            self.base_url + '/api/tts/live-call/stream',
            json=payload,
            timeout=(5, 120),
            headers=service_headers(),
            retry=False,
        )
        try:
            if response.status_code == 429:
                raise TtsServiceSaturated(response.headers.get('Retry-After', '1'))
            response.raise_for_status()
            if response.headers.get('X-Omnix-Audio-Format') != 'pcm_s16le':
                raise ValueError('Qwen service must return streaming PCM16 audio')
            if response.headers.get('X-Omnix-Channels', '1') != '1':
                raise ValueError('Qwen service must return mono PCM16 audio')
            rate = int(response.headers.get('X-Omnix-Sample-Rate', '24000'))
            remainder = b''
            for chunk in response.iter_bytes(chunk_size=4800):
                if not chunk:
                    continue
                pcm = remainder + chunk
                aligned_size = len(pcm) - len(pcm) % 2
                remainder = pcm[aligned_size:]
                if aligned_size:
                    yield np.frombuffer(pcm[:aligned_size], dtype='<i2').astype(np.float32) / 32768, rate, {
                        'transport': 'http_streaming_pcm16', 'elapsed_ms': (time.perf_counter() - started) * 1000}
            if remainder:
                raise ValueError('Qwen service returned a partial PCM16 sample')
        finally:
            response.close()
