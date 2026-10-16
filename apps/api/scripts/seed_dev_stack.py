"""Seed the local Compose demo, create staff, and queue a premium embedding backfill.

Only the existing guarded development seed/staff helpers write directly to the DB.
RAG changes go through the authenticated, CSRF-protected staff API. The worker
processes the queued backfill asynchronously; this CLI does not wait for embeddings.
"""

import os

import httpx
from pydantic import EmailStr, SecretStr, TypeAdapter, ValidationError
from sqlalchemy.exc import SQLAlchemyError

from app.core.config import Settings
from app.db.session import create_db_engine, session_factory
from app.knowledge.storage import get_storage
from scripts.create_platform_staff import read_password, upsert_staff
from scripts.seed_demo import ROLES, SeedResult, demo_password, guard_database, seed_demo

API_URL = "http://api:8000"
WEB_URL = "http://localhost:3000"


def enable_premium_and_backfill(result: SeedResult, email: str, password: str) -> str:
    """Use the staff contract, including cookie authentication and CSRF checks."""
    rag_path = f"/api/v1/tenants/{result.tenant_id}/bots/{result.bot_id}/rag"
    with httpx.Client(base_url=API_URL, timeout=30, trust_env=False) as client:
        client.post(
            "/api/v1/auth/login", json={"email": email, "password": password}
        ).raise_for_status()
        csrf = client.cookies.get("chatbot_csrf")
        if not csrf:
            raise ValueError("Staff login did not issue a CSRF cookie; no RAG changes made.")
        headers = {"X-CSRF-Token": csrf}
        try:
            client.patch(rag_path, json={"tier": "premium"}, headers=headers).raise_for_status()
            response = client.post(rag_path + "/backfill", json={}, headers=headers)
            response.raise_for_status()
            job_id = response.json().get("job_id")
            if not isinstance(job_id, str) or not job_id:
                raise ValueError("Backfill response did not contain a job ID; inspect worker logs.")
            return job_id
        finally:
            # Revoke the bootstrap session even if a RAG request fails.
            client.post("/api/v1/auth/logout", headers=headers).raise_for_status()


def main() -> int:
    try:
        database_url = os.environ.get("DATABASE_URL", "")
        _, database_name = guard_database(
            database_url, os.environ.get("ENVIRONMENT", "development")
        )
        password = read_password(interactive=False)
        try:
            email = str(
                TypeAdapter(EmailStr).validate_python(
                    os.environ.get("PLATFORM_STAFF_EMAIL", "staff@example.com").strip().lower()
                )
            )
        except ValidationError:
            raise ValueError("Set PLATFORM_STAFF_EMAIL to a valid email address.") from None
        if email in {f"demo-{role}@example.com" for role in ROLES}:
            raise ValueError("Use a separate staff email, not a demo client login.")
        fixture_password = demo_password(database_name)
        # Match the existing offline seed: explicit env only, no dotenv/provider keys.
        settings = Settings.model_construct(
            database_url=SecretStr(database_url),
            storage_root=os.environ.get("STORAGE_ROOT", "/data/storage"),
        )
        engine = create_db_engine(settings)
        try:
            with session_factory(engine)() as db:
                result = seed_demo(db, get_storage(settings), settings, fixture_password)
                upsert_staff(db, email, password)
        finally:
            engine.dispose()
        job_id = enable_premium_and_backfill(result, email, password)
        print(
            f"Demo {'created' if result.created else 'reused'}; premium backfill queued: {job_id}"
        )
        print("Embedding completion is asynchronous; check bot RAG status and worker logs.")
        print(f"Staff: {email}")
        print(f"Web: {WEB_URL}")
        return 0
    except ValueError as error:
        print(str(error))
    except SQLAlchemyError:
        print("Dev seed failed; check database connectivity, migrations and storage permissions.")
    except httpx.HTTPError:
        print("Staff API setup failed; check API logs. Seeded data is safe to reuse on retry.")
    except Exception:
        # Provider bodies, DB URLs, passwords and validation input must never be logged.
        print(
            "Dev seed failed; inspect local service logs and retry after correcting configuration."
        )
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
