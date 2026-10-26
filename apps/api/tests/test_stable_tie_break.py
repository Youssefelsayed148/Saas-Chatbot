"""R3-8: equal-score documents rank by title, page and ordinal, never by chunk
UUID, so the same corpus ranks the same on every seeding."""

from dataclasses import replace
from uuid import UUID, uuid4

from fastapi import FastAPI
from sqlalchemy.orm import Session as OrmSession

from app.core.config import get_settings
from app.retrieval import hybrid
from app.retrieval.service import RetrievedChunk, retrieve
from tests.helpers import make_bot, seeded_tenant
from tests.knowledge_helpers import drain_jobs, publish_draft, start_ingestion, upload_sources
from tests.retrieval_helpers import TMP, _engine, published_revision_id, retrieval_settings


def doc(title: str, body: str) -> bytes:
    return (
        f"---\ntitle: {title}\nsource_url: https://t.example.com/{title.lower()}\n"
        f"language: en\npage_type: faq\n---\n\n# {title}\n\n{body}\n"
    ).encode()


def test_fusion_ties_follow_title_not_chunk_id() -> None:
    base = RetrievedChunk(uuid4(), uuid4(), "T", None, "x", "en", 0, 0, None, "1", 4, 0)
    # The same two equal-score chunks with the UUIDs in both orders: the old
    # chunk-id tie-break flips the result, the title tie-break must not.
    for alpha_id, beta_id in ((UUID(int=1), UUID(int=2)), (UUID(int=2), UUID(int=1))):
        alpha = replace(base, chunk_id=alpha_id, title="Alpha")
        beta = replace(base, chunk_id=beta_id, title="Beta")
        for fts, vectors in (([alpha], [beta]), ([beta], [alpha])):
            fused = hybrid.fuse(fts, vectors, 8, 60)
            assert [c.title for c in fused] == ["Alpha", "Beta"]


def test_page_then_ordinal_break_the_next_tie() -> None:
    base = RetrievedChunk(uuid4(), uuid4(), "T", None, "x", "en", 0, 0, None, "1", 4, 0)
    low = replace(base, chunk_id=UUID(int=1), page_ref="2", ordinal=0)
    high = replace(base, chunk_id=UUID(int=2), page_ref="1", ordinal=5)
    fused = hybrid.fuse([low], [high], 8, 60)
    assert [c.page_ref for c in fused] == ["1", "2"]  # page before ordinal before chunk id


def test_reseeded_corpus_ranks_equal_documents_the_same(app: FastAPI, db: OrmSession) -> None:
    """Three independent seedings (fresh tenant, bot, document and chunk UUIDs) of
    two documents with identical text: the order is the title order every time."""
    app.dependency_overrides[get_settings] = lambda: retrieval_settings()
    orders: list[list[str]] = []
    for run in range(3):
        users = seeded_tenant(app, db, prefix=f"tie-{run}")
        try:
            bot = make_bot(users, f"Tie {run}")
            body = "Refunds are processed within fourteen business days after the parcel returns."
            # Upload order is the reverse of title order on purpose.
            upload = upload_sources(
                users,
                bot["id"],
                [("zz.md", doc("Zulu", body)), ("aa.md", doc("Alpha", body))],
                TMP,
            )
            assert upload.status_code == 201, upload.text
            assert start_ingestion(users, bot["id"]).status_code == 202
            drain_jobs(_engine(db), TMP)
            publish_draft(users, bot["id"])
            db.expire_all()
            result = retrieve(
                db,
                tenant_id=users.tenant_id,
                bot_id=UUID(str(bot["id"])),
                revision_id=UUID(published_revision_id(db, users.tenant_id, str(bot["id"]))),
                question="refunds processed business days",
                question_language="en",
                settings=retrieval_settings(),
            )
            orders.append([chunk.title for chunk in result.candidates])
        finally:
            users.cleanup()
    assert orders[0] == ["Alpha", "Zulu"], orders
    assert orders[0] == orders[1] == orders[2]
