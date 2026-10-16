"""P3-01: retrieval per docs/14 §2 and §5.

Seeds a real corpus through the actual ingest pipeline (upload → job →
publish) and then queries the retrieval service directly. Every retrieval
filter (tenant / bot / published revision / language) has a seeded decoy
that would (wrongly) match if that filter were removed. Arabic
normalisation, ال variants and prefix matching get dedicated cases.
"""

from typing import Any
from uuid import UUID

from sqlalchemy import text
from sqlalchemy.orm import Session as OrmSession

import tests.retrieval_helpers as _rh  # noqa: F401 — registers the corpus fixture
from app.knowledge.language import normalise_text
from app.retrieval.query import build_tsquery
from app.retrieval.service import retrieve
from tests.helpers import make_bot
from tests.knowledge_helpers import (
    drain_jobs,
    publish_draft,
    start_ingestion,
    upload_sources,
)
from tests.retrieval_helpers import (
    MD_AR_PLURAL,
    MD_CONTACT,
    TMP,
    languages,
    published_revision_id,
    retrieval_settings,
    titles,
)

corpus = _rh.corpus  # the import is consumed as a pytest fixture parameter name


def run_retrieval(
    db: OrmSession,
    users: Any,
    bot_id: str,
    question: str,
    *,
    question_language: str = "en",
    settings: Any = None,
    always_include: set[str] | None = None,
) -> Any:
    return retrieve(
        db,
        tenant_id=users.tenant_id,
        bot_id=UUID(bot_id),
        revision_id=UUID(published_revision_id(db, users.tenant_id, bot_id)),
        question=question,
        question_language=question_language,
        bot_primary_language="en",
        settings=settings,
        always_include_document_ids=always_include,
    )


def _engine(db: OrmSession) -> Any:
    from app.db.session import get_engine

    return get_engine()


# --- all four filters: tenant / bot / published revision / language ------------


def test_every_filter_holds(app: Any, db: OrmSession, corpus: dict[str, Any]) -> None:
    users = corpus["users_a"]
    result = run_retrieval(db, users, corpus["bot_main"], "What are your opening hours?")
    assert result.used_fallback is False
    assert result.applied_language == "en"
    # tenant filter: tenant B runs the identical copy — only tenant A rows return;
    # bot filter: the decoy bot's own "Opening hours" copy stays out;
    # revision filter: the unpublished "changed" draft never shows.
    assert titles(result.evidence) == {"Opening hours"}

    ids = [str(chunk.chunk_id) for chunk in result.evidence]
    in_scope = db.execute(
        text(
            "SELECT COUNT(*) FROM chunks "
            "WHERE id IN (SELECT unnest(CAST(:ids AS uuid[]))) "
            "AND tenant_id = CAST(:t AS uuid) AND bot_id = CAST(:b AS uuid) "
            "AND revision_id = CAST(:r AS uuid) AND language = 'en'"
        ),
        {
            "ids": ids,
            "t": str(users.tenant_id),
            "b": corpus["bot_main"],
            "r": published_revision_id(db, users.tenant_id, corpus["bot_main"]),
        },
    ).scalar_one()
    assert in_scope == len(ids) > 0


def test_decoys_would_match_without_filters(
    app: Any, db: OrmSession, corpus: dict[str, Any]
) -> None:
    """Sanity: each decoy really matches its words, so the filters matter."""
    decoy_rows = db.execute(
        text(
            "SELECT COUNT(*) FROM chunks c JOIN documents d ON d.id = c.document_id "
            "WHERE c.bot_id = CAST(:b AS uuid) AND d.title = 'Opening hours'"
        ),
        {"b": corpus["bot_decoy"]},
    ).scalar_one()
    assert decoy_rows > 0
    tenant_b_rows = db.execute(
        text(
            "SELECT COUNT(*) FROM chunks c JOIN documents d ON d.id = c.document_id "
            "WHERE c.tenant_id = CAST(:t AS uuid) AND d.title = 'Opening hours'"
        ),
        {"t": str(corpus["users_b"].tenant_id)},
    ).scalar_one()
    assert tenant_b_rows > 0
    draft_rows = db.execute(
        text(
            "SELECT COUNT(*) FROM chunks c JOIN documents d ON d.id = c.document_id "
            "JOIN knowledge_revisions kr ON kr.id = c.revision_id "
            "WHERE kr.bot_id = CAST(:b AS uuid) AND kr.status = 'draft' "
            "AND d.title = 'Opening hours changed'"
        ),
        {"b": corpus["bot_main"]},
    ).scalar_one()
    assert draft_rows > 0


def test_decoys_never_returned(app: Any, db: OrmSession, corpus: dict[str, Any]) -> None:
    result = run_retrieval(
        db, corpus["users_a"], corpus["bot_main"], "returns within days delivery invoice"
    )
    assert titles(result.evidence) == {"Return policy"}


def test_arabic_language_pass(app: Any, db: OrmSession, corpus: dict[str, Any]) -> None:
    result = run_retrieval(
        db, corpus["users_a"], corpus["bot_main"], "ساعات العمل", question_language="ar"
    )
    assert result.used_fallback is False
    assert result.applied_language == "ar"
    assert languages(result.evidence) == {"ar"}
    # Indexed text covers title+heading+text (§4), so the heading word hits.
    assert "الأسئلة الشائعة" in titles(result.evidence)


def test_cross_language_fallback(app: Any, db: OrmSession, corpus: dict[str, Any]) -> None:
    result = run_retrieval(
        db,
        corpus["users_a"],
        corpus["bot_main"],
        "invoice delivery",
        question_language="ar",
    )
    # The Arabic pass finds nothing (the words exist only in the EN content);
    # the fallback runs against the bot's primary language and finds the EN hits.
    assert result.used_fallback is True
    assert result.applied_language == "en"
    assert titles(result.evidence) == {"Return policy"}


# --- Arabic normalisation, ال variants, prefix matching ------------------------


def test_arabic_normalisation_and_prefix(
    app: Any, db: OrmSession, corpus: dict[str, Any], tmp_path: Any
) -> None:
    users = corpus["users_a"]
    upload = upload_sources(
        users, corpus["bot_main"], [("plural.md", MD_AR_PLURAL.encode())], tmp_path
    )
    assert upload.status_code == 201
    start = start_ingestion(users, corpus["bot_main"])
    assert start.status_code == 202
    drain_jobs(_engine(db), TMP)
    publish_draft(users, corpus["bot_main"])
    db.expire_all()

    def titles_for(question: str) -> set[str]:
        result = run_retrieval(db, users, corpus["bot_main"], question, question_language="ar")
        return titles(result.evidence)

    # Diacritics in the question are stripped: مُتَى → متي (matches متي).
    plural = titles_for("مُتَى تَفْتَحُونَ")
    assert "أوقات الإقبال" in plural
    # Prefix: the bare verb تَفْتَح matches تفتحون via تفتح:*.
    prefix = titles_for("تَفْتَحُ")
    assert "أوقات الإقبال" in prefix
    # ال variants hit the same page for both the articled and bare question forms.
    assert "الأسئلة الشائعة" in titles_for("الأسئلة")
    assert "الأسئلة الشائعة" in titles_for("أسئلة")


def test_tsquery_builder_rules() -> None:
    assert build_tsquery("What are your opening hours now?", "en") == "opening | hours | now"
    assert build_tsquery("i do it a", "en") is None  # stop words / short tokens
    query = build_tsquery("مرحبا إلى الساعات", "ar")
    assert query is not None
    assert "الساعات" in query and "الساعات:*" in query  # bare + stripped variants
    assert "ساعات" in query and "ساعات:*" in query  # .article-prefixed variants
    assert normalise_text("مُتَى") == "متي"  # ى → ي per spec
    assert build_tsquery("", "en") is None
    assert build_tsquery("!!!!! ???", "en") is None


# --- evidence shaping -----------------------------------------------------------


def test_best_document_whole_and_budget_cap(
    app: Any, db: OrmSession, corpus: dict[str, Any], tmp_path: Any
) -> None:
    users = corpus["users_a"]
    bot = make_bot(users, "LongDoc")
    long_text = " ".join(f"Hour sentence {index} about the showroom rows." for index in range(600))
    settings = retrieval_settings()
    doc = (
        f"---\ntitle: Long hour policy\nlanguage: en\n---\n\n# Reach\n\n{long_text}\n"
        "\n# Contact hours\n\nYou can contact the team during hours.\n"
    )
    upload = upload_sources(users, str(bot["id"]), [("long.md", doc.encode())], TMP)
    assert upload.status_code == 201
    start = start_ingestion(users, str(bot["id"]))
    assert start.status_code == 202
    drain_jobs(_engine(db), TMP)
    revision_id = publish_draft(users, str(bot["id"]))
    db.expire_all()

    result = retrieve(
        db,
        tenant_id=users.tenant_id,
        bot_id=UUID(str(bot["id"])),
        revision_id=UUID(revision_id),
        question="hour",
        question_language="en",
        settings=settings,
    )
    doc_counts: dict[str, int] = {}
    for chunk in result.evidence:
        doc_counts[str(chunk.document_id)] = doc_counts.get(str(chunk.document_id), 0) + 1
    best_total = db.execute(
        text(
            "SELECT COUNT(*) FROM chunks WHERE document_id = CAST(:d AS uuid) AND language = 'en'"
        ),
        {"d": str(result.evidence[0].document_id)},
    ).scalar_one()
    assert best_total > 1  # the long document really has multiple chunks
    # The best document is included whole, capped by the hard evidence limit.
    assert doc_counts[str(result.evidence[0].document_id)] == min(
        best_total, settings.retrieval_max_evidence_chunks
    )
    assert len(result.evidence) <= settings.retrieval_max_evidence_chunks


def test_always_include_reserved_slots(
    app: Any, db: OrmSession, corpus: dict[str, Any], tmp_path: Any
) -> None:
    users = corpus["users_a"]
    upload = upload_sources(users, corpus["bot_main"], [("contact.md", MD_CONTACT.encode())], TMP)
    assert upload.status_code == 201
    start = start_ingestion(users, corpus["bot_main"])
    assert start.status_code == 202
    drain_jobs(_engine(db), TMP)
    revision_id = publish_draft(users, corpus["bot_main"])
    db.expire_all()

    contact_ids = db.execute(
        text(
            "SELECT id FROM documents "
            "WHERE revision_id = CAST(:r AS uuid) AND title = 'Contact page'"
        ),
        {"r": revision_id},
    ).scalars()
    reserved = {str(value) for value in contact_ids}
    result = run_retrieval(
        db,
        users,
        corpus["bot_main"],
        "returns within days delivery invoice",
        always_include=reserved,
    )
    assert "Return policy" in titles(result.evidence)
    assert "Contact page" in titles(result.evidence)  # reserved slot, included whole
    contact_chunks = [chunk for chunk in result.evidence if chunk.title == "Contact page"]
    whole = db.execute(
        text("SELECT COUNT(*) FROM chunks WHERE document_id = CAST(:d AS uuid)"),
        {"d": str(contact_chunks[0].document_id)},
    ).scalar_one()
    assert len(contact_chunks) == whole


def test_lexical_signal_count_uses_postgres_terms_and_tenant_scope(
    db: OrmSession,
    corpus: dict[str, Any],
) -> None:
    from dataclasses import replace

    from app.retrieval.service import score_lexical

    users = corpus["users_a"]
    bot_id = corpus["bot_main"]
    result = run_retrieval(db, users, bot_id, "opening hours")
    assert result.evidence and all(c.matched_terms == 2 for c in result.evidence)
    # Inflections collapse to one English tsquery; repetition cannot inflate the count.
    score_lexical(
        db,
        result.evidence,
        tenant_id=users.tenant_id,
        bot_id=UUID(bot_id),
        revision_id=UUID(published_revision_id(db, users.tenant_id, bot_id)),
        question="hour hours hours",
        language="en",
    )
    assert all(c.matched_terms == 1 for c in result.evidence)
    foreign = [replace(c) for c in result.evidence]
    score_lexical(
        db,
        foreign,
        tenant_id=corpus["users_b"].tenant_id,
        bot_id=UUID(bot_id),
        revision_id=UUID(published_revision_id(db, users.tenant_id, bot_id)),
        question="opening hours",
        language="en",
    )
    assert all(c.fts_match == 0 and c.matched_terms == 0 for c in foreign)
    arabic = run_retrieval(db, users, bot_id, "العمل", question_language="ar")
    assert arabic.evidence and all(c.matched_terms == 1 for c in arabic.evidence)


def test_arabic_index_uses_the_real_arabic_configuration(db: OrmSession) -> None:
    definition = db.execute(
        text(
            "SELECT pg_get_expr(d.adbin, d.adrelid) FROM pg_attrdef d "
            "JOIN pg_attribute a ON a.attrelid = d.adrelid AND a.attnum = d.adnum "
            "WHERE d.adrelid = 'chunks'::regclass AND a.attname = 'fts_ar'"
        )
    ).scalar_one()
    assert "'arabic'" in definition and "text_norm" in definition
    # Snowball stemming: singular and plural share a lexeme (the simple config did not).
    assert db.execute(
        text("SELECT to_tsvector('arabic', 'المكتبات') = to_tsvector('arabic', 'مكتبة')")
    ).scalar_one()


def test_arabic_text_is_normalised_before_indexing() -> None:
    # Diacritics and tatweel removed; alef (أ إ آ) and ya (ى) variants folded.
    assert normalise_text("أَإآ") == "ااا"
    assert normalise_text("مَدرَسـة") == "مدرسة"
    assert normalise_text("على") == "علي"
