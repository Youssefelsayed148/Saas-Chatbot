"""H2: knowledge hygiene — upload dedupe, replace, delete, cross-source duplicate chunks and
the stable always-include setting. Every new endpoint has tenant A/B, role and CSRF checks."""

from pathlib import Path
from typing import Any
from uuid import UUID

import pytest
from fastapi import FastAPI
from sqlalchemy import func, select
from sqlalchemy.orm import Session as OrmSession

from app.core.config import get_settings
from app.db.models import AuditEvent, Bot, Chunk, Document, Source
from app.knowledge.service import always_include_document_ids
from tests.helpers import make_bot, seeded_tenant
from tests.knowledge_helpers import (
    MD_AR,
    MD_EN,
    drain_jobs,
    publish_draft,
    start_ingestion,
    upload_settings,
    upload_sources,
)


@pytest.fixture
def rooted_app(app: FastAPI, tmp_path: Path) -> FastAPI:
    app.dependency_overrides[get_settings] = lambda: upload_settings(tmp_path)
    return app


def _engine() -> Any:
    from app.db.session import get_engine

    return get_engine()


def _base(users: Any, bot_id: str) -> str:
    return f"/api/v1/tenants/{users.tenant_id}/bots/{bot_id}"


def _setup(rooted_app: FastAPI, db: OrmSession, name: str) -> tuple[Any, str]:
    users = seeded_tenant(rooted_app, db, prefix=name)
    return users, str(make_bot(users, name)["id"])


def _ingest(users: Any, bot_id: str, tmp_path: Path) -> None:
    assert start_ingestion(users, bot_id).status_code == 202
    drain_jobs(_engine(), tmp_path)


def _upload_one(users: Any, bot_id: str, name: str, data: bytes, tmp_path: Path) -> dict[str, Any]:
    response = upload_sources(users, bot_id, [(name, data)], tmp_path)
    assert response.status_code in (200, 201), response.text
    return dict(response.json()[0])


def _documents(users: Any, bot_id: str, revision: str) -> list[dict[str, Any]]:
    response = users.call("staff", "GET", f"{_base(users, bot_id)}/documents?revision={revision}")
    assert response.status_code == 200, response.text
    return list(response.json())


def _replace(users: Any, bot_id: str, source_id: str, name: str, data: bytes, **kw: Any) -> Any:
    role = kw.pop("role", "staff")
    return users.call(
        role,
        "POST",
        f"{_base(users, bot_id)}/sources/{source_id}/replace",
        files={"file": (name, data, "application/octet-stream")},
    )


def _source_count(db: OrmSession, bot_id: str, *, live_only: bool = True) -> int:
    db.expire_all()
    statement = select(func.count()).select_from(Source).where(Source.bot_id == UUID(bot_id))
    if live_only:
        statement = statement.where(Source.status != "removed")
    return int(db.scalar(statement) or 0)


# --- 1. upload dedupe -----------------------------------------------------------


def test_duplicate_upload_returns_existing_source(
    rooted_app: FastAPI, db: OrmSession, tmp_path: Path
) -> None:
    users, bot_id = _setup(rooted_app, db, "h2-dup")
    first = upload_sources(users, bot_id, [("a.md", MD_EN.read_bytes())], tmp_path)
    assert first.status_code == 201 and first.json()[0]["duplicate"] is False
    _ingest(users, bot_id, tmp_path)
    second = upload_sources(users, bot_id, [("renamed.md", MD_EN.read_bytes())], tmp_path)
    assert second.status_code == 200  # nothing new was stored
    row = second.json()[0]
    assert row["duplicate"] is True and row["id"] == first.json()[0]["id"]
    assert "already uploaded" in row["message"]
    assert _source_count(db, bot_id) == 1
    # No new source means nothing new to ingest.
    assert start_ingestion(users, bot_id).status_code == 409


def test_duplicate_inside_one_batch_and_mixed_batch(
    rooted_app: FastAPI, db: OrmSession, tmp_path: Path
) -> None:
    users, bot_id = _setup(rooted_app, db, "h2-batch")
    response = upload_sources(
        users,
        bot_id,
        [("a.md", MD_EN.read_bytes()), ("b.md", MD_EN.read_bytes()), ("c.md", MD_AR.read_bytes())],
        tmp_path,
    )
    assert response.status_code == 201
    rows = response.json()
    assert [row["duplicate"] for row in rows] == [False, True, False]
    assert rows[0]["id"] == rows[1]["id"]
    assert _source_count(db, bot_id) == 2


def test_same_file_on_other_bot_or_tenant_is_independent(
    rooted_app: FastAPI, db: OrmSession, tmp_path: Path
) -> None:
    users_a, bot_a = _setup(rooted_app, db, "h2-ind-a")
    users_b, bot_b = _setup(rooted_app, db, "h2-ind-b")
    bot_a2 = str(make_bot(users_a, "second")["id"])
    data = MD_EN.read_bytes()
    ids = {
        _upload_one(users_a, bot_a, "x.md", data, tmp_path)["id"],
        _upload_one(users_a, bot_a2, "x.md", data, tmp_path)["id"],
        _upload_one(users_b, bot_b, "x.md", data, tmp_path)["id"],
    }
    assert len(ids) == 3


# --- 2. replace -----------------------------------------------------------------


def test_replace_keeps_identity_and_swaps_content_on_publish(
    rooted_app: FastAPI, db: OrmSession, tmp_path: Path
) -> None:
    users, bot_id = _setup(rooted_app, db, "h2-rep")
    source = _upload_one(users, bot_id, "kb.md", MD_EN.read_bytes(), tmp_path)
    _ingest(users, bot_id, tmp_path)
    publish_draft(users, bot_id)
    old_titles = {doc["title"] for doc in _documents(users, bot_id, "published")}

    # Identical bytes: nothing changes.
    same = _replace(users, bot_id, source["id"], "kb.md", MD_EN.read_bytes())
    assert same.status_code == 200 and same.json()["duplicate"] is True

    replaced = _replace(users, bot_id, source["id"], "kb.md", MD_AR.read_bytes())
    assert replaced.status_code == 200, replaced.text
    body = replaced.json()
    assert body["id"] == source["id"] and body["status"] == "stored"
    assert body["sha256"] != source["sha256"] and body["duplicate"] is False
    assert _source_count(db, bot_id) == 1

    _ingest(users, bot_id, tmp_path)
    # Published knowledge is untouched until publish.
    assert {doc["title"] for doc in _documents(users, bot_id, "published")} == old_titles
    draft_docs = _documents(users, bot_id, "draft")
    assert draft_docs and {doc["source_id"] for doc in draft_docs} == {source["id"]}
    assert {doc["title"] for doc in draft_docs}.isdisjoint(old_titles)

    publish_draft(users, bot_id)
    live = _documents(users, bot_id, "published")
    assert {doc["title"] for doc in live}.isdisjoint(old_titles)
    assert {doc["source_id"] for doc in live} == {source["id"]}


def test_replace_with_content_of_another_source_links_that_source(
    rooted_app: FastAPI, db: OrmSession, tmp_path: Path
) -> None:
    users, bot_id = _setup(rooted_app, db, "h2-rep-dup")
    first = _upload_one(users, bot_id, "a.md", MD_EN.read_bytes(), tmp_path)
    second = _upload_one(users, bot_id, "b.md", MD_AR.read_bytes(), tmp_path)
    response = _replace(users, bot_id, second["id"], "b.md", MD_EN.read_bytes())
    assert response.status_code == 200
    assert response.json()["duplicate"] is True and response.json()["id"] == first["id"]


# --- 3. delete ------------------------------------------------------------------


def test_delete_removes_from_draft_then_publish_and_rollback_restores(
    rooted_app: FastAPI, db: OrmSession, tmp_path: Path
) -> None:
    users, bot_id = _setup(rooted_app, db, "h2-del")
    keep = _upload_one(users, bot_id, "keep.md", MD_AR.read_bytes(), tmp_path)
    gone = _upload_one(users, bot_id, "gone.md", MD_EN.read_bytes(), tmp_path)
    _ingest(users, bot_id, tmp_path)
    first_revision = publish_draft(users, bot_id)
    storage_file = tmp_path / str(
        db.scalar(select(Source.storage_key).where(Source.id == UUID(gone["id"])))
    )
    assert storage_file.exists()

    response = users.call("staff", "DELETE", f"{_base(users, bot_id)}/sources/{gone['id']}")
    assert response.status_code == 204, response.text
    assert not storage_file.exists()  # stored file cleaned up via the storage interface

    listed = users.call("staff", "GET", f"{_base(users, bot_id)}/sources").json()
    assert [row["id"] for row in listed] == [keep["id"]]
    assert (
        users.call("staff", "GET", f"{_base(users, bot_id)}/sources/{gone['id']}").status_code
        == 404
    )
    # Deleting again is a hidden resource.
    assert (
        users.call("staff", "DELETE", f"{_base(users, bot_id)}/sources/{gone['id']}").status_code
        == 404
    )

    # Published knowledge is unchanged until publish; the draft no longer has it.
    assert gone["id"] in {d["source_id"] for d in _documents(users, bot_id, "published")}
    assert gone["id"] not in {d["source_id"] for d in _documents(users, bot_id, "draft")}

    publish_draft(users, bot_id)
    live = {d["source_id"] for d in _documents(users, bot_id, "published")}
    assert live == {keep["id"]}
    db.expire_all()
    bot = db.get(Bot, UUID(bot_id))
    assert bot is not None and bot.published_revision_id is not None
    leaked = db.scalar(
        select(func.count())
        .select_from(Chunk)
        .where(Chunk.revision_id == bot.published_revision_id, Chunk.source_id == UUID(gone["id"]))
    )
    assert leaked == 0

    # Rollback restores the content the archived revision still holds.
    rolled = users.call(
        "staff", "POST", f"{_base(users, bot_id)}/revisions/{first_revision}/publish"
    )
    assert rolled.status_code == 200
    assert gone["id"] in {d["source_id"] for d in _documents(users, bot_id, "published")}

    audited = db.scalar(
        select(func.count())
        .select_from(AuditEvent)
        .where(AuditEvent.action == "knowledge.source_removed")
    )
    assert audited == 1


def test_removed_source_is_not_resurrected_by_retry_or_a_new_draft(
    rooted_app: FastAPI, db: OrmSession, tmp_path: Path
) -> None:
    users, bot_id = _setup(rooted_app, db, "h2-del2")
    keep = _upload_one(users, bot_id, "keep.md", MD_AR.read_bytes(), tmp_path)
    gone = _upload_one(users, bot_id, "gone.md", MD_EN.read_bytes(), tmp_path)
    _ingest(users, bot_id, tmp_path)
    publish_draft(users, bot_id)
    assert (
        users.call("staff", "DELETE", f"{_base(users, bot_id)}/sources/{gone['id']}").status_code
        == 204
    )
    publish_draft(users, bot_id)
    # A brand-new draft is copied from the published snapshot: still without the source.
    third = _upload_one(users, bot_id, "third.md", MD_EN.read_bytes() + b"\nMore.\n", tmp_path)
    _ingest(users, bot_id, tmp_path)
    sources = {d["source_id"] for d in _documents(users, bot_id, "draft")}
    assert gone["id"] not in sources and {keep["id"], third["id"]} <= sources
    # Explicitly ingesting the removed id is a 404.
    assert start_ingestion(users, bot_id, [gone["id"]]).status_code == 404


def test_delete_frees_storage_quota_and_clears_always_include(
    rooted_app: FastAPI, db: OrmSession, tmp_path: Path
) -> None:
    users, bot_id = _setup(rooted_app, db, "h2-del3")
    source = _upload_one(users, bot_id, "gone.md", MD_EN.read_bytes(), tmp_path)
    base = _base(users, bot_id)
    assert (
        users.call(
            "staff", "PUT", f"{base}/sources/{source['id']}/always-include", json={"enabled": True}
        ).status_code
        == 200
    )
    assert users.call("staff", "DELETE", f"{base}/sources/{source['id']}").status_code == 204
    db.expire_all()
    row = db.get(Source, UUID(source["id"]))
    bot = db.get(Bot, UUID(bot_id))
    assert row is not None and row.status == "removed" and row.size_bytes == 0
    assert bot is not None and "always_include_source_ids" not in bot.config


# --- 4. cross-source duplicate chunks -------------------------------------------


def test_cross_source_duplicate_chunks_keep_the_newer_source(
    rooted_app: FastAPI, db: OrmSession, tmp_path: Path
) -> None:
    users, bot_id = _setup(rooted_app, db, "h2-xdup")
    older = _upload_one(users, bot_id, "old.md", MD_EN.read_bytes(), tmp_path)
    _ingest(users, bot_id, tmp_path)
    # Same text, different bytes (trailing whitespace) → a different source, same chunk hashes.
    newer = _upload_one(users, bot_id, "new.md", MD_EN.read_bytes() + b"\n\n", tmp_path)
    assert newer["id"] != older["id"] and newer["duplicate"] is False
    _ingest(users, bot_id, tmp_path)
    docs = _documents(users, bot_id, "draft")
    assert {doc["source_id"] for doc in docs} == {newer["id"]}
    assert any("identical chunk" in " ".join(doc["warnings"]) for doc in docs)
    db.expire_all()
    hashes = list(db.scalars(select(Chunk.content_hash)))
    assert len(hashes) == len(set(hashes))

    # Re-ingesting the OLDER source must not flip-flop: the newer one keeps the chunks.
    assert start_ingestion(users, bot_id, [older["id"]]).status_code in (202, 404, 409)
    drain_jobs(_engine(), tmp_path)
    assert {doc["source_id"] for doc in _documents(users, bot_id, "draft")} == {newer["id"]}


# --- 5. always-include ----------------------------------------------------------


def test_always_include_survives_reingest_draft_copy_and_replace(
    rooted_app: FastAPI, db: OrmSession, tmp_path: Path
) -> None:
    users, bot_id = _setup(rooted_app, db, "h2-ai")
    base = _base(users, bot_id)
    source = _upload_one(users, bot_id, "contact.md", MD_EN.read_bytes(), tmp_path)
    other = _upload_one(users, bot_id, "faq.md", MD_AR.read_bytes(), tmp_path)
    _ingest(users, bot_id, tmp_path)
    publish_draft(users, bot_id)

    on = users.call(
        "staff", "PUT", f"{base}/sources/{source['id']}/always-include", json={"enabled": True}
    )
    assert on.status_code == 200 and on.json()["always_include"] is True
    listed = {row["id"]: row for row in users.call("staff", "GET", f"{base}/sources").json()}
    assert listed[source["id"]]["always_include"] is True
    assert listed[other["id"]]["always_include"] is False

    def reserved() -> set[str]:
        db.expire_all()
        bot = db.get(Bot, UUID(bot_id))
        assert bot is not None and bot.published_revision_id is not None
        return always_include_document_ids(
            db, bot, bot.published_revision_id, upload_settings(tmp_path)
        )

    before = reserved()
    assert before
    live_docs = {
        d["id"] for d in _documents(users, bot_id, "published") if d["source_id"] == source["id"]
    }
    assert before <= live_docs

    # Replace + re-ingest + publish: document ids change, the reservation follows the source.
    assert (
        _replace(
            users, bot_id, source["id"], "contact.md", MD_EN.read_bytes() + b"\nNew line.\n"
        ).status_code
        == 200
    )
    _ingest(users, bot_id, tmp_path)
    publish_draft(users, bot_id)
    after = reserved()
    assert after and after.isdisjoint(before)

    off = users.call(
        "staff", "PUT", f"{base}/sources/{source['id']}/always-include", json={"enabled": False}
    )
    assert off.status_code == 200 and off.json()["always_include"] is False
    assert reserved() == set()


def test_bot_settings_validate_always_include_ids(
    rooted_app: FastAPI, db: OrmSession, tmp_path: Path
) -> None:
    users, bot_id = _setup(rooted_app, db, "h2-cfg")
    users_b, bot_b = _setup(rooted_app, db, "h2-cfg-b")
    mine = _upload_one(users, bot_id, "a.md", MD_EN.read_bytes(), tmp_path)
    foreign = _upload_one(users_b, bot_b, "a.md", MD_EN.read_bytes(), tmp_path)
    base = _base(users, bot_id)

    ok = users.call(
        "staff", "PATCH", base, json={"config": {"always_include_source_ids": [mine["id"]]}}
    )
    assert ok.status_code == 200, ok.text
    assert ok.json()["config"]["always_include_source_ids"] == [mine["id"]]
    # Another tenant's source id is indistinguishable from an unknown one.
    bad = users.call(
        "staff", "PATCH", base, json={"config": {"always_include_source_ids": [foreign["id"]]}}
    )
    assert bad.status_code == 422
    too_many = users.call(
        "staff",
        "PATCH",
        base,
        json={"config": {"always_include_source_ids": [mine["id"]] + [foreign["id"]] * 3}},
    )
    assert too_many.status_code == 422
    not_uuid = users.call(
        "staff", "PATCH", base, json={"config": {"always_include_source_ids": ["nope"]}}
    )
    assert not_uuid.status_code == 422
    cleared = users.call("staff", "PATCH", base, json={"config": {"always_include_source_ids": []}})
    assert (
        cleared.status_code == 200 and "always_include_source_ids" not in cleared.json()["config"]
    )


# --- tenant A/B, roles, CSRF on every new endpoint ------------------------------


def test_new_endpoints_are_tenant_scoped_and_staff_only(
    rooted_app: FastAPI, db: OrmSession, tmp_path: Path
) -> None:
    users_a, bot_a = _setup(rooted_app, db, "h2-iso-a")
    users_b, bot_b = _setup(rooted_app, db, "h2-iso-b")
    source = _upload_one(users_a, bot_a, "a.md", MD_EN.read_bytes(), tmp_path)
    sid = source["id"]
    data = MD_AR.read_bytes()

    # Tenant B's bot with tenant A's source id: always 404, nothing changes.
    base_b = _base(users_b, bot_b)
    assert users_b.call("staff", "DELETE", f"{base_b}/sources/{sid}").status_code == 404
    assert _replace(users_b, bot_b, sid, "x.md", data).status_code == 404
    assert (
        users_b.call(
            "staff", "PUT", f"{base_b}/sources/{sid}/always-include", json={"enabled": True}
        ).status_code
        == 404
    )
    # Tenant B's client admin on tenant A's path is not a member: hidden (404).
    # (Platform staff may act on any tenant by design, so "staff" is not used here.)
    base_a_via_b = f"/api/v1/tenants/{users_a.tenant_id}/bots/{bot_a}"
    assert users_b.call("admin", "DELETE", f"{base_a_via_b}/sources/{sid}").status_code in (
        403,
        404,
    )

    # Non-staff roles are refused.
    base = _base(users_a, bot_a)
    for role in ("admin", "editor", "viewer"):
        assert users_a.call(role, "DELETE", f"{base}/sources/{sid}").status_code == 403
        assert _replace(users_a, bot_a, sid, "x.md", data, role=role).status_code == 403
        assert (
            users_a.call(
                role, "PUT", f"{base}/sources/{sid}/always-include", json={"enabled": True}
            ).status_code
            == 403
        )

    # CSRF is required.
    client = users_a.as_user("staff")
    assert client.delete(f"{base}/sources/{sid}").status_code == 403
    assert (
        client.put(f"{base}/sources/{sid}/always-include", json={"enabled": True}).status_code
        == 403
    )
    assert (
        client.post(f"{base}/sources/{sid}/replace", files={"file": ("x.md", data)}).status_code
        == 403
    )

    db.expire_all()
    still = db.get(Source, UUID(sid))
    assert still is not None and still.status == "stored" and still.sha256 == source["sha256"]
    assert (
        db.scalar(select(func.count()).select_from(Document).where(Document.source_id == UUID(sid)))
        == 0
    )
