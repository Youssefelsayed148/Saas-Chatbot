"""Every declared tenant route: real requests, 403 or success, plus tenant A/B."""

from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any
from uuid import UUID, uuid4

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select

from app.core.config import get_settings
from app.core.tenancy import ROLE_LEVELS
from app.db.models import (
    Bot,
    ChangeRequest,
    Contact,
    Conversation,
    Document,
    FollowUp,
    Invitation,
    Job,
    Membership,
    Message,
    Source,
    User,
    VisitorSession,
)
from app.knowledge.storage import get_storage
from scripts.seed_demo import FAKE_PASSWORD, seed_demo
from tests.conftest import build_test_settings, csrf_headers
from tests.helpers import logged_in, seeded_tenant

CHANNEL_PLATFORM_ROUTE_ROLES = {
    ("GET", "/api/v1/platform/channel-connections"): "platform_staff_only",
    ("POST", "/api/v1/platform/channel-connections"): "platform_staff_only",
    ("GET", "/api/v1/platform/channel-connections/{connection_id}"): "platform_staff_only",
    ("PATCH", "/api/v1/platform/channel-connections/{connection_id}"): "platform_staff_only",
    (
        "POST",
        "/api/v1/platform/channel-connections/{connection_id}/pause",
    ): "platform_staff_only",
    (
        "POST",
        "/api/v1/platform/channel-connections/{connection_id}/resume",
    ): "platform_staff_only",
    (
        "POST",
        "/api/v1/platform/channel-connections/{connection_id}/revoke",
    ): "platform_staff_only",
    (
        "POST",
        "/api/v1/platform/channel-connections/{connection_id}/rotate-secret",
    ): "platform_staff_only",
    (
        "POST",
        "/api/v1/platform/channel-connections/{connection_id}/check-health",
    ): "platform_staff_only",
}


@pytest.mark.parametrize("role", ["viewer", "editor", "admin", "staff"])
def test_every_openapi_route_role_and_cross_tenant(
    app: Any, db: Any, tmp_path: Path, monkeypatch: Any, role: str
) -> None:
    settings = build_test_settings(storage_root=str(tmp_path), chat_stub_model=True)
    app.dependency_overrides[get_settings] = lambda: settings
    seed = seed_demo(db, get_storage(settings), settings, FAKE_PASSWORD)
    tid, bid = seed.tenant_id, seed.bot_id
    client = TestClient(app)
    if role == "staff":
        client.close()
        client, payload = logged_in(app, "matrix-staff@example.com")
        staff = db.get(User, UUID(payload["id"]))
        staff.is_platform_staff = True
        db.commit()
    else:
        result = client.post(
            "/api/v1/auth/login",
            json={"email": f"demo-{role}@example.com", "password": FAKE_PASSWORD},
        )
        assert result.status_code == 200
        payload = result.json()
    foreign = seeded_tenant(app, db, prefix=f"foreign-{role}")
    # Only bound the stream transport; the actual endpoint and its real
    # authentication/tenant/role dependencies are exercised over HTTP.
    monkeypatch.setattr(
        "app.inbox.listing.event_stream", lambda *args: iter(["event: inbox.ready\ndata: {}\n\n"])
    )
    uid = UUID(payload["id"])
    bot = db.get(Bot, bid)
    contact = db.scalar(select(Contact).where(Contact.tenant_id == tid))
    conversation = db.scalar(
        select(Conversation).where(Conversation.tenant_id == tid, Conversation.source == "website")
    )
    visitor = VisitorSession(
        tenant_id=tid,
        bot_id=bid,
        token_hash=uuid4().hex,
        expires_at=datetime.now(UTC) + timedelta(days=1),
    )
    db.add(visitor)
    db.flush()
    conversation.session_id = visitor.id
    source = db.scalar(select(Source).where(Source.tenant_id == tid))
    document = db.scalar(select(Document).where(Document.tenant_id == tid))
    message = db.scalar(
        select(Message).where(Message.tenant_id == tid, Message.sender_type == "ai")
    )
    token = uuid4().hex
    from app.auth.security import hash_token

    invite = Invitation(
        id=uuid4(),
        tenant_id=tid,
        email="pending@example.com",
        role="viewer",
        token_hash=hash_token(token),
        expires_at=datetime.now(UTC) + timedelta(days=7),
        created_by=uid,
    )
    job = Job(
        tenant_id=tid,
        bot_id=bid,
        type="ingest_batch",
        status="failed",
        payload={"source_ids": [str(source.id)]},
    )
    followup = FollowUp(
        tenant_id=tid,
        bot_id=bid,
        conversation_id=conversation.id,
        text="Follow up",
        send_at=datetime.now(UTC) + timedelta(days=1),
        created_by=uid,
    )
    key = get_storage(settings).save(tid, uuid4(), "txt", b"request attachment")
    attachment_id = uuid4()
    change = ChangeRequest(
        tenant_id=tid,
        requester_id=uid,
        type="other",
        text="Matrix",
        attachments=[
            {"id": str(attachment_id), "name": "evidence.txt", "size_bytes": 18, "storage_key": key}
        ],
    )
    db.add_all([invite, job, followup, change])
    db.commit()
    ids = dict(
        tenant_id=tid,
        bot_id=bid,
        source_id=source.id,
        document_id=document.id,
        revision_id=bot.published_revision_id,
        conversation_id=conversation.id,
        contact_id=contact.id,
        message_id=message.id,
        invitation_id=invite.id,
        job_id=job.id,
        follow_up_id=followup.id,
        request_id=change.id,
        attachment_id=attachment_id,
        tag="matrix",
        user_id=uuid4(),
    )
    extra, extra_payload = logged_in(app, "matrix-target@example.com")
    db.add(Membership(tenant_id=tid, user_id=UUID(extra_payload["id"]), role="viewer"))
    db.commit()
    ids["user_id"] = UUID(extra_payload["id"])
    if role == "staff":
        assert db.scalar(select(Membership).where(Membership.user_id == uid)) is None
    operations = []
    for path, methods in app.openapi()["paths"].items():
        if not path.startswith("/api/v1/tenants"):
            continue
        for method, operation in methods.items():
            if method.upper() not in {"GET", "POST", "PATCH", "DELETE"}:
                continue
            minimum = operation.get("x-minimum-role")
            assert minimum in {*ROLE_LEVELS, "authenticated", "platform_staff_only"}, (method, path)
            operations.append((method.upper(), path, minimum))
    # Read first; destructive operations last; organization disablement last of all.
    operations.sort(
        key=lambda item: (
            item[1].endswith("/data") and item[0] == "DELETE",
            {"GET": 0, "POST": 1, "PATCH": 2, "DELETE": 3}[item[0]],
        )
    )
    try:
        for method, template, minimum in operations:
            if role == "staff":
                assert db.get(Membership, (tid, uid)) is None
            db.expire_all()
            # Reset business state so success assertions measure authorization,
            # not an earlier action's conflicting state.
            bot.status = "active"
            conversation.mode = "human" if template.endswith("/messages") else "ai"
            conversation.status = "open"
            conversation.assigned_user_id = (
                uid if conversation.mode == "human" and role != "staff" else None
            )
            source.status = "stored"
            job.status = "failed" if template.endswith("/retry") else "pending"
            db.commit()
            path = template.format(**ids)
            if template.endswith("/contacts/{contact_id}/merge"):
                merge_source = Contact(tenant_id=tid, email=f"source-{uuid4().hex}@example.com")
                db.add(merge_source)
                db.commit()
                path = template.format(**{**ids, "contact_id": merge_source.id})
            body: dict[str, Any] = {}
            kwargs: dict[str, Any] = {}
            if method in {"POST", "PATCH", "DELETE"}:
                body = {
                    "name": "Matrix",
                    "text": "Please help",
                    "rating": "up",
                    "role": "viewer",
                    "assigned_user_id": None,
                    "email": f"invite-{uuid4().hex}@example.com",
                    "tag": "matrix",
                    "old_name": "new",
                    "confirm_name": "Demo Dental Clinic",
                    "reason": "Matrix deletion request",
                    "conversation_id": str(conversation.id),
                    "send_at": (datetime.now(UTC) + timedelta(days=1)).isoformat(),
                }
                if template.endswith("/invitations"):
                    body = {"email": f"invite-{uuid4().hex}@example.com", "role": "viewer"}
                    # Existing-account prerequisite; retain the route/RBAC assertions.
                    db.add(User(id=uuid4(), email=body["email"], password_hash="fixture"))
                    db.commit()
                if template.endswith("/invitations/{invitation_id}/resend"):
                    body = {}
                if template.endswith("/members/{user_id}"):
                    body = {"role": "viewer"}
                if template == "/api/v1/tenants/{tenant_id}":
                    body = {"retention_days": 30}
                if template.endswith("/ingestion"):
                    body = {"source_ids": [str(source.id)]}
                if template.endswith("/contacts/{contact_id}") and method == "PATCH":
                    body = {"display_name": "Updated"}
                if template.endswith("/contacts/{contact_id}/merge"):
                    other = Contact(tenant_id=tid, email=f"merge-{uuid4().hex}@example.com")
                    db.add(other)
                    db.commit()
                    body = {}
                    kwargs["params"] = {"target_id": str(other.id)}
                if template.endswith("/data"):
                    body = {
                        "confirm_name": "Demo Dental Clinic",
                        "reason": "Matrix deletion request",
                    }
                if template.endswith("/bots") or template == "/api/v1/tenants":
                    body = {"name": "Matrix"}
                if template.endswith("/bots/{bot_id}") and method == "PATCH":
                    body = {"name": "Matrix bot"}
                kwargs["json"] = body
                if template.endswith(("/rag", "/rag/backfill")):
                    kwargs["json"] = {}
                if template.endswith("/sources/files"):
                    kwargs = {
                        "files": [
                            ("files", ("matrix.md", b"# Matrix\nA matrix source.", "text/markdown"))
                        ]
                    }
                if template.endswith("/change-requests"):
                    kwargs = {"data": {"type": "other", "text": "Matrix request"}}
            membership_required = (
                minimum == "editor"
                and method != "GET"
                and (
                    "/inbox/" in template
                    or template.startswith("/api/v1/tenants/{tenant_id}/conversations/")
                )
            )
            allowed = (
                (role == "staff" and not membership_required)
                or minimum == "authenticated"
                or (
                    role != "staff"
                    and minimum != "platform_staff_only"
                    and ROLE_LEVELS[role] >= ROLE_LEVELS[minimum]
                )
            )
            # Give destructive endpoints disposable targets, preserving the main fixture.
            if method == "DELETE" and template.endswith("/contacts/{contact_id}"):
                target = Contact(tenant_id=tid, email=f"delete-{uuid4().hex}@example.com")
                db.add(target)
                db.commit()
                path = template.format(**{**ids, "contact_id": target.id})
            if method == "DELETE" and template.endswith("/conversations/{conversation_id}"):
                target_cv = Conversation(tenant_id=tid, bot_id=bid, source="website")
                db.add(target_cv)
                db.commit()
                path = template.format(**{**ids, "conversation_id": target_cv.id})
            if "{tenant_id}" in template and role != "staff":
                denied = client.request(
                    method,
                    template.format(**{**ids, "tenant_id": foreign.tenant_id}),
                    headers=csrf_headers(client),
                    **kwargs,
                )
                assert denied.status_code == 404, (
                    role,
                    method,
                    template,
                    denied.status_code,
                    denied.text,
                )
            response = client.request(method, path, headers=csrf_headers(client), **kwargs)
            assert (
                (200 <= response.status_code < 300) if allowed else response.status_code == 403
            ), (role, method, template, minimum, response.status_code, response.text)
    finally:
        client.close()
        extra.close()
        foreign.cleanup()


def test_every_platform_route_denies_each_client_role(app: Any, db: Any) -> None:
    import re

    users = seeded_tenant(app, db, "platform-matrix")
    try:
        for path, methods in app.openapi()["paths"].items():
            if not path.startswith("/api/v1/platform"):
                continue
            for method, operation in methods.items():
                if method.upper() not in {"GET", "POST", "PATCH", "DELETE"}:
                    continue
                assert operation["x-minimum-role"] == "platform_staff_only"
                url = re.sub(r"\{[^}]+\}", lambda _: str(uuid4()), path)
                for role in ("admin", "editor", "viewer"):
                    response = users.call(
                        role,
                        method.upper(),
                        url,
                        **({"json": {}} if method.upper() != "GET" else {}),
                    )
                    assert response.status_code == 403, (role, method, path, response.text)
    finally:
        users.cleanup()


def test_exact_route_contract_and_operator_knowledge(app: Any) -> None:
    from app.core.permissions import TENANT_ROUTE_ROLES

    actual = {
        (method.upper(), path): operation["x-minimum-role"]
        for path, methods in app.openapi()["paths"].items()
        if path.startswith("/api/v1/tenants")
        for method, operation in methods.items()
        if method.upper() in {"GET", "POST", "PATCH", "DELETE"}
    }
    assert len(actual) == len(TENANT_ROUTE_ROLES) == 83
    assert actual == TENANT_ROUTE_ROLES
    base = "/api/v1/tenants/{tenant_id}/bots/{bot_id}"
    for suffix in (
        "/sources",
        "/sources/{source_id}",
        "/sources/qa-template",
        "/jobs",
        "/jobs/{job_id}",
        "/documents",
        "/documents/{document_id}/chunks",
        "/revisions",
        "/rag",
    ):
        assert actual[("GET", base + suffix)] == "platform_staff_only"


def test_channel_platform_routes_are_classified(app: Any) -> None:
    actual = {
        (method.upper(), path): operation["x-minimum-role"]
        for path, methods in app.openapi()["paths"].items()
        for method, operation in methods.items()
        if (method.upper(), path) in CHANNEL_PLATFORM_ROUTE_ROLES
    }
    assert actual == CHANNEL_PLATFORM_ROUTE_ROLES
