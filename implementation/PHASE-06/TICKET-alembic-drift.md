# TICKET (main-owned): `alembic check` reports model/migration drift

Status: proposed, NOT implemented on `feature/phase-6-channels` (those files and migrations belong to main). Written 2026-10-27 (close-out session 2, batch 3b).

## Evidence

Both on a fresh disposable database after `alembic upgrade head`, PostgreSQL 16.15 + pgvector 0.8.0, venv from `requirements-dev.lock`:

- clean `origin/main` d189893 (head `0022_knowledge_hygiene`): the drift below.
- `feature/phase-6-channels` 8987b24 (head `0030_channel_health_poll_index`): the identical drift. Phase 6 adds none (the 0030 index is declared in the `Job` model).

Command: `cd apps/api && DATABASE_URL=postgresql+psycopg://test:test@127.0.0.1:5432/<fresh_db> alembic check` (exit 255). Exact output (INFO setup lines and the two SAWarnings about the `vector` column type and the `bots`/`knowledge_revisions` FK cycle omitted; they are unrelated):

```
INFO  [alembic.autogenerate.compare.constraints] Detected removed index 'uq_bots_widget_locator' on 'bots'
INFO  [alembic.autogenerate.compare.constraints] Detected added unique constraint None on '('widget_locator',)'
INFO  [alembic.autogenerate.compare.types] Couldn't determine database type for column 'chunks.embedding'
INFO  [alembic.autogenerate.compare.types] Couldn't determine database type for column 'chunks.embedding'
INFO  [alembic.autogenerate.compare.constraints] Detected removed index 'ix_provisioning_requests_created' on 'provisioning_requests'
INFO  [alembic.autogenerate.compare.constraints] Detected removed unique constraint 'uq_provisioning_scope_key' on 'provisioning_requests'
INFO  [alembic.autogenerate.compare.constraints] Detected added index 'uq_provisioning_scope_key' on '('mode', 'idempotency_key')'
ERROR [alembic.util.messaging] New upgrade operations detected: [('remove_index', Index('uq_bots_widget_locator', Column('widget_locator', TEXT(), table=<bots>), unique=True)), ('add_constraint', UniqueConstraint(Column('widget_locator', NullType(), table=<bots>))), ('remove_index', Index('ix_provisioning_requests_created', Column('created_at', TIMESTAMP(timezone=True), table=<provisioning_requests>, nullable=False))), ('remove_constraint', UniqueConstraint(Column('mode', NullType(), table=<provisioning_requests>), Column('idempotency_key', NullType(), table=<provisioning_requests>))), ('add_index', Index('uq_provisioning_scope_key', Column('mode', Text(), table=<provisioning_requests>, nullable=False), Column('idempotency_key', Text(), table=<provisioning_requests>, nullable=False), unique=True))]
FAILED: New upgrade operations detected: [... same list ...]
```

## Cause

The database objects are what the migrations created and are correct; the ORM declarations disagree with them.

| Object | Migration (what the DB has) | Model `apps/api/app/db/models/core.py` (what alembic compares) |
|---|---|---|
| `bots.widget_locator` | 0004: `op.create_index("uq_bots_widget_locator", "bots", ["widget_locator"], unique=True)` (a unique INDEX) | `mapped_column(Text, unique=True)` (an anonymous unique CONSTRAINT) |
| `provisioning_requests` unique key | 0006: `sa.UniqueConstraint("mode", "idempotency_key", name="uq_provisioning_scope_key")` | `Index("uq_provisioning_scope_key", "mode", "idempotency_key", unique=True)` (a unique INDEX) |
| `ix_provisioning_requests_created` | 0006: `op.create_index(..., ["created_at"])` | not declared at all |

## Proposed fix (recommended, option A): align the models, no schema change, no migration

Nothing in the database has to change, so there is no revision number to collide with the Phase 6 chain (0023-0030) and no lock or deploy risk. Change `core.py` only:

```python
# Bot
widget_locator: Mapped[str | None] = mapped_column(Text)               # drop unique=True
__table_args__ = (
    Index("uq_bots_widget_locator", "widget_locator", unique=True),    # add, first entry
    ...existing constraints...
)
# ProvisioningRequest.__table_args__: replace the Index line with
UniqueConstraint("mode", "idempotency_key", name="uq_provisioning_scope_key"),
Index("ix_provisioning_requests_created", "created_at"),
# and import UniqueConstraint from sqlalchemy
```

Verified (throwaway edit on this branch, reverted; nothing committed): with exactly those edits, `alembic check` on the fresh upgraded database prints `No new upgrade operations detected.` Run the touched-model tests (bots, widget, provisioning) on main before merging.

## Alternative (option B): migration to make the DB match the models as they are today

Only if the owner prefers the anonymous-constraint / index form. NOT run, NOT added to any branch; the revision id and `down_revision` must be the head of main at the time. It would break after the Phase 6 chain lands unless rebased onto `0030_channel_health_poll_index`.

```python
def upgrade() -> None:
    # bots.widget_locator: unique index -> unique constraint (name is Postgres' default)
    op.drop_index("uq_bots_widget_locator", table_name="bots")
    op.create_unique_constraint("bots_widget_locator_key", "bots", ["widget_locator"])
    # provisioning_requests: constraint -> unique index; drop the created_at index
    op.drop_constraint("uq_provisioning_scope_key", "provisioning_requests", type_="unique")
    op.create_index("uq_provisioning_scope_key", "provisioning_requests", ["mode", "idempotency_key"], unique=True)
    op.drop_index("ix_provisioning_requests_created", table_name="provisioning_requests")
```

Downgrade is the mirror image. Risks: it swaps two unique enforcements (a short exclusive lock on `bots` and `provisioning_requests`, and a window without uniqueness unless done in one transaction, which `op` in Alembic is by default on PostgreSQL), and it drops a `created_at` index the provisioning list may use. Option A has none of these.

## Acceptance

`alembic check` on a freshly upgraded database exits 0 on main; optionally add `alembic check` to the manual CI checklist so new drift is caught.
