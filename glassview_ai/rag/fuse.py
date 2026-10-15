"""Fold recalled memories into the prompt.

The mirror of :func:`glassview_ai.ocr.fuse_prompt`: OCR supplies what is on the
screen *now*, this supplies what was said *before*. Recall is advisory — the
block is explicitly labelled as possibly-unrelated so a bad hit degrades the
answer's preamble rather than its facts.

Selection deliberately does not rely on the vector distance alone. The default
:class:`~glassview_ai.rag.embed.HashEmbedder` is lexical, not semantic: measured
on this corpus, a genuine match scores ~0.99-1.17, text sharing only stopwords
scores ~1.21, and unrelated text sits at exactly sqrt(2) ~= 1.414. That leaves
too little room to separate a real hit from noise with a distance cut alone, so
a hit must *also* share a content word with the query.
"""

from __future__ import annotations

import re
from collections.abc import Iterable, Sequence

from .store import MemoryHit

MAX_RECALL_CHARS = 1200  # keep the fused prompt bounded
MAX_HITS = 3

# Anything at or above orthogonal (sqrt(2)) shares nothing; treat it as no hit.
MAX_DISTANCE = 1.40

_TOKEN = re.compile(r"[a-z0-9]{3,}")

# Words too common to count as evidence that two texts are about the same thing.
_STOPWORDS = frozenset(
    """
    the and for are but not you all any can had her was one our out day get has him his
    how man new now old see two way who did its let put say she too use with that this
    from have they what when your there their would about which been were will more
    into some than then them these want does doing just like make made over such take
    very well why here also back even much most only same take that's whats does why
    """.split()
)


def _content_tokens(text: str) -> set[str]:
    return {t for t in _TOKEN.findall(text.lower()) if t not in _STOPWORDS}


def select_hits(
    hits: Iterable[MemoryHit],
    query: str,
    *,
    exclude_chat_id: str | None = None,
    max_distance: float = MAX_DISTANCE,
    limit: int = MAX_HITS,
) -> list[MemoryHit]:
    """Filter raw query hits down to the ones worth putting in a prompt.

    A hit is kept when it beats ``max_distance``, is not from
    ``exclude_chat_id``, and shares at least one content word with ``query``.
    The chat-id exclusion matters because the current chat's own turns are
    already replayed as history: recalling them wastes context and encourages
    the model to parrot its previous answer.
    """
    wanted = _content_tokens(query)
    kept: list[MemoryHit] = []
    for hit in hits:
        if hit.distance > max_distance:
            continue
        if exclude_chat_id is not None and hit.meta.get("chat_id") == exclude_chat_id:
            continue
        if wanted and not (wanted & _content_tokens(hit.text)):
            continue
        kept.append(hit)
        if len(kept) >= limit:
            break
    return kept


def fuse_recall(question: str, hits: Sequence[MemoryHit]) -> str:
    """Prepend recalled memories to the question, if any survived selection."""
    if not hits:
        return question

    lines: list[str] = []
    used = 0
    for hit in hits:
        snippet = " ".join(hit.text.split())
        if used + len(snippet) > MAX_RECALL_CHARS:
            snippet = snippet[: max(0, MAX_RECALL_CHARS - used)]
        if not snippet:
            break
        lines.append(f"- {snippet}")
        used += len(snippet)
        if used >= MAX_RECALL_CHARS:
            break

    if not lines:
        return question

    joined = "\n".join(lines)
    return (
        "Notes recalled from earlier sessions (may be unrelated - ignore them if so):\n"
        f"{joined}\n\n"
        f"{question}"
    )
