"""P1-02: database constraints — uniqueness, checks and FKs (docs/04)."""

from datetime import UTC, datetime
from uuid import uuid4

import pytest
from sqlalchemy import inspect, select, text
from sqlalchemy.engine import Engine
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session as OrmSession

from app.db.models import AuditEvent, Bot, Invitation, Membership, Session, Tenant, User


def _utcnow() -> datetime:
    return datetime.now(UTC)


def _user(db: OrmSession, email: str) -> User:
    user = User(id=uuid4(), email=email, password_hash="argon2id$test")
    db.add(user)
    db.flush()
    return user


def _tenant(db: OrmSession, name: str = "Acme") -> Tenant:
    tenant = Tenant(id=uuid4(), name=name, slug=name.lower())
    db.add(tenant)
    db.flush()
    return tenant


def _membership(db: OrmSession, tenant: Tenant, user: User, role: str = "owner") -> Membership:
    membership = Membership(tenant_id=tenant.id, user_id=user.id, role=role, status="active")
    db.add(membership)
    db.flush()
    return membership


def _bot(db: OrmSession, tenant: Tenant, name: str = "Bot") -> Bot:
    bot = Bot(id=uuid4(), tenant_id=tenant.id, name=name, status="draft", config={})
    db.add(bot)
    db.flush()
    return bot


def test_duplicate_email_case_insensitive(db: OrmSession) -> None:
    _user(db, "owner@example.com")
    duplicate = User(id=uuid4(), email="OWNER@example.com", password_hash="argon2id$x")
    db.add(duplicate)
    with pytest.raises(IntegrityError):
        db.flush()
    db.rollback()


def test_email_unique_across_register_flow(db: OrmSession) -> None:
    """citext emails are unique: ACME@a vs acme@a collide (exact unique index)."""
    _user(db, "Support@Client.co")
    clone = User(id=uuid4(), email="support@client.co", password_hash="argon2id$x")
    db.add(clone)
    with pytest.raises(IntegrityError):
        db.flush()
    db.rollback()


def test_membership_unique_tenant_user(db: OrmSession) -> None:
    tenant = _tenant(db)
    user = _user(db, "member@example.com")
    _membership(db, tenant, user, role="owner")
    again = Membership(tenant_id=tenant.id, user_id=user.id, role="editor", status="active")
    db.add(again)
    with pytest.raises(IntegrityError):
        db.flush()
    db.rollback()


def test_membership_role_check_constraint(db: OrmSession) -> None:
    tenant = _tenant(db)
    user = _user(db, "WeirdRole@example.com")
    rogue = Membership(tenant_id=tenant.id, user_id=user.id, role="superadmin", status="active")
    db.add(rogue)
    with pytest.raises(IntegrityError):
        db.flush()
    db.rollback()


def test_membership_status_check_constraint(db: OrmSession) -> None:
    tenant = _tenant(db)
    user = _user(db, "WeirdStatus@example.com")
    botched = Membership(tenant_id=tenant.id, user_id=user.id, role="viewer", status="paused")
    db.add(botched)
    with pytest.raises(IntegrityError):
        db.flush()
    db.rollback()


def test_bots_tenant_id_id_unique_anchor_index(engine: Engine) -> None:
    """(tenant_id, id) unique index exists so child tables can use composite FKs (ADR-010)."""
    indexes = {idx["name"]: idx["column_names"] for idx in inspect(engine).get_indexes("bots")}
    assert indexes.get("uq_bots_tenant_id_id") == ["tenant_id", "id"]
    memberships_indexes = {
        idx["name"]: idx["column_names"] for idx in inspect(engine).get_indexes("memberships")
    }
    assert memberships_indexes.get("ix_memberships_tenant_id") == ["tenant_id"]


def test_bot_status_check_constraint(db: OrmSession) -> None:
    tenant = _tenant(db)
    bot = Bot(id=uuid4(), tenant_id=tenant.id, name="X", status="deleted", config={})
    db.add(bot)
    with pytest.raises(IntegrityError):
        db.flush()
    db.rollback()


def test_tenant_status_check_constraint(db: OrmSession) -> None:
    tenant = Tenant(id=uuid4(), name="Odd", slug="odd-status", status="suspended")
    db.add(tenant)
    with pytest.raises(IntegrityError):
        db.flush()
    db.rollback()


def test_session_fk_to_users(db: OrmSession) -> None:
    session = Session(
        id=uuid4(),
        token_hash="a" * 64,
        user_id=uuid4(),  # no such user
        expires_at=_utcnow(),
    )
    db.add(session)
    with pytest.raises(IntegrityError):
        db.flush()
    db.rollback()


def test_session_token_hash_unique(db: OrmSession) -> None:
    user = _user(db, "twice@example.com")
    db.add(
        Session(
            id=uuid4(),
            token_hash="b" * 64,
            user_id=user.id,
            expires_at=_utcnow(),
        )
    )
    db.flush()
    db.add(
        Session(
            id=uuid4(),
            token_hash="b" * 64,  # same hash, fresh session row
            user_id=user.id,
            expires_at=_utcnow(),
        )
    )
    with pytest.raises(IntegrityError):
        db.flush()
    db.rollback()


def test_invitation_role_check_and_constraints(db: OrmSession) -> None:
    tenant = _tenant(db)
    creator = _user(db, "owner2@example.com")
    db.commit()  # keep the base rows through the later IntegrityError rollbacks
    botched = Invitation(
        id=uuid4(),
        tenant_id=tenant.id,
        email="invitee@example.com",
        role="superadmin",
        token_hash="c" * 64,
        expires_at=_utcnow(),
        created_by=creator.id,
    )
    db.add(botched)
    with pytest.raises(IntegrityError):
        db.flush()
    db.rollback()

    valid = Invitation(
        id=uuid4(),
        tenant_id=tenant.id,
        email="invitee2@example.com",
        role="editor",
        token_hash="d" * 64,
        expires_at=_utcnow(),
        created_by=creator.id,
    )
    db.add(valid)
    db.flush()

    duplicate_token = Invitation(
        id=uuid4(),
        tenant_id=tenant.id,
        email="invitee3@example.com",
        role="viewer",
        token_hash="d" * 64,
        expires_at=_utcnow(),
        created_by=creator.id,
    )
    db.add(duplicate_token)
    with pytest.raises(IntegrityError):
        db.flush()
    db.rollback()


def test_audit_events_allow_null_tenant_and_actor(db: OrmSession) -> None:
    event = AuditEvent(
        id=uuid4(),
        tenant_id=None,
        actor_user_id=None,
        action="system.boot",
        target_type=None,
        target_id=None,
        metadata_json={},
    )
    db.add(event)
    db.flush()
    stored = db.execute(select(AuditEvent)).scalar_one()
    assert stored.action == "system.boot"
    assert stored.metadata_json == {}


def test_cascade_delete_tenant_removes_owned_rows(db: OrmSession) -> None:
    tenant = _tenant(db, "Cascade")
    user = _user(db, "cascade@example.com")
    _membership(db, tenant, user, role="owner")
    _bot(db, tenant)
    db.commit()

    db.execute(text('DELETE FROM "tenants" WHERE "id" = CAST(:id AS uuid)'), {"id": str(tenant.id)})
    db.commit()
    db.expire_all()
    assert db.execute(select(Bot)).scalars().all() == []
    assert db.execute(select(Membership)).scalars().all() == []
