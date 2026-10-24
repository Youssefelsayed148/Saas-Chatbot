"""R2-6: whole-document fetch uses the chunk's own language and the
cross-language fallback still runs when only always-include documents matched."""

from typing import Any
from uuid import UUID

from sqlalchemy import text

import tests.retrieval_helpers as helpers
from app.retrieval.service import assemble_evidence, retrieve

corpus = helpers.corpus


def _ids(db: Any, corpus: dict[str, Any]) -> tuple[UUID, UUID]:
    users = corpus["users_a"]
    revision = UUID(helpers.published_revision_id(db, users.tenant_id, corpus["bot_main"]))
    return users.tenant_id, revision


def test_whole_document_fetch_uses_the_chunks_own_language(db: Any, corpus: dict[str, Any]) -> None:
    tenant_id, revision = _ids(db, corpus)
    english = retrieve(
        db,
        tenant_id=tenant_id,
        bot_id=UUID(corpus["bot_main"]),
        revision_id=revision,
        question="opening hours",
        question_language="en",
        settings=corpus["settings"],
    )
    hit = english.candidates[0]
    assert hit.language == "en"
    # A hybrid pass can be labelled "ar" while its best vector hit is English.
    evidence = assemble_evidence(
        db,
        tenant_id=tenant_id,
        bot_id=UUID(corpus["bot_main"]),
        revision_id=revision,
        language="ar",
        ranked=[hit],
        settings=corpus["settings"],
        always_include_document_ids=None,
    )
    document_chunks = set(
        db.execute(
            text("SELECT id FROM chunks WHERE document_id = :d"), {"d": hit.document_id}
        ).scalars()
    )
    assert document_chunks and {c.chunk_id for c in evidence} >= document_chunks


def test_always_include_only_evidence_still_runs_the_cross_language_fallback(
    db: Any, corpus: dict[str, Any]
) -> None:
    tenant_id, revision = _ids(db, corpus)
    reserved = db.execute(
        text(
            "SELECT id FROM documents WHERE revision_id = CAST(:r AS uuid) "
            "AND title = 'Return policy'"
        ),
        {"r": str(revision)},
    ).scalar_one()
    result = retrieve(
        db,
        tenant_id=tenant_id,
        bot_id=UUID(corpus["bot_main"]),
        revision_id=revision,
        question="zzqq",  # no English hit at all
        question_language="en",
        bot_primary_language="ar",
        settings=corpus["settings"],
        always_include_document_ids={str(reserved)},
        translate_query=lambda raw, target: "ساعات العمل",
    )
    assert result.used_fallback and result.applied_language == "ar"
    assert result.fallback_query == "ساعات العمل"
    assert "ar" in {c.language for c in result.evidence}
    assert reserved in {c.document_id for c in result.evidence}  # reserved slot kept

    # Nothing anywhere: the reserved document is still returned, no fallback claimed.
    nothing = retrieve(
        db,
        tenant_id=tenant_id,
        bot_id=UUID(corpus["bot_main"]),
        revision_id=revision,
        question="zzqq",
        question_language="en",
        bot_primary_language="ar",
        settings=corpus["settings"],
        always_include_document_ids={str(reserved)},
        translate_query=lambda raw, target: "قققق",
    )
    assert not nothing.used_fallback
    assert {c.document_id for c in nothing.evidence} == {reserved}
