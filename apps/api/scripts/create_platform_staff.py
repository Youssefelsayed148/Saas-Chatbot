"""Create or update a platform-staff user.

The password comes from the PLATFORM_STAFF_PASSWORD environment variable or an
interactive prompt. It is never accepted as an argument, hardcoded or printed.
Outside ENVIRONMENT=production it refuses any database not named *_dev / *_demo
(same guard as the demo seed). With ENVIRONMENT=production (the deployed stack)
it accepts any PostgreSQL database, because that is how the first admin exists.
"""

import argparse
import getpass
import os
import sys
from uuid import uuid4

from pydantic import SecretStr
from sqlalchemy import select
from sqlalchemy.engine import make_url
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from app.auth.schemas import PASSWORD_MIN_LENGTH
from app.auth.security import hash_password
from app.core.config import Settings
from app.db.models import User
from app.db.session import create_db_engine, session_factory
from scripts.seed_demo import guard_database

PASSWORD_ENV = "PLATFORM_STAFF_PASSWORD"


def guard_staff_database(database_url: str, environment: str) -> tuple[str, str]:
    """Development keeps the demo-database guard; production only requires PostgreSQL."""
    if environment != "production":
        return guard_database(database_url, environment)
    try:
        url = make_url(database_url)
    except Exception:
        raise ValueError("DATABASE_URL must be a PostgreSQL URL.") from None
    if url.get_backend_name() != "postgresql" or not url.database:
        raise ValueError("DATABASE_URL must be a PostgreSQL URL.")
    return url.host or "", url.database


def read_password(*, interactive: bool) -> str:
    password = os.environ.get(PASSWORD_ENV)
    if not password:
        if not interactive:
            raise ValueError(f"Set {PASSWORD_ENV} or run from an interactive terminal.")
        password = getpass.getpass("Platform staff password: ")
        if getpass.getpass("Repeat password: ") != password:
            raise ValueError("Passwords do not match.")
    if not PASSWORD_MIN_LENGTH <= len(password) <= 200:
        raise ValueError(f"Password must be {PASSWORD_MIN_LENGTH}–200 characters.")
    return password


def upsert_staff(db: Session, email: str, password: str) -> bool:
    """Return True when the user was created, False when an existing one was updated."""
    email = email.strip().lower()
    user = db.scalar(select(User).where(User.email == email))
    created = user is None
    if user is None:
        user = User(id=uuid4(), email=email, password_hash=hash_password(password))
        db.add(user)
    else:
        user.password_hash = hash_password(password)
    user.is_platform_staff = True
    db.commit()
    return created


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--email", default=os.environ.get("PLATFORM_STAFF_EMAIL", ""))
    args = parser.parse_args(argv)
    try:
        if "@" not in args.email:
            raise ValueError("Pass --email or set PLATFORM_STAFF_EMAIL to a valid address.")
        database_url = os.environ.get("DATABASE_URL", "")
        host, name = guard_staff_database(
            database_url, os.environ.get("ENVIRONMENT", "development")
        )
        password = read_password(interactive=sys.stdin.isatty())
        settings = Settings.model_construct(database_url=SecretStr(database_url))
        engine = create_db_engine(settings)
        try:
            with session_factory(engine)() as db:
                created = upsert_staff(db, args.email, password)
        finally:
            engine.dispose()
        print(
            f"Platform staff {'created' if created else 'updated'}: {args.email} on {host}/{name}"
        )
        return 0
    except ValueError as error:
        print(str(error))
    except SQLAlchemyError:
        print("Staff account failed; check connectivity and that migrations are applied.")
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
