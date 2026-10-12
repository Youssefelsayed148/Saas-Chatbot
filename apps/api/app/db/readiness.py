import psycopg

from app.core.config import Settings


def database_is_ready(settings: Settings) -> bool:
    if settings.database_url is None:
        return False
    try:
        with psycopg.connect(
            settings.database_url.get_secret_value(),
            connect_timeout=settings.database_connect_timeout,
        ) as connection:
            with connection.cursor() as cursor:
                cursor.execute("SELECT 1")
                return cursor.fetchone() == (1,)
    except psycopg.Error:
        # Do not expose connection strings or exception details.
        return False
