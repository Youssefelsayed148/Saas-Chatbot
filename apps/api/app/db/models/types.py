"""PostgreSQL CITEXT type for case-insensitive unique emails (docs/04).

Requires the ``citext`` contrib extension; the initial migration creates it.
"""

import json
from collections.abc import Callable
from typing import Any

from sqlalchemy import types
from sqlalchemy.engine import Dialect


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


class VECTOR1024(types.UserDefinedType[list[float]]):
    """pgvector's fixed deployment dimension; text wire format needs no driver plugin."""

    cache_ok = True

    def get_col_spec(self, **kw: Any) -> str:
        return "VECTOR(1024)"

    def bind_processor(self, dialect: Dialect) -> Callable[[Any], str | None]:
        def encode(value: Any) -> str | None:
            return None if value is None else json.dumps(value, allow_nan=False)

        return encode

    def result_processor(
        self, dialect: Dialect, coltype: object
    ) -> Callable[[Any], list[float] | None]:
        def decode(value: Any) -> list[float] | None:
            if value is None:
                return None
            raw = json.loads(value) if isinstance(value, str) else value
            return [float(item) for item in raw]

        return decode
