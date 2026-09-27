"""Durable coordination around the established Chat store orchestration."""

from __future__ import annotations

from contextlib import contextmanager

from .errors import EntityNotFound
from .execution_repositories import JobClaimConflict
from .transaction_binding import share_transaction
from .unit_of_work import unit_of_work


class ChatExecutionTransactions:
    def find_job_by_submission(self, *, job_type, session_id, submission_id):
        with unit_of_work(self.database) as work:
            row = work.connection.execute(
                "SELECT id FROM omnix_jobs WHERE workspace_id = %s AND job_type = %s "
                "AND input_payload ->> 'session_id' = %s AND input_payload ->> 'submission_id' = %s "
                "ORDER BY created_at, id LIMIT 1",
                (self.context.workspace_id, job_type, session_id, submission_id),
            ).fetchone()
            record = work.jobs.get_job(self.context, row[0]) if row else None
            work.rollback()
        return self._record(record) if record else None

    @contextmanager
    def chat_transaction(
        self, chat_store, session_id: str, *, job_id: str | None = None
    ):
        adapter = getattr(chat_store, "_repository", None)
        if (
            adapter is None
            or adapter.database is not self.database
            or adapter.context.workspace_id != self.context.workspace_id
        ):
            raise RuntimeError(
                "Chat and job stores must share database and tenant authority"
            )
        with unit_of_work(self.database) as work:
            # All admission and completion operations lock the session before jobs.
            session = work.connection.execute(
                "SELECT id FROM omnix_chat_sessions WHERE id = %s AND workspace_id = %s AND status = 'active' FOR UPDATE",
                (session_id, self.context.workspace_id),
            ).fetchone()
            if session is None and job_id is not None:
                raise EntityNotFound(session_id)
            if job_id is not None:
                work.connection.execute(
                    "SELECT id FROM omnix_jobs WHERE id = %s AND workspace_id = %s FOR UPDATE",
                    (job_id, self.context.workspace_id),
                )
            with share_transaction(work):
                yield work
            work.commit()

    @contextmanager
    def chat_completion(self, chat_store, job_id: str):
        job = self.get_job(job_id)
        if job is None or job.type != "chat.generate":
            raise JobClaimConflict("Chat job no longer exists")
        session_id = (job.input_payload or {}).get("session_id")
        with self.chat_transaction(chat_store, session_id, job_id=job_id) as work:
            current = work.jobs.get_job(self.context, job_id)
            if current is None or current["status"] not in ("queued", "running"):
                raise JobClaimConflict("Chat job is no longer eligible for completion")
            self.require_chat_execution_owner(job_id)
            yield
            # A lease may expire while a completion validator is running.
            # Roll back every transcript/metadata/job write if that happened.
            self.require_chat_execution_owner(job_id)

    def list_active_chat_jobs(self, session_id: str):
        with unit_of_work(self.database) as work:
            rows = work.connection.execute(
                "SELECT id FROM omnix_jobs WHERE workspace_id = %s AND job_type = 'chat.generate' "
                "AND input_payload ->> 'session_id' = %s "
                "AND status IN ('queued', 'leased', 'running', 'waiting', 'retrying') ORDER BY created_at, id",
                (self.context.workspace_id, session_id),
            ).fetchall()
            records = [work.jobs.get_job(self.context, row[0]) for row in rows]
            work.rollback()
        return [self._record(record) for record in records]

    def try_start_chat_job(self, job_id: str):
        job = self.get_job(job_id)
        if job is None or job.status.value != "queued":
            return job
        session_id = (job.input_payload or {}).get("session_id")
        if not session_id:
            return self.mark_running(job_id)
        with unit_of_work(self.database) as work:
            work.connection.execute(
                "SELECT id FROM omnix_chat_sessions WHERE id = %s AND workspace_id = %s FOR UPDATE",
                (session_id, self.context.workspace_id),
            )
            current = work.jobs.get_job(self.context, job_id)
            if current is None or current["status"] != "queued":
                work.rollback()
                return self._record(current) if current else None
            earlier = work.connection.execute(
                "SELECT 1 FROM omnix_jobs WHERE workspace_id = %s AND job_type = 'chat.generate' "
                "AND input_payload ->> 'session_id' = %s "
                "AND status IN ('queued', 'leased', 'running', 'waiting', 'retrying', 'cancel_requested') "
                "AND (created_at, id) < (%s::timestamptz, %s) LIMIT 1",
                (self.context.workspace_id, session_id, current["created_at"], job_id),
            ).fetchone()
            if earlier:
                work.rollback()
                return None
            owner = getattr(self, "chat_execution_owner", None)
            record = work.jobs.mark_record_only_running(
                self.context,
                job_id=job_id,
                execution_owner=owner.node_id if owner else None,
            )
            work.commit()
        return self._record(record)
