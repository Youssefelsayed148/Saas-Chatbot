# Website ingestion
## Sources
Two input paths feed the same pipeline: (a) uploaded files (PDF, DOCX, TXT, MD, CSV) parsed, chunked and indexed per `docs/14-AGREED-BUILD-SPECS.md` (§3–5); a Q&A CSV path imports question/answer pairs with a row-level error report; (b) website content prepared by the staff `website-to-knowledge` skill as Markdown pages with source URLs (docs/14 §13). There is no in-app URL fetcher in the MVP. Both produce documents → chunks → embeddings → draft revision. Jobs run in the DB-backed worker (ADR-011).

## Stages
File upload → type/size validation → parse (page/heading sections, front matter) → clean text → chunk → dedupe → full-text index → draft revision → review → publish. Track stage progress and actionable errors per source/job.
## Safety (fetcher rules below apply only if an in-app fetcher is added later; MVP ingests uploaded files only)
Allow HTTP(S) only; deny private/loopback/link-local/metadata targets at egress layer; revalidate redirects and resolved IPs; cap pages, depth, bytes, wall time, redirects and concurrency; honor robots policy chosen by owner; sanitize HTML and strip executable content; isolate fetcher. Arbitrary client websites are hostile input. Do not make crawler publicly available before containment tests pass.
## Consistency
A failed crawl never changes published knowledge. Revision publish is atomic and rollbackable. New/changed/deleted pages are reconciled in draft. Retry idempotently, record model/version/dimension and content provenance. Provide manual refresh and job cancellation.
## Acceptance
Two tenants with overlapping URL names never share chunks; crash during indexing leaves published revision intact; redirects to internal targets denied; a site prompt-injection string cannot change assistant policy.

## Scope notes
MVP has no in-app crawling and computes no embeddings. Uploaded files are untrusted input too: enforce size/type limits, parse in the worker, never execute content, and treat text (including instruction-like phrases) as data.
