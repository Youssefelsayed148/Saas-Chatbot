"""P1-03: invitations — one-time links, expiry, revocation, resend, email match, audit."""

import threading
from typing import Any

from fastapi.testclient import TestClient
from sqlalchemy import text
from sqlalchemy.orm import Session as OrmSession

from app.auth.security import hash_token
from tests.helpers import (
    accept_invitation,
    audit_actions,
    cleanup_clients,
    logged_in,
    make_invitation,
    seeded_tenant,
)


def test_invitation_create_accept_single_use(app: Any, db: OrmSession) -> None:
    users = seeded_tenant(app, db)
    try:
        token, invitation = make_invitation(users, "NewTeammate@example.com", "editor")
        assert invitation["role"] == "editor"
        assert invitation["email"] == "newteammate@example.com"

        # The invitee registers with the invited address, then accepts.
        invitee, _ = logged_in(app, "newteammate@example.com")
        try:
            accepted = accept_invitation(invitee, token)
            assert accepted.status_code == 200, accepted.text
            me_payload: dict[str, Any] = accepted.json()
            roles = {m["tenant_id"]: m["role"] for m in me_payload["memberships"]}
            assert roles[str(users.tenant_id)] == "editor"

            # The token is single-use.
            used = accept_invitation(invitee, token)
            assert used.status_code == 409
            assert used.json()["error"]["code"] == "INVITATION_USED"
        finally:
            cleanup_clients(invitee)

        # It no longer appears as a pending invitation.
        pending = users.call("admin", "GET", f"/api/v1/tenants/{users.tenant_id}/invitations")
        assert pending.status_code == 200
        assert all(row["id"] != invitation["id"] for row in pending.json())

        # Only the SHA-256 hash of the token is stored.
        stored = db.execute(
            text("SELECT token_hash FROM invitations WHERE id = CAST(:id AS uuid)"),
            {"id": invitation["id"]},
        ).scalar()
        assert token not in str(stored)
        assert len(str(stored)) == 64

        members = users.call("admin", "GET", f"/api/v1/tenants/{users.tenant_id}/members").json()
        roles_by_email = {row["email"]: row["role"] for row in members}
        assert roles_by_email["newteammate@example.com"] == "editor"

        audit = audit_actions(db, "invitation.accepted", users.tenant_id)
        assert len(audit) == 1
    finally:
        users.cleanup()


def test_invitation_expired_and_unknown_and_revoked(app: Any, db: OrmSession) -> None:
    users = seeded_tenant(app, db)
    try:
        invitee, _ = logged_in(app, "late@example.com")
        try:
            # Expired.
            token, _ = make_invitation(users, "late@example.com", "viewer")
            db.execute(
                text(
                    "UPDATE invitations SET expires_at = NOW() - INTERVAL '1 day' "
                    "WHERE token_hash = :hash"
                ),
                {"hash": hash_token(token)},
            )
            db.commit()
            expired = accept_invitation(invitee, token)
            assert expired.status_code == 409
            assert expired.json()["error"]["code"] == "INVITATION_EXPIRED"

            # Unknown token.
            unknown = accept_invitation(invitee, "x" * 43)
            assert unknown.status_code == 404
            assert unknown.json()["error"]["code"] == "NOT_FOUND"
        finally:
            cleanup_clients(invitee)

        # Revoked before acceptance.
        token, invitation = make_invitation(users, "revoked@example.com", "viewer")
        users.call(
            "admin",
            "DELETE",
            f"/api/v1/tenants/{users.tenant_id}/invitations/{invitation['id']}",
        )
        invitee2, _ = logged_in(app, "revoked@example.com")
        try:
            response = accept_invitation(invitee2, token)
            assert response.status_code == 409
            assert response.json()["error"]["code"] == "INVITATION_REVOKED"
        finally:
            cleanup_clients(invitee2)
    finally:
        users.cleanup()


def test_resend_replaces_token(app: Any, db: OrmSession) -> None:
    users = seeded_tenant(app, db)
    try:
        token, invitation = make_invitation(users, "resend@example.com", "viewer")
        resent = users.call(
            "admin",
            "POST",
            f"/api/v1/tenants/{users.tenant_id}/invitations/{invitation['id']}/resend",
        )
        assert resent.status_code == 200
        new_token = resent.json()["link_path"].split("token=")[1]
        assert new_token != token

        invitee, _ = logged_in(app, "resend@example.com")
        try:
            stale = accept_invitation(invitee, token)
            assert stale.status_code == 404  # the old hash is replaced server-side
            current = accept_invitation(invitee, new_token)
            assert current.status_code == 200

            # Resending an accepted invitation is a conflict.
            again = users.call(
                "admin",
                "POST",
                f"/api/v1/tenants/{users.tenant_id}/invitations/{invitation['id']}/resend",
            )
            assert again.status_code == 409
        finally:
            cleanup_clients(invitee)
    finally:
        users.cleanup()


def test_accept_requires_matching_email(app: Any, db: OrmSession) -> None:
    users = seeded_tenant(app, db)
    try:
        token, _ = make_invitation(users, "specific@example.com", "editor")
        other, _ = logged_in(app, "someoneelse@example.com")
        try:
            mismatched = accept_invitation(other, token)
            assert mismatched.status_code == 403
            assert mismatched.json()["error"]["code"] == "INVITEE_EMAIL_MISMATCH"
            pending = users.call(
                "admin", "GET", f"/api/v1/tenants/{users.tenant_id}/invitations"
            ).json()
            assert len(pending) == 1
        finally:
            cleanup_clients(other)
    finally:
        users.cleanup()


def test_admin_cannot_mint_owner_invitation_and_viewer_blocked(app: Any, db: OrmSession) -> None:
    users = seeded_tenant(app, db)
    try:
        admin_attempt = users.call(
            "admin",
            "POST",
            f"/api/v1/tenants/{users.tenant_id}/invitations",
            json={"email": "escalated@example.com", "role": "owner"},
        )
        assert admin_attempt.status_code == 422

        editor_blocked = users.call(
            "editor",
            "GET",
            f"/api/v1/tenants/{users.tenant_id}/invitations",
        )
        assert editor_blocked.status_code == 403

        # S2 invitations target an account provisioned before the invitation.
        logged_in(app, "admin-invite@example.com")[0].close()
        created_by_admin = users.call(
            "admin",
            "POST",
            f"/api/v1/tenants/{users.tenant_id}/invitations",
            json={"email": "admin-invite@example.com", "role": "viewer"},
        )
        assert created_by_admin.status_code == 201
    finally:
        users.cleanup()


def test_invitation_double_accept_race_exactly_one_succeeds(app: Any, db: OrmSession) -> None:
    """Two concurrent accepts of one token: exactly one succeeds (P2-00)."""
    users = seeded_tenant(app, db)
    try:
        invitee, invitee_payload = logged_in(app, "racer@example.com")
        token, _ = make_invitation(users, "racer@example.com", "editor")
        try:
            barrier = threading.Barrier(2)
            results: list[Any] = []

            def attempt(running_client: TestClient) -> None:
                barrier.wait()
                results.append(accept_invitation(running_client, token))

            threads = [
                threading.Thread(target=attempt, args=(invitee,)),
                threading.Thread(target=attempt, args=(invitee,)),
            ]
            for thread in threads:
                thread.start()
            for thread in threads:
                thread.join(timeout=30)
            assert len(results) == 2
            statuses = sorted(response.status_code for response in results)
            assert statuses == [200, 409], [r.text for r in results]
            rejected = next(r for r in results if r.status_code == 409)
            assert rejected.json()["error"]["code"] == "INVITATION_USED"

            # Exactly one membership row was created for the invitee.
            count = db.execute(
                text(
                    "SELECT COUNT(*) FROM memberships "
                    "WHERE tenant_id = CAST(:tid AS uuid) AND user_id = CAST(:uid AS uuid)"
                ),
                {"tid": str(users.tenant_id), "uid": invitee_payload["id"]},
            ).scalar()
            assert count == 1

            # The audit trail holds a single accept event.
            assert len(audit_actions(db, "invitation.accepted", users.tenant_id)) == 1
        finally:
            cleanup_clients(invitee)
    finally:
        users.cleanup()
