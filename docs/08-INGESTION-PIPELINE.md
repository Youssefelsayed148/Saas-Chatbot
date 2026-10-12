# Website ingestion
## Sources
Two input paths feed the same pipeline: (a) uploaded files (PDF, DOCX, TXT, MD, CSV) parsed, chunked and indexed per `docs/14-AGREED-BUILD-SPECS.md` (§3–5); a Q&A CSV path imports question/answer pairs with a row-level error report; (b) website URLs fetched by the guarded fetcher. Both produce documents → chunks → embeddings → draft revision. Jobs run in the DB-backed worker (ADR-011).

## Stages
URL submission → scope/ownership policy → secure fetch/crawl → content extraction → canonical URL + content hash dedupe → clean text → chunk → dedupe → full-text index → draft revision → review → publish. Track stage progress and actionable errors per source/job.
## Safety
Allow HTTP(S) only; deny private/loopback/link-local/metadata targets at egress layer; revalidate redirects and resolved IPs; cap pages, depth, bytes, wall time, redirects and concurrency; honor robots policy chosen by owner; sanitize HTML and strip executable content; isolate fetcher. Arbitrary client websites are hostile input. Do not make crawler publicly available before containment tests pass.
## Consistency
A failed crawl never changes published knowledge. Revision publish is atomic and rollbackable. New/changed/deleted pages are reconciled in draft. Retry idempotently, record model/version/dimension and content provenance. Provide manual refresh and job cancellation.
## Acceptance
Two tenants with overlapping URL names never share chunks; crash during indexing leaves published revision intact; redirects to internal targets denied; a site prompt-injection string cannot change assistant policy.

## Scope notes
MVP fetches static HTML only. Pages that need JavaScript rendering are reported as "needs rendering" and handled later by an isolated headless-browser worker (ADR-006). No embeddings are computed in the MVP.
