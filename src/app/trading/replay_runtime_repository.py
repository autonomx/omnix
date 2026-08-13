from __future__ import annotations

import hashlib

from app.persistence.blob_store import LocalBlobStore

from .backtest import BacktestArtifactReference, BacktestRunResult
from .replay_repository import TradingReplayRepository


class TradingReplayRuntimeRepository(TradingReplayRepository):
    def __init__(self, *args, blob_store: LocalBlobStore | None = None, **kwargs) -> None:
        super().__init__(*args, **kwargs)
        self.blob_store = blob_store or LocalBlobStore()

    def _artifact_key(self, run_id: str) -> str:
        workspace = hashlib.sha256(self.context.workspace_id.encode("utf-8")).hexdigest()[:16]
        safe_run = hashlib.sha256(run_id.encode("utf-8")).hexdigest()
        return f"trading/backtests/{workspace}/{safe_run}.json"

    def save_backtest(self, result: BacktestRunResult) -> BacktestRunResult:
        storage_key = self._artifact_key(result.run_id)
        blob = self.blob_store.put_bytes(
            storage_key,
            result.model_dump_json(indent=2).encode("utf-8"),
        )
        artifact = BacktestArtifactReference(
            storage_provider=str(blob["storage_provider"]),
            storage_key=str(blob["storage_key"]),
            checksum_sha256=str(blob["checksum_sha256"]),
            byte_size=int(blob["byte_size"]),
        )
        saved = result.model_copy(update={"artifact": artifact})
        try:
            super().save_backtest(saved)
        except Exception:
            if bool(blob.get("created")):
                self.blob_store.delete(storage_key)
            raise
        return saved

    def get_backtest(self, run_id: str) -> BacktestRunResult | None:
        result = super().get_backtest(run_id)
        if result is not None and result.artifact is not None:
            self.blob_store.read_bytes(
                result.artifact.storage_key,
                expected_checksum=result.artifact.checksum_sha256,
            )
        return result


def default_runtime_replay_repository() -> TradingReplayRuntimeRepository:
    return TradingReplayRuntimeRepository()
