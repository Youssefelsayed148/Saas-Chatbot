"""PostgreSQL CITEXT type for case-insensitive unique emails (docs/04).

Requires the ``citext`` contrib extension; the initial migration creates it.
"""

from typing import Any

from sqlalchemy import types


class CITEXT(types.UserDefinedType[Any]):
    """User-defined type rendering as PostgreSQL ``CITEXT``."""

    cache_ok = True

    def get_col_spec(self, **kw: Any) -> str:
        return "CITEXT"


class TSVECTOR(types.UserDefinedType[Any]):
    """PostgreSQL ``tsvector``; the P2 migration declares the GENERATED expressions."""

    cache_ok = True

    def get_col_spec(self, **kw: Any) -> str:
        return "TSVECTOR"
