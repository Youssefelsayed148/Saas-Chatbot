"use client";

import { useParams } from "next/navigation";
import { useCallback, useEffect, useMemo, useState } from "react";

import { LabelBadge } from "@/lib/labels";
import * as api from "@/lib/api";
import type {
  KnowledgeDocument,
  KnowledgeJob,
  KnowledgeRevision,
  KnowledgeSource,
} from "@/lib/api";
import { useSession } from "@/lib/session";
import { Button, Empty, Field, Loading, Notice, PageHeader } from "@/lib/ui";
import BotWorkspaceNav from "@/lib/bot-workspace-nav";
import "@/app/knowledge-screen.css";

const KIND_LABEL: Record<string, string> = {
  pdf: "PDF",
  docx: "Word",
  txt: "Text",
  md: "Markdown",
  qa_csv: "Q&A CSV",
};

const ACCEPTED_FILES = ".pdf,.docx,.txt,.md,.csv";

export default function KnowledgePage() {
  const params = useParams<{ tenant: string; botId: string }>();
  const tenantId = params.tenant;
  const botId = params.botId;
  const { me } = useSession();
  const canRead = !!me?.is_platform_staff;
  const canEdit = !!me?.is_platform_staff;
  const canPublish = !!me?.is_platform_staff;

  const [sources, setSources] = useState<KnowledgeSource[] | null>(null);
  const [jobs, setJobs] = useState<KnowledgeJob[] | null>(null);
  const [revisions, setRevisions] = useState<api.RevisionsResponse | null>(
    null,
  );
  const [documents, setDocuments] = useState<KnowledgeDocument[] | null>(null);
  // Which view the loaded documents belong to (presentation only).
  const [documentsView, setDocumentsView] = useState<"published" | "draft">(
    "published",
  );
  const [revisionView, setRevisionView] = useState<"published" | "draft">(
    "published",
  );
  const [expandedDoc, setExpandedDoc] = useState<string | null>(null);
  const [chunks, setChunks] = useState<
    Record<string, api.KnowledgeChunk[] | null>
  >({});
  const [selectedFiles, setSelectedFiles] = useState<File[]>([]);
  const [uploading, setUploading] = useState(false);
  const [ingesting, setIngesting] = useState(false);
  const [publishing, setPublishing] = useState<string | null>(null);
  const [pageError, setPageError] = useState<string | null>(null);
  const [actionError, setActionError] = useState<string | null>(null);
  const [actionDone, setActionDone] = useState<string | null>(null);

  const error = actionError ?? pageError;

  const loadAll = useCallback(
    async (view: "published" | "draft") => {
      try {
        const [nextSources, nextJobs, nextRevisions, nextDocs] =
          await Promise.all([
            api.listSources(tenantId, botId),
            api.listJobs(tenantId, botId),
            api.listRevisions(tenantId, botId),
            api.listDocuments(tenantId, botId, { revision: view }),
          ]);
        setSources(nextSources);
        setJobs(nextJobs);
        setRevisions(nextRevisions);
        setDocuments(nextDocs);
        setDocumentsView(view);
        setPageError(null);
      } catch (caught) {
        setPageError(
          caught instanceof Error
            ? caught.message
            : "Could not load the knowledge data.",
        );
      }
    },
    [tenantId, botId],
  );

  useEffect(() => {
    if (!canRead) return;
    const timer = setTimeout(() => {
      void loadAll(revisionView);
    }, 0);
    return () => clearTimeout(timer);
  }, [loadAll, revisionView, canRead]);

  // Poll while a job is queued or running so statuses move to done without a reload.
  const busy = useMemo(
    () =>
      (jobs ?? []).some(
        (job) => job.status === "pending" || job.status === "running",
      ),
    [jobs],
  );

  useEffect(() => {
    if (!busy || pageError) return;
    const timer = setInterval(() => {
      void loadAll(revisionView);
    }, 2500);
    return () => clearInterval(timer);
  }, [busy, loadAll, revisionView, pageError]);

  async function onUpload(event: React.FormEvent) {
    event.preventDefault();
    setActionError(null);
    setActionDone(null);
    if (selectedFiles.length === 0) {
      setActionError("Choose at least one file first.");
      return;
    }
    setUploading(true);
    try {
      const created = await api.uploadSources(tenantId, botId, selectedFiles);
      setSelectedFiles([]);
      const input = document.getElementById(
        "knowledge-file-input",
      ) as HTMLInputElement | null;
      if (input) input.value = "";
      setActionDone(
        `Stored ${created.length} file${created.length === 1 ? "" : "s"}. Start the ingest job when ready.`,
      );
      await loadAll(revisionView);
    } catch (caught) {
      setActionError(
        caught instanceof Error ? caught.message : "Upload failed.",
      );
    } finally {
      setUploading(false);
    }
  }

  async function onIngest() {
    setActionError(null);
    setActionDone(null);
    setIngesting(true);
    try {
      await api.startIngestion(tenantId, botId, null);
      setActionDone("Ingest job queued — parsing happens in the worker.");
      await loadAll(revisionView);
    } catch (caught) {
      setActionError(
        caught instanceof Error ? caught.message : "Could not start ingestion.",
      );
    } finally {
      setIngesting(false);
    }
  }

  async function onRetry(job: KnowledgeJob) {
    setActionError(null);
    setActionDone(null);
    try {
      await api.retryJob(tenantId, botId, job.id);
      setActionDone("Job re-queued.");
      await loadAll(revisionView);
    } catch (caught) {
      setActionError(
        caught instanceof Error ? caught.message : "Could not retry the job.",
      );
    }
  }

  async function onCancel(job: KnowledgeJob) {
    setActionError(null);
    setActionDone(null);
    try {
      await api.cancelJob(tenantId, botId, job.id);
      await loadAll(revisionView);
    } catch (caught) {
      setActionError(
        caught instanceof Error ? caught.message : "Could not cancel the job.",
      );
    }
  }

  async function onPublish(revision: KnowledgeRevision) {
    setActionError(null);
    setActionDone(null);
    setPublishing(revision.id);
    try {
      await api.publishRevision(tenantId, botId, revision.id);
      setActionDone(
        revision.status === "archived"
          ? "Rolled back to the previous knowledge."
          : "Published — visitors now use this knowledge.",
      );
      await loadAll(revisionView);
    } catch (caught) {
      setActionError(
        caught instanceof Error ? caught.message : "Publish failed.",
      );
    } finally {
      setPublishing(null);
    }
  }

  async function onToggleChunks(document: KnowledgeDocument) {
    if (expandedDoc === document.id) {
      setExpandedDoc(null);
      return;
    }
    setExpandedDoc(document.id);
    try {
      const rows = await api.listDocumentChunks(tenantId, botId, document.id);
      setChunks((current) => ({ ...current, [document.id]: rows }));
    } catch (caught) {
      setActionError(
        caught instanceof Error
          ? caught.message
          : "Could not load the chunk preview.",
      );
    }
  }

  const storedSources = (sources ?? []).filter(
    (source) => source.status === "stored",
  );

  // Display-only derivations from data the API already returns.
  const sortedSources = useMemo(
    () =>
      [...(sources ?? [])].sort(
        (a, b) =>
          a.kind.localeCompare(b.kind) ||
          a.original_name.localeCompare(b.original_name),
      ),
    [sources],
  );
  const kindSummary = useMemo(() => {
    const counts = new Map<string, number>();
    for (const source of sortedSources)
      counts.set(source.kind, (counts.get(source.kind) ?? 0) + 1);
    return [...counts.entries()].map(
      ([kind, count]) => `${KIND_LABEL[kind] ?? kind} ${count}`,
    );
  }, [sortedSources]);
  // The documents list belongs to one revision (published, or the newest
  // draft); only for that revision can the file count be derived.
  const viewedRevisionId = useMemo(() => {
    if (!revisions) return null;
    if (revisionView === "published") return revisions.published_revision_id;
    return (
      [...revisions.revisions]
        .filter((revision) => revision.status === "draft")
        .sort((a, b) => b.created_at.localeCompare(a.created_at))[0]?.id ?? null
    );
  }, [revisions, revisionView]);
  const viewedFileCount =
    documents && documentsView === revisionView
      ? new Set(documents.map((document) => document.source_id).filter(Boolean))
          .size
      : null;
  const plural = (count: number, one: string, many = `${one}s`) =>
    `${count} ${count === 1 ? one : many}`;

  if (!canRead) return null;

  return (
    <main className="knowledge-page">
      <BotWorkspaceNav tenantId={tenantId} botId={botId} />
      <PageHeader
        title="Knowledge"
        purpose="Upload files, review what was learned and publish trusted answers."
      />
      <nav aria-label="Page sections" className="section-jump">
        {canEdit && <a href="#upload-heading">Upload</a>}
        <a href="#sources-heading">Files</a>
        <a href="#jobs-heading">Jobs</a>
        <a href="#documents-heading">Documents and chunks</a>
        <a href="#revisions-heading">Revisions</a>
      </nav>
      {!canEdit && (
        <Notice message="Read-only knowledge. Request a change to ask your operator for updates." />
      )}
      {error && <Notice message={error} tone="error" />}
      {!error && actionDone && <Notice message={actionDone} />}

      {canEdit && (
        <section aria-labelledby="upload-heading" className="ui-card">
          <header className="section-heading">
            <h2 id="upload-heading">Upload files</h2>
          </header>
          <p className="muted">
            PDF (text-based), Word, TXT, Markdown or a Q&A CSV{" "}
            {canEdit ? (
              <a
                href={`/api/v1/tenants/${tenantId}/bots/${botId}/sources/qa-template`}
              >
                (download the template)
              </a>
            ) : null}
            . Website page files prepared by staff fit here too. Parsing happens
            after you start the ingest job.
          </p>
          <form onSubmit={onUpload}>
            <label className="field">
              Files (max 20, up to 25 MB each under current plan limits)
              <input
                id="knowledge-file-input"
                type="file"
                multiple
                accept={ACCEPTED_FILES}
                disabled={!canEdit || uploading}
                onChange={(event) =>
                  setSelectedFiles(Array.from(event.target.files ?? []))
                }
              />
            </label>
            <div className="action-row knowledge-actions">
              {canEdit && (
                <Button
                  type="submit"
                  disabled={uploading || selectedFiles.length === 0}
                >
                  {uploading ? "Uploading…" : "Upload"}
                </Button>
              )}
              {canEdit && (
                <Button
                  type="button"
                  variant="quiet"
                  onClick={() => void onIngest()}
                  disabled={ingesting || storedSources.length === 0}
                  title={
                    storedSources.length === 0
                      ? "Upload files first"
                      : "Run parse → chunk → index for the stored files"
                  }
                >
                  {ingesting ? "Starting…" : "Ingest files"}
                </Button>
              )}
            </div>
          </form>
        </section>
      )}

      <section aria-labelledby="sources-heading" className="ui-card">
        <header className="section-heading">
          <h2 id="sources-heading">Files</h2>
          {sources !== null && sources.length > 0 && (
            <p className="muted file-summary">
              {[plural(sources.length, "file"), ...kindSummary].join(" · ")}
            </p>
          )}
        </header>
        {sources === null ? (
          <Loading label="Loading files…" />
        ) : sources.length === 0 ? (
          <Empty>
            {canEdit
              ? "No files uploaded yet. Use Upload files above to add knowledge."
              : "No files uploaded yet."}
          </Empty>
        ) : (
          <ul data-testid="sources-list" className="record-list">
            {sortedSources.map((source) => (
              <li key={source.id} data-source-status={source.status}>
                <span className="record-title">{source.original_name}</span>
                <span className="record-meta">
                  {KIND_LABEL[source.kind] ?? source.kind} ·{" "}
                  {(source.size_bytes / 1024).toFixed(1)} KB ·{" "}
                  <LabelBadge value={source.status} />
                  {source.valid_rows !== null && (
                    <>
                      {" · "}
                      {source.valid_rows}/{source.total_rows} valid rows
                    </>
                  )}
                </span>
                {source.error && <Notice message={source.error} tone="error" />}
                {source.row_errors && source.row_errors.length > 0 && (
                  <div data-testid="row-errors">
                    {source.row_errors.map((rowError) => (
                      <Notice
                        key={`${source.id}-${rowError.row}`}
                        message={`Row ${rowError.row}: ${rowError.reason}`}
                        tone="error"
                      />
                    ))}
                  </div>
                )}
              </li>
            ))}
          </ul>
        )}
      </section>

      <section aria-labelledby="jobs-heading" className="ui-card">
        <header className="section-heading">
          <h2 id="jobs-heading">Jobs</h2>
        </header>
        {jobs === null ? (
          <Loading label="Loading jobs…" />
        ) : jobs.length === 0 ? (
          <Empty>No ingest jobs yet.</Empty>
        ) : (
          <ul data-testid="jobs-list" className="record-list">
            {jobs.map((job) => (
              <li key={job.id} data-job-status={job.status}>
                <span className="record-meta">
                  <span data-testid="job-status" data-status={job.status}>
                    <LabelBadge value={job.status} />
                  </span>
                  {(job.status === "pending" || job.status === "running") && (
                    <progress aria-label="Ingestion in progress" />
                  )}
                  {" · started "}
                  {new Date(job.created_at).toLocaleTimeString()}
                  {job.source_ids.length > 0 && (
                    <> · {plural(job.source_ids.length, "file")}</>
                  )}
                  {job.attempts > 1 && <> · attempt {job.attempts}</>}
                  {job.status === "succeeded" && (
                    <>
                      {" · "}
                      <a href="#revisions-heading">See revisions</a>
                    </>
                  )}
                </span>
                {job.error && <Notice message={job.error} tone="error" />}
                {canEdit &&
                  (job.status === "pending" || job.status === "running") && (
                    <Button
                      type="button"
                      variant="quiet"
                      onClick={() => void onCancel(job)}
                      disabled={busy && job.status === "running"}
                    >
                      Cancel
                    </Button>
                  )}
                {canEdit && job.status === "failed" && (
                  <Button
                    type="button"
                    variant="quiet"
                    onClick={() => void onRetry(job)}
                  >
                    Retry
                  </Button>
                )}
              </li>
            ))}
          </ul>
        )}
      </section>

      <section aria-labelledby="documents-heading" className="ui-card">
        <header className="section-heading">
          <h2 id="documents-heading">Documents and chunks</h2>
        </header>
        <Field label="View" className="view-field">
          {(control) => (
            <select
              {...control}
              value={revisionView}
              onChange={(event) =>
                setRevisionView(event.target.value as "published" | "draft")
              }
            >
              <option value="published">Published knowledge</option>
              <option value="draft">Draft (latest ingest)</option>
            </select>
          )}
        </Field>
        {documents === null ? (
          <Loading label="Loading documents…" />
        ) : documents.length === 0 ? (
          <Empty>
            {revisionView === "published"
              ? "Nothing published yet. Ingest files and publish a draft."
              : "No documents in the draft yet."}
          </Empty>
        ) : (
          <ul data-testid="documents-list" className="record-list">
            {documents.map((document) => (
              <li key={document.id}>
                <Button
                  type="button"
                  variant="quiet"
                  className="record-toggle"
                  aria-expanded={expandedDoc === document.id}
                  onClick={() => void onToggleChunks(document)}
                >
                  {document.title}
                  {document.heading ? ` — ${document.heading}` : ""}
                </Button>
                <p className="muted record-meta">
                  {document.status} · {document.page_ref}
                  {document.source_url && (
                    <>
                      {" · "}
                      <span className="record-title">
                        {document.source_url}
                      </span>
                    </>
                  )}{" "}
                  · {document.language} · {document.chunk_count} chunk
                  {document.chunk_count === 1 ? "" : "s"} ·{" "}
                  {document.total_chars} chars
                </p>
                {document.warnings?.map((warning) => (
                  <Notice key={warning} message={warning} />
                ))}
                <code className="doc-snippet">
                  {document.text.slice(0, 240)}
                </code>
                {expandedDoc === document.id && (
                  <ul data-testid="chunk-list" className="chunk-list">
                    {chunks[document.id] === undefined ? (
                      <li>
                        <Loading label="Loading chunks…" />
                      </li>
                    ) : chunks[document.id] &&
                      chunks[document.id]!.length > 0 ? (
                      chunks[document.id]!.map((chunk) => (
                        <li
                          key={chunk.id}
                          dir={chunk.language === "ar" ? "rtl" : undefined}
                        >
                          #{chunk.ordinal} · {chunk.text.slice(0, 300)}
                        </li>
                      ))
                    ) : (
                      <li className="muted">No chunks for this document.</li>
                    )}
                  </ul>
                )}
              </li>
            ))}
          </ul>
        )}
      </section>

      <section aria-labelledby="revisions-heading" className="ui-card">
        <header className="section-heading">
          <h2 id="revisions-heading">Revisions</h2>
        </header>
        {!canPublish && (
          <p className="muted">
            Publishing is managed by your platform operator.
          </p>
        )}
        {revisions === null ? (
          <Loading label="Loading revisions…" />
        ) : revisions.revisions.length === 0 ? (
          <Empty>No revisions yet.</Empty>
        ) : (
          <ul data-testid="revisions-list" className="record-list">
            {revisions.revisions.map((revision) => (
              <li key={revision.id} data-revision-status={revision.status}>
                <span className="record-meta">
                  <LabelBadge value={revision.status} /> ·{" "}
                  {revision.id === viewedRevisionId && viewedFileCount !== null
                    ? `${plural(viewedFileCount, "file")} · `
                    : ""}
                  {plural(revision.document_count, "page")} ·{" "}
                  {plural(revision.chunk_count, "chunk")} ·{" "}
                  {new Date(revision.created_at).toLocaleString()}
                  {revision.published_at
                    ? ` · published ${new Date(revision.published_at).toLocaleString()}`
                    : ""}
                  {revision.id === revisions.published_revision_id
                    ? " · current"
                    : ""}
                </span>
                {canPublish &&
                  (revision.status === "draft" ||
                    revision.status === "archived") && (
                    <Button
                      type="button"
                      onClick={() => void onPublish(revision)}
                      disabled={publishing === revision.id}
                    >
                      {publishing === revision.id
                        ? "Publishing…"
                        : revision.status === "archived"
                          ? "Roll back to this revision"
                          : "Publish"}
                    </Button>
                  )}
              </li>
            ))}
          </ul>
        )}
      </section>
    </main>
  );
}
