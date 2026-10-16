# Deferred code-review findings

Source: CODE-REVIEW.md (review of `fc3fdcd`, on branch `review/rag-phase-2`).
These are NOT fixed on `fix/rag-phase-2-final`. One line of reason each; none is a
blocker or high. Fixed and not-applicable findings are in FINAL-REPORT.md.

| ID | Sev | Reason deferred |
|---|---|---|
| F-07 | medium | Paid OpenRouter Standard tier is a product/spec decision (owner override limits live work to `:free`); needs an ADR, not a code tweak. |
| F-10 | medium | Null-vs-zero cost reporting touches the cost API contract and the Operator panel; needs a contract decision and a SQL aggregation rewrite. |
| F-11 | medium | Backfill batching/revision scope is a performance rework of a resumable job with lease fencing; too large to change safely without a load test. |
| F-12 | medium | Readiness semantics for draft ingests plus a staff backfill/mode UI is new product surface (ticket-sized), not a small fix. |
| F-13 | medium | Prompt-injection hardening changes the generation prompt shape (role split, delimiters); needs real-model evaluation (PENDING) before changing. |
| F-16 | low | Windows process-tree kill needs a Windows-gated test harness; the dev host is Windows but CI/production target is POSIX. Documented as POSIX-only. |
| F-17 | low | Per-document parse warnings need a schema change and parser plumbing (new column + UI). |
| F-18 | low | Pinning the pgvector image/version is an infrastructure change (compose is out of scope; no docker compose in this task). |
| F-19 | low | Moving the shared baseline helpers out of `scripts/` is a refactor with no behaviour change; nothing in `main` imports `evaluation`. |
| F-21 | low | Provider/model pair validation on `PATCH .../rag` changes the staff API contract. |
| F-22 | low | Passing the event kind explicitly changes the `ChatModel` call signature across all callers. |
| F-23 | low | Remaining style drift is pre-existing in untouched code (`knowledge/service.py`, the `jobs` check line); touched files were formatted. |
| R-02, R-03 | risk | Exact-repair double work and bot-row lock serialisation need load data (UNVERIFIED), not a code change. |
