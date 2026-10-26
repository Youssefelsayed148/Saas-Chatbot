"""Staff/owner-only RAG eval runner. No dotenv; local disposable databases only."""

import argparse
import json
import time
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any
from unittest.mock import patch
from uuid import uuid4

import httpx
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.chat.service import chat_answer
from app.core.config import Settings
from app.db.models import Bot, Chunk, Source
from app.db.session import create_db_engine, session_factory
from app.embeddings.backfill import queue_backfill
from app.embeddings.providers import Embedder, TestHashEmbedder, configured_identity, from_settings
from app.jobs.runner import execute_claimed_job
from app.knowledge.ingest import plan_source
from app.knowledge.parsers import parse_text
from app.knowledge.storage import get_storage
from app.retrieval.evaluation import (
    CachedEmbedder,
    CappedChatTransport,
    estimate_calibration,
    read_cache,
    summarize,
    text_key,
    threshold_proposal,
    threshold_sweep,
)
from app.retrieval.gate import relevance_gate
from app.retrieval.hybrid import retrieve_hybrid
from scripts.rag_stage0_baseline import (
    API_DIR,
    LEAK_PATTERN,
    BudgetModel,
    StopBaseline,
    append_record,
    load_credentials,
    prepare_database,
    started_ids,
)
from scripts.seed_demo import FAKE_PASSWORD, FAQS, demo_id, demo_source_data, seed_demo

DEFAULT_CASES = API_DIR / "tests/fixtures/rag-phase2-eval.jsonl"


def load_cases(path: Path) -> list[dict[str, Any]]:
    rows = [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines()]
    ids = [row["id"] for row in rows]
    if len(set(ids)) != len(ids) or len(rows) < 30:
        raise ValueError("Eval requires at least 30 uniquely identified cases.")
    if any(
        row["type"] not in {"paraphrase", "follow-up", "arabic", "mixed", "unanswerable"}
        for row in rows
    ):
        raise ValueError("Unknown evaluation case type.")
    # Spend any generation budget on informative groups first.
    priority = {"arabic": 0, "mixed": 1, "unanswerable": 2, "paraphrase": 3, "follow-up": 4}
    return sorted(rows, key=lambda row: priority[row["type"]])


def bind_cases(cases: list[dict[str, Any]], chunks: list[Chunk]) -> list[dict[str, Any]]:
    bound = []
    for case in cases:
        source = case.get("expected_source")
        expected = [
            chunk for chunk in chunks if source and chunk.source_id == demo_id(f"source/{source}")
        ]
        unanswerable = case.get("expected") == "unanswerable" or (
            source is None
            and not case.get("expected_chunk_ids")
            and not case.get("expected_document_ids")
        )
        if source and not expected:
            raise ValueError("Expected source is absent from the calibration corpus.")
        bound.append(
            {
                **case,
                "unanswerable": unanswerable,
                "expected": "unanswerable" if unanswerable else "knowledge",
                "expected_chunk_ids": case.get("expected_chunk_ids")
                or [str(chunk.id) for chunk in expected],
                "expected_document_ids": case.get("expected_document_ids")
                or sorted({str(chunk.document_id) for chunk in expected}),
            }
        )
    return bound


def planned_embedding_texts(settings: Settings) -> list[str]:
    """Use the real demo parser/planner before opening any DB/provider connection."""
    bot = Bot(id=demo_id("bot"), tenant_id=demo_id("tenant"), config={"default_language": "en"})
    texts: list[str] = []
    for key, title, body in FAQS:
        source = Source(id=demo_id(f"source/{key}"), original_name=f"{key}.md", kind="md")
        _, documents = plan_source(
            source,
            parse_text(demo_source_data(key, title, body), source.original_name),
            bot,
            settings,
        )
        texts.extend(
            " ".join(part for part in (c.title, c.heading, c.text) if part)
            for document in documents
            for c in document.chunks
        )
    return texts


def corpus(db: Session, settings: Settings) -> tuple[Bot, list[Chunk]]:
    seed = seed_demo(db, get_storage(settings), settings, FAKE_PASSWORD)
    bot = db.scalar(select(Bot).where(Bot.tenant_id == seed.tenant_id, Bot.id == seed.bot_id))
    assert bot is not None and bot.published_revision_id is not None
    chunks = list(
        db.scalars(
            select(Chunk).where(
                Chunk.tenant_id == seed.tenant_id,
                Chunk.bot_id == seed.bot_id,
                Chunk.revision_id == bot.published_revision_id,
            )
        )
    )
    return bot, chunks


def cache_embeddings(embedder: Embedder, texts: list[str], output: Path) -> CachedEmbedder:
    # No replay: a crash after a started batch requires owner inspection.
    if output.exists() or output.with_suffix(".started").exists():
        raise ValueError(
            "Embedding run already started; inspect saved artifacts before another run."
        )
    vectors = {}
    unique = list(dict.fromkeys(texts))
    output.with_suffix(".started").write_text("Embedding budget reserved; no automatic replay.\n")
    for offset in range(0, len(unique), 16):
        batch_text = unique[offset : offset + 16]
        batch = embedder.embed(batch_text)
        append_record(
            output.with_name("embedding-usage.jsonl"),
            {
                "batch_offset": offset,
                "embedding_model": embedder.identity,
                "tokens": batch.tokens,
                "cost_usd": str(batch.cost_usd) if batch.cost_usd is not None else None,
            },
        )
        for value, vector in zip(batch_text, batch.vectors, strict=True):
            key = text_key(value)
            vectors[key] = vector
            append_record(
                output,
                {
                    "embedding_model": embedder.identity,
                    "text_key": key,
                    "vector": vector,
                },
            )
    return CachedEmbedder(embedder.identity, vectors)


def embed_demo(db: Session, bot: Bot, settings: Settings, cached: CachedEmbedder) -> None:
    job = queue_backfill(db, bot.tenant_id, bot.id, settings, model=cached.identity)
    if job.status != "pending":
        raise ValueError("A backfill is already running; do not steal its lease.")
    # Claim this exact eval job under the Bot/Job locks held by queue_backfill.
    # Never claim an unrelated job from the global queue.
    job.status, job.leased_by = "running", f"owner-eval-{uuid4()}"
    job.attempts += 1
    job.started_at = datetime.now(UTC)
    job.lease_expires_at = datetime.now(UTC) + timedelta(seconds=settings.job_lease_seconds)
    db.commit()
    with patch("app.embeddings.backfill.from_settings", return_value=cached):
        execute_claimed_job(db, job, settings, get_storage(settings))
    if job.status != "succeeded":
        raise ValueError("Eval backfill did not complete; partial progress preserved.")


def evaluate(
    db: Session,
    bot: Bot,
    cases: list[dict[str, Any]],
    settings: Settings,
    cached: CachedEmbedder,
    destination: Path,
) -> dict[str, Any]:
    if destination.exists():
        raise ValueError("Retrieval results already exist; do not overwrite evidence.")
    assert bot.published_revision_id is not None
    by_mode: dict[str, list[dict[str, Any]]] = {}
    with patch("app.retrieval.hybrid.from_settings", return_value=cached):
        for mode in ("fts_only", "hybrid"):
            measured = []
            for case in cases:
                result = retrieve_hybrid(
                    db,
                    tenant_id=bot.tenant_id,
                    bot_id=bot.id,
                    revision_id=bot.published_revision_id,
                    question=case["question"],
                    question_language=case["language"],
                    settings=settings,
                    mode_override=mode,
                )
                if result.mode != mode:
                    raise ValueError(
                        "Requested retrieval mode degraded; inspect saved artifacts before retry."
                    )
                decision = relevance_gate(result, settings)
                expected = set(case["expected_chunk_ids"])
                docs = set(case["expected_document_ids"])

                def signals(chunk: Any) -> dict[str, Any]:
                    return {
                        "chunk_id": str(chunk.chunk_id),
                        "document_id": str(chunk.document_id),
                        "vector_similarity": chunk.vector_similarity,
                        "fts_match": chunk.fts_match,
                        "matched_terms": chunk.matched_terms,
                    }

                first_rank = next(
                    (
                        i
                        for i, c in enumerate(result.candidates, 1)
                        if str(c.chunk_id) in expected or str(c.document_id) in docs
                    ),
                    None,
                )
                row = {
                    **case,
                    "requested_mode": mode,
                    "actual_mode": result.mode,
                    "embedding_model": cached.identity,
                    "gate_passed": bool(decision.passed),
                    "hit_at_k": first_rank is not None,
                    "hit_at_3": first_rank is not None and first_rank <= 3,
                    "reciprocal_rank": 1 / first_rank if first_rank else 0.0,
                    "candidates": [signals(c) for c in result.candidates],
                    "evidence": [signals(c) for c in result.evidence],
                    "applied_language": result.applied_language,
                    "fts_config": "simple" if result.applied_language == "ar" else "english",
                    "generation_measured": False,
                    "rewrite_enabled": False,
                    "translation_enabled": False,
                    "query_embeddings_cached": True,
                }
                append_record(destination, row)
                measured.append(row)
            by_mode[mode] = measured
    return {
        "modes": {mode: summarize(rows) for mode, rows in by_mode.items()},
        "threshold_proposal": threshold_proposal(by_mode["hybrid"]),
        "threshold_sweeps": {mode: threshold_sweep(rows, mode) for mode, rows in by_mode.items()},
    }


def parser() -> argparse.ArgumentParser:
    cli = argparse.ArgumentParser(description=__doc__)
    cli.add_argument("--database-url", required=True)
    cli.add_argument("--output", required=True, type=Path)
    cli.add_argument("--cases", default=DEFAULT_CASES, type=Path)
    return cli


def retrieval_main(*, openai_calibration: bool = False) -> int:
    cli = parser()
    if not openai_calibration:
        cli.add_argument("--test-vectors", action="store_true", required=True)
    args = cli.parse_args()
    cases = load_cases(args.cases)
    planning_settings = Settings.model_construct()
    planned = planned_embedding_texts(planning_settings)
    texts = planned + [case["question"] for case in cases]
    estimate = estimate_calibration(texts, enforce=False)
    print(json.dumps({**estimate, "real_calls_enabled": openai_calibration}), flush=True)
    estimate_calibration(texts)  # abort before filesystem, DB or provider activity
    if len(planned) < 40:
        raise ValueError("Calibration requires at least 40 demo chunks.")
    options: dict[str, Any] = {
        "_env_file": None,
        "environment": "test",
        "database_url": args.database_url,
        "storage_root": str(args.output / "storage"),
        "embedding_test_stub": not openai_calibration,
        "embedding_provider": "openai",
        "embedding_model": "text-embedding-3-large",
        "embedding_dimensions": 1024,
        "chunk_size": planning_settings.chunk_size,
        "chunk_overlap": planning_settings.chunk_overlap,
        "retrieval_top_k": 8,
        "retrieval_final_k": 4,
    }
    settings = Settings(**options)
    if openai_calibration and not settings.chat_openai_api_key:
        raise ValueError("CHAT_OPENAI_API_KEY must be set in the process environment.")
    args.output.mkdir(parents=True, exist_ok=True)
    if (args.output / "embedding-cache.jsonl").exists() or (
        args.output / "embedding-cache.started"
    ).exists():
        raise ValueError(
            "Embedding run already started; inspect saved artifacts before another run."
        )
    prepare_database(args.database_url)
    engine = create_db_engine(settings)
    try:
        with session_factory(engine)() as db:
            bot, chunks = corpus(db, settings)
            actual = [" ".join(p for p in (c.title, c.heading, c.text) if p) for c in chunks]
            if sorted(actual) != sorted(planned):
                raise ValueError(
                    "Database demo differs from expanded corpus; use a fresh disposable _test DB."
                )
            bound = bind_cases(cases, chunks)  # validate every label before spending
            embedder = (
                from_settings(settings)
                if openai_calibration
                else TestHashEmbedder(configured_identity(settings))
            )
            cached = cache_embeddings(embedder, texts, args.output / "embedding-cache.jsonl")
            embed_demo(db, bot, settings, cached)
            for case in bound:
                append_record(args.output / "bound-cases.jsonl", case)
            metrics = evaluate(
                db, bot, bound, settings, cached, args.output / "retrieval-results.jsonl"
            )
            metrics.update(
                embedding_model=cached.identity,
                synthetic_vectors=not openai_calibration,
                estimate=estimate,
                chat_requests_used=0,
                corpus_chunks=len(chunks),
                eval_cases=len(bound),
                embedding_usage=[
                    json.loads(line)
                    for line in (args.output / "embedding-usage.jsonl")
                    .read_text(encoding="utf-8")
                    .splitlines()
                ],
                fts_configs={"ar": "simple on normalized fts_simple", "en": "english on fts_en"},
                retrieval_results=[
                    json.loads(line)
                    for line in (args.output / "retrieval-results.jsonl")
                    .read_text(encoding="utf-8")
                    .splitlines()
                ],
            )
            recommendation = metrics["threshold_sweeps"]["hybrid"]["recommended"]
            floor = recommendation["cosine_floor"]
            metrics["recommended_threshold_set"] = {
                "RETRIEVAL_VECTOR_FLOORS": {cached.identity: floor} if floor is not None else {},
                "RETRIEVAL_MIN_FTS_MATCH": recommendation["fts_floor"],
                "RETRIEVAL_MIN_MATCHED_TERMS": recommendation["min_matched_terms"],
                "status": "UNTUNED, pending owner calibration review; not automatically applied",
            }
            (args.output / "calibration-results.json").write_text(
                json.dumps(metrics, indent=2, ensure_ascii=False), encoding="utf-8"
            )
            print(
                json.dumps({k: v for k, v in metrics.items() if k != "retrieval_results"}, indent=2)
            )
            print(f"Paste back: {args.output / 'calibration-results.json'}")
    finally:
        engine.dispose()
    return 0


def generation_main() -> int:
    cli = parser()
    cli.add_argument("--mode", choices=("fts_only", "hybrid"), default="fts_only")
    cli.add_argument("--embedding-cache", type=Path)
    cli.add_argument("--baseline-results", type=Path, required=True)
    cli.add_argument("--resume", action="store_true")
    cli.add_argument("--calibration-results", type=Path)
    args = cli.parse_args()
    args.output.mkdir(parents=True, exist_ok=True)
    journal, results = args.output / "questions.jsonl", args.output / "generation-results.jsonl"
    if journal.exists() and not args.resume:
        raise ValueError("Generation already started; explicit --resume skips every started case.")
    saved = (
        [json.loads(line) for line in results.read_text(encoding="utf-8").splitlines()]
        if results.exists()
        else []
    )
    if any(
        row["status"] in {"quota_or_rate_limit", "provider_authorization_failed"} for row in saved
    ):
        raise ValueError("Previous quota/auth stop remains pending; no automatic retry.")
    skipped = started_ids(journal)
    for line in args.baseline_results.read_text(encoding="utf-8").splitlines():
        baseline_row = json.loads(line)
        if baseline_row["status"] == "completed":
            skipped.add(baseline_row["id"])
    key, chain = load_credentials()
    cases = load_cases(args.cases)
    options: dict[str, Any] = {
        "_env_file": None,
        "environment": "test",
        "database_url": args.database_url,
        "storage_root": str(args.output / "storage"),
        "chat_rewrite_enabled": False,
    }
    if args.calibration_results:
        calibration = json.loads(args.calibration_results.read_text(encoding="utf-8"))
        if calibration["synthetic_vectors"]:
            raise ValueError("Real generation requires real calibration vectors.")
        recommendation = calibration["recommended_threshold_set"]
        options.update(
            retrieval_vector_floors=recommendation["RETRIEVAL_VECTOR_FLOORS"],
            retrieval_min_fts_match=recommendation["RETRIEVAL_MIN_FTS_MATCH"],
            retrieval_min_matched_terms=recommendation["RETRIEVAL_MIN_MATCHED_TERMS"],
        )
    settings = Settings(**options)
    prepare_database(args.database_url)
    engine = create_db_engine(settings)
    transport = CappedChatTransport(args.output / "requests.jsonl")
    try:
        with (
            session_factory(engine)() as db,
            httpx.Client(
                headers={"Authorization": f"Bearer {key}"},
                timeout=25,
                transport=transport,
                follow_redirects=False,
            ) as client,
        ):
            bot, chunks = corpus(db, settings)
            cached = (
                read_cache(args.embedding_cache, bot.active_embedding_model or "")
                if args.embedding_cache
                else CachedEmbedder("unused", {})
            )
            if args.mode == "hybrid" and not args.embedding_cache:
                raise ValueError(
                    "Hybrid generation checks require cached embeddings; no live embedding calls."
                )
            for case in bind_cases(cases, chunks):
                if case["id"] in skipped:
                    continue
                if transport.used >= 40:
                    break
                append_record(journal, {"id": case["id"], "event": "started"})
                model, start = BudgetModel(client, chain), time.perf_counter()
                requests_before = transport.used
                row: dict[str, Any] = {
                    **case,
                    "status": "interrupted",
                    "answer": None,
                    "citations": [],
                }
                try:

                    def retrieval(*positional: Any, **keywords: Any) -> Any:
                        keywords["mode_override"] = args.mode
                        keywords["translate_query"] = None
                        return retrieve_hybrid(*positional, **keywords)

                    with (
                        patch("app.chat.service.retrieve", side_effect=retrieval),
                        patch("app.retrieval.hybrid.from_settings", return_value=cached),
                    ):
                        reply = chat_answer(
                            db,
                            tenant_id=bot.tenant_id,
                            bot=bot,
                            question=case["question"],
                            history=case.get("history", []),
                            model=model,
                            settings=settings,
                        )
                    trace_chunks = reply.trace.get("chunks", [])
                    accepted = (
                        {item["chunk_id"] for item in trace_chunks if item["accepted"]}
                        if isinstance(trace_chunks, list)
                        else set()
                    )
                    row.update(
                        status="completed",
                        answer=reply.answer,
                        citations=reply.citations,
                        can_answer=reply.can_answer,
                        citations_valid=(
                            bool(reply.citations)
                            and all(c["chunk_id"] in accepted for c in reply.citations)
                        )
                        if reply.can_answer
                        else None,
                        refusal_correct=(not reply.can_answer) if case["unanswerable"] else None,
                        wrong_refusal=(not reply.can_answer) if not case["unanswerable"] else None,
                        internals_leak=bool(LEAK_PATTERN.search(reply.answer)),
                    )
                except StopBaseline as error:
                    row["status"] = error.status
                finally:
                    row.update(
                        model_used=model.model_used,
                        requests_used=transport.used - requests_before,
                        latency_ms=round((time.perf_counter() - start) * 1000),
                        raw_completion=model.raw_completion,
                    )
                    append_record(results, row, secret=key)
                if row["status"] != "completed":
                    return 2
            print(json.dumps({"requests_reserved": transport.used, "cap": 40}))
    finally:
        engine.dispose()
    return 0


if __name__ == "__main__":
    raise SystemExit(retrieval_main())
