"""Memory v2 embedding retrieval (VoiceMem's dual-brain retrieval, step 2 of the owner-approved plan).

A fake embedder maps related words to the same dimension, so these tests run
without the e5 model: "vehicle" lands next to "Subaru", which shares no word
with the question.
"""
from __future__ import annotations

import hashlib
import os
import re
from datetime import datetime, timedelta, timezone
from uuid import uuid4

import numpy as np
import pytest

from app.assistant_memory.v2 import (
    GraphAssertion,
    GraphEntityRef,
    GraphValue,
    MemorySpaceKey,
    ObservationProvenance,
    VisibilityScope,
)
from app.assistant_memory.v2.contracts import RetrievalQuery
from app.assistant_memory.v2.embedding_index import PostgresMemoryV2EmbeddingIndex, content_digest
from app.assistant_memory.v2.embeddings import DIMENSIONS, MODEL_ID
from app.assistant_memory.v2.episode_store import PostgresMemoryV2EpisodeStore
from app.assistant_memory.v2.graph_store import PostgresMemoryV2GraphStore
from app.assistant_memory.v2.observation_store import ObservationAppendRequest, PostgresMemoryV2ObservationStore
from app.assistant_memory.v2.relationship_store import PostgresMemoryV2RelationshipStore
from app.assistant_memory.v2.retrieval import UnifiedMemoryV2Retriever
from app.assistant_memory.v2.search_index import PostgresMemoryV2SearchIndex
from app.persistence.config import DatabaseSettings
from app.persistence.database import PostgresDatabase
from app.persistence.migrations import apply_migrations

pytestmark = pytest.mark.skipif(
    not os.environ.get("OMNIX_TEST_DATABASE_URL"),
    reason="OMNIX_TEST_DATABASE_URL is required for PostgreSQL integration tests",
)

GLOBAL = VisibilityScope(kind="global", scope_id="global")
NOW = datetime(2026, 10, 2, 12, tzinfo=timezone.utc)
_CONCEPTS = {
    "vehicle": 0, "car": 0, "subaru": 0, "outback": 0, "drive": 0,
    "pet": 1, "dog": 1, "collie": 1, "juno": 1,
    "coffee": 2, "roast": 2, "oat": 2,
}


class ConceptEmbedder:
    """Words of one concept share a dimension; other words hash to the rest.

    A shared component puts cosines where e5's sit (unrelated texts about 0.8,
    related ones higher), which the retriever's calibration expects.
    """

    def __init__(self) -> None:
        self.calls = 0

    def embed(self, texts, *, kind):
        self.calls += len(texts)
        vectors = np.zeros((len(texts), DIMENSIONS), dtype=np.float32)
        for row, text in enumerate(texts):
            vectors[row, 15] = 6.0
            for word in re.findall(r"[a-z0-9]+", text.casefold()):
                index = _CONCEPTS.get(word)
                if index is None:
                    index = 16 + int(hashlib.sha256(word.encode()).hexdigest(), 16) % (DIMENSIONS - 16)
                vectors[row, index] += 1.0
            vectors[row] /= max(1e-9, float(np.linalg.norm(vectors[row])))
        return vectors


@pytest.fixture
def stores():
    database = PostgresDatabase(DatabaseSettings(url=os.environ["OMNIX_TEST_DATABASE_URL"], pool_min=1, pool_max=6))
    apply_migrations(database)
    embedder = ConceptEmbedder()
    observations = PostgresMemoryV2ObservationStore(database)
    graph = PostgresMemoryV2GraphStore(database)
    search = PostgresMemoryV2SearchIndex(database)
    embeddings = PostgresMemoryV2EmbeddingIndex(database, embedder_provider=lambda: embedder)
    retriever = UnifiedMemoryV2Retriever(
        graph_store=graph, observation_store=observations,
        episode_store=PostgresMemoryV2EpisodeStore(database),
        relationship_store=PostgresMemoryV2RelationshipStore(database),
        index_graph_revision_provider=search.index_graph_revision,
        search_index=search, embedding_index=embeddings,
    )
    try:
        yield database, observations, graph, search, embeddings, retriever, embedder
    finally:
        database.close()


def _space() -> MemorySpaceKey:
    return MemorySpaceKey(principal_id="profile:embedding-test", owner_type="character", owner_id=f"embed-{uuid4().hex}")


def _remember(observations, graph, space, facts):
    """Each fact as an observation plus an active assertion (unique ids per run)."""
    assertions = {}
    for index, (text, scope) in enumerate(facts):
        observation = observations.append(ObservationAppendRequest(
            space=space, visibility_scope=scope, event_type="user_said",
            occurred_at=NOW - timedelta(minutes=len(facts) - index),
            provenance=ObservationProvenance(source_type="user", source_id="user:alice", trust_level="user_explicit"),
            idempotency_key=f"{space.owner_id}:{index}", payload={"text": text},
        ))
        assertion = GraphAssertion(
            assertion_id=f"assert:{uuid4().hex}", space=space, visibility_scopes=(scope,),
            subject=GraphEntityRef(entity_id="user:alice", entity_type="user"),
            predicate="said", object=GraphValue(kind="literal", literal=text),
            domain="fact", confidence=0.9, evidence_observation_ids=(observation.observation_id,),
            derivation_version="embedding-test@1",
        )
        graph.put(assertion, source_observation_watermark=observation.authority_sequence)
        assertions[text] = assertion
    return assertions


def _query(space, text):
    return RetrievalQuery(query_id=f"q:{uuid4().hex}", space=space, visible_scopes=(GLOBAL,), text=text,
                          authority="final", as_of=NOW + timedelta(days=1), top_k=5, token_budget=600, deadline_ms=5_000)


def test_a_paraphrase_finds_its_memory_through_embeddings(stores) -> None:
    _database, observations, graph, search, embeddings, retriever, _embedder = stores
    space = _space()
    facts = _remember(observations, graph, space, [
        ("I drive a 2019 Subaru Outback", GLOBAL),
        ("My dog is a border collie named Juno", GLOBAL),
        ("I like dark roast with oat milk", GLOBAL),
    ])
    search.rebuild(space)
    assert embeddings.sync(space) == 3

    result = retriever.retrieve(_query(space, "Which vehicle is mine?"))

    assert result.candidates[0].ref_id == facts["I drive a 2019 Subaru Outback"].assertion_id
    assert "embedding_candidate" in result.candidates[0].reasons
    assert search.search(space, "Which vehicle is mine?", visible_scopes=(GLOBAL,)) == []  # no shared word


def test_sync_reuses_vectors_and_drops_those_of_forgotten_memories(stores) -> None:
    database, observations, graph, search, embeddings, _retriever, embedder = stores
    space = _space()
    facts = _remember(observations, graph, space, [
        ("I drive a 2019 Subaru Outback", GLOBAL),
        ("My dog is a border collie named Juno", GLOBAL),
    ])
    search.rebuild(space)
    embeddings.sync(space)
    calls = embedder.calls

    search.rebuild(space)
    assert embeddings.sync(space) == 0 and embedder.calls == calls  # unchanged texts are not embedded again

    forgotten = facts["My dog is a border collie named Juno"]
    graph.put(forgotten.model_copy(update={"status": "retracted", "revision": forgotten.revision + 1}),
              source_observation_watermark=observations.watermark(space))
    search.rebuild(space)
    embeddings.sync(space)
    with database.transaction() as connection:
        digests = {row[0] for row in connection.execute(
            "SELECT content_digest FROM omnix_memory_v2_embeddings WHERE principal_id = %s AND owner_id = %s AND model_id = %s",
            (space.principal_id, space.owner_id, MODEL_ID),
        ).fetchall()}
    remaining = {hit.content for hit in search.search(space, "subaru", visible_scopes=(GLOBAL,))}
    assert digests == {content_digest(text) for text in remaining}
    assert all("collie" not in text for text in remaining)


def test_embeddings_never_reach_a_memory_outside_the_visible_scopes(stores) -> None:
    _database, observations, graph, search, embeddings, retriever, _embedder = stores
    space = _space()
    project = VisibilityScope(kind="project", scope_id="project:secret")
    facts = _remember(observations, graph, space, [
        ("The project car is a Subaru Outback", project),
        ("My dog is a border collie named Juno", GLOBAL),
    ])
    search.rebuild(space)
    embeddings.sync(space)

    result = retriever.retrieve(_query(space, "Which vehicle is mine?"))

    assert facts["The project car is a Subaru Outback"].assertion_id not in [item.ref_id for item in result.candidates]


def test_without_a_model_retrieval_falls_back_to_words(stores) -> None:
    database, observations, graph, search, _embeddings, _retriever, _embedder = stores
    space = _space()
    _remember(observations, graph, space, [("I drive a 2019 Subaru Outback", GLOBAL)])
    search.rebuild(space)
    missing = PostgresMemoryV2EmbeddingIndex(database, embedder_provider=lambda: None)

    assert missing.sync(space) == 0
    assert missing.nearest(space, "Which vehicle is mine?", limit=5) == []
