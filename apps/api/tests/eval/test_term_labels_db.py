"""B.3 / B.5 on the real index: term labels in the trace and the ignore list.

Needs the disposable database (the SQL in ``score_lexical`` is exercised here;
the offline suite covers the pure logic).
"""

from typing import Any
from uuid import UUID

import tests.retrieval_helpers as helpers
from app.retrieval.service import retrieve

corpus = helpers.corpus


def _retrieve(db: Any, corpus: dict[str, Any], question: str, **overrides: Any) -> Any:
    users = corpus["users_a"]
    settings = corpus["settings"].model_copy(update=overrides)
    return retrieve(
        db,
        tenant_id=users.tenant_id,
        bot_id=UUID(corpus["bot_main"]),
        revision_id=UUID(helpers.published_revision_id(db, users.tenant_id, corpus["bot_main"])),
        question=question,
        question_language="en",
        settings=settings,
    )


def test_trace_labels_are_consistent_with_the_counts(db: Any, corpus: dict[str, Any]) -> None:
    result = _retrieve(db, corpus, "What are your opening hours today?")
    assert result.evidence
    for chunk in result.evidence:
        assert chunk.query_term_labels == ["opening", "hours", "today"]
        assert chunk.matched_terms == len(chunk.matched_term_labels)
        assert set(chunk.matched_term_labels) <= set(chunk.query_term_labels)
    assert any("hours" in chunk.matched_term_labels for chunk in result.evidence)


def test_ignore_terms_change_the_count_but_not_the_ranking(db: Any, corpus: dict[str, Any]) -> None:
    plain = _retrieve(db, corpus, "opening hours")
    ignoring = _retrieve(db, corpus, "opening hours", retrieval_gate_ignore_terms=["opening"])
    assert [c.chunk_id for c in plain.evidence] == [c.chunk_id for c in ignoring.evidence]
    for chunk in ignoring.evidence:
        assert chunk.query_term_labels == ["hours"]
        assert chunk.query_terms == 1
    assert max(c.query_terms for c in plain.evidence) == 2
