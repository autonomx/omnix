"""Compare memory retrieval: assistant_memory (v1) against Memory v2.

    python scripts/compare_memory_retrieval.py --database-url postgresql://.../omnix_test \\
        --sizes 100,500,2000 --output docs/measurements/memory-retrieval-comparison.json

The same curated memories go into both systems: v1 as ``MemoryRecord`` lists,
v2 through the legacy importer and the deterministic seed projector (no LLM
consolidation, so this measures retrieval, not v2's richer extraction). Each
store holds 24 target memories, each paired with a question about it (half
share keywords with the memory, half are paraphrases), padded with
deterministic distractors. Three paths answer every question:

- ``v1_chat``: what Chat prompts get today (``select_memory_records``: pinned,
  category, confidence and recency order under the memory token budget; the
  question is not used);
- ``v1_companion``: the companion's temporal ranker (term overlap and time
  of day, top 12);
- ``v2_words``: ``UnifiedMemoryV2Retriever`` by words only (top 12 within the same budget);
- ``v2``: the same with VoiceMem's embedding retrieval (multilingual-e5-small),
  when the model is installed (``python -m app.assistant_memory_v2.embeddings download``).

Besides the 24 questions, 8 "hard" paraphrases share no meaningful word with
their memory.

Reported per path and store size: recall (questions whose memory was in the
prompt), the share of injected memories that were relevant, tokens injected,
and the mean time per question. The database must be disposable (its name
contains ``test`` or ``bench``); the benchmark writes Memory v2 rows under its
own principal and deletes them afterwards.
"""
from __future__ import annotations

import argparse
import json
import random
import statistics
import sys
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path
from urllib.parse import urlsplit
from uuid import uuid4

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

TOKEN_BUDGET = 4_000  # the Chat default (assistant_memory settings memory_token_budget)
TOP_K = 12
PROFILE_ID = "profile:benchmark"  # v1's global scope id is the profile
NOW = datetime(2026, 10, 2, 15, 0, tzinfo=timezone.utc)

# (category, memory, question, paraphrased?)
TARGETS = [
    ("preference", "My favorite game is Skyrim", "What is my favorite game?", False),
    ("preference", "I prefer dark roast coffee with oat milk", "How do I take my coffee?", True),
    ("fact", "My sister Leila lives in Toronto", "Where does my sister Leila live?", False),
    ("fact", "I am allergic to peanuts", "Do I have any food allergies?", True),
    ("project", "The Omnix gateway runs on PostgreSQL 17", "Which PostgreSQL version does the Omnix gateway run on?", False),
    ("instruction", "Always answer code questions with Python examples", "What language should code examples use?", True),
    ("relationship", "Marco is my running partner on Sundays", "Who do I run with on Sundays?", False),
    ("fact", "My passport expires in March 2027", "When does my passport expire?", False),
    ("preference", "I like to read science fiction before bed", "What genre do I read at night?", True),
    ("fact", "My dog is a border collie named Juno", "What breed is my dog Juno?", False),
    ("project", "The trading strategy backtests use Alpaca market data", "Where does backtest market data come from?", True),
    ("fact", "I moved to Vancouver in 2021", "When did I move to Vancouver?", False),
    ("preference", "My preferred meeting time is late morning", "When do I like to have meetings?", True),
    ("fact", "My laptop is a ThinkPad X1 Carbon", "Which laptop do I use?", False),
    ("relationship", "Dr. Patel is my family doctor", "Who is my family doctor?", False),
    ("instruction", "Keep replies under three paragraphs unless asked", "How long should your answers be?", True),
    ("fact", "My car is a 2019 Subaru Outback", "What car do I drive?", True),
    ("project", "The audiobook pipeline renders chapters with Qwen TTS", "Which TTS renders audiobook chapters?", False),
    ("fact", "My birthday is on July 14", "When is my birthday?", False),
    ("preference", "I avoid flights that leave before 8 am", "What flight times do I dislike?", True),
    ("fact", "I speak Farsi and English at home", "Which languages are spoken in my home?", True),
    ("relationship", "Ana from accounting approves my expense reports", "Who approves my expense reports?", False),
    ("fact", "My gym membership renews every January", "When does my gym membership renew?", False),
    ("preference", "I like my desk lamp set to warm white", "What lighting do I like at my desk?", True),
]

# (target index, question sharing no meaningful word with the memory)
HARD = [
    (0, "Which title do I enjoy playing most?"),
    (2, "Where is my sibling based?"),
    (3, "Is there anything I must not eat?"),
    (6, "Who joins me for weekend jogs?"),
    (9, "What kind of pet do I have?"),
    (11, "Which city did I relocate to?"),
    (13, "What computer do I work on?"),
    (16, "What vehicle do I own?"),
]

_SUBJECTS = ["coworker", "neighbor", "cousin", "friend", "client", "teacher", "landlord", "colleague"]
_NAMES = ["Sam", "Rita", "Omar", "Lena", "Victor", "Mina", "Jonas", "Priya", "Theo", "Yara", "Ilya", "Nora"]
_THINGS = ["the garden", "the quarterly report", "a road trip", "the kitchen renovation", "a chess club",
           "the photo archive", "a pottery class", "the budget spreadsheet", "a podcast idea", "the bike repair"]
_CATEGORIES = ["preference", "fact", "project", "relationship", "fact", "fact"]


def require_disposable(url: str) -> None:
    name = urlsplit(url).path.lstrip("/")
    if not any(marker in name for marker in ("test", "bench")):
        raise SystemExit(f"refusing to benchmark against {name!r}: the database name must contain 'test' or 'bench'")


def _record(record_id: str, category: str, content: str, *, days_ago: float, confidence: float):
    from app.memory_contracts import MemoryRecord

    stamp = (NOW - timedelta(days=days_ago)).isoformat()
    return MemoryRecord(
        id=record_id, scope="global", scope_id=PROFILE_ID, category=category, source="user_saved",
        content=content, normalized_content=content.casefold(), confidence=confidence,
        provenance_type="user_message", provenance_id=f"message:{record_id}", created_at=stamp, updated_at=stamp,
    )


def build_store(size: int, rng: random.Random) -> tuple[list, dict[str, str]]:
    """``size`` memories: the targets at random ages among deterministic distractors."""
    records, targets = [], {}
    for index, (category, content, _question, _paraphrase) in enumerate(TARGETS):
        record_id = f"target-{index:02d}"
        targets[record_id] = content
        records.append(_record(record_id, category, content, days_ago=rng.uniform(1, 400), confidence=rng.uniform(0.7, 1.0)))
    for index in range(max(0, size - len(TARGETS))):
        name, subject, thing = rng.choice(_NAMES), rng.choice(_SUBJECTS), rng.choice(_THINGS)
        content = f"My {subject} {name} mentioned {thing} on day {index}"
        records.append(_record(f"noise-{index:05d}", rng.choice(_CATEGORIES), content,
                               days_ago=rng.uniform(0, 400), confidence=rng.uniform(0.5, 1.0)))
    rng.shuffle(records)
    return records, targets


def _scope_context():
    from app.memory_contracts import MemoryScopeContext

    return MemoryScopeContext(profile_id=PROFILE_ID, workspace_id="workspace:benchmark", session_id="session:benchmark")


def run_v1_chat(records, question: str) -> tuple[list[str], int]:
    from app.assistant_memory.selection import estimate_memory_tokens, select_memory_records

    selection = select_memory_records(records, _scope_context(), token_budget=TOKEN_BUDGET)
    return [record.id for record in selection.records], sum(estimate_memory_tokens(r.content) for r in selection.records)


def run_v1_companion(records, question: str) -> tuple[list[str], int]:
    from app.assistant_memory.selection import estimate_memory_tokens
    from app.assistant_memory.temporal_retrieval import rank_temporal_records

    items = rank_temporal_records(records, question, now=NOW, timezone_name="UTC", limit=TOP_K)
    return [item.memory_id for item in items], sum(estimate_memory_tokens(item.record.content) for item in items)


class V2Store:
    def __init__(self, database) -> None:
        from app.assistant_memory_v2.convergence import PostgresMemoryV2DerivedCoordinator
        from app.assistant_memory_v2.derived_state import PostgresMemoryV2DerivedStateStore
        from app.assistant_memory_v2.episode_store import PostgresMemoryV2EpisodeStore
        from app.assistant_memory_v2.graph_store import PostgresMemoryV2GraphStore
        from app.assistant_memory_v2.observation_store import PostgresMemoryV2ObservationStore
        from app.assistant_memory_v2.relationship_store import PostgresMemoryV2RelationshipStore
        from app.assistant_memory_v2.retrieval import UnifiedMemoryV2Retriever
        from app.assistant_memory_v2.search_index import PostgresMemoryV2SearchIndex

        self.database = database
        self.observations = PostgresMemoryV2ObservationStore(database)
        self.graph = PostgresMemoryV2GraphStore(database)
        self.derived = PostgresMemoryV2DerivedStateStore(database)
        self.search = PostgresMemoryV2SearchIndex(database)
        self.coordinator = PostgresMemoryV2DerivedCoordinator(
            database, observation_store=self.observations, graph_store=self.graph, derived_store=self.derived,
        )
        from app.assistant_memory_v2.embedding_index import PostgresMemoryV2EmbeddingIndex

        self.embeddings = PostgresMemoryV2EmbeddingIndex(database)
        self.retriever = UnifiedMemoryV2Retriever(
            graph_store=self.graph, observation_store=self.observations,
            episode_store=PostgresMemoryV2EpisodeStore(database),
            relationship_store=PostgresMemoryV2RelationshipStore(database),
            index_graph_revision_provider=self.search.index_graph_revision,
            search_index=self.search, derived_store=self.derived, embedding_index=self.embeddings,
        )
        self.words_retriever = UnifiedMemoryV2Retriever(
            graph_store=self.graph, observation_store=self.observations,
            episode_store=PostgresMemoryV2EpisodeStore(database),
            relationship_store=PostgresMemoryV2RelationshipStore(database),
            index_graph_revision_provider=self.search.index_graph_revision,
            search_index=self.search, derived_store=self.derived,
        )

    def load(self, principal_id: str, records) -> object:
        from app.assistant_memory_v2.convergence import DerivedPlanPayload
        from app.assistant_memory_v2.legacy_shadow import LegacyMemoryV2Importer, legacy_seed_projector

        importer = LegacyMemoryV2Importer(self.observations)
        importer.import_records(principal_id=principal_id, records=records)
        space = importer.space_for(principal_id, records[0])
        prepared = self.coordinator.prepare(
            space,
            lambda _space, window, _existing: DerivedPlanPayload(
                assertions=legacy_seed_projector(window), consolidator_version="memory-benchmark@1",
            ),
        )
        if prepared is not None:
            self.coordinator.commit(prepared)
        self.search.rebuild(space)
        self.embeddings.sync(space)
        return space

    def ask(self, space, question: str, *, words_only: bool = False) -> tuple[list[str], int]:
        from app.assistant_memory_v2.contracts import RetrievalQuery, VisibilityScope

        retriever = self.words_retriever if words_only else self.retriever
        result = retriever.retrieve(RetrievalQuery(
            query_id=f"benchmark:{uuid4().hex}", space=space,
            visible_scopes=(VisibilityScope(kind="global", scope_id=PROFILE_ID),),
            text=question, authority="final", as_of=NOW, top_k=TOP_K, token_budget=TOKEN_BUDGET, deadline_ms=2_000,
        ))
        return [candidate.content for candidate in result.candidates], result.token_estimate


def cleanup(database, principal_ids: list[str]) -> None:
    with database.connection() as connection:
        tables = [row[0] for row in connection.execute(
            """SELECT c.table_name FROM information_schema.columns AS c
                JOIN information_schema.tables AS t ON t.table_name = c.table_name AND t.table_schema = c.table_schema
               WHERE c.table_schema = current_schema() AND c.column_name = 'principal_id'
                 AND c.table_name LIKE 'omnix_memory_v2_%' AND t.table_type = 'BASE TABLE'"""
        ).fetchall()]
        for table in tables:
            connection.execute(f"DELETE FROM {table} WHERE principal_id = ANY(%s)", (principal_ids,))
        connection.commit()


def score(selected_ids: list[str], relevant_id: str, tokens: int, elapsed_ms: float) -> dict:
    hit = relevant_id in selected_ids
    return {
        "hit": hit,
        "rank": selected_ids.index(relevant_id) + 1 if hit else None,
        "injected": len(selected_ids),
        "tokens": tokens,
        "elapsed_ms": elapsed_ms,
    }


def summarize(rows: list[dict], kinds: list[str]) -> dict:
    def recall(selection):
        return round(sum(row["hit"] for row in selection) / len(selection), 3) if selection else None

    main = [row for row, kind in zip(rows, kinds) if kind != "hard"]
    rows_all, rows = rows, main
    injected = [row["injected"] for row in rows]
    return {
        "recall": recall(rows),
        "recall_keyword_questions": recall([row for row, k in zip(rows_all, kinds) if k == "keyword"]),
        "recall_paraphrased_questions": recall([row for row, k in zip(rows_all, kinds) if k == "paraphrase"]),
        "recall_hard_paraphrases": recall([row for row, k in zip(rows_all, kinds) if k == "hard"]),
        "relevant_share_of_injected": round(sum(row["hit"] for row in rows) / max(1, sum(injected)), 4),
        "mean_memories_injected": round(statistics.mean(injected), 1),
        "mean_tokens_injected": round(statistics.mean(row["tokens"] for row in rows), 1),
        "mean_reciprocal_rank": round(statistics.mean((1 / row["rank"]) if row["rank"] else 0 for row in rows), 3),
        "mean_ms": round(statistics.mean(row["elapsed_ms"] for row in rows), 2),
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--database-url", required=True)
    parser.add_argument("--sizes", default="100,500,2000")
    parser.add_argument("--seed", type=int, default=7)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    require_disposable(args.database_url)

    from app.persistence.config import DatabaseSettings
    from app.persistence.database import PostgresDatabase
    from app.persistence.migrations import apply_migrations

    database = PostgresDatabase(DatabaseSettings(url=args.database_url, pool_min=1, pool_max=4, statement_timeout_ms=120_000))
    apply_migrations(database)
    v2 = V2Store(database)
    principals: list[str] = []
    from app.assistant_memory_v2.embeddings import MODEL_ID, default_embedder

    embedder = default_embedder()
    report: dict = {"token_budget": TOKEN_BUDGET, "top_k": TOP_K, "questions": len(TARGETS),
                    "hard_paraphrases": len(HARD), "embedding_model": MODEL_ID if embedder else None, "sizes": {}}
    questions = [(index, question, "paraphrase" if paraphrase else "keyword")
                 for index, (_c, _m, question, paraphrase) in enumerate(TARGETS)]
    questions += [(index, question, "hard") for index, question in HARD]
    kinds = [kind for _index, _question, kind in questions]
    try:
        for size in [int(item) for item in args.sizes.split(",")]:
            rng = random.Random(args.seed + size)
            records, targets = build_store(size, rng)
            principal = f"profile:memory-benchmark-{uuid4().hex[:8]}"
            principals.append(principal)
            load_started = time.perf_counter()
            space = v2.load(principal, records)
            load_seconds = round(time.perf_counter() - load_started, 2)
            content_to_id = {record.content: record.id for record in records}
            results: dict[str, list[dict]] = {"v1_chat": [], "v1_companion": [], "v2_words": [], "v2": []}
            for index, question, _kind in questions:
                relevant = f"target-{index:02d}"
                for path, run in (("v1_chat", lambda q: run_v1_chat(records, q)),
                                  ("v1_companion", lambda q: run_v1_companion(records, q))):
                    started = time.perf_counter()
                    ids, tokens = run(question)
                    results[path].append(score(ids, relevant, tokens, (time.perf_counter() - started) * 1000))
                for path, words_only in (("v2_words", True), ("v2", False)):
                    started = time.perf_counter()
                    contents, tokens = v2.ask(space, question, words_only=words_only)
                    elapsed = (time.perf_counter() - started) * 1000
                    # v2 renders an assertion as "<subject> <predicate> <memory text>".
                    matched = [next((rid for text, rid in content_to_id.items() if c.endswith(text)), "") for c in contents]
                    results[path].append(score(matched, relevant, tokens, elapsed))
            report["sizes"][str(size)] = {
                "v2_load_seconds": load_seconds,
                **{path: summarize(rows, kinds) for path, rows in results.items()},
            }
            print(json.dumps({"size": size, **{p: report["sizes"][str(size)][p]["recall"] for p in results}}), flush=True)
    finally:
        cleanup(database, principals)
        database.close()
    text = json.dumps(report, indent=2)
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(text + "\n", encoding="utf-8")
    print(text)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
