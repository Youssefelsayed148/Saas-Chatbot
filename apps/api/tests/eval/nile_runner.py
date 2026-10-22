"""DB-backed runner for the Nile eval (B.4): fts_only and hybrid, stub or real model.

Ingests the frozen PDFs through the real pipeline into a disposable bot, then
answers every case in ``nile_eval.jsonl`` through the real chat pipeline in each
requested retrieval mode and returns plain verdicts (see ``nile_metrics``).

Safety: needs the disposable test database like every other test. The stub model
and the deterministic test embedder make no network call. The real-model option
only reads the owner's key from the process environment (never a file).

Hybrid caveat: the test embedder is a deterministic token-hash, not a semantic
model, so a stub-embedding hybrid run proves the plumbing and the gate mechanics
only. Real-embedding hybrid vs fts_only is measured on the owner's stack (the
playground trace now shows cosine, terms and the gate rule per chunk).
"""

from pathlib import Path
from typing import Any
from uuid import UUID

from fastapi import FastAPI
from sqlalchemy import select, update
from sqlalchemy.orm import Session as OrmSession

from app.chat.providers import ChatModel, ExtractiveStubModel
from app.chat.service import chat_answer
from app.core.config import Settings
from app.db.models import Bot, Chunk
from app.embeddings.providers import TestHashEmbedder
from tests.eval import nile_metrics
from tests.eval.nile_metrics import judge_case, locate_source
from tests.knowledge_helpers import publish_draft, start_ingestion, upload_sources
from tests.retrieval_helpers import published_revision_id, retrieval_settings

CORPUS_DIR = nile_metrics.EVAL_DIR / "corpus"
EMBEDDING_IDENTITY = "openai:text-embedding-3-large"
MODES = ("fts_only", "hybrid")


def corpus_files() -> list[tuple[str, bytes]]:
    return [(path.name, path.read_bytes()) for path in sorted(CORPUS_DIR.glob("*.pdf"))]


def seed_nile_bot(app: FastAPI, db: OrmSession, tmp_root: Path) -> dict[str, Any]:
    from app.core.config import get_settings
    from app.db.session import get_engine
    from tests.helpers import make_bot, seeded_tenant
    from tests.knowledge_helpers import run_jobs_to_completion

    app.dependency_overrides[get_settings] = lambda: retrieval_settings(storage_root=str(tmp_root))
    users = seeded_tenant(app, db, prefix="nile")
    bot = make_bot(users, "Nile bot")
    upload = upload_sources(users, str(bot["id"]), corpus_files(), tmp_root)
    assert upload.status_code == 201, upload.text
    start = start_ingestion(users, str(bot["id"]))
    assert start.status_code == 202, start.text
    run_jobs_to_completion(get_engine(), tmp_root, db)
    db.expire_all()
    publish_draft(users, str(bot["id"]))
    db.expire_all()
    return {"users": users, "bot_id": str(bot["id"])}


def prepare_hybrid(db: OrmSession, seeded: dict[str, Any]) -> int:
    """Embed the bot's published chunks with the deterministic test embedder."""
    users, bot_id = seeded["users"], UUID(seeded["bot_id"])
    chunks = list(
        db.scalars(select(Chunk).where(Chunk.tenant_id == users.tenant_id, Chunk.bot_id == bot_id))
    )
    embedder = TestHashEmbedder(EMBEDDING_IDENTITY)
    vectors = embedder.embed([chunk.text for chunk in chunks]).vectors
    for chunk, vector in zip(chunks, vectors, strict=True):
        chunk.embedding = vector
        chunk.embedding_model = EMBEDDING_IDENTITY
        chunk.embedding_dim = 1024
    db.execute(
        update(Bot)
        .where(Bot.tenant_id == users.tenant_id, Bot.id == bot_id)
        .values(embedding_ready=True, active_embedding_model=EMBEDDING_IDENTITY)
    )
    db.commit()
    return len(chunks)


def set_mode(db: OrmSession, seeded: dict[str, Any], mode: str) -> None:
    users = seeded["users"]
    db.execute(
        update(Bot)
        .where(Bot.tenant_id == users.tenant_id, Bot.id == UUID(seeded["bot_id"]))
        .values(retrieval_mode=mode)
    )
    db.commit()


def _facts(reply: Any) -> dict[str, Any]:
    trace = reply.trace if isinstance(reply.trace, dict) else {}
    accepted: list[tuple[str, int]] = []
    for row in trace.get("chunks", []) or []:
        if row.get("accepted"):
            located = locate_source(str(row.get("title", "")), str(row.get("locator", "")))
            if located:
                accepted.append(located)
    cited = []
    for citation in reply.citations:
        located = locate_source(str(citation.get("title", "")), str(citation.get("page_ref", "")))
        if located:
            cited.append(located)
    mode = str(trace.get("retrieval_mode", ""))
    if trace.get("degradation_reason"):
        mode = f"{mode} ({trace['degradation_reason']})"
    return {
        "kind": reply.kind,
        "can_answer": reply.can_answer,
        "answer": reply.answer,
        "cited": cited,
        "accepted": accepted,
        "error": reply.kind == "busy" or bool(trace.get("provider_error")),
        "mode_effective": mode,
    }


def run_cases(
    db: OrmSession,
    seeded: dict[str, Any],
    cases: list[dict[str, Any]],
    *,
    model: ChatModel | None,
    settings: Settings,
) -> list[dict[str, Any]]:
    users = seeded["users"]
    revision = UUID(published_revision_id(db, users.tenant_id, seeded["bot_id"]))
    verdicts = []
    for case in cases:
        bot = Bot(
            id=UUID(seeded["bot_id"]),
            tenant_id=users.tenant_id,
            name="Nile bot",
            status="active",
            published_revision_id=revision,
            config={
                "assistant_name": "Nile assistant",
                "business_name": "NileCart",
                "support_email": "support@nilecart.example",
            },
        )
        reply = chat_answer(
            db,
            tenant_id=users.tenant_id,
            bot=bot,
            question=case["question"],
            history=list(case["history"]),
            model=model or ExtractiveStubModel(),
            settings=settings,
        )
        verdicts.append(judge_case(case, _facts(reply)))
    return verdicts


def run_nile(
    app: FastAPI,
    db: OrmSession,
    tmp_root: Path,
    *,
    modes: tuple[str, ...] = MODES,
    model: ChatModel | None = None,
    settings_overrides: dict[str, Any] | None = None,
) -> dict[str, list[dict[str, Any]]]:
    seeded = seed_nile_bot(app, db, tmp_root)
    cases = nile_metrics.load_cases()
    settings = retrieval_settings(storage_root=str(tmp_root), **(settings_overrides or {}))
    if "hybrid" in modes:
        assert prepare_hybrid(db, seeded) > 0
    results: dict[str, list[dict[str, Any]]] = {}
    for mode in modes:
        set_mode(db, seeded, mode)
        results[mode] = run_cases(db, seeded, cases, model=model, settings=settings)
    return results
