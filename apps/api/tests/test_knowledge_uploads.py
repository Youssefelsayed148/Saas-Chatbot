"""P2-02: upload endpoint hardening (docs/06) — limits, magic-byte sniffing,
CSRF, roles, tenant A/B isolation; Q&A CSV report and template endpoints."""

from collections.abc import Iterator
from typing import Any
from uuid import uuid4

import pytest
from fastapi import FastAPI
from sqlalchemy import text
from sqlalchemy.orm import Session as OrmSession

from app.core.config import get_settings
from tests.fixtures_factory import (
    make_binary_junk,
    make_corrupt_pdf,
    make_docx,
    make_pdf_pages,
)
from tests.helpers import make_bot, seeded_tenant
from tests.knowledge_helpers import MD_AR, MD_EN, upload_settings, upload_sources


@pytest.fixture
def storage_rooted_app(app: FastAPI, tmp_path: Any) -> FastAPI:
    """Uploads during these tests store under a disposable temp directory."""
    app.dependency_overrides[get_settings] = lambda: upload_settings(tmp_path)
    return app


@pytest.fixture
def raw_db(app: FastAPI) -> Iterator[OrmSession]:
    """A raw session bound to the test engine (cleaned via clean_tables)."""
    from app.db.session import get_engine, session_factory

    session: OrmSession = session_factory(get_engine())()
    try:
        yield session
    finally:
        # The session must CLOSE here: an open transaction (even a read)
        # blocks the clean_tables TRUNCATE of the next test forever.
        session.rollback()
        session.close()


def bot_of_users_response(users: Any) -> str:
    response = users.call(
        "owner", "POST", f"/api/v1/tenants/{users.tenant_id}/bots", json={"name": "K"}
    )
    assert response.status_code == 201
    return str(response.json()["id"])


def sources_of(users: Any, bot_id: str) -> list[dict[str, Any]]:
    listing = users.call("owner", "GET", f"/api/v1/tenants/{users.tenant_id}/bots/{bot_id}/sources")
    assert listing.status_code == 200
    return list(listing.json())


# --- basic upload ------------------------------------------------------------


def test_upload_md_and_docx_stores_sources_with_generated_keys(
    storage_rooted_app: FastAPI, raw_db: OrmSession, tmp_path: Any
) -> None:
    try:
        users = seeded_tenant(storage_rooted_app, raw_db, prefix="up-ok")
        bot_id = bot_of_users_response(users)
        response = upload_sources(
            users,
            bot_id,
            [("pricing.md", MD_EN.read_bytes()), ("arabic.md", MD_AR.read_bytes())],
            tmp_path,
        )
        assert response.status_code == 201, response.text
        rows = response.json()
        assert [row["kind"] for row in rows] == ["md", "md"]
        assert rows[0]["status"] == "stored"
        assert rows[0]["original_name"] == "pricing.md"
        # Display name is kept; the storage key is a generated path and the
        # user-supplied filename never appears in it.
        keys = [row["storage_key"] for row in rows] if "storage_key" in rows[0] else None
        del keys
        stored = raw_db.execute(
            text("SELECT storage_key, sha256 FROM sources WHERE tenant_id = CAST(:t AS uuid)"),
            {"t": str(users.tenant_id)},
        ).fetchall()
        assert len(stored) == 2
        for key, _sha in stored:
            assert "pricing.md" not in key and "arabic.md" not in key
            assert key.startswith(f"{users.tenant_id}/{bot_id}/")
            assert not (tmp_path / key).parent.name == "pricing.md"
            assert (tmp_path / key).exists()
    finally:
        pass


def test_upload_sets_sha256_and_size(
    storage_rooted_app: FastAPI, raw_db: OrmSession, tmp_path: Any
) -> None:
    import hashlib

    try:
        users = seeded_tenant(storage_rooted_app, raw_db, prefix="up-hash")
        bot_id = bot_of_users_response(users)
        response = upload_sources(users, bot_id, [("only.md", MD_EN.read_bytes())], tmp_path)
        assert response.status_code == 201, response.text
        source = response.json()[0]
        assert source["size_bytes"] == MD_EN.stat().st_size
        assert source["sha256"] == hashlib.sha256(MD_EN.read_bytes()).hexdigest()
    finally:
        pass


def test_upload_accepts_chunked_multipart_without_content_length(
    storage_rooted_app: FastAPI, raw_db: OrmSession, tmp_path: Any
) -> None:
    users = seeded_tenant(storage_rooted_app, raw_db, prefix="up-chunked")
    bot_id = bot_of_users_response(users)
    boundary = "p7-chunked-upload-boundary"
    content = MD_EN.read_bytes()

    def multipart_chunks() -> Iterator[bytes]:
        yield f"--{boundary}\r\n".encode()
        yield b'Content-Disposition: form-data; name="files"; filename="chunked.md"\r\n'
        yield b"Content-Type: text/markdown; charset=utf-8\r\n\r\n"
        for offset in range(0, len(content), 13):
            yield content[offset : offset + 13]
        yield f"\r\n--{boundary}--\r\n".encode()

    try:
        response = users.call(
            "owner",
            "POST",
            f"/api/v1/tenants/{users.tenant_id}/bots/{bot_id}/sources/files",
            content=multipart_chunks(),
            headers={"Content-Type": f"multipart/form-data; boundary={boundary}"},
        )
        assert response.status_code == 201, response.text
        assert response.json()[0]["original_name"] == "chunked.md"
    finally:
        users.cleanup()


# --- hardening ---------------------------------------------------------------


def test_oversize_file_rejected_with_413(
    storage_rooted_app: FastAPI, raw_db: OrmSession, tmp_path: Any
) -> None:
    try:
        users = seeded_tenant(storage_rooted_app, raw_db, prefix="up-big")
        bot_id = bot_of_users_response(users)
        blob = b"a" * (10 * 1024 * 1024 + 1)
        response = upload_sources(users, bot_id, [("big.md", blob)], tmp_path)
        assert response.status_code == 413
        assert response.json()["error"]["code"] == "FILE_TOO_LARGE"
        assert sources_of(users, bot_id) == []
    finally:
        pass


def test_too_many_files_rejected(
    storage_rooted_app: FastAPI, raw_db: OrmSession, tmp_path: Any
) -> None:
    try:
        users = seeded_tenant(storage_rooted_app, raw_db, prefix="up-many")
        bot_id = bot_of_users_response(users)
        tiny = b"title: t\n\nbody text\n"
        files = [(f"file-{index}.md", tiny) for index in range(21)]
        response = upload_sources(users, bot_id, files, tmp_path)
        assert response.status_code == 422
        assert "At most 20 files" in response.json()["error"]["message"]
    finally:
        pass


def test_empty_file_rejected(
    storage_rooted_app: FastAPI, raw_db: OrmSession, tmp_path: Any
) -> None:
    try:
        users = seeded_tenant(storage_rooted_app, raw_db, prefix="up-empty")
        bot_id = bot_of_users_response(users)
        response = upload_sources(users, bot_id, [("empty.md", b"")], tmp_path)
        assert response.status_code == 422
    finally:
        pass


def test_mislabelled_pdf_as_md_rejected(
    storage_rooted_app: FastAPI, raw_db: OrmSession, tmp_path: Any
) -> None:
    try:
        users = seeded_tenant(storage_rooted_app, raw_db, prefix="up-misp1")
        bot_id = bot_of_users_response(users)
        response = upload_sources(users, bot_id, [("looks-md.md", make_corrupt_pdf())], tmp_path)
        assert response.status_code == 415
        assert "content is a PDF" in response.json()["error"]["message"]
    finally:
        pass


def test_mislabelled_docx_rejected(
    storage_rooted_app: FastAPI, raw_db: OrmSession, tmp_path: Any
) -> None:
    try:
        users = seeded_tenant(storage_rooted_app, raw_db, prefix="up-misp2")
        bot_id = bot_of_users_response(users)
        response = upload_sources(
            users, bot_id, [("fake.pdf", make_docx([("t", ["b"])]))], tmp_path
        )
        assert response.status_code == 415
        assert "zip archive" in response.json()["error"]["message"]
    finally:
        pass


def test_binary_junk_rejected(
    storage_rooted_app: FastAPI, raw_db: OrmSession, tmp_path: Any
) -> None:
    try:
        users = seeded_tenant(storage_rooted_app, raw_db, prefix="up-bin")
        bot_id = bot_of_users_response(users)
        response = upload_sources(users, bot_id, [("data.csv", make_binary_junk())], tmp_path)
        assert response.status_code == 415
        assert "Unsupported file type" in response.json()["error"]["message"]
    finally:
        pass


def test_valid_pdf_and_docx_accepted(
    storage_rooted_app: FastAPI, raw_db: OrmSession, tmp_path: Any
) -> None:
    try:
        users = seeded_tenant(storage_rooted_app, raw_db, prefix="up-pdf")
        bot_id = bot_of_users_response(users)
        response = upload_sources(
            users,
            bot_id,
            [
                ("real.pdf", make_pdf_pages([["Hello page one."]])),
                ("real.docx", make_docx([("H", ["body"])])),
            ],
            tmp_path,
        )
        assert response.status_code == 201, response.text
        assert [row["kind"] for row in response.json()] == ["pdf", "docx"]
    finally:
        pass


# --- Q&A CSV -----------------------------------------------------------------


def test_qa_csv_partial_is_valid_with_row_report(
    storage_rooted_app: FastAPI, raw_db: OrmSession, tmp_path: Any
) -> None:
    try:
        users = seeded_tenant(storage_rooted_app, raw_db, prefix="up-csv1")
        bot_id = bot_of_users_response(users)
        data = (
            b"Question,Answer,Topic,Priority\n"
            b"What is the return window?,14 days with the invoice.,returns,7\n"
            b"Answermissing,,,\n"
            b"Bad priority,x,,42\n"
            b"Where are you?,On the main street.,company,2\n"
        )
        response = upload_sources(users, bot_id, [("mixed.csv", data)], tmp_path)
        assert response.status_code == 201, response.text
        source = response.json()[0]
        assert source["kind"] == "qa_csv"
        assert source["valid_rows"] == 2
        assert source["total_rows"] == 4
        assert source["status"] == "stored"
        assert len(source["row_errors"]) == 2
        reasons = {error["reason"] for error in source["row_errors"]}
        assert any("missing answer" in reason for reason in reasons)
        assert any("priority" in reason for reason in reasons)
    finally:
        pass


def test_qa_csv_all_invalid_rejected_with_reasons(
    storage_rooted_app: FastAPI, raw_db: OrmSession, tmp_path: Any
) -> None:
    try:
        users = seeded_tenant(storage_rooted_app, raw_db, prefix="up-csv2")
        bot_id = bot_of_users_response(users)
        data = b"Question,Answer,Topic,Priority\nNoAnswer,,,\n,AlsoNone,,\n"
        response = upload_sources(users, bot_id, [("bad.csv", data)], tmp_path)
        assert response.status_code == 422
        message = response.json()["error"]["message"]
        assert "Row" in message and "missing" in message
        assert sources_of(users, bot_id) == []
    finally:
        pass


def test_qa_template_download(
    storage_rooted_app: FastAPI, raw_db: OrmSession, tmp_path: Any
) -> None:
    try:
        users = seeded_tenant(storage_rooted_app, raw_db, prefix="up-tpl")
        bot_id = bot_of_users_response(users)
        response = users.as_user("owner").get(
            f"/api/v1/tenants/{users.tenant_id}/bots/{bot_id}/sources/qa-template"
        )
        assert response.status_code == 200
        assert response.headers["content-type"].startswith("text/csv")
        assert "Disposition" in response.headers or "attachment" in response.headers.get(
            "content-disposition", "attachment"
        )
        body = response.content.decode("utf-8")
        assert body.startswith("question,answer,topic,priority\n")

        # Viewer denied (docs/05: editor+).
        denied = users.as_user("viewer").get(
            f"/api/v1/tenants/{users.tenant_id}/bots/{bot_id}/sources/qa-template"
        )
        assert denied.status_code == 403
    finally:
        pass


# --- CSRF / isolation ---------------------------------------------------------


def test_upload_requires_csrf(
    storage_rooted_app: FastAPI, raw_db: OrmSession, tmp_path: Any
) -> None:
    try:
        users = seeded_tenant(storage_rooted_app, raw_db, prefix="up-csrf")
        bot_id = bot_of_users_response(users)
        response = users.as_user("owner").post(
            f"/api/v1/tenants/{users.tenant_id}/bots/{bot_id}/sources/files",
            files=[("files", ("x.md", MD_EN.read_bytes(), "text/markdown"))],
        )
        assert response.status_code == 403
        assert response.json()["error"]["code"] == "CSRF_MISSING"
    finally:
        pass


def test_tenant_b_cannot_reach_tenant_a_bot_sources_or_upload(
    app: FastAPI, db: OrmSession, tmp_path: Any
) -> None:
    a_owner = seeded_tenant(app, db, prefix="iso-a")
    b_owner = seeded_tenant(app, db, prefix="iso-b")
    a_bot = make_bot(a_owner, "Bot A")
    ghost_bot = str(uuid4())
    try:
        # Guessed bot id → 404 on every knowledge route.
        base_b = f"/api/v1/tenants/{b_owner.tenant_id}/bots"
        for path, method in [
            (f"{base_b}/{a_bot['id']}/sources", "GET"),
            (f"{base_b}/{ghost_bot}/sources", "GET"),
            (f"{base_b}/{a_bot['id']}/jobs", "GET"),
            (f"{base_b}/{a_bot['id']}/documents", "GET"),
            (f"{base_b}/{a_bot['id']}/revisions", "GET"),
        ]:
            assert b_owner.call("owner", method, path).status_code == 404, path

        # Upload to A's bot via B's owner → 404 (bot hidden), nothing stored.
        upload = upload_sources(b_owner, a_bot["id"], [("x.md", MD_EN.read_bytes())], tmp_path)
        assert upload.status_code == 404
    finally:
        cleanup = [a_owner, b_owner]
        for group in cleanup:
            group.cleanup()


def test_viewer_write_denied_on_every_new_write_endpoint(
    storage_rooted_app: FastAPI, raw_db: OrmSession, tmp_path: Any
) -> None:
    users = seeded_tenant(storage_rooted_app, raw_db, prefix="up-role")
    bot_id = bot_of_users_response(users)
    ghost = uuid4()
    base = f"/api/v1/tenants/{users.tenant_id}/bots/{bot_id}"
    try:
        assert (
            upload_sources(
                users, bot_id, [("x.md", MD_EN.read_bytes())], tmp_path, as_role="viewer"
            ).status_code
            == 403
        )
        assert users.call("viewer", "POST", f"{base}/ingestion", json={}).status_code == 403
        assert users.call("viewer", "POST", f"{base}/jobs/{ghost}/cancel").status_code == 403
        assert users.call("viewer", "POST", f"{base}/jobs/{ghost}/retry").status_code == 403
        assert users.call("viewer", "POST", f"{base}/revisions/{ghost}/publish").status_code == 403
    finally:
        users.cleanup()


def test_editor_cannot_publish(
    storage_rooted_app: FastAPI, raw_db: OrmSession, tmp_path: Any
) -> None:
    users = seeded_tenant(storage_rooted_app, raw_db, prefix="up-role2")
    bot_id = bot_of_users_response(users)
    ghost = uuid4()
    try:
        response = users.call(
            "editor",
            "POST",
            f"/api/v1/tenants/{users.tenant_id}/bots/{bot_id}/revisions/{ghost}/publish",
        )
        assert response.status_code == 403
    finally:
        users.cleanup()


def test_upload_on_archived_bot_conflict(
    storage_rooted_app: FastAPI, raw_db: OrmSession, tmp_path: Any
) -> None:
    users = seeded_tenant(storage_rooted_app, raw_db, prefix="up-arch")
    bot = make_bot(users, "Archivable")
    users.call("owner", "DELETE", f"/api/v1/tenants/{users.tenant_id}/bots/{bot['id']}")
    try:
        response = upload_sources(users, bot["id"], [("x.md", MD_EN.read_bytes())], tmp_path)
        assert response.status_code == 409
        assert response.json()["error"]["code"] == "BOT_ARCHIVED"
    finally:
        users.cleanup()


def test_batch_is_atomic_on_invalid_file(
    storage_rooted_app: FastAPI, raw_db: OrmSession, tmp_path: Any
) -> None:
    try:
        users = seeded_tenant(storage_rooted_app, raw_db, prefix="up-atom")
        bot_id = bot_of_users_response(users)
        response = upload_sources(
            users,
            bot_id,
            [("good.md", MD_EN.read_bytes()), ("junk.csv", make_binary_junk())],
            tmp_path,
        )
        assert response.status_code == 415
        assert sources_of(users, bot_id) == []
    finally:
        pass
