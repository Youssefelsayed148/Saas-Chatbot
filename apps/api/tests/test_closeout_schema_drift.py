"""Model declarations must match the existing Alembic-built constraints/indexes."""

from sqlalchemy import inspect
from sqlalchemy.engine import Engine

from app.db.models import Bot, ProvisioningRequest


def test_widget_locator_uses_the_migrated_named_unique_index(engine: Engine) -> None:
    indexes = {row["name"]: row for row in inspect(engine).get_indexes("bots")}
    assert indexes["uq_bots_widget_locator"]["unique"]
    assert indexes["uq_bots_widget_locator"]["column_names"] == ["widget_locator"]
    model_indexes = {
        str(index.name): index for index in Bot.metadata.tables[Bot.__tablename__].indexes
    }
    assert model_indexes["uq_bots_widget_locator"].unique
    assert not Bot.metadata.tables[Bot.__tablename__].c.widget_locator.unique


def test_provisioning_preserves_scope_uniqueness_and_created_lookup(engine: Engine) -> None:
    schema = inspect(engine)
    constraints = {
        row["name"]: row for row in schema.get_unique_constraints("provisioning_requests")
    }
    assert constraints["uq_provisioning_scope_key"]["column_names"] == ["mode", "idempotency_key"]
    model_constraints = {
        constraint.name: constraint
        for constraint in ProvisioningRequest.metadata.tables[
            ProvisioningRequest.__tablename__
        ].constraints
    }
    assert "uq_provisioning_scope_key" in model_constraints
    indexes = {row["name"]: row for row in schema.get_indexes("provisioning_requests")}
    assert indexes["ix_provisioning_requests_created"]["column_names"] == ["created_at"]
    assert "ix_provisioning_requests_created" in {
        index.name
        for index in ProvisioningRequest.metadata.tables[ProvisioningRequest.__tablename__].indexes
    }


def test_health_poll_lookup_index_is_already_migrated(engine: Engine) -> None:
    indexes = {row["name"]: row for row in inspect(engine).get_indexes("jobs")}
    index = indexes["ix_jobs_channel_health_poll_last"]
    assert index["column_names"][0] == "tenant_id"
    assert index["column_names"][-1] == "created_at"
    assert "channel_health_poll" in str(index["dialect_options"]["postgresql_where"])
