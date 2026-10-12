"""Knowledge endpoints (P2-02/03): sources, uploads, ingestion, jobs,
documents, revisions, publish/rollback.

Roles (docs/06): uploads/ingest/retry/cancel = editor+; publish/rollback =
admin+; reads = member. Every write requires CSRF. Hidden resources are 404
(unknown ids and other tenants' ids are indistinguishable by design).
"""

from typing import Annotated, Any
from uuid import UUID

from fastapi import APIRouter, Depends, File, Query, Response, UploadFile

from app.auth import cookies
from app.core.config import Settings, get_settings
from app.core.tenancy import TenantContextDep
from app.db.models import Job
from app.knowledge import schemas, service
from app.knowledge.storage import LocalStorage

router = APIRouter(prefix="/api/v1/tenants/{tenant_id}/bots/{bot_id}")

CsrfOk = Annotated[None, Depends(cookies.require_csrf)]


def _sources_out(rows: Any) -> list[schemas.SourceOut]:
    return [schemas.SourceOut.model_validate(row) for row in rows]


def _job_out(job: Job) -> schemas.JobOut:
    payload = job.payload if isinstance(job.payload, dict) else {}
    raw_list = payload.get("source_ids")
    source_ids_value: list[object] = raw_list if isinstance(raw_list, list) else []
    return schemas.JobOut(
        id=job.id,
        status=job.status,
        type=job.type,
        source_ids=[UUID(value) for value in source_ids_value if isinstance(value, str)],
        attempts=job.attempts,
        max_attempts=job.max_attempts,
        error=job.error,
        cancel_requested=job.cancel_requested,
        run_at=job.run_at,
        started_at=job.started_at,
        finished_at=job.finished_at,
        created_at=job.created_at,
    )


# --- sources and uploads -----------------------------------------------------


@router.get("/sources", response_model=list[schemas.SourceOut])
def list_sources(
    tenant_id: UUID, bot_id: UUID, context: TenantContextDep
) -> list[schemas.SourceOut]:
    return _sources_out(service.list_sources(context, bot_id))


@router.get("/sources/qa-template")
def download_qa_template(tenant_id: UUID, bot_id: UUID, context: TenantContextDep) -> Response:
    context.require_role("editor")
    return Response(
        content=service.qa_template(),
        media_type="text/csv; charset=utf-8",
        headers={"Content-Disposition": 'attachment; filename="qa-template.csv"'},
    )


@router.post("/sources/files", response_model=list[schemas.SourceOut], status_code=201)
def upload_sources(
    tenant_id: UUID,
    bot_id: UUID,
    context: TenantContextDep,
    _: CsrfOk,
    settings: Annotated[Settings, Depends(get_settings)],
    files: Annotated[list[UploadFile], File(description="PDF/DOCX/TXT/MD files, or one Q&A CSV")],
) -> list[schemas.SourceOut]:
    """Store uploaded files as sources (editor+). Parsing happens in a worker job."""
    context.require_role("editor")
    uploads: list[tuple[str | None, Any]] = [(file.filename, file.file) for file in files]
    rows = service.upload_files(context, bot_id, uploads, settings, storage=LocalStorage(settings))
    return _sources_out(rows)


@router.get("/sources/{source_id}", response_model=schemas.SourceOut)
def get_source(
    tenant_id: UUID, bot_id: UUID, source_id: UUID, context: TenantContextDep
) -> schemas.SourceOut:
    return schemas.SourceOut.model_validate(service.get_source(context, bot_id, source_id))


# --- ingestion jobs ----------------------------------------------------------


@router.post("/ingestion", response_model=schemas.JobOut, status_code=202)
def start_ingestion(
    tenant_id: UUID,
    bot_id: UUID,
    body: schemas.IngestionStartRequest,
    context: TenantContextDep,
    _: CsrfOk,
    settings: Annotated[Settings, Depends(get_settings)],
) -> schemas.JobOut:
    """Start one ingest job for the bot's stored sources (editor+)."""
    context.require_role("editor")
    return _job_out(service.start_ingestion(context, bot_id, body.source_ids, settings))


@router.get("/jobs", response_model=list[schemas.JobOut])
def list_jobs(tenant_id: UUID, bot_id: UUID, context: TenantContextDep) -> list[schemas.JobOut]:
    return [_job_out(job) for job in service.list_jobs(context, bot_id)]


@router.get("/jobs/{job_id}", response_model=schemas.JobOut)
def get_job(
    tenant_id: UUID, bot_id: UUID, job_id: UUID, context: TenantContextDep
) -> schemas.JobOut:
    return _job_out(service.get_job_or_404(context, bot_id, job_id))


@router.post("/jobs/{job_id}/cancel", response_model=schemas.JobOut)
def cancel_job(
    tenant_id: UUID, bot_id: UUID, job_id: UUID, context: TenantContextDep, _: CsrfOk
) -> schemas.JobOut:
    context.require_role("editor")
    return _job_out(service.cancel_job(context, bot_id, job_id))


@router.post("/jobs/{job_id}/retry", response_model=schemas.JobOut)
def retry_job(
    tenant_id: UUID,
    bot_id: UUID,
    job_id: UUID,
    context: TenantContextDep,
    _: CsrfOk,
    settings: Annotated[Settings, Depends(get_settings)],
) -> schemas.JobOut:
    context.require_role("editor")
    return _job_out(service.retry_job(context, bot_id, job_id, settings))


# --- documents and chunk preview ---------------------------------------------


@router.get("/documents", response_model=list[schemas.DocumentOut])
def list_documents(
    tenant_id: UUID,
    bot_id: UUID,
    context: TenantContextDep,
    source_id: Annotated[UUID | None, Query()] = None,
    revision: Annotated[str, Query(pattern="^(published|draft)$")] = "published",
) -> list[schemas.DocumentOut]:
    rows = service.list_documents(context, bot_id, source_id, revision)
    return [
        schemas.DocumentOut(
            id=document.id,
            source_id=document.source_id,
            title=document.title,
            heading=document.heading,
            source_url=document.source_url,
            page_ref=document.page_ref,
            language=document.language,
            priority=document.priority,
            text=document.text,
            total_chars=document.total_chars,
            chunk_count=count,
            created_at=document.created_at,
        )
        for document, count in rows
    ]


@router.get("/documents/{document_id}/chunks", response_model=list[schemas.ChunkOut])
def list_document_chunks(
    tenant_id: UUID, bot_id: UUID, document_id: UUID, context: TenantContextDep
) -> list[schemas.ChunkOut]:
    return [
        schemas.ChunkOut.model_validate(chunk)
        for chunk in service.list_document_chunks(context, bot_id, document_id)
    ]


# --- revisions, publish, rollback --------------------------------------------


@router.get("/revisions", response_model=schemas.RevisionsResponse)
def list_revisions(
    tenant_id: UUID, bot_id: UUID, context: TenantContextDep
) -> schemas.RevisionsResponse:
    bot = service.get_bot(context, bot_id)
    out = service.list_revisions(context, bot_id)
    return schemas.RevisionsResponse(
        revisions=[schemas.RevisionOut.model_validate(revision) for revision in out],
        published_revision_id=bot.published_revision_id,
    )


@router.post("/revisions/{revision_id}/publish", status_code=200)
def publish_revision(
    tenant_id: UUID,
    bot_id: UUID,
    revision_id: UUID,
    context: TenantContextDep,
    _: CsrfOk,
) -> dict[str, object]:
    """Publish the revision (admin+); publishing an archived one rolls back."""
    context.require_role("admin")
    return service.publish_revision(context, bot_id, revision_id)
