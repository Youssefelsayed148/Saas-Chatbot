"""Ingest pipeline job handler (docs/08, docs/14 §3–§5).

parse → chunk → dedupe by content hash → write into a draft revision.

A job NEVER touches a published revision: work happens in the bot's draft
revision (a snapshot copy of the published content when one exists) and the
publish endpoint performs the atomic pointer swap. Re-ingesting an unchanged
source is a no-op (identical planned documents + chunks are detected and left
as-is). The job re-validates tenant + bot before doing anything; a bot of
another tenant (or any missing resource) fails the job permanently.
"""

from collections.abc import Callable
from multiprocessing import get_context
from queue import Empty
from typing import Any, cast
from uuid import UUID

from sqlalchemy import delete, func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session as OrmSession

from app.core.config import Settings
from app.db.models import (
    Bot,
    Chunk,
    Document,
    Job,
    KnowledgeRevision,
    Source,
    SourcePage,
    Tenant,
)
from app.knowledge.chunking import split_text
from app.knowledge.csv_qa import parse_qa_csv
from app.knowledge.language import content_hash, detect_language, normalise_text
from app.knowledge.parsers import ParseLimits, parse_docx, parse_pdf, parse_text
from app.knowledge.parsing import ParsedPage, ParsedSection, ParseError
from app.knowledge.storage import Storage
from app.quotas.service import limits_for, lock_tenant


class JobFatal(Exception):
    """The job cannot run against this tenant/bot; it must fail permanently."""


# --- parsing -------------------------------------------------------------


def parse_limits_from(settings: Settings) -> ParseLimits:
    return ParseLimits(
        max_pdf_pages=settings.max_pdf_pages,
        max_docx_uncompressed_bytes=settings.max_docx_uncompressed_bytes,
        max_docx_zip_ratio=settings.max_docx_zip_ratio,
    )


def _parse_payload(
    kind: str, original_name: str, data: bytes, limits: ParseLimits
) -> list[ParsedPage]:
    """Parse one stored source by its kind (docs/14 §3)."""
    if kind == "pdf":
        return parse_pdf(data, original_name, limits)
    if kind == "docx":
        return parse_docx(data, original_name, limits)
    if kind in ("txt", "md"):
        return parse_text(data, original_name)
    if kind == "qa_csv":
        result = parse_qa_csv(data)
        if result.valid_rows == 0:
            first = result.errors[0]["reason"] if result.errors else "no valid rows"
            raise ParseError(f"No valid Q&A rows (first problem: {first}).")
        sections = [
            ParsedSection(
                heading=row.topic,
                text=f"Q: {row.question}\nA: {row.answer}",
                language=None,
                priority=row.priority,
                ref=f"Row {index}",
            )
            for index, row in enumerate(result.rows, start=1)
        ]
        return [
            ParsedPage(
                page_number=None,
                title=original_name,
                text="\n\n".join(section.text for section in sections),
                sections=sections,
            )
        ]
    raise ParseError("Unsupported source kind.")  # pragma: no cover


def _parse_process_entry(
    output: Any,
    parser: Callable[[str, str, bytes, ParseLimits], list[ParsedPage]],
    kind: str,
    original_name: str,
    data: bytes,
    limits: ParseLimits,
) -> None:
    """Spawn target. It receives bytes only; it has no database or storage handles."""
    try:
        result = parser(kind, original_name, data, limits)
        output.put(("ok", result))
    except ParseError as error:
        output.put(("parse_error", error.message))
    except Exception:
        output.put(("unexpected", None))


def parse_source(
    source: Source,
    data: bytes,
    settings: Settings,
    *,
    parser: Callable[[str, str, bytes, ParseLimits], list[ParsedPage]] = _parse_payload,
) -> list[ParsedPage]:
    """Parse in an isolated subprocess that is killed at the wall-clock limit."""
    context = get_context("spawn")
    output = context.Queue(maxsize=1)
    process = context.Process(
        target=_parse_process_entry,
        args=(output, parser, source.kind, source.original_name, data, parse_limits_from(settings)),
        daemon=True,
    )
    process.start()
    try:
        try:
            status, result = output.get(timeout=settings.parse_timeout_seconds)
        except Empty as error:
            if process.is_alive():
                process.terminate()
                process.join(timeout=1)
            if process.is_alive():
                process.kill()
                process.join()
            raise ParseError("Parsing timed out; the file is too complex to process.") from error
        process.join(timeout=1)
        if process.is_alive():
            process.terminate()
            process.join()
        if status == "parse_error":
            raise ParseError(str(result))
        if status != "ok":
            raise ParseError("The file could not be processed.")
        return cast(list[ParsedPage], result)
    finally:
        if process.is_alive():
            process.terminate()
            process.join(timeout=1)
        output.cancel_join_thread()
        output.close()


# --- planning ------------------------------------------------------------


class PagePlan:
    """Planned ``source_pages`` row."""

    __slots__ = ("page_number", "title", "source_url", "page_type", "language", "raw_text")

    def __init__(
        self,
        page_number: int | None,
        title: str,
        source_url: str | None,
        page_type: str | None,
        language: str,
        raw_text: str,
    ) -> None:
        self.page_number = page_number
        self.title = title
        self.source_url = source_url
        self.page_type = page_type
        self.language = language
        self.raw_text = raw_text


class ChunkPlanRow:
    """Planned ``chunks`` row."""

    __slots__ = (
        "title",
        "heading",
        "text",
        "text_norm",
        "language",
        "priority",
        "content_hash",
        "ordinal",
    )

    def __init__(
        self,
        title: str,
        heading: str | None,
        text: str,
        text_norm: str,
        language: str,
        priority: int,
        content_hash: str,
        ordinal: int,
    ) -> None:
        self.title = title
        self.heading = heading
        self.text = text
        self.text_norm = text_norm
        self.language = language
        self.priority = priority
        self.content_hash = content_hash
        self.ordinal = ordinal


class DocumentPlan:
    """Planned ``documents`` row with its planned chunks."""

    __slots__ = (
        "ordinal",
        "title",
        "heading",
        "source_url",
        "page_ref",
        "language",
        "priority",
        "text",
        "total_chars",
        "chunks",
    )

    def __init__(
        self,
        ordinal: int,
        title: str,
        heading: str | None,
        source_url: str | None,
        page_ref: str,
        language: str,
        priority: int,
        text: str,
        total_chars: int,
        chunks: list[ChunkPlanRow],
    ) -> None:
        self.ordinal = ordinal
        self.title = title
        self.heading = heading
        self.source_url = source_url
        self.page_ref = page_ref
        self.language = language
        self.priority = priority
        self.text = text
        self.total_chars = total_chars
        self.chunks = chunks


def _fallback_language(bot: Bot) -> str:
    configured = bot.config.get("default_language")
    return configured if configured in ("en", "ar") else "en"


def plan_source(
    source: Source,
    pages: list[ParsedPage],
    bot: Bot,
    settings: Settings,
) -> tuple[list[PagePlan], list[DocumentPlan]]:
    """Turn parsed pages into planned source_pages/documents/chunks (§3, §4)."""
    page_plans: list[PagePlan] = []
    document_plans: list[DocumentPlan] = []
    seen_hashes: set[str] = set()
    fallback = _fallback_language(bot)

    for page in pages:
        page_language = (
            page.language
            if page.language in ("en", "ar")
            else detect_language(page.text) or fallback
        )
        page_plans.append(
            PagePlan(
                page_number=page.page_number,
                title=page.title,
                source_url=page.source_url,
                page_type=page.page_type,
                language=page_language,
                raw_text=page.text,
            )
        )
        for section_index, section in enumerate(page.sections, start=1):
            text = section.text
            if not text:
                continue
            document_language = (
                section.language or page.language or detect_language(text) or fallback
            )
            priority = section.priority if section.priority is not None else 0
            page_ref = section.ref or (
                f"Page {page.page_number}"
                if page.page_number is not None
                else f"Section {section_index}"
            )
            # Q&A rows become ONE chunk, never split (docs/14 §3).
            if source.kind == "qa_csv":
                chunk_texts = [text]
            else:
                chunk_texts = split_text(text, settings.chunk_size, settings.chunk_overlap)
            planned_chunks: list[ChunkPlanRow] = []
            for chunk_ordinal, chunk_text in enumerate(chunk_texts):
                # Indexed text = title + heading + text (docs/14 §4); the
                # Arabic side stores its normalised form in text_norm, which
                # feeds the GIN-indexed fts_simple column.
                indexed_text = " ".join(
                    part for part in (page.title, section.heading or "", chunk_text) if part
                )
                normalised = normalise_text(indexed_text)
                digest = content_hash(normalised)
                if digest in seen_hashes:
                    # Identical chunk text is stored once per source (§3).
                    continue
                seen_hashes.add(digest)
                planned_chunks.append(
                    ChunkPlanRow(
                        title=page.title,
                        heading=section.heading,
                        text=chunk_text,
                        text_norm=normalised,
                        language=section.language
                        or page.language
                        or detect_language(chunk_text)
                        or detect_language(text)
                        or fallback,
                        priority=priority,
                        content_hash=digest,
                        ordinal=chunk_ordinal,
                    )
                )
            if not planned_chunks:
                continue
            document_plans.append(
                DocumentPlan(
                    ordinal=len(document_plans),
                    title=page.title,
                    heading=section.heading,
                    source_url=page.source_url,
                    page_ref=page_ref,
                    language=document_language,
                    priority=priority,
                    text=text,
                    total_chars=len(text),
                    chunks=planned_chunks,
                )
            )
    return page_plans, document_plans


# --- revisions -----------------------------------------------------------


def get_or_create_draft_revision(
    db: OrmSession, bot: Bot, created_by: UUID | None
) -> KnowledgeRevision:
    """Exactly one draft revision per bot; a new draft copies the published snapshot."""
    draft = db.execute(
        select(KnowledgeRevision).where(
            KnowledgeRevision.tenant_id == bot.tenant_id,
            KnowledgeRevision.bot_id == bot.id,
            KnowledgeRevision.status == "draft",
        )
    ).scalar_one_or_none()
    if draft is not None:
        return draft
    revision = KnowledgeRevision(
        tenant_id=bot.tenant_id,
        bot_id=bot.id,
        status="draft",
        created_by=created_by,
    )
    db.add(revision)
    try:
        db.flush()
    except IntegrityError:
        # A concurrent ingest created the draft first; reuse it.
        db.rollback()
        draft = db.execute(
            select(KnowledgeRevision).where(
                KnowledgeRevision.tenant_id == bot.tenant_id,
                KnowledgeRevision.bot_id == bot.id,
                KnowledgeRevision.status == "draft",
            )
        ).scalar_one()
        return draft
    if bot.published_revision_id is not None:
        _copy_revision_snapshot(
            db, bot, from_revision_id=bot.published_revision_id, to_revision_id=revision.id
        )
    db.flush()
    return revision


def _copy_revision_snapshot(
    db: OrmSession, bot: Bot, *, from_revision_id: UUID, to_revision_id: UUID
) -> None:
    """Duplicate every document and chunk of one revision into another."""
    documents = (
        db.execute(
            select(Document)
            .where(Document.tenant_id == bot.tenant_id, Document.revision_id == from_revision_id)
            .order_by(Document.ordinal, Document.created_at)
        )
        .scalars()
        .all()
    )
    id_map: dict[UUID, Document] = {}
    for document in documents:
        clone = Document(
            tenant_id=document.tenant_id,
            bot_id=document.bot_id,
            revision_id=to_revision_id,
            source_id=document.source_id,
            title=document.title,
            heading=document.heading,
            source_url=document.source_url,
            page_ref=document.page_ref,
            ordinal=document.ordinal,
            language=document.language,
            priority=document.priority,
            text=document.text,
            total_chars=document.total_chars,
        )
        db.add(clone)
        id_map[document.id] = clone
    db.flush()
    chunks = (
        db.execute(
            select(Chunk)
            .where(Chunk.tenant_id == bot.tenant_id, Chunk.revision_id == from_revision_id)
            .order_by(Chunk.created_at)
        )
        .scalars()
        .all()
    )
    for chunk in chunks:
        db.add(
            Chunk(
                tenant_id=chunk.tenant_id,
                bot_id=chunk.bot_id,
                revision_id=to_revision_id,
                source_id=chunk.source_id,
                document_id=id_map[chunk.document_id].id,
                title=chunk.title,
                heading=chunk.heading,
                text=chunk.text,
                text_norm=chunk.text_norm,
                language=chunk.language,
                priority=chunk.priority,
                content_hash=chunk.content_hash,
                ordinal=chunk.ordinal,
            )
        )
    db.flush()


# --- per-source processing ------------------------------------------------


def _existing_state(
    db: OrmSession, revision_id: UUID, source_id: UUID
) -> tuple[list[tuple[object, ...]], list[tuple[object, ...]]]:
    documents = (
        db.execute(
            select(Document)
            .where(Document.revision_id == revision_id, Document.source_id == source_id)
            .order_by(Document.ordinal, Document.id)
        )
        .scalars()
        .all()
    )
    doc_rows: list[tuple[object, ...]] = [
        (
            document.ordinal,
            document.title,
            document.heading,
            document.source_url,
            document.page_ref,
            document.language,
            document.priority,
            document.text,
            document.total_chars,
        )
        for document in documents
    ]
    chunk_rows: list[tuple[object, ...]] = []
    rows = db.execute(
        select(Chunk, Document.ordinal)
        .join(Document, Chunk.document_id == Document.id)
        .where(Chunk.revision_id == revision_id, Chunk.source_id == source_id)
        .order_by(Document.ordinal, Chunk.ordinal, Chunk.id)
    ).all()
    for chunk, _document_ordinal in rows:
        chunk_rows.append(
            (
                chunk.title,
                chunk.heading,
                chunk.text,
                chunk.text_norm,
                chunk.language,
                chunk.priority,
                chunk.content_hash,
                chunk.ordinal,
            )
        )
    return doc_rows, chunk_rows


def _planned_state(
    document_plans: list[DocumentPlan],
) -> tuple[list[tuple[object, ...]], list[tuple[object, ...]]]:
    doc_rows: list[tuple[object, ...]] = [
        (
            plan.ordinal,
            plan.title,
            plan.heading,
            plan.source_url,
            plan.page_ref,
            plan.language,
            plan.priority,
            plan.text,
            plan.total_chars,
        )
        for plan in document_plans
    ]
    chunk_rows: list[tuple[object, ...]] = [
        (
            chunk.title,
            chunk.heading,
            chunk.text,
            chunk.text_norm,
            chunk.language,
            chunk.priority,
            chunk.content_hash,
            chunk.ordinal,
        )
        for plan in document_plans
        for chunk in plan.chunks
    ]
    return doc_rows, chunk_rows


def process_source(
    db: OrmSession,
    bot: Bot,
    source: Source,
    revision: KnowledgeRevision,
    settings: Settings,
    storage: Storage,
) -> str | None:
    """Ingest one source into the draft revision. Returns an error message or None."""
    try:
        data = storage.open(source.storage_key)
    except (FileNotFoundError, ValueError):
        source.status = "failed"
        source.error = "The stored file could not be found."
        db.commit()
        return "The stored file could not be found."
    try:
        pages = parse_source(source, data, settings)
    except ParseError as error:
        source.status = "failed"
        source.error = error.message
        db.commit()
        return error.message
    except Exception:  # noqa: BLE001 - untrusted input must never crash the job
        source.status = "failed"
        source.error = "The file could not be processed."
        db.commit()
        return "The file could not be processed."

    page_plans, document_plans = plan_source(source, pages, bot, settings)
    if not document_plans:
        source.status = "failed"
        source.error = "No readable text was found in the file."
        db.commit()
        return "No readable text was found in the file."

    tenant = lock_tenant(db, source.tenant_id)
    existing_pages = int(
        db.execute(
            select(func.count())
            .select_from(SourcePage)
            .where(SourcePage.tenant_id == source.tenant_id, SourcePage.bot_id == bot.id)
        ).scalar_one()
    )
    old_source_pages = int(
        db.execute(
            select(func.count()).select_from(SourcePage).where(SourcePage.source_id == source.id)
        ).scalar_one()
    )
    page_limit = limits_for(tenant).pages_per_bot
    if existing_pages - old_source_pages + len(page_plans) > page_limit:
        source.status = "failed"
        source.error = (
            f"This file would exceed the PLACEHOLDER plan limit of {page_limit} "
            "knowledge pages per bot."
        )
        db.commit()
        return source.error

    # Unchanged re-ingest is a no-op (docs/14 §3).
    planned_docs, planned_chunks = _planned_state(document_plans)
    existing_docs, existing_chunks = _existing_state(db, revision.id, source.id)
    if planned_docs == existing_docs and planned_chunks == existing_chunks:
        source.status = "ingested"
        source.error = None
        db.commit()
        return None

    db.execute(delete(Chunk).where(Chunk.revision_id == revision.id, Chunk.source_id == source.id))
    db.execute(
        delete(Document).where(Document.revision_id == revision.id, Document.source_id == source.id)
    )
    db.execute(delete(SourcePage).where(SourcePage.source_id == source.id))
    db.flush()

    db.add_all(
        SourcePage(
            tenant_id=source.tenant_id,
            bot_id=source.bot_id,
            source_id=source.id,
            page_number=plan.page_number,
            title=plan.title,
            source_url=plan.source_url,
            page_type=plan.page_type,
            language=plan.language,
            raw_text=plan.raw_text,
        )
        for plan in page_plans
    )
    for plan in document_plans:
        document = Document(
            tenant_id=source.tenant_id,
            bot_id=source.bot_id,
            revision_id=revision.id,
            source_id=source.id,
            title=plan.title,
            heading=plan.heading,
            source_url=plan.source_url,
            page_ref=plan.page_ref,
            ordinal=plan.ordinal,
            language=plan.language,
            priority=plan.priority,
            text=plan.text,
            total_chars=plan.total_chars,
        )
        db.add(document)
        # Documents must exist before their chunks (composite FK) resolves.
        db.flush()
        db.add_all(
            Chunk(
                tenant_id=source.tenant_id,
                bot_id=source.bot_id,
                revision_id=revision.id,
                source_id=source.id,
                document_id=document.id,
                title=chunk.title,
                heading=chunk.heading,
                text=chunk.text,
                text_norm=chunk.text_norm,
                language=chunk.language,
                priority=chunk.priority,
                content_hash=chunk.content_hash,
                ordinal=chunk.ordinal,
            )
            for chunk in plan.chunks
        )
    source.status = "ingested"
    source.error = None
    db.commit()
    return None


# --- job entry point ------------------------------------------------------


def run_ingest_batch(
    job: Job,
    db: OrmSession,
    settings: Settings,
    storage: Storage,
    *,
    worker: bool = True,
) -> str | None:
    """handler for ``ingest_batch``. Returns an error message or None for success."""
    # Re-validate tenant + bot before acting on the payload (docs/06).
    tenant = db.get(Tenant, job.tenant_id)
    bot = db.get(Bot, job.bot_id)
    if tenant is None or tenant.status != "active":
        raise JobFatal("Tenant missing or archived; the job cannot run.")
    if bot is None or bot.tenant_id != job.tenant_id:
        raise JobFatal("Bot missing or not owned by this tenant; the job cannot run.")
    if bot.status == "archived":
        raise JobFatal("The bot is archived; ingest again after unarchiving.")

    draft_revision = get_or_create_draft_revision(db, bot, job.created_by)
    db.commit()

    payload = job.payload if isinstance(job.payload, dict) else {}
    raw_list = payload.get("source_ids")
    source_ids = raw_list if isinstance(raw_list, list) else []
    failures: list[str] = []
    ingested = 0
    for raw_id in source_ids:
        db.refresh(job)  # see a cancel request issued mid-run
        if job.cancel_requested:
            break
        try:
            source_id = raw_id if isinstance(raw_id, UUID) else UUID(str(raw_id))
        except (ValueError, TypeError):
            failures.append("A queued source id is invalid.")
            continue
        source = db.get(Source, source_id)
        if source is None or source.tenant_id != job.tenant_id or source.bot_id != job.bot_id:
            failures.append("A queued source does not belong to this bot or no longer exists.")
            continue
        error = process_source(db, bot, source, draft_revision, settings, storage)
        if error is None:
            ingested += 1
        else:
            failures.append(error)
    if ingested == 0 and failures:
        return "; ".join(failures[:3]) if failures else "All sources failed."
    return None
