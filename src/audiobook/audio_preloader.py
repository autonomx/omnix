"""
Audio preloading/buffering system for zero-gap audiobook playback.

While playing chunk N, generates chunk N+1 asynchronously in the background.
"""

import threading
import logging
from typing import Callable, Dict, Optional, Any

logger = logging.getLogger(__name__)


class AudioPreloader:
    """Manages asynchronous preloading of audio chunks.

    Usage:
        preloader = AudioPreloader(generate_fn=my_tts_function)

        # Request chunk 0 - generates synchronously first time
        audio_0 = preloader.get_chunk(0, text_chunks[0])

        # By now, chunk 1 is already being generated in background
        audio_1 = preloader.get_chunk(1, text_chunks[1])
    """

    def __init__(self, generate_fn: Callable[[str], bytes], max_cache_size: int = 5):
        """
        Args:
            generate_fn: Function that takes text and returns audio bytes
            max_cache_size: Maximum number of chunks to keep in cache
        """
        self._generate_fn = generate_fn
        self._cache: Dict[int, bytes] = {}
        self._pending: Dict[int, threading.Thread] = {}
        self._lock = threading.Lock()
        self._max_cache_size = max_cache_size
        self._text_chunks: Dict[int, str] = {}

    def set_chunks(self, chunks: list) -> None:
        """Set all text chunks upfront for preloading."""
        self._text_chunks = {i: text for i, text in enumerate(chunks)}

    def get_chunk(self, index: int, text: str = None) -> Optional[bytes]:
        """Get audio for chunk at index. Generates if not cached.

        Also triggers preloading of the next chunk.

        Args:
            index: Chunk index
            text: Text for this chunk (optional if set_chunks was called)

        Returns:
            Audio bytes or None on failure
        """
        resolved_text = text or self._text_chunks.get(index)

        # Check cache
        with self._lock:
            if index in self._cache:
                logger.debug("Cache hit for chunk %d", index)
                audio = self._cache[index]
                self._evict_old(index)
            else:
                audio = None
            pending_thread = self._pending.get(index)
            cache_hit = index in self._cache

        if cache_hit:
            self.preload(index + 1)
            return audio

        # Wait for pending preload
        if pending_thread is not None:
            logger.debug("Waiting for pending preload of chunk %d", index)
            pending_thread.join(timeout=300)
            with self._lock:
                audio = self._cache.get(index)
                self._evict_old(index)
            self.preload(index + 1)
            return audio

        # Not cached and not pending — generate synchronously
        if resolved_text is None:
            logger.error("No text available for chunk %d", index)
            return None

        logger.debug("Generating chunk %d synchronously", index)
        self._generate_and_cache(index, resolved_text)

        with self._lock:
            audio = self._cache.get(index)
            self._evict_old(index)
        self.preload(index + 1)
        return audio

    def preload(self, index: int, text: str = None) -> None:
        """Start generating chunk in background."""
        resolved_text = text or self._text_chunks.get(index)
        if resolved_text is None:
            return

        with self._lock:
            if index in self._cache or index in self._pending:
                return

            thread = threading.Thread(
                target=self._generate_and_cache,
                args=(index, resolved_text),
                daemon=True,
            )
            self._pending[index] = thread

        thread.start()
        logger.debug("Started preloading chunk %d in background", index)

    def _generate_and_cache(self, index: int, text: str) -> None:
        """Generate audio and store in cache (runs in background thread)."""
        try:
            audio = self._generate_fn(text)
            with self._lock:
                self._cache[index] = audio
        except Exception:
            logger.exception("Failed to generate audio for chunk %d", index)
            with self._lock:
                self._cache[index] = None
        finally:
            with self._lock:
                self._pending.pop(index, None)

    def _evict_old(self, current_index: int) -> None:
        """Remove old cache entries to save memory.

        Must be called while self._lock is held.
        """
        cutoff = max(0, current_index - self._max_cache_size)
        keys_to_remove = [k for k in self._cache if k < cutoff]
        for k in keys_to_remove:
            del self._cache[k]
            logger.debug("Evicted chunk %d from cache", k)

    def clear(self) -> None:
        """Clear all cached audio."""
        with self._lock:
            self._cache.clear()
            self._pending.clear()
            logger.debug("Cleared preloader cache")

    @property
    def cached_indices(self) -> list:
        """Return list of currently cached chunk indices."""
        with self._lock:
            return list(self._cache.keys())
