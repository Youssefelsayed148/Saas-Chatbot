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
import { roleSatisfies, useSession } from "@/lib/session";
import { Empty, Loading, Notice } from "@/lib/ui";
import BotWorkspaceNav from "@/lib/bot-workspace-nav";

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
  const { roleIn } = useSession();
  const role = roleIn(tenantId);
  const canEdit = roleSatisfies(role, "editor");
  const canPublish = roleSatisfies(role, "admin");

  const [sources, setSources] = useState<KnowledgeSource[] | null>(null);
  const [jobs, setJobs] = useState<KnowledgeJob[] | null>(null);
  const [revisions, setRevisions] = useState<api.RevisionsResponse | null>(
    null,
  );
  const [documents, setDocuments] = useState<KnowledgeDocument[] | null>(null);
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
    const timer = setTimeout(() => {
      void loadAll(revisionView);
    }, 0);
    return () => clearTimeout(timer);
  }, [loadAll, revisionView]);

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

  return (
    <main>
      <BotWorkspaceNav tenantId={tenantId} botId={botId} />
      <h1>Knowledge</h1>
      <p className="page-purpose">
        Upload files, review what was learned and publish trusted answers.
      </p>
      {!canEdit && (
        <Notice
          message={`Read-only view: uploads and ingest require the editor role (you are ${role}).`}
        />
      )}
      {error && <Notice message={error} tone="error" />}
      {!error && actionDone && <Notice message={actionDone} />}

      <section aria-labelledby="upload-heading">
        <h2 id="upload-heading">Upload files</h2>
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
          <label>
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
          {canEdit && (
            <button
              type="submit"
              disabled={uploading || selectedFiles.length === 0}
            >
              {uploading ? "Uploading…" : "Upload"}
            </button>
          )}{" "}
          {canEdit && (
            <button
              type="button"
              onClick={() => void onIngest()}
              disabled={ingesting || storedSources.length === 0}
              title={
                storedSources.length === 0
                  ? "Upload files first"
                  : "Run parse → chunk → index for the stored files"
              }
            >
              {ingesting ? "Starting…" : "Ingest files"}
            </button>
          )}
        </form>
      </section>

      <section aria-labelledby="sources-heading">
        <h2 id="sources-heading">Files</h2>
        {sources === null ? (
          <Loading label="Loading files…" />
        ) : sources.length === 0 ? (
          <Empty>
            No files uploaded yet. Use Upload files above to add knowledge.
          </Empty>
        ) : (
          <ul data-testid="sources-list">
            {sources.map((source) => (
              <li key={source.id} data-source-status={source.status}>
                {source.original_name} —{" "}
                {KIND_LABEL[source.kind] ?? source.kind} ·{" "}
                {(source.size_bytes / 1024).toFixed(1)} KB · {source.status}
                {source.valid_rows !== null && (
                  <>
                    {" · "}
                    {source.valid_rows}/{source.total_rows} valid rows
                  </>
                )}
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

      <section aria-labelledby="jobs-heading">
        <h2 id="jobs-heading">Jobs</h2>
        {jobs === null ? (
          <Loading label="Loading jobs…" />
        ) : jobs.length === 0 ? (
          <Empty>No ingest jobs yet.</Empty>
        ) : (
          <ul data-testid="jobs-list">
            {jobs.map((job) => (
              <li key={job.id} data-job-status={job.status}>
                <span data-testid="job-status" data-status={job.status}>
                  <LabelBadge value={job.status} />
                </span>
                {(job.status === "pending" || job.status === "running") && (
                  <progress aria-label="Ingestion in progress" />
                )}
                {" · started "}
                {new Date(job.created_at).toLocaleTimeString()}
                {job.attempts > 1 && <> · attempt {job.attempts}</>}
                {job.error && <Notice message={job.error} tone="error" />}
                {canEdit &&
                  (job.status === "pending" || job.status === "running") && (
                    <button
                      type="button"
                      onClick={() => void onCancel(job)}
                      disabled={busy && job.status === "running"}
                    >
                      Cancel
                    </button>
                  )}
                {canEdit &&
                  job.status !== "pending" &&
                  job.status !== "running" && (
                    <button type="button" onClick={() => void onRetry(job)}>
                      Retry
                    </button>
                  )}
              </li>
            ))}
          </ul>
        )}
      </section>

      <section aria-labelledby="documents-heading">
        <h2 id="documents-heading">Documents and chunks</h2>
        <label>
          View
          <select
            value={revisionView}
            onChange={(event) =>
              setRevisionView(event.target.value as "published" | "draft")
            }
          >
            <option value="published">Published knowledge</option>
            <option value="draft">Draft (latest ingest)</option>
          </select>
        </label>
        {documents === null ? (
          <Loading label="Loading documents…" />
        ) : documents.length === 0 ? (
          <Empty>
            {revisionView === "published"
              ? "Nothing published yet. Ingest files and publish a draft."
              : "No documents in the draft yet."}
          </Empty>
        ) : (
          <ul data-testid="documents-list">
            {documents.map((document) => (
              <li key={document.id}>
                <button
                  type="button"
                  aria-expanded={expandedDoc === document.id}
                  onClick={() => void onToggleChunks(document)}
                >
                  {document.title}
                  {document.heading ? ` — ${document.heading}` : ""}
                </button>
                <p className="muted">
                  {document.page_ref}
                  {document.source_url
                    ? ` · ${document.source_url}`
                    : ""} · {document.language} · {document.chunk_count} chunk
                  {document.chunk_count === 1 ? "" : "s"} ·{" "}
                  {document.total_chars} chars
                </p>
                <code>{document.text.slice(0, 240)}</code>
                {expandedDoc === document.id && (
                  <ul data-testid="chunk-list">
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

      <section aria-labelledby="revisions-heading">
        <h2 id="revisions-heading">Revisions</h2>
        {!canPublish && (
          <p className="muted">Publishing requires the admin role or higher.</p>
        )}
        {revisions === null ? (
          <Loading label="Loading revisions…" />
        ) : revisions.revisions.length === 0 ? (
          <Empty>No revisions yet.</Empty>
        ) : (
          <ul data-testid="revisions-list">
            {revisions.revisions.map((revision) => (
              <li key={revision.id} data-revision-status={revision.status}>
                <LabelBadge value={revision.status} /> ·{" "}
                {revision.document_count} documents · {revision.chunk_count}{" "}
                chunks · {new Date(revision.created_at).toLocaleString()}
                {revision.published_at
                  ? ` · published ${new Date(revision.published_at).toLocaleString()}`
                  : ""}
                {revision.id === revisions.published_revision_id
                  ? " · current"
                  : ""}
                {canPublish &&
                  (revision.status === "draft" ||
                    revision.status === "archived") && (
                    <button
                      type="button"
                      onClick={() => void onPublish(revision)}
                      disabled={publishing === revision.id}
                    >
                      {publishing === revision.id
                        ? "Publishing…"
                        : revision.status === "archived"
                          ? "Roll back to this revision"
                          : "Publish"}
                    </button>
                  )}
              </li>
            ))}
          </ul>
        )}
      </section>
    </main>
  );
}
