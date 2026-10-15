"""Recall selection + prompt fusion (pure functions, no store needed)."""

from __future__ import annotations

from glassview_ai.rag import fuse_recall, select_hits
from glassview_ai.rag.fuse import MAX_RECALL_CHARS
from glassview_ai.rag.store import MemoryHit


def _hit(text: str, distance: float, chat_id: str = "other") -> MemoryHit:
    return MemoryHit(text=text, distance=distance, meta={"chat_id": chat_id}, created_at=0.0)


def test_distant_hits_are_dropped() -> None:
    hits = [_hit("close", 0.4), _hit("far", 1.9)]
    assert [h.text for h in select_hits(hits, "close")] == ["close"]


def test_current_chat_is_excluded() -> None:
    """The current chat's turns are already replayed as history."""
    hits = [_hit("mine", 0.1, chat_id="chat_a"), _hit("theirs", 0.2, chat_id="chat_b")]
    kept = select_hits(hits, "mine theirs", exclude_chat_id="chat_a")
    assert [h.text for h in kept] == ["theirs"]


def test_limit_caps_the_number_of_hits() -> None:
    hits = [_hit(f"note {i}", 0.1) for i in range(10)]
    assert len(select_hits(hits, "note", limit=2)) == 2


def test_fuse_recall_is_identity_without_hits() -> None:
    assert fuse_recall("what broke?", []) == "what broke?"


def test_fuse_recall_prepends_notes_and_keeps_question_last() -> None:
    out = fuse_recall("what broke?", [_hit("Q: db down A: restart it", 0.2)])
    assert "restart it" in out
    assert out.rstrip().endswith("what broke?")


def test_fuse_recall_is_bounded() -> None:
    hits = [_hit("x" * 5000, 0.1), _hit("y" * 5000, 0.2)]
    out = fuse_recall("q", hits)
    assert len(out) < MAX_RECALL_CHARS + 300


def test_hit_sharing_only_stopwords_is_rejected() -> None:
    """The lexical embedder scores stopword overlap close to a real match, so
    selection requires a shared *content* word, not just a good distance."""
    hits = [_hit("Q: what is the best way to bake a cake with the oven on", 1.21)]
    assert select_hits(hits, "why does the deploy fail with the database") == []


def test_hit_sharing_a_content_word_is_kept() -> None:
    hits = [_hit("Q: the deploy fails with ECONNREFUSED 5432", 1.17)]
    assert len(select_hits(hits, "why ECONNREFUSED 5432 on deploy")) == 1
