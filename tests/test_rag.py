from __future__ import annotations

from glassview_ai.rag import HashEmbedder, MemoryStore


def test_recall_returns_most_relevant_memory() -> None:
    store = MemoryStore(embedder=HashEmbedder(dim=256))
    store.add("Postgres connection refused on port 5432 while running migrations")
    store.add("The cat sat on a warm windowsill in the afternoon sun")
    store.add("Kubernetes pod stuck in CrashLoopBackOff after a bad deploy")

    hits = store.query("database connection error postgres", k=2)
    assert hits
    assert "Postgres" in hits[0].text
    # Distances are sorted ascending (nearest first).
    assert hits == sorted(hits, key=lambda h: h.distance)
    store.close()


def test_secret_is_redacted_before_storage() -> None:
    store = MemoryStore(embedder=HashEmbedder(dim=128))
    store.add("login with password = supersecretvalue123 to the box")
    hit = store.query("login password", k=1)[0]
    assert "supersecretvalue123" not in hit.text
    assert "[REDACTED:SECRET]" in hit.text
    store.close()


def test_meta_round_trips() -> None:
    store = MemoryStore()
    store.add("a build failed", meta={"chat_id": "c1", "kind": "answer"})
    hit = store.query("build failure", k=1)[0]
    assert hit.meta["chat_id"] == "c1"
    store.close()
