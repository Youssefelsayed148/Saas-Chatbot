# Phase 1 follow-up and local merge

2026-10-16 (Africa/Cairo). Implementation `4f5a00f29d71e22b65c3f2bb80e0f35d0c82188b`; normal merge `fde670f83c0f5e67e0ffe597a519f0ddd8d6c62b` (parents `60745a7`, `4f5a00f`). Local tag `phase-1-complete` points to that merge. Evidence-only report commit follows the tested merge; application source is unchanged.

## Result

- Eight knowledge reads and all existing knowledge writes require platform staff; client admin/editor/viewer receive 403 in their tenant, foreign tenants stay 404. Exact 77-route OpenAPI/declaration comparison passes.
- Knowledge/install navigation and pages are staff-only. Bot status list/detail stay available; every client role receives empty config and null widget locator. There is no separate snippet endpoint to give its own x-minimum-role; existing config mutations are staff-only and return 403 to clients.
- Client inbox/conversation and visitor turn/history responses redact citations; UI also hides source lists. Internal citation validation/storage and staff review remain. Client exports retain operational data and exclude knowledge, bot config and citations; staff exports retain these.
- Existing platform-linked delete dialog verified end to end: staff without membership, deletion-preview counts, exact typed organization name, reason, cancel preserving tenant, 204 deletion and subsequent 404. No replacement dialog was necessary.
- No migrations added by this follow-up; merge carries the product branch's existing migration 0013. No deployment, push, paid calls or environment-file reads. Only plain Docker and disposable test databases used.

## Affected checks (before merge)

| API file | Final result |
|---|---|
| `test_tenant_route_matrix.py` | 6 passed, 1 warning in 26.30s |
| `test_knowledge_pipeline.py` | 9 passed, 1 warning in 33.68s |
| `test_knowledge_uploads.py` | 19 passed, 1 warning in 10.43s |
| `test_bots.py` | 4 passed, 1 warning in 4.56s |
| `test_members.py` | 8 passed, 1 warning in 5.53s |
| `test_conversations_view.py` | 5 passed, 1 warning in 79.08s (0:01:19) |
| `test_widget_public.py` | 14 passed, 1 warning in 199.90s (0:03:19) |
| `test_tenant_data.py` | 2 passed, 1 warning in 4.16s |

Latest affected outcomes: **67 passed across 8 files**. Browser specs: knowledge 4, install 1, roles-control 2, platform 2, widget 4 = **13 passed**. Initial failures and exact commands are retained in PROGRESS.md: stale admin revision fixture, delete-test 200/204 assertion, obsolete widget source-label assertion. Only failing affected files/specs were rechecked.

Web typecheck and lint exited 0. Pinned container Ruff on every changed API file passed; mypy passed for 154 files. A broader host Ruff attempt reported 9 existing issues in unrelated files; whole-repository lint is **not green/verified** by this task. The early container lint/format attempt could not write its cache on the read-only mount; subsequent lint used --no-cache.

## Merge gate (once on main)

API: **282 passed, 0 failed**, all **37 files** run individually, exactly once at the merge gate. Includes nested `eval/test_eval.py`. Offline eval output was directed to `/tmp/p1follow-gate-eval`, preserving the historical tracked report.

| File under apps/api/tests | Pass count | Full outcome |
|---|---:|---|
| `eval/test_eval.py` | 2 | 2 passed, 1 warning in 12.92s |
| `test_analytics.py` | 6 | 6 passed, 1 warning in 116.79s (0:01:56) |
| `test_auth.py` | 15 | 15 passed, 1 warning in 4.43s |
| `test_bot_status.py` | 5 | 5 passed, 1 warning in 78.69s (0:01:18) |
| `test_bots.py` | 4 | 4 passed, 1 warning in 2.96s |
| `test_change_requests.py` | 1 | 1 passed, 1 warning in 3.31s |
| `test_chat.py` | 15 | 15 passed, 1 warning in 181.76s (0:03:01) |
| `test_contacts.py` | 1 | 1 passed, 1 warning in 14.88s |
| `test_conversations.py` | 13 | 13 passed, 1 warning in 190.28s (0:03:10) |
| `test_conversations_view.py` | 5 | 5 passed, 1 warning in 77.42s (0:01:17) |
| `test_cross_script.py` | 3 | 3 passed, 1 warning in 36.68s |
| `test_database_guard.py` | 5 | 5 passed, 1 warning in 0.63s |
| `test_followups_analytics.py` | 2 | 2 passed, 1 warning in 32.00s |
| `test_handoff.py` | 5 | 5 passed, 1 warning in 62.50s (0:01:02) |
| `test_health.py` | 6 | 6 passed, 1 warning in 1.77s |
| `test_inbox_list.py` | 5 | 5 passed, 1 warning in 13.30s |
| `test_invitations.py` | 6 | 6 passed, 1 warning in 6.20s |
| `test_jobs.py` | 8 | 8 passed, 1 warning in 2.75s |
| `test_knowledge_parsers.py` | 27 | 27 passed, 1 warning in 3.43s |
| `test_knowledge_pipeline.py` | 9 | 9 passed, 1 warning in 31.68s |
| `test_knowledge_uploads.py` | 19 | 19 passed, 1 warning in 9.28s |
| `test_members.py` | 8 | 8 passed, 1 warning in 4.29s |
| `test_migrations.py` | 1 | 1 passed, 1 warning in 6.40s |
| `test_models_constraints.py` | 13 | 13 passed, 1 warning in 1.08s |
| `test_platform.py` | 9 | 9 passed, 1 warning in 127.57s (0:02:07) |
| `test_platform_ops.py` | 4 | 4 passed, 1 warning in 3.39s |
| `test_quotas.py` | 10 | 10 passed, 1 warning in 5.55s |
| `test_retrieval.py` | 9 | 9 passed, 1 warning in 123.62s (0:02:03) |
| `test_seed_demo.py` | 21 | 21 passed, 1 warning in 2.61s |
| `test_self_service_signup.py` | 4 | 4 passed, 1 warning in 3.38s |
| `test_startup_guard.py` | 5 | 5 passed, 1 warning in 1.15s |
| `test_tenant_data.py` | 2 | 2 passed, 1 warning in 3.77s |
| `test_tenant_route_matrix.py` | 6 | 6 passed, 1 warning in 26.36s |
| `test_tenants.py` | 6 | 6 passed, 1 warning in 3.57s |
| `test_widget_appearance.py` | 3 | 3 passed, 1 warning in 43.63s |
| `test_widget_leads.py` | 5 | 5 passed, 1 warning in 80.10s (0:01:20) |
| `test_widget_public.py` | 14 | 14 passed, 1 warning in 189.12s (0:03:09) |

API command for each file (all 37 exact commands and exits recorded in PROGRESS.md):

```text
docker exec -e ENVIRONMENT=test -e EVAL_REAL_RERUN=0 -e REPO_IMPL_DIR=/tmp/p1follow-gate-eval -e DATABASE_URL=postgresql://postgres@host.docker.internal:55447/p1followgate phase1-verification-api python -m pytest -q tests/<file> --tb=short -p no:cacheprovider --basetemp=/tmp/p1follow-gate-<stem>
```

Full unscoped Playwright: **40 passed, 0 failed (3.3m), exit 0**, one run on main, no retries. **ECONNRESET: 0; affected spec: none.** No full suite was repeated for reporting.

```text
# From apps/web, with explicit process environment:
ENVIRONMENT=test DATABASE_URL=postgresql://postgres@127.0.0.1:55447/p1followgate E2E_API_PORT=18147 API_PROXY_TARGET=http://127.0.0.1:18147 npm.cmd test -- --reporter=line
```

Logs retained under `.test-storage/phase1-followup/` (`gate-*.log`, `gate-results.json`, `playwright-gate.log`, affected logs).

## Branches and worktrees before merge

| Branch | Last commit | Last subject | Merged into main before merge |
|---|---|---|---|
| `feat/p1-01-foundation` | `1bea650` | docs: update README and implementation documents for P7 completion and P6 prerequisites | Yes |
| `feat/product-cycle-1` | `4f5a00f` | fix(auth): restrict knowledge and installation to platform operators | No; tested and merged in this task |
| `feat/ui-redesign` | `51bafec` | docs: commit UI redesign plan and ignore generated screenshots | Yes |
| `main` | `60745a7` | build: one-command Docker stack from repo root | Yes |

Exactly one worktree before merge:

```text
worktree D:/Projects/Work Projects/The Osiris Labs/SAAS-chats-ai
HEAD 4f5a00f29d71e22b65c3f2bb80e0f35d0c82188b
branch refs/heads/feat/product-cycle-1
```

UI redesign and foundation were already merged; neither needed a second merge. No unfinished branch was merged; no other local branch needed a merge.

## Cleanup and end state

Merged branches deleted only with `git branch -d`: feat/p1-01-foundation, feat/product-cycle-1, feat/ui-redesign. `git worktree prune` completed. No secondary worktrees existed, so none were removed. Unmerged local branches: none. Untracked inventory: none; nothing removed. Ignored files, .env, .test-storage and logs retained. .gitignore covers .test-storage, generated pytest temp directories, web build and Playwright output.

`git branch -a`:

```text
* main
```

Worktree after cleanup:

```text
worktree D:/Projects/Work Projects/The Osiris Labs/SAAS-chats-ai
HEAD fde670f83c0f5e67e0ffe597a519f0ddd8d6c62b
branch refs/heads/main
```

After the evidence-only commit, final status is checked clean on main; final commit ID and git log --oneline -10 are provided in the chat completion report. No test rerun follows evidence recording.

## Files changed in this follow-up

33 files in implementation commit; this report is the additional evidence artifact. The merged product branch changes 133 paths relative to the former main, including earlier work.

- `.gitignore`
- `PROGRESS.md`
- `apps/api/app/bots/router.py`
- `apps/api/app/conversations/router.py`
- `apps/api/app/core/permissions.py`
- `apps/api/app/inbox/router.py`
- `apps/api/app/knowledge/router.py`
- `apps/api/app/tenants/data.py`
- `apps/api/app/widget/router.py`
- `apps/api/tests/knowledge_helpers.py`
- `apps/api/tests/test_bots.py`
- `apps/api/tests/test_conversations_view.py`
- `apps/api/tests/test_knowledge_pipeline.py`
- `apps/api/tests/test_knowledge_uploads.py`
- `apps/api/tests/test_tenant_data.py`
- `apps/api/tests/test_tenant_route_matrix.py`
- `apps/api/tests/test_widget_public.py`
- `apps/web/app/app/[tenant]/bots/[botId]/conversations/[conversationId]/page.tsx`
- `apps/web/app/app/[tenant]/bots/[botId]/install/page.tsx`
- `apps/web/app/app/[tenant]/bots/[botId]/knowledge/page.tsx`
- `apps/web/app/app/[tenant]/inbox/[conversation]/page.tsx`
- `apps/web/app/app/[tenant]/page.tsx`
- `apps/web/app/app/[tenant]/settings/data/page.tsx`
- `apps/web/app/widget/frame/page.tsx`
- `apps/web/lib/bot-workspace-nav.tsx`
- `apps/web/next-env.d.ts`
- `apps/web/tests/knowledge.spec.ts`
- `apps/web/tests/platform.spec.ts`
- `apps/web/tests/roles-control.spec.ts`
- `apps/web/tests/widget.spec.ts`
- `docs/06-AUTHORIZATION-AND-SECURITY.md`
- `implementation/MANUAL-TEST.md`
- `implementation/PHASE-02/PHASE-SPECIFICATION.md`
- `implementation/PHASE-01/FOLLOW-UP-MERGE-REPORT.md`

## Limits / UNVERIFIED

- Whole-repository lint remains unverified/failed in the broader host check (9 pre-existing issues); changed API files and web lint pass.
- Hosted CI, production deployment, live providers and real-model answer quality were not exercised. Tests use offline providers and disposable local databases. No staging work or OPEN hosting/billing decision was advanced.
- Ignored inaccessible historical pytest temp directories were preserved; their contents were not inspected.
