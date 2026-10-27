# Failures that are NOT caused by the Phase 6 channel work

Rewritten 2026-10-27 against the branch merged with `origin/main` (d189893). The earlier version of this file described a pre-merge state (22 API failures, 14 Playwright failures) and is obsolete: main fixed most of them.

## API tests (pytest, file by file, 96 files): 1083 passed, 2 failed

Command: `cd apps/api && TEST_DATABASE_URL=<disposable PostgreSQL 16 + pgvector 0.8.0 URL> python -m pytest tests/<file>.py -q -p no:cacheprovider`, one run per file.

| Test | Result on this branch | Result on clean `origin/main` (scratch worktree, separate DB `mainchk_test`) |
|---|---|---|
| `tests/test_tone_prompt.py::test_empty_tone_leaves_prompt_body_byte_identical` | fails: pinned hash `2cd35a17...` vs rendered `33c62542...` | fails identically (also on main) |
| `tests/test_trace_context.py::test_zero_evidence_lists_the_top_rejected_candidates` | fails: `kind` is `answer`, expected `cannot_confirm` | fails identically (also on main) |

Both are NOT caused by this branch. Causes were not investigated: the first test pins a prompt hash that main's later prompt changes no longer match (the website prompt on this branch is byte-identical to main's, pinned in `test_chat.py`); the second looks like retrieval behaviour that changed on main.

## Lint and types

`ruff check .` and `ruff format --check .` clean; `mypy app` clean. `alembic check` reports drift that is on main as well and in files this branch does not change (`models/core.py`, migrations 0004 and 0006): `bots.uq_bots_widget_locator` (index vs unique constraint) and `provisioning_requests` (`ix_provisioning_requests_created`, `uq_provisioning_scope_key`). The two channel indexes that used to show up are now declared in the models.

## Playwright

Only the three channel specs were run in this verification (channels, channel-insights, channel-delivery): 5 passed. Every other Playwright spec is NOT VERIFIED here; the old list of 14 failures (conversations, group-a-operator, overview, group-c-polish, install, knowledge, widget-*) predates the merge and was not re-run, so do not treat it as current.
