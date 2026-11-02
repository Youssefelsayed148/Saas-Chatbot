# Progress and verified results

Short, current status. Add a dated entry for every verification you run, with the exact command, the database used (host and name only) and the outcome. Never record a result you did not observe. History before 2026-11-02 is summarised in [docs/HISTORY.md](docs/HISTORY.md); the old 3,904-line log is `git show ed965ab:PROGRESS.md`.

## Status on 2026-11-02

- `main` is at `ed965ab` (connection ID shown with a Copy ID button; channel connections can be created paused, and the staff form defaults to paused).
- Alembic sole head: `0031_contact_erasure`. No migration was added after the close-out.
- Deployment: the owner redeploys from `main`. Earlier report: the deployed SHA was `26d6b66`. Re-verify after the redeploy.
- Live: one WhatsApp round trip through ManyOsirisChat on Meta's test number was observed (customer message reached the inbox, bot answer reached the handset). Handoff, agent reply, delivery status, health, closed window, rotation, replay and erasure are still to be checked live (see the Many repository's `docs/saas-delegation/LIVE-CHECKS-HANDOFF.md`).

## Verified results

| Date | What | Result |
| --- | --- | --- |
| 2026-11-02 | API suite, PostgreSQL 16.15 with pgvector 0.6.0 (`ENVIRONMENT=test`, local disposable DB), 1,217 tests, 42 min | 1,207 passed, 10 failed: nine retrieval/embedding tests need pgvector 0.8 or newer (`hnsw.iterative_scan`), one migration test needs the socket guard (`PGHOST` under `/var/tmp/saas-*`, base name ending `_test`) |
| 2026-11-02 | Those 10 on PostgreSQL 16.15 with pgvector 0.8.5 and the guard satisfied | 10 passed (run on their own, not as part of one full run) |
| 2026-11-02 | `ruff check` on `apps/api`, `ruff format --check` on the two changed API files | pass |
| 2026-11-02 | Web `typecheck` and `lint` (Node 22 here; the repo asks for 24) | pass |
| 2026-11-02 | Full Playwright on `main` at `ed965ab`, chromium, 39 files | 177 passed, 0 failed, 0 skipped, 6.2 min. (A first attempt failed 66 tests because the database server had stopped when the sandbox restarted; it was discarded and rerun.) |
| 2026-10-29 | Full Playwright at `88599d7` | 176 passed (gate D1) |

## Open items

See [implementation/KNOWN-ISSUES.md](implementation/KNOWN-ISSUES.md). Not yet done: a single end-to-end API run on pgvector 0.8 or newer, the live delegation checks, the backup/restore drill, the independent security review, and the Meta submission items tracked in the Many repository.
