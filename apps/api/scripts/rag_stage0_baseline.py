"""Operator-only Stage 0 baseline; raw FTS, no rewrite/translation model calls.

Uses fictional demo knowledge and an explicitly supplied disposable database.
Secrets stay in memory. A durable journal prevents replaying a question after a
crash; --resume skips every started question, including an interrupted one.
"""

import argparse
import json
import os
import re
import time
from pathlib import Path
from typing import Any
from unittest.mock import patch

import httpx
import psycopg
from alembic.config import Config
from psycopg import sql
from pydantic import SecretStr
from sqlalchemy import make_url, select

from alembic import command
from app.chat.providers import ChatModel, ProviderError
from app.chat.service import chat_answer
from app.core.config import Settings
from app.db.models import Bot, Chunk
from app.db.session import create_db_engine, session_factory, sqlalchemy_url
from app.knowledge.language import detect_language
from app.knowledge.storage import get_storage
from app.retrieval.service import (
    RetrievalResult,
    RetrievedChunk,
    _best_chunk_per_document,
    retrieve,
)
from scripts.seed_demo import FAKE_PASSWORD, demo_id, seed_demo

API_DIR = Path(__file__).resolve().parents[1]
ROOT = API_DIR.parent.parent
LEAK_PATTERN = re.compile(
    r"Traceback|sqlalchemy|psycopg|ECONNRESET|api[_ -]?key|Bearer\s|"
    r"SELECT\s+.+FROM|/app/app/|[A-Z]:\\",
    re.IGNORECASE,
)


class StopBaseline(Exception):
    """Fatal provider status; deliberately not swallowed as ProviderError."""

    def __init__(self, status: str) -> None:
        self.status = status
        super().__init__(status)


class BudgetModel(ChatModel):
    """At most one generation, with one non-quota fallback and no retries."""

    def __init__(
        self, client: httpx.Client, models: list[str], history: list[str] | None = None
    ) -> None:
        if not models or any(not model.endswith(":free") for model in models):
            raise ValueError("A verified free model chain is required.")
        self.client = client
        self.models = models[:2]
        self.requests_used = 0
        self.preprocessing_skipped = 0
        self.generation_started = False
        self.model_used: str | None = None
        self.raw_completion: str | None = None
        self.http_statuses: list[int] = []
        self.history = history or []

    def complete(self, messages: list[dict[str, str]], *, json_mode: bool, max_tokens: int) -> str:
        if not json_mode:
            self.preprocessing_skipped += 1
            raise ProviderError("Stage 0 preprocessing is disabled by the request budget.")
        if self.generation_started:
            raise StopBaseline("question_budget_exhausted")
        self.generation_started = True
        messages = (
            [
                messages[0],
                *({"role": "user", "content": item} for item in self.history),
                *messages[1:],
            ]
            if messages
            else messages
        )
        for model in self.models:
            self.requests_used += 1
            self.model_used = model
            try:
                response = self.client.post(
                    "https://openrouter.ai/api/v1/chat/completions",
                    json={
                        "model": model,
                        "messages": messages,
                        "temperature": 0.2,
                        "max_tokens": max_tokens,
                        "response_format": {"type": "json_object"},
                    },
                )
            except httpx.HTTPError:
                continue
            self.http_statuses.append(response.status_code)
            try:
                payload = response.json()
            except ValueError:
                payload = {}
            error = payload.get("error") if isinstance(payload, dict) else None
            error_text = json.dumps(error).lower() if error else ""
            if response.status_code in (402, 429) or any(
                word in error_text for word in ("quota", "rate limit", "credits", '"code": 429')
            ):
                raise StopBaseline("quota_or_rate_limit")
            if response.status_code in (401, 403):
                raise StopBaseline("provider_authorization_failed")
            if response.status_code != 200 or not isinstance(payload, dict) or error:
                continue
            try:
                content = payload["choices"][0]["message"]["content"]
            except (KeyError, IndexError, TypeError):
                continue
            if isinstance(content, str) and content.strip():
                self.raw_completion = content
                usage = payload.get("usage")
                if isinstance(usage, dict):
                    self.usage_totals = {
                        key: value
                        for key, value in usage.items()
                        if key in {"prompt_tokens", "completion_tokens", "total_tokens"}
                        and isinstance(value, int)
                        and not isinstance(value, bool)
                        and value >= 0
                    } or None
                return content
        raise ProviderError("Stage 0 provider attempts exhausted.")


def load_credentials(_dotenv_path: None = None) -> tuple[str, list[str]]:
    names = ("CHAT_OPENROUTER_API_KEY", "CHAT_FREE_MODEL_CHAIN")
    values = {name: os.environ.get(name, "") for name in names}
    if not all(values[name].strip() for name in names):
        raise ValueError("The two required variables must be set.")
    try:
        models = json.loads(values[names[1]])
    except ValueError:
        raise ValueError("The model chain must be a JSON array.") from None
    if (
        not isinstance(models, list)
        or not models
        or any(
            not isinstance(model, str) or model != model.strip() or not model.endswith(":free")
            for model in models
        )
    ):
        raise ValueError("The chain must contain non-empty, whitespace-free :free IDs.")
    return values[names[0]], models


def prepare_database(database_url: str) -> None:
    url = make_url(database_url)
    name = url.database or ""
    if (
        url.get_backend_name() != "postgresql"
        or url.host not in ("localhost", "127.0.0.1")
        or not re.fullmatch(r"[a-zA-Z0-9_]+_test", name)
        or re.search(r"prod|live|staging", name, re.IGNORECASE)
        or url.query
    ):
        raise ValueError("Only an explicit local disposable PostgreSQL _test database is allowed.")
    maintenance = url.set(database="postgres").render_as_string(hide_password=False)
    with psycopg.connect(maintenance, autocommit=True) as connection:
        exists = connection.execute(
            "SELECT 1 FROM pg_database WHERE datname = %s", (name,)
        ).fetchone()
        if exists is None:
            connection.execute(sql.SQL("CREATE DATABASE {}").format(sql.Identifier(name)))
    config = Config(str(API_DIR / "alembic.ini"))
    config.set_main_option("script_location", str(API_DIR / "alembic"))
    config.set_main_option("sqlalchemy.url", sqlalchemy_url(database_url))
    command.upgrade(config, "head")


def append_record(path: Path, record: dict[str, Any], *, secret: str = "") -> None:
    serialized = json.dumps(record, ensure_ascii=False, default=str)
    if secret:
        serialized = serialized.replace(secret, "[REDACTED]")
    with path.open("a", encoding="utf-8") as stream:
        stream.write(serialized + "\n")
        stream.flush()
        os.fsync(stream.fileno())


def started_ids(journal: Path) -> set[str]:
    if not journal.exists():
        return set()
    return {json.loads(line)["id"] for line in journal.read_text(encoding="utf-8").splitlines()}


def run(args: argparse.Namespace) -> int:
    if os.environ.get("ENVIRONMENT") != "test" or os.environ.get("CHAT_STUB_MODEL"):
        raise ValueError("Set ENVIRONMENT=test and unset CHAT_STUB_MODEL.")
    if getattr(args, "retrieval_only", False):
        return run_retrieval_only(args)
    key, models = load_credentials()
    cases = [json.loads(line) for line in args.cases.read_text(encoding="utf-8").splitlines()]
    args.output.mkdir(parents=True, exist_ok=True)
    journal = args.output / "journal.jsonl"
    results = args.output / "results.jsonl"
    if journal.exists() and not args.resume:
        raise ValueError(
            "Baseline already started; replay is forbidden. Explicit --resume required."
        )
    skipped = started_ids(journal)
    prepare_database(args.database_url)
    settings = Settings.model_construct(
        environment="test",
        database_url=SecretStr(args.database_url),
        storage_root=str(args.output / "storage"),
        chat_stub_model=False,
    )
    engine = create_db_engine(settings)
    completed = 0
    requests_used = 0
    try:
        with session_factory(engine)() as db:
            seeded = seed_demo(db, get_storage(settings), settings, FAKE_PASSWORD)
            bot = db.scalar(
                select(Bot).where(Bot.tenant_id == seeded.tenant_id, Bot.id == seeded.bot_id)
            )
            if bot is None:
                raise RuntimeError("Demo bot was not seeded.")
            chunks = list(
                db.scalars(
                    select(Chunk).where(
                        Chunk.tenant_id == seeded.tenant_id,
                        Chunk.bot_id == seeded.bot_id,
                        Chunk.revision_id == bot.published_revision_id,
                    )
                )
            )
            with httpx.Client(
                headers={"Authorization": f"Bearer {key}"}, timeout=25.0, follow_redirects=False
            ) as client:
                for case in cases:
                    if case["id"] in skipped:
                        continue
                    append_record(journal, {"id": case["id"], "event": "started"})
                    model = BudgetModel(client, models, case["history"])
                    captured: list[RetrievalResult] = []
                    ranked: list[RetrievedChunk] = []

                    def observe(
                        *positional: Any,
                        _captured: list[RetrievalResult] = captured,
                        **keywords: Any,
                    ) -> RetrievalResult:
                        keywords.pop("channel", None)  # hybrid-only arguments
                        keywords.pop("embed_timeout", None)
                        retrieval = retrieve(*positional, **keywords)
                        _captured.append(retrieval)
                        return retrieval

                    def observe_ranked(
                        *positional: Any,
                        _ranked: list[RetrievedChunk] = ranked,
                        **keywords: Any,
                    ) -> list[RetrievedChunk]:
                        # RetrievalResult.candidates is not populated by the current
                        # implementation. Observe the actual ranked SQL result instead.
                        candidates = _best_chunk_per_document(*positional, **keywords)
                        _ranked.extend(candidates)
                        return candidates

                    source = case["expected_source"]
                    expected = [
                        chunk
                        for chunk in chunks
                        if source is not None and chunk.source_id == demo_id(f"source/{source}")
                    ]
                    row: dict[str, Any] = {
                        **case,
                        "status": "interrupted",
                        "expected_document_ids": sorted(
                            {str(chunk.document_id) for chunk in expected}
                        ),
                        "expected_chunk_ids": [str(chunk.id) for chunk in expected],
                        "mode": "fts_only",
                        "rewrite_enabled": False,
                        "translation_enabled": False,
                    }
                    start = time.perf_counter()
                    stop = False
                    try:
                        with (
                            patch("app.chat.service.retrieve", side_effect=observe),
                            patch(
                                "app.retrieval.service._best_chunk_per_document",
                                side_effect=observe_ranked,
                            ),
                        ):
                            reply = chat_answer(
                                db,
                                tenant_id=seeded.tenant_id,
                                bot=bot,
                                question=case["question"],
                                history=case["history"],
                                model=model,
                                settings=settings,
                            )
                        expected_ids = {str(chunk.id) for chunk in expected}
                        candidates = ranked
                        evidence = captured[0].evidence if captured else []
                        evidence_ids = {str(chunk.chunk_id) for chunk in evidence}
                        row.update(
                            status="completed",
                            answer=reply.answer,
                            citations=reply.citations,
                            kind=reply.kind,
                            can_answer=reply.can_answer,
                            needs_human=reply.needs_human,
                            candidates=[str(chunk.chunk_id) for chunk in candidates],
                            evidence=sorted(evidence_ids),
                            hit_at_8=bool(expected_ids & {str(c.chunk_id) for c in candidates}),
                            hit_in_evidence=bool(expected_ids & evidence_ids),
                            citations_valid=all(
                                c["chunk_id"] in evidence_ids for c in reply.citations
                            ),
                            internals_leak=bool(LEAK_PATTERN.search(reply.answer)),
                        )
                        completed += 1
                    except StopBaseline as error:
                        row.update(status=error.status, answer=None, citations=[])
                        stop = True
                    finally:
                        row.update(
                            latency_ms=round((time.perf_counter() - start) * 1000),
                            model_used=model.model_used,
                            requests_used=model.requests_used,
                            http_statuses=model.http_statuses,
                            raw_completion=model.raw_completion,
                            preprocessing_skipped=model.preprocessing_skipped,
                        )
                        append_record(results, row, secret=key)
                        requests_used += model.requests_used
                    print(
                        json.dumps(
                            {
                                "id": case["id"],
                                "status": row["status"],
                                "completed": completed,
                                "requests_used": requests_used,
                            }
                        ),
                        flush=True,
                    )
                    if stop:
                        return 2
    finally:
        engine.dispose()
    return 0


def run_retrieval_only(args: argparse.Namespace) -> int:
    """Measure all cases without credentials, translation or generation calls."""
    cases = [json.loads(line) for line in args.cases.read_text(encoding="utf-8").splitlines()]
    args.output.mkdir(parents=True, exist_ok=True)
    saved = args.output / "results.jsonl"
    generated = (
        {
            row["id"]: row
            for row in (json.loads(line) for line in saved.read_text(encoding="utf-8").splitlines())
        }
        if saved.exists()
        else {}
    )
    destination = args.output / "retrieval-results.jsonl"
    measured = started_ids(destination)
    prepare_database(args.database_url)
    settings = Settings.model_construct(
        environment="test",
        database_url=SecretStr(args.database_url),
        storage_root=str(args.output / "storage"),
        chat_stub_model=False,
    )
    engine = create_db_engine(settings)
    try:
        with session_factory(engine)() as db:
            seed = seed_demo(db, get_storage(settings), settings, FAKE_PASSWORD)
            bot = db.scalar(
                select(Bot).where(Bot.tenant_id == seed.tenant_id, Bot.id == seed.bot_id)
            )
            if bot is None or bot.published_revision_id is None:
                raise RuntimeError("Published demo knowledge is required.")
            chunks = list(
                db.scalars(
                    select(Chunk).where(
                        Chunk.tenant_id == seed.tenant_id,
                        Chunk.bot_id == seed.bot_id,
                        Chunk.revision_id == bot.published_revision_id,
                    )
                )
            )
            for case in cases:
                if case["id"] in measured:
                    continue
                ranked: list[RetrievedChunk] = []

                def observe(
                    *positional: Any, _ranked: list[RetrievedChunk] = ranked, **keywords: Any
                ) -> list[RetrievedChunk]:
                    found = _best_chunk_per_document(*positional, **keywords)
                    _ranked.extend(found)
                    return found

                with patch("app.retrieval.service._best_chunk_per_document", side_effect=observe):
                    result = retrieve(
                        db,
                        tenant_id=seed.tenant_id,
                        bot_id=seed.bot_id,
                        revision_id=bot.published_revision_id,
                        question=case["question"],
                        question_language=detect_language(case["question"]) or "en",
                        settings=settings,
                        translate_query=None,
                    )
                expected = {
                    str(chunk.id)
                    for chunk in chunks
                    if case["expected_source"]
                    and chunk.source_id == demo_id(f"source/{case['expected_source']}")
                }
                append_record(
                    destination,
                    {
                        **case,
                        "mode": "FTS-only, translation off",
                        "status": "measured",
                        "hit_at_8": bool(expected & {str(chunk.chunk_id) for chunk in ranked}),
                        "evidence": [str(chunk.chunk_id) for chunk in result.evidence],
                        "expected_chunk_ids": sorted(expected),
                        "gate_refuses": not result.evidence,
                        "generation_status": generated.get(case["id"], {}).get("status", "PENDING"),
                        "chat_requests_used": 0,
                    },
                )
    finally:
        engine.dispose()
    print("Retrieval-only measurements saved; chat requests used: 0.")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--database-url", required=True)
    parser.add_argument("--cases", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--retrieval-only", action="store_true")
    parser.add_argument("--resume", action="store_true")
    try:
        return run(parser.parse_args())
    except Exception as error:
        # Configuration, DB and transport exceptions may contain sensitive values.
        print(f"Baseline stopped safely ({type(error).__name__}); inspect configuration locally.")
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
