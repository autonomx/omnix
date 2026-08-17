from __future__ import annotations

import threading
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any

import requests

from .errors import (
    ProviderCancelledError,
    ProviderRateLimitedError,
    ProviderUnavailableError,
)


_RETRYABLE_STATUS = {429, 500, 502, 503, 504}


@dataclass(slots=True)
class ProviderRuntimeSnapshot:
    status: str
    request_count: int
    success_count: int
    failure_count: int
    consecutive_failures: int
    rate_limit_count: int
    in_flight: int
    max_concurrency: int
    last_success_at: str | None
    last_failure_at: str | None
    last_error: str | None


class ProviderHttpRuntime:
    """Bounded HTTP runtime with retry/backoff, cancellation, and health evidence."""

    def __init__(
        self,
        provider_id: str,
        *,
        session: requests.Session | None = None,
        max_concurrency: int = 4,
        max_attempts: int = 3,
        initial_backoff_seconds: float = 0.25,
    ) -> None:
        self.provider_id = provider_id
        self.session = session or requests.Session()
        self.max_concurrency = max(1, int(max_concurrency))
        self.max_attempts = max(1, int(max_attempts))
        self.initial_backoff_seconds = max(0.0, float(initial_backoff_seconds))
        self._semaphore = threading.BoundedSemaphore(self.max_concurrency)
        self._guard = threading.Lock()
        self._request_count = 0
        self._success_count = 0
        self._failure_count = 0
        self._consecutive_failures = 0
        self._rate_limit_count = 0
        self._in_flight = 0
        self._last_success_at: datetime | None = None
        self._last_failure_at: datetime | None = None
        self._last_error: str | None = None

    @staticmethod
    def _cancelled(cancellation: threading.Event | None) -> bool:
        return cancellation is not None and cancellation.is_set()

    def _sleep(self, delay: float, cancellation: threading.Event | None) -> None:
        deadline = time.monotonic() + delay
        while time.monotonic() < deadline:
            if self._cancelled(cancellation):
                raise ProviderCancelledError(f"{self.provider_id} request cancelled")
            time.sleep(min(0.05, max(0.0, deadline - time.monotonic())))

    def _record_start(self) -> None:
        with self._guard:
            self._request_count += 1
            self._in_flight += 1

    def _record_success(self) -> None:
        with self._guard:
            self._success_count += 1
            self._consecutive_failures = 0
            self._last_success_at = datetime.now(timezone.utc)
            self._last_error = None

    def _record_failure(self, error: BaseException, *, rate_limited: bool = False) -> None:
        with self._guard:
            self._failure_count += 1
            self._consecutive_failures += 1
            if rate_limited:
                self._rate_limit_count += 1
            self._last_failure_at = datetime.now(timezone.utc)
            self._last_error = f"{type(error).__name__}: {error}"

    def _record_finish(self) -> None:
        with self._guard:
            self._in_flight = max(0, self._in_flight - 1)

    def _send(self, method: str, url: str, **kwargs: Any) -> requests.Response:
        request = getattr(self.session, "request", None)
        if callable(request):
            return request(method, url, **kwargs)
        method_call = getattr(self.session, method.lower(), None)
        if not callable(method_call):
            raise AttributeError(
                f"{type(self.session).__name__} supports neither request() nor {method.lower()}()"
            )
        return method_call(url, **kwargs)

    def request(
        self,
        method: str,
        url: str,
        *,
        cancellation: threading.Event | None = None,
        **kwargs: Any,
    ) -> requests.Response:
        if self._cancelled(cancellation):
            raise ProviderCancelledError(f"{self.provider_id} request cancelled")
        with self._semaphore:
            self._record_start()
            try:
                last_error: BaseException | None = None
                for attempt in range(self.max_attempts):
                    if self._cancelled(cancellation):
                        raise ProviderCancelledError(f"{self.provider_id} request cancelled")
                    try:
                        response = self._send(method, url, **kwargs)
                        status_code = int(getattr(response, "status_code", 200))
                        if status_code not in _RETRYABLE_STATUS:
                            raise_for_status = getattr(response, "raise_for_status", None)
                            if callable(raise_for_status):
                                raise_for_status()
                            self._record_success()
                            return response
                        headers = getattr(response, "headers", {}) or {}
                        retry_after = headers.get("Retry-After")
                        delay = (
                            float(retry_after)
                            if retry_after and retry_after.replace(".", "", 1).isdigit()
                            else self.initial_backoff_seconds * (2**attempt)
                        )
                        if status_code == 429:
                            error = ProviderRateLimitedError(
                                f"{self.provider_id} rate limited request: HTTP 429"
                            )
                            self._record_failure(error, rate_limited=True)
                        else:
                            error = ProviderUnavailableError(
                                f"{self.provider_id} unavailable: HTTP {status_code}"
                            )
                            self._record_failure(error)
                        last_error = error
                    except ProviderCancelledError:
                        raise
                    except (requests.Timeout, requests.ConnectionError) as exc:
                        error = ProviderUnavailableError(
                            f"{self.provider_id} transport failure: {exc}"
                        )
                        self._record_failure(error)
                        last_error = error
                        delay = self.initial_backoff_seconds * (2**attempt)
                    except requests.RequestException:
                        raise
                    if attempt + 1 < self.max_attempts:
                        self._sleep(delay, cancellation)
                if last_error is not None:
                    raise last_error
                raise ProviderUnavailableError(f"{self.provider_id} request failed")
            finally:
                self._record_finish()

    def get(self, url: str, **kwargs: Any) -> requests.Response:
        return self.request("GET", url, **kwargs)

    def post(self, url: str, **kwargs: Any) -> requests.Response:
        return self.request("POST", url, **kwargs)

    def snapshot(self) -> ProviderRuntimeSnapshot:
        with self._guard:
            if self._consecutive_failures >= 3:
                status = "unavailable"
            elif self._consecutive_failures > 0:
                status = "degraded"
            else:
                status = "ready"
            return ProviderRuntimeSnapshot(
                status=status,
                request_count=self._request_count,
                success_count=self._success_count,
                failure_count=self._failure_count,
                consecutive_failures=self._consecutive_failures,
                rate_limit_count=self._rate_limit_count,
                in_flight=self._in_flight,
                max_concurrency=self.max_concurrency,
                last_success_at=(
                    self._last_success_at.isoformat() if self._last_success_at else None
                ),
                last_failure_at=(
                    self._last_failure_at.isoformat() if self._last_failure_at else None
                ),
                last_error=self._last_error,
            )
