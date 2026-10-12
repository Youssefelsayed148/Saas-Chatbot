"""Shared retrieval corpus fixture (used by test_retrieval and test_chat).

Seeds, through the real pipeline, a tenant A with a published "main" bot
(hours/returns/FAQ-ar), a decoy bot in the same tenant, an identical copy in
tenant B, plus an unpublished "changed" draft on the main bot — so every
retrieval filter has a decoy that fails the assertions if removed.
"""

from pathlib import Path
from typing import Any
from uuid import UUID

import pytest
from fastapi import FastAPI
from sqlalchemy import text
from sqlalchemy.orm import Session as OrmSession

from app.core.config import Settings, get_settings
from tests.knowledge_helpers import (
    drain_jobs,
    publish_draft,
    start_ingestion,
    upload_settings,
    upload_sources,
)

TMP = Path("/tmp/ret-tests")  # upload storage; refreshed between test runs

MD_HOURS = (
    "---\ntitle: Opening hours\nsource_url: https://hours.example.com/hours\n"
    "language: en\npage_type: faq\n---\n\n"
    "# Opening hours\n\n"
    "We are open Monday to Friday from 9:00 to 17:00 and on Saturdays until"
    " 14:00. The support team works the same schedule as the showroom.\n"
)

MD_RETURNS = (
    "---\ntitle: Return policy\nsource_url: https://returns.example.com/returns\n"
    "language: en\npage_type: policy\n---\n\n"
    "# Return policy\n\n"
    "Products can be returned within 14 days of delivery with the original"
    " invoice. Personalised items cannot be returned unless faulty.\n"
)

MD_CONTACT = (
    "---\ntitle: Contact page\nsource_url: https://contact.example.com/contact\n"
    "language: en\npage_type: contact\n---\n\n"
    "# Contact\n\n"
    "During office hours you can reach our team at the front desk or by the"
    " website form; we answer within one business day.\n"
)

MD_AR = (
    "---\ntitle: الأسئلة الشائعة\nsource_url: https://ar.example.com/faq\n"
    "language: ar\npage_type: faq\n---\n\n"
    "# الأسئلة الشائعة\n\n"
    "## ساعات العمل\n\n"
    "نحن نعمل من الأحد إلى الخميس من الساعة ٩ صباحاً حتى ٥ مساءً.\n"
)

MD_AR_PLURAL = (
    "---\ntitle: أوقات الإقبال\nsource_url: https://ar.example.com/plural\n"
    "language: ar\npage_type: faq\n---\n\n"
    "# الأوقات\n\n"
    "متى تفتحون المكتب؟ زوارنا يأتون خلال الساعات من التاسعة صباحاً حتى الخامسة مساءً.\n"
)


def retrieval_settings(**overrides: Any) -> Settings:
    """Test settings: session defaults + temp storage + §5 retrieval defaults."""
    values = dict(upload_settings(TMP).__dict__)
    values.update(
        retrieval_top_k=8,
        retrieval_final_k=4,
        retrieval_max_evidence_chunks=8,
        chunk_size=1500,
        chunk_overlap=200,
    )
    values.update(overrides)
    return Settings.model_construct(**values)


def _engine(db: OrmSession) -> Any:
    from app.db.session import get_engine

    return get_engine()


def published_revision_id(db: OrmSession, tenant_id: UUID, bot_id: str) -> str:
    row = db.execute(
        text(
            "SELECT id FROM knowledge_revisions "
            "WHERE tenant_id = CAST(:t AS uuid) AND bot_id = CAST(:b AS uuid) "
            "AND status = 'published'"
        ),
        {"t": str(tenant_id), "b": bot_id},
    ).scalar()
    assert row is not None
    return str(row)


def titles(evidence: list[Any]) -> set[str]:
    return {chunk.title for chunk in evidence}


def languages(evidence: list[Any]) -> set[str]:
    return {chunk.language for chunk in evidence}


def build_corpus(app: FastAPI, db: OrmSession) -> dict[str, Any]:
    """Seed the full decoy corpus; returns the ids the tests work with."""
    from tests.helpers import make_bot, seeded_tenant

    app.dependency_overrides[get_settings] = lambda: retrieval_settings()
    users_a = seeded_tenant(app, db, prefix="ret-a")
    users_b = seeded_tenant(app, db, prefix="ret-b")
    bot_main = make_bot(users_a, "Main")
    bot_decoy = make_bot(users_a, "Decoy")
    bot_b = make_bot(users_b, "BCopy")

    main_files = {
        "hours.md": MD_HOURS,
        "returns.md": MD_RETURNS,
        "faq-ar.md": MD_AR,
    }
    decoy_files = {"hours.md": MD_HOURS, "contact.md": MD_CONTACT}
    for users, bot_id, files in [
        (users_a, bot_main["id"], main_files),
        (users_a, bot_decoy["id"], decoy_files),
        (users_b, bot_b["id"], main_files),
    ]:
        upload = upload_sources(
            users,
            bot_id,
            [(name, data.encode()) for name, data in files.items()],
            TMP,
        )
        assert upload.status_code == 201, upload.text
        start = start_ingestion(users, bot_id)
        assert start.status_code == 202, start.text
        drain_jobs(_engine(db), TMP)
        publish_draft(users, bot_id)
    db.expire_all()

    # A second, unpublished draft for bot_main: re-ingesting a changed copy of
    # hours must NOT become visible to retrieval (revision filter decoy).
    changed_front = (
        "---\ntitle: Opening hours changed\n"
        "source_url: https://changed.example.com\nlanguage: en\n---\n\n"
    )
    changed = (
        changed_front
        + "# Opening hours\n\nTomato opening hours are 07:00 to 24:00 every day, with hours"
        + " and returns mentioned repeatedly.\n"
    )
    upload2 = upload_sources(users_a, bot_main["id"], [("changed.md", changed.encode())], TMP)
    assert upload2.status_code == 201
    start2 = start_ingestion(users_a, bot_main["id"])
    assert start2.status_code == 202
    drain_jobs(_engine(db), TMP)
    db.expire_all()

    return {
        "users_a": users_a,
        "users_b": users_b,
        "bot_main": str(bot_main["id"]),
        "bot_decoy": str(bot_decoy["id"]),
        "bot_b": str(bot_b["id"]),
        "settings": retrieval_settings(),
        "tmp": TMP,
    }


@pytest.fixture
def corpus(app: FastAPI, db: OrmSession) -> dict[str, Any]:
    return build_corpus(app, db)
