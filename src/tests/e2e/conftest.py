"""Browser-parity hooks for the hardware-dependent Live Voice API benchmark.

The API benchmark intentionally stays browserless, but the production browser owns
some latency-critical orchestration that is not part of the HTTP/WebSocket
contracts themselves. This fixture ports those policies into the benchmark at
runtime so ``test_live_voice_api`` exercises the same stable-clause deadlines and
TTS request knobs without duplicating them in production code.
"""

from __future__ import annotations

import asyncio
import json
import re
import subprocess
import time
from collections.abc import Callable, Generator
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import pytest
from playwright.sync_api import Playwright, sync_playwright

FIRST_MINIMUM = 8
FIRST_LOOKAHEAD = 4
FIRST_MAXIMUM = 56
FIRST_DEADLINE_MS = 55
NORMAL_MINIMUM = 12
NORMAL_LOOKAHEAD = 12
NORMAL_MAXIMUM = 64
NORMAL_DEADLINE_MS = 140

STRONG_BOUNDARY = re.compile(r"[.!?][\]})\"'’”]*(?=\s|$)")
WEAK_BOUNDARY = re.compile(r"[,;:][\]})\"'’”]*(?=\s|$)")
ABBREVIATION = re.compile(r"(?:\b(?:mr|mrs|ms|dr|prof|sr|jr|st|vs|etc|e\.g|i\.e)|\b[A-Z])\.$", re.IGNORECASE)
DECIMAL_OR_VERSION = re.compile(r"\d\.\d$")
URL_TAIL = re.compile(r"(?:https?://|www\.)\S*$", re.IGNORECASE)
OPENING_QUOTE = re.compile(r'^[\"“‘]')
SERIOUS_PATTERN = re.compile(r"\b(?:sorry|grief|loss|afraid|hurt|serious|take your time)\b", re.IGNORECASE)
REASSURANCE_PATTERN = re.compile(r"\b(?:i understand|that sounds|take your time|i'm sorry|i am sorry)\b")
UNCERTAINTY_PATTERN = re.compile(r"\b(?:maybe|perhaps|might|not sure|uncertain)\b")


@pytest.fixture(scope="session")
def playwright() -> Generator[Playwright, None, None]:
    """Provide Playwright when the optional pytest-playwright plugin is absent."""

    with sync_playwright() as instance:
        yield instance


@dataclass(frozen=True)
class StableClause:
    text: str
    reason: str


@dataclass(frozen=True)
class ClausePolicy:
    minimum: int
    lookahead: int
    maximum: int
    deadline_ms: int


FIRST_POLICY = ClausePolicy(FIRST_MINIMUM, FIRST_LOOKAHEAD, FIRST_MAXIMUM, FIRST_DEADLINE_MS)
NORMAL_POLICY = ClausePolicy(NORMAL_MINIMUM, NORMAL_LOOKAHEAD, NORMAL_MAXIMUM, NORMAL_DEADLINE_MS)


def _merge_stream_text(current: str, next_text: str) -> str:
    left = current.rstrip()
    right = next_text.lstrip()
    if not left:
        return right
    if not right:
        return left
    if re.match(r"^[,.;:!?%\]})]", right) or re.search(r"[([{“‘]$", left):
        return f"{left}{right}"
    return f"{left} {right}"


def _odd_unescaped_quote_count(text: str, quote: str = '"') -> bool:
    count = 0
    for index, character in enumerate(text):
        if character != quote:
            continue
        backslashes = 0
        cursor = index - 1
        while cursor >= 0 and text[cursor] == "\\":
            backslashes += 1
            cursor -= 1
        if backslashes % 2 == 0:
            count += 1
    return count % 2 == 1


def _unclosed_pair(text: str, opening: str, closing: str) -> bool:
    return text.rfind(opening) > text.rfind(closing)


def _protected_boundary(prefix: str) -> bool:
    trimmed = prefix.rstrip()
    return bool(
        ABBREVIATION.search(trimmed)
        or DECIMAL_OR_VERSION.search(trimmed)
        or URL_TAIL.search(trimmed)
        or _unclosed_pair(trimmed, "(", ")")
        or _unclosed_pair(trimmed, "[", "]")
        or _unclosed_pair(trimmed, "{", "}")
        or _unclosed_pair(trimmed, "“", "”")
        or _unclosed_pair(trimmed, "‘", "’")
        or _odd_unescaped_quote_count(trimmed)
    )


def _safe_boundary(text: str, pattern: re.Pattern[str], minimum: int) -> int | None:
    for match in pattern.finditer(text):
        end = match.end()
        if end < minimum or _protected_boundary(text[:end]):
            continue
        return end
    return None


def _stable_weak_boundary(text: str, minimum: int, lookahead: int) -> int | None:
    for match in WEAK_BOUNDARY.finditer(text):
        end = match.end()
        if end < minimum or len(text) - end < lookahead:
            continue
        if OPENING_QUOTE.match(text[end:].lstrip()) or _protected_boundary(text[:end]):
            continue
        return end
    return None


def _whitespace_boundary(text: str, limit: int, minimum: int) -> int | None:
    bounded = text[: max(minimum, limit)]
    for index in range(len(bounded) - 1, minimum - 1, -1):
        if not bounded[index].isspace():
            continue
        if not _protected_boundary(bounded[:index]):
            return index
    return None


def _sanitize_spoken_text(text: str) -> str:
    # The benchmark corpus is plain conversational text. Keep the same whitespace
    # and punctuation normalization as the browser stabilizer without pulling a
    # Unicode-property regex dependency into the test runner.
    cleaned = re.sub(r"\s+", " ", text).strip()
    cleaned = re.sub(r"\s+([,.;:!?])", r"\1", cleaned)
    cleaned = re.sub(r"\s+([)\]}])", r"\1", cleaned)
    return re.sub(r"^[\s,;:!?…—–.\-]+", "", cleaned).strip()


class StableClauseAccumulator:
    """Python port of the production ``StableClauseAccumulator`` timing policy."""

    def __init__(self) -> None:
        self.buffer = ""
        self.opened_at_ms: float | None = None
        self.committed_clause_count = 0

    def append(self, fragment: str, now_ms: float | None = None) -> list[StableClause]:
        normalized = fragment.strip()
        if not normalized:
            return []
        self.buffer = _merge_stream_text(self.buffer, normalized)
        if self.opened_at_ms is None:
            self.opened_at_ms = _now_ms() if now_ms is None else now_ms
        return self.take_ready(now_ms)

    def take_ready(self, now_ms: float | None = None) -> list[StableClause]:
        now = _now_ms() if now_ms is None else now_ms
        committed: list[StableClause] = []
        while True:
            boundary = self._next_boundary(now)
            if boundary is None:
                break
            end, reason = boundary
            text = _sanitize_spoken_text(self.buffer[:end].strip())
            self.buffer = self.buffer[end:].lstrip()
            if text:
                committed.append(StableClause(text=text, reason=reason))
                self.committed_clause_count += 1
            self.opened_at_ms = now if self.buffer else None
        return committed

    def flush(self) -> list[StableClause]:
        text = _sanitize_spoken_text(self.buffer.strip())
        self.buffer = ""
        self.opened_at_ms = None
        if not text:
            return []
        self.committed_clause_count += 1
        return [StableClause(text=text, reason="stream-end")]

    def deadline_remaining_ms(self, now_ms: float | None = None) -> float | None:
        if self.opened_at_ms is None or not self.buffer:
            return None
        now = _now_ms() if now_ms is None else now_ms
        return max(0.0, self._policy().deadline_ms - (now - self.opened_at_ms))

    def _policy(self) -> ClausePolicy:
        return FIRST_POLICY if self.committed_clause_count == 0 else NORMAL_POLICY

    def _next_boundary(self, now_ms: float) -> tuple[int, str] | None:
        policy = self._policy()
        strong = _safe_boundary(self.buffer, STRONG_BOUNDARY, policy.minimum)
        weak = _stable_weak_boundary(self.buffer, policy.minimum, policy.lookahead)
        if weak is not None and (strong is None or weak < strong):
            natural: tuple[int, str] | None = (weak, "stable-boundary")
        elif strong is not None:
            natural = (strong, "strong-boundary")
        else:
            natural = None

        if natural is not None and natural[0] <= policy.maximum:
            return natural

        if len(self.buffer) >= policy.maximum:
            split_limit = (
                min(policy.maximum, max(policy.minimum, natural[0] - policy.minimum))
                if natural is not None
                else policy.maximum
            )
            fallback = _whitespace_boundary(self.buffer, split_limit, policy.minimum)
            if fallback is not None:
                return fallback, "maximum"

        if natural is not None:
            return natural

        if (
            self.opened_at_ms is not None
            and now_ms - self.opened_at_ms >= policy.deadline_ms
            and len(self.buffer) >= policy.minimum
        ):
            fallback = _whitespace_boundary(
                self.buffer,
                min(policy.maximum, len(self.buffer)),
                policy.minimum,
            )
            if fallback is not None:
                return fallback, "deadline"
        return None


def _now_ms() -> float:
    return time.perf_counter() * 1_000


def _fallback_delivery_plan(text: str) -> dict[str, Any]:
    """Match the browser's canonical-chat fallback speech plan."""

    normalized = text.strip()
    lower = normalized.lower()
    words = [word for word in re.split(r"\s+", normalized) if word]
    speech_act = "question" if normalized.endswith("?") else "answer"
    if REASSURANCE_PATTERN.search(lower):
        speech_act = "reassurance"
    elif len(words) <= 4:
        speech_act = "acknowledgement"
    serious = bool(SERIOUS_PATTERN.search(normalized))
    reflective = serious or speech_act == "reassurance"
    certainty = "low" if UNCERTAINTY_PATTERN.search(lower) else "high" if speech_act == "answer" else "moderate"
    emphasis = [
        re.sub(r"[.,!?;:]", "", word)
        for word in words
        if len(word) > 1 and word == word.upper()
    ][:6]
    return {
        "schema_version": 1,
        "speech_act": speech_act,
        "energy": "low" if reflective else "moderate",
        "warmth": "high" if serious else "moderate",
        "certainty": certainty,
        "pace": "slightly_slow" if serious else "natural",
        "clause_pause": "long" if serious else "short" if speech_act == "acknowledgement" else "medium",
        "emphasis": emphasis,
        "onset_policy": {
            "desired_perceived_onset_ms": 120,
            "maximum_additional_delay_ms": 80,
        },
        "nonverbal_eligibility": {
            "breath": True,
            "acknowledgement": False,
            "amused_exhale": False,
            "sigh": False,
        },
    }


class _ParityWebSocket:
    def __init__(self, delegate: Any) -> None:
        self._delegate = delegate

    def __getattr__(self, name: str) -> Any:
        return getattr(self._delegate, name)

    async def send(self, data: Any) -> Any:
        if isinstance(data, str):
            try:
                payload = json.loads(data)
            except json.JSONDecodeError:
                payload = None
            if isinstance(payload, dict) and payload.get("type") == "synthesize":
                text = str(payload.get("text") or "")
                payload.update(
                    chunk_size=8,
                    repetition_penalty=1.0,
                    parity_mode=True,
                    delivery_plan=_fallback_delivery_plan(text),
                )
                data = json.dumps(payload)
        return await self._delegate.send(data)


async def _browser_parity_stream_chat_to_tts(
    module: Any,
    http: Any,
    api_url: str,
    session_id: str,
    transcript: str,
    turn_suffix: str,
    turn: Any,
    reporter: Any,
    tts_client: Any,
) -> str:
    voice_turn_id = f"voice-turn:{turn_suffix}"
    chat_payload: dict[str, Any] = {
        "content": transcript,
        "live_voice_turn_id": voice_turn_id,
        "user_turn_id": f"voice-user-turn:{turn_suffix}",
        "speech_segment_id": f"voice-segment:{turn_suffix}",
    }
    provider = module.os.environ.get("OMNIX_LIVE_VOICE_API_PROVIDER", "").strip()
    model = module.os.environ.get("OMNIX_LIVE_VOICE_API_MODEL", "").strip()
    if provider:
        chat_payload["provider_id"] = provider
    if model:
        chat_payload["model_id"] = model
    reporter.record(
        "chat_submit_started",
        {
            "input_chars": len(transcript),
            "provider_configured": bool(provider),
            "model_configured": bool(model),
            "clause_policy": "browser_stable_clause_v1",
        },
        "chatbot_workspace",
    )

    phrase_queue: asyncio.Queue[tuple[int, str] | None] = asyncio.Queue()
    llm_done = asyncio.Event()
    tts_task = asyncio.create_task(
        module._tts_worker(phrase_queue, tts_client, turn, reporter, llm_done),
        name=f"live-voice-api-tts-turn-{turn.index}",
    )
    clauses = StableClauseAccumulator()
    clause_changed = asyncio.Event()
    deadline_stop = asyncio.Event()
    response_text = ""
    phrase_index = 0
    chat_path = f"/api/chat/sessions/{session_id}/messages/stream"

    async def commit(ready: list[StableClause], source: str) -> None:
        nonlocal phrase_index
        for clause in ready:
            reporter.record(
                "tts_phrase_committed",
                {
                    "phrase_index": phrase_index,
                    "text_chars": len(clause.text),
                    "commit_source": source,
                    "clause_reason": clause.reason,
                },
                "chatbot_workspace",
            )
            await phrase_queue.put((phrase_index, clause.text))
            phrase_index += 1

    async def deadline_worker() -> None:
        while not deadline_stop.is_set():
            remaining = clauses.deadline_remaining_ms()
            if remaining is None:
                clause_changed.clear()
                change_wait = asyncio.create_task(clause_changed.wait())
                stop_wait = asyncio.create_task(deadline_stop.wait())
                done, pending_tasks = await asyncio.wait(
                    {change_wait, stop_wait},
                    return_when=asyncio.FIRST_COMPLETED,
                )
                for task in pending_tasks:
                    task.cancel()
                await asyncio.gather(*pending_tasks, return_exceptions=True)
                if stop_wait in done:
                    return
                continue

            clause_changed.clear()
            change_wait = asyncio.create_task(clause_changed.wait())
            stop_wait = asyncio.create_task(deadline_stop.wait())
            done, pending_tasks = await asyncio.wait(
                {change_wait, stop_wait},
                timeout=max(0.001, remaining / 1_000),
                return_when=asyncio.FIRST_COMPLETED,
            )
            for task in pending_tasks:
                task.cancel()
            await asyncio.gather(*pending_tasks, return_exceptions=True)
            if stop_wait in done:
                return
            if change_wait in done:
                continue
            await commit(clauses.take_ready(), "stable_clause_deadline")

    deadline_task = asyncio.create_task(
        deadline_worker(),
        name=f"live-voice-api-clause-deadline-{turn.index}",
    )

    async def accept_event(event: dict[str, Any]) -> None:
        nonlocal response_text
        event_type = event.get("type")
        if event_type == "error":
            raise RuntimeError(str(event.get("message") or "Live chat stream failed"))
        if event_type != "text_chunk":
            return
        chunk_text = str(event.get("text") or "")
        if not chunk_text:
            return
        now = time.perf_counter()
        if turn.first_llm_chunk_at is None:
            turn.first_llm_chunk_at = now
            reporter.record(
                "llm_first_text_chunk_received",
                {
                    "text_chunk_chars": len(chunk_text),
                    "elapsed_ms": module._delta_ms(turn.final_received_at, now),
                },
                "chatbot_workspace",
            )
        response_text += chunk_text
        await commit(clauses.append(chunk_text), "incremental_llm")
        clause_changed.set()

    try:
        module._console_log(
            "HTTP message sent",
            method="POST",
            path=chat_path,
            turn=turn.index,
            chars=len(transcript),
            text=module._preview(transcript),
        )
        async with http.post(
            f"{api_url}{chat_path}",
            json=chat_payload,
            timeout=module.CHAT_TIMEOUT_SECONDS,
        ) as response:
            module._console_log(
                "HTTP response received",
                method="POST",
                path=chat_path,
                status=response.status,
                turn=turn.index,
            )
            if response.status >= 400:
                body = await response.text()
                raise RuntimeError(f"Live chat stream failed: HTTP {response.status} {body[:240]}")
            reporter.record("chat_response_opened", {"status": response.status}, "chatbot_workspace")
            pending = ""
            async for chunk in response.content.iter_chunked(16_384):
                pending += chunk.decode("utf-8", errors="replace")
                events, pending = module._sse_events(pending)
                for event in events:
                    await accept_event(event)
            if pending.strip():
                events, _ = module._sse_events(f"{pending}\n\n")
                for event in events:
                    await accept_event(event)

        deadline_stop.set()
        clause_changed.set()
        await deadline_task
        await commit(clauses.flush(), "llm_stream_flush")
        turn.llm_completed_at = time.perf_counter()
        llm_done.set()
        reporter.record(
            "llm_stream_completed",
            {
                "response_chars": len(response_text.strip()),
                "elapsed_ms": module._delta_ms(turn.final_received_at, turn.llm_completed_at),
                "tts_already_started": turn.first_tts_request_at is not None
                and turn.first_tts_request_at < turn.llm_completed_at,
            },
            "chatbot_workspace",
        )
        await phrase_queue.put(None)
        await tts_task
    except BaseException:
        llm_done.set()
        deadline_stop.set()
        clause_changed.set()
        if not deadline_task.done():
            deadline_task.cancel()
        if not tts_task.done():
            tts_task.cancel()
        await asyncio.gather(deadline_task, tts_task, return_exceptions=True)
        raise

    response_text = response_text.strip()
    if not response_text:
        raise RuntimeError(f"Live chat returned no assistant text for turn {turn.index}")
    return response_text


def _git_provenance(module: Any) -> dict[str, Any]:
    root = Path(module.ROOT_DIR)
    try:
        sha = subprocess.run(
            ["git", "-C", str(root), "rev-parse", "HEAD"],
            check=True,
            capture_output=True,
            text=True,
            timeout=5,
        ).stdout.strip()
        dirty = subprocess.run(
            ["git", "-C", str(root), "status", "--porcelain", "--untracked-files=no"],
            check=True,
            capture_output=True,
            text=True,
            timeout=5,
        ).stdout.splitlines()
    except (OSError, subprocess.SubprocessError):
        return {"git_sha": None, "working_tree_dirty": None}
    return {
        "git_sha": sha or None,
        "working_tree_dirty": bool(dirty),
        "working_tree_dirty_file_count": len(dirty),
    }


@pytest.fixture(autouse=True)
def live_voice_api_browser_parity(request: pytest.FixtureRequest, monkeypatch: pytest.MonkeyPatch) -> None:
    """Apply browser-owned latency policy only to ``test_live_voice_api``."""

    module = request.module
    if module.__name__.rsplit(".", 1)[-1] != "test_live_voice_api":
        return

    original_init: Callable[..., None] = module.ApiTtsClient.__init__

    def parity_init(self: Any, websocket: Any, reporter: Any, voice: str | None, session_id: str) -> None:
        original_init(self, _ParityWebSocket(websocket), reporter, voice, session_id)

    async def parity_stream(*args: Any, **kwargs: Any) -> str:
        return await _browser_parity_stream_chat_to_tts(module, *args, **kwargs)

    original_record = module.DiagnosticReporter.record
    provenance = _git_provenance(module)

    def record_with_provenance(self: Any, event: str, details: dict[str, Any] | None = None, source: str = "api_test") -> None:
        enriched = dict(details or {})
        if event in {"reporter_created", "live_audio_session_created", "stt_negotiated"}:
            enriched.update(provenance)
        original_record(self, event, enriched, source)

    monkeypatch.setattr(module.ApiTtsClient, "__init__", parity_init)
    monkeypatch.setattr(module, "_stream_chat_to_tts", parity_stream)
    monkeypatch.setattr(module.DiagnosticReporter, "record", record_with_provenance)
