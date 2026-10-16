# Phase 1 roles and operator control - verification report

Implementation and local verification complete. No production migration or deployment has been performed.

Client roles are admin/editor/viewer. `is_platform_staff` is independent of membership and controls bot/knowledge/playground operations and organization deletion. Migration 0013 maps owner to admin and merges the fictional demo-owner login into demo-admin while preserving historical identity references. Member removal revokes access while preserving sender/assignment anchors; last-admin checks keep their tenant row lock. The deletion ledger survives tenant purge; purge also removes tenant visitor rate counters and storage while retaining unrelated counters; grace defaults to 30 days (`ORG_DELETION_GRACE_DAYS`). Viewers retain read-only contact lists and profiles, as confirmed by the owner. Change-request attachment downloads are tenant scoped; operators triage through /platform/change-requests.

## Declared tenant route matrix

Success means authorization allows the route with valid, existing resources and a valid payload. Business-state and validation checks still apply. Hidden tenant resources return 404 for every client role. Required operator actions are tested without tenant membership. Ordinary inbox actions require an active membership because assignment/sender/read-marker composite foreign keys remain tenant bound.

| Method | Route | Minimum | Admin | Editor | Viewer |
|---|---|---|---|---|---|
| GET | `/api/v1/tenants/{tenant_id}/inbox/assignees` | editor | Success | Success | 403 |
| GET | `/api/v1/tenants/{tenant_id}/change-requests` | admin | Success | 403 | 403 |
| POST | `/api/v1/tenants/{tenant_id}/change-requests` | admin | Success | 403 | 403 |
| GET | `/api/v1/tenants/{tenant_id}/change-requests/{request_id}/attachments/{attachment_id}` | admin | Success | 403 | 403 |
| GET | `/api/v1/tenants/{tenant_id}/quota` | viewer | Success | Success | Success |
| GET | `/api/v1/tenants/{tenant_id}/bots/{bot_id}/quota` | viewer | Success | Success | Success |
| POST | `/api/v1/tenants` | authenticated | Success | Success | Success |
| GET | `/api/v1/tenants/{tenant_id}` | viewer | Success | Success | Success |
| PATCH | `/api/v1/tenants/{tenant_id}` | admin | Success | 403 | 403 |
| GET | `/api/v1/tenants/{tenant_id}/members` | admin | Success | 403 | 403 |
| PATCH | `/api/v1/tenants/{tenant_id}/members/{user_id}` | admin | Success | 403 | 403 |
| DELETE | `/api/v1/tenants/{tenant_id}/members/{user_id}` | admin | Success | 403 | 403 |
| POST | `/api/v1/tenants/{tenant_id}/invitations` | admin | Success | 403 | 403 |
| GET | `/api/v1/tenants/{tenant_id}/invitations` | admin | Success | 403 | 403 |
| POST | `/api/v1/tenants/{tenant_id}/invitations/{invitation_id}/resend` | admin | Success | 403 | 403 |
| DELETE | `/api/v1/tenants/{tenant_id}/invitations/{invitation_id}` | admin | Success | 403 | 403 |
| GET | `/api/v1/tenants/{tenant_id}/data/export` | admin | Success | 403 | 403 |
| GET | `/api/v1/tenants/{tenant_id}/data/audit` | admin | Success | 403 | 403 |
| GET | `/api/v1/tenants/{tenant_id}/data/deletion-preview` | platform_staff_only | 403 | 403 | 403 |
| DELETE | `/api/v1/tenants/{tenant_id}/data` | platform_staff_only | 403 | 403 | 403 |
| POST | `/api/v1/tenants/{tenant_id}/bots` | platform_staff_only | 403 | 403 | 403 |
| GET | `/api/v1/tenants/{tenant_id}/bots` | viewer | Success | Success | Success |
| GET | `/api/v1/tenants/{tenant_id}/bots/{bot_id}` | viewer | Success | Success | Success |
| PATCH | `/api/v1/tenants/{tenant_id}/bots/{bot_id}` | platform_staff_only | 403 | 403 | 403 |
| DELETE | `/api/v1/tenants/{tenant_id}/bots/{bot_id}` | platform_staff_only | 403 | 403 | 403 |
| GET | `/api/v1/tenants/{tenant_id}/bots/{bot_id}/sources` | admin | Success | 403 | 403 |
| GET | `/api/v1/tenants/{tenant_id}/bots/{bot_id}/sources/qa-template` | admin | Success | 403 | 403 |
| POST | `/api/v1/tenants/{tenant_id}/bots/{bot_id}/sources/files` | platform_staff_only | 403 | 403 | 403 |
| GET | `/api/v1/tenants/{tenant_id}/bots/{bot_id}/sources/{source_id}` | admin | Success | 403 | 403 |
| POST | `/api/v1/tenants/{tenant_id}/bots/{bot_id}/ingestion` | platform_staff_only | 403 | 403 | 403 |
| GET | `/api/v1/tenants/{tenant_id}/bots/{bot_id}/jobs` | admin | Success | 403 | 403 |
| GET | `/api/v1/tenants/{tenant_id}/bots/{bot_id}/jobs/{job_id}` | admin | Success | 403 | 403 |
| POST | `/api/v1/tenants/{tenant_id}/bots/{bot_id}/jobs/{job_id}/cancel` | platform_staff_only | 403 | 403 | 403 |
| POST | `/api/v1/tenants/{tenant_id}/bots/{bot_id}/jobs/{job_id}/retry` | platform_staff_only | 403 | 403 | 403 |
| GET | `/api/v1/tenants/{tenant_id}/bots/{bot_id}/documents` | admin | Success | 403 | 403 |
| GET | `/api/v1/tenants/{tenant_id}/bots/{bot_id}/documents/{document_id}/chunks` | admin | Success | 403 | 403 |
| GET | `/api/v1/tenants/{tenant_id}/bots/{bot_id}/revisions` | admin | Success | 403 | 403 |
| POST | `/api/v1/tenants/{tenant_id}/bots/{bot_id}/revisions/{revision_id}/publish` | platform_staff_only | 403 | 403 | 403 |
| POST | `/api/v1/tenants/{tenant_id}/bots/{bot_id}/playground/messages` | platform_staff_only | 403 | 403 | 403 |
| GET | `/api/v1/tenants/{tenant_id}/bots/{bot_id}/playground/conversation` | platform_staff_only | 403 | 403 | 403 |
| POST | `/api/v1/tenants/{tenant_id}/bots/{bot_id}/messages/{message_id}/feedback` | platform_staff_only | 403 | 403 | 403 |
| GET | `/api/v1/tenants/{tenant_id}/bots/{bot_id}/conversations` | viewer | Success | Success | Success |
| GET | `/api/v1/tenants/{tenant_id}/bots/{bot_id}/conversations/{conversation_id}` | viewer | Success | Success | Success |
| DELETE | `/api/v1/tenants/{tenant_id}/bots/{bot_id}/conversations/{conversation_id}` | admin | Success | 403 | 403 |
| GET | `/api/v1/tenants/{tenant_id}/follow-ups` | viewer | Success | Success | Success |
| POST | `/api/v1/tenants/{tenant_id}/follow-ups` | editor | Success | Success | 403 |
| DELETE | `/api/v1/tenants/{tenant_id}/follow-ups/{follow_up_id}` | editor | Success | Success | 403 |
| GET | `/api/v1/tenants/{tenant_id}/contacts` | viewer | Success | Success | Success |
| POST | `/api/v1/tenants/{tenant_id}/contacts` | editor | Success | Success | 403 |
| GET | `/api/v1/tenants/{tenant_id}/contacts/stages` | viewer | Success | Success | Success |
| PATCH | `/api/v1/tenants/{tenant_id}/contacts/stages` | admin | Success | 403 | 403 |
| GET | `/api/v1/tenants/{tenant_id}/contacts/export.csv` | admin | Success | 403 | 403 |
| POST | `/api/v1/tenants/{tenant_id}/contacts/{contact_id}/merge` | admin | Success | 403 | 403 |
| GET | `/api/v1/tenants/{tenant_id}/contacts/{contact_id}` | viewer | Success | Success | Success |
| PATCH | `/api/v1/tenants/{tenant_id}/contacts/{contact_id}` | editor | Success | Success | 403 |
| DELETE | `/api/v1/tenants/{tenant_id}/contacts/{contact_id}` | admin | Success | 403 | 403 |
| GET | `/api/v1/tenants/{tenant_id}/conversations/{conversation_id}` | viewer | Success | Success | Success |
| POST | `/api/v1/tenants/{tenant_id}/conversations/{conversation_id}/takeover` | editor | Success | Success | 403 |
| POST | `/api/v1/tenants/{tenant_id}/conversations/{conversation_id}/return-to-ai` | editor | Success | Success | 403 |
| POST | `/api/v1/tenants/{tenant_id}/conversations/{conversation_id}/resolve` | editor | Success | Success | 403 |
| POST | `/api/v1/tenants/{tenant_id}/conversations/{conversation_id}/assign` | editor | Success | Success | 403 |
| POST | `/api/v1/tenants/{tenant_id}/conversations/{conversation_id}/messages` | editor | Success | Success | 403 |
| POST | `/api/v1/tenants/{tenant_id}/conversations/{conversation_id}/notes` | editor | Success | Success | 403 |
| GET | `/api/v1/tenants/{tenant_id}/inbox` | viewer | Success | Success | Success |
| GET | `/api/v1/tenants/{tenant_id}/inbox/counts` | viewer | Success | Success | Success |
| POST | `/api/v1/tenants/{tenant_id}/inbox/{conversation_id}/read` | editor | Success | Success | 403 |
| POST | `/api/v1/tenants/{tenant_id}/inbox/{conversation_id}/tags` | editor | Success | Success | 403 |
| DELETE | `/api/v1/tenants/{tenant_id}/inbox/{conversation_id}/tags/{tag}` | editor | Success | Success | 403 |
| GET | `/api/v1/tenants/{tenant_id}/inbox/events` | viewer | Success | Success | Success |
| GET | `/api/v1/tenants/{tenant_id}/bots/{bot_id}/analytics/summary` | viewer | Success | Success | Success |
| GET | `/api/v1/tenants/{tenant_id}/bots/{bot_id}/analytics/volume` | viewer | Success | Success | Success |
| GET | `/api/v1/tenants/{tenant_id}/bots/{bot_id}/analytics/top-questions` | viewer | Success | Success | Success |
| GET | `/api/v1/tenants/{tenant_id}/bots/{bot_id}/analytics/unanswered` | viewer | Success | Success | Success |
| GET | `/api/v1/tenants/{tenant_id}/bots/{bot_id}/analytics/leads` | viewer | Success | Success | Success |
| GET | `/api/v1/tenants/{tenant_id}/bots/{bot_id}/analytics/conversations.csv` | admin | Success | 403 | 403 |
| GET | `/api/v1/tenants/{tenant_id}/bots/{bot_id}/analytics/leads.csv` | admin | Success | 403 | 403 |
| GET | `/api/v1/tenants/{tenant_id}/analytics` | viewer | Success | Success | Success |

All /api/v1/platform routes declare platform_staff_only and deny each client role; existing platform tests verify successful staff operations. Public/widget/auth capability contracts remain separate from tenant roles.

## Validation

The final API sweep ran every test file separately, followed by scoped rechecks of failed files. All **278 tests across 37 files pass** on the latest result for each file. Initial failures and all exact commands remain in PROGRESS.md; this is not a claim that the first sweep was green. Test databases were disposable local PostgreSQL databases only. The test helper now forces collapsed retry backoffs into the past, avoiding database/application clock timing in tests; production job timing is unchanged.

| Pytest file | Latest result |
|---|---|
| `tests/eval/test_eval.py` | 2 passed, 1 warning in 12.93s |
| `tests/test_analytics.py` | 6 passed, 1 warning in 84.35s (0:01:24) |
| `tests/test_auth.py` | 15 passed, 1 warning in 7.39s |
| `tests/test_bot_status.py` | 5 passed, 1 warning in 54.37s |
| `tests/test_bots.py` | 4 passed, 1 warning in 1.79s |
| `tests/test_change_requests.py` | 1 passed, 1 warning in 1.39s |
| `tests/test_chat.py` | 15 passed, 1 warning in 145.42s (0:02:25) |
| `tests/test_contacts.py` | 1 passed, 1 warning in 11.86s |
| `tests/test_conversations.py` | 13 passed, 1 warning in 147.42s (0:02:27) |
| `tests/test_conversations_view.py` | 5 passed, 1 warning in 59.99s |
| `tests/test_cross_script.py` | 3 passed, 1 warning in 30.20s |
| `tests/test_database_guard.py` | 5 passed, 1 warning in 0.81s |
| `tests/test_followups_analytics.py` | 2 passed, 1 warning in 22.03s |
| `tests/test_handoff.py` | 5 passed, 1 warning in 48.48s |
| `tests/test_health.py` | 6 passed, 1 warning in 1.16s |
| `tests/test_inbox_list.py` | 5 passed, 1 warning in 16.76s |
| `tests/test_invitations.py` | 6 passed, 1 warning in 2.83s |
| `tests/test_jobs.py` | 8 passed, 1 warning in 1.34s |
| `tests/test_knowledge_parsers.py` | 27 passed, 1 warning in 13.64s |
| `tests/test_knowledge_pipeline.py` | 9 passed, 1 warning in 32.91s |
| `tests/test_knowledge_uploads.py` | 19 passed, 1 warning in 35.52s |
| `tests/test_members.py` | 5 passed, 1 warning in 3.11s |
| `tests/test_migrations.py` | 1 passed, 1 warning in 3.34s |
| `tests/test_models_constraints.py` | 13 passed, 1 warning in 1.48s |
| `tests/test_platform.py` | 9 passed, 1 warning in 97.74s (0:01:37) |
| `tests/test_platform_ops.py` | 4 passed, 1 warning in 2.43s |
| `tests/test_quotas.py` | 10 passed, 1 warning in 15.87s |
| `tests/test_retrieval.py` | 9 passed, 1 warning in 89.37s (0:01:29) |
| `tests/test_seed_demo.py` | 21 passed, 1 warning in 6.11s |
| `tests/test_self_service_signup.py` | 4 passed, 1 warning in 1.87s |
| `tests/test_startup_guard.py` | 5 passed, 1 warning in 0.97s |
| `tests/test_tenant_data.py` | 2 passed, 1 warning in 2.02s |
| `tests/test_tenant_route_matrix.py` | 5 passed, 1 warning in 41.88s |
| `tests/test_tenants.py` | 6 passed, 1 warning in 2.07s |
| `tests/test_widget_appearance.py` | 3 passed, 1 warning in 31.03s |
| `tests/test_widget_leads.py` | 5 passed, 1 warning in 60.06s (0:01:00) |
| `tests/test_widget_public.py` | 14 passed, 1 warning in 142.42s (0:02:22) |

The full browser run completed with **37 passed, 3 failed (7.2m)**. Scoped rechecks corrected the isolation caller fixture and triage selector, and verified the protected-page signed-out redirect. That redirect fix initially included the public invitation page; it has been narrowed to workspace/platform paths. The final focused invitation recheck passed **2/2 (1.1m)**. All **40 browser scenarios** have passing latest results across the full run and scoped rechecks. No full suite was repeated after these fixes.

| Playwright file | Latest result |
|---|---|
| `tests/contacts.spec.ts` | 1 passed |
| `tests/conversations.spec.ts` | 2 passed |
| `tests/dashboard.spec.ts` | 5 passed across scoped rechecks (invitation journey: final build) |
| `tests/followups.spec.ts` | 1 passed |
| `tests/foundation.spec.ts` | 1 passed |
| `tests/install.spec.ts` | 1 passed |
| `tests/knowledge.spec.ts` | 4 passed |
| `tests/overview.spec.ts` | 2 passed on scoped recheck (initial full run: 1 failed, 1 passed) |
| `tests/platform.spec.ts` | 2 passed |
| `tests/playground.spec.ts` | 3 passed across scoped rechecks (viewer invitation journey: final build) |
| `tests/roles-control.spec.ts` | 2 passed on scoped recheck (initial full run: 1 failed, 1 passed) |
| `tests/security-headers.spec.ts` | 2 passed |
| `tests/ui-characterization.spec.ts` | 6 passed |
| `tests/ui-redesign.spec.ts` | 4 passed |
| `tests/widget.spec.ts` | 4 passed |

The deferred `ECONNRESET` appeared in `tests/overview.spec.ts` during **unanswered list shows the question the bot could not confirm**, on the Next proxy's `/api/v1/auth/me` request. That test passed; no flake fix was attempted.


Web ESLint and TypeScript passed (including a scoped lint check and typecheck after the session/test fixes) (`npm.cmd run lint`, `npm.cmd run typecheck`). Changed Python files passed Ruff. Repository-wide Ruff has existing violations in untouched code. Python mypy could not run because Windows Application Control blocked its dependency DLL.


## Limits

- Python mypy is UNVERIFIED: Windows Application Control blocks its ast_serialize DLL. No security control was bypassed.
- No production migration, real provider API, cloud resource, push or deployment was used. Apply migration 0013 before deploying the changed application. Downgrade restores schema compatibility but does not restore former owner roles or the retired demo-owner login; data rollback requires the appropriate backup.
- Existing onboarding payload field names owner_email/owner_invite are retained for compatibility; their membership/invitation role is admin.
- Request lists currently show the latest 200 records. No email notifications or automatic execution of requested changes is included.
- Channel connections and per-channel analytics filtering are deferred to the owner-approved Phase 3 scope.
- Staff without client membership can control bots and read client data; inbox actions require an active client membership.

## Files changed

- `DECISIONS.md`
- `PROGRESS.md`
- `apps/api/alembic/versions/0013_roles_operator_control.py`
- `apps/api/app/auth/router.py`
- `apps/api/app/auth/schemas.py`
- `apps/api/app/auth/service.py`
- `apps/api/app/bots/router.py`
- `apps/api/app/chat/router.py`
- `apps/api/app/conversations/router.py`
- `apps/api/app/core/config.py`
- `apps/api/app/core/permissions.py`
- `apps/api/app/core/tenancy.py`
- `apps/api/app/db/models/__init__.py`
- `apps/api/app/db/models/core.py`
- `apps/api/app/db/models/operations.py`
- `apps/api/app/inbox/listing.py`
- `apps/api/app/knowledge/router.py`
- `apps/api/app/knowledge/storage.py`
- `apps/api/app/main.py`
- `apps/api/app/platform/staff.py`
- `apps/api/app/provisioning/service.py`
- `apps/api/app/tenants/changes.py`
- `apps/api/app/tenants/data.py`
- `apps/api/app/tenants/deletion.py`
- `apps/api/app/tenants/router.py`
- `apps/api/app/tenants/schemas.py`
- `apps/api/app/tenants/service.py`
- `apps/api/app/widget/service.py`
- `apps/api/app/worker/__main__.py`
- `apps/api/scripts/seed_demo.py`
- `apps/api/tests/helpers.py`
- `apps/api/tests/knowledge_helpers.py`
- `apps/api/tests/test_analytics.py`
- `apps/api/tests/test_auth.py`
- `apps/api/tests/test_bot_status.py`
- `apps/api/tests/test_bots.py`
- `apps/api/tests/test_change_requests.py`
- `apps/api/tests/test_contacts.py`
- `apps/api/tests/test_conversations.py`
- `apps/api/tests/test_conversations_view.py`
- `apps/api/tests/test_followups_analytics.py`
- `apps/api/tests/test_handoff.py`
- `apps/api/tests/test_inbox_list.py`
- `apps/api/tests/test_invitations.py`
- `apps/api/tests/test_knowledge_pipeline.py`
- `apps/api/tests/test_knowledge_uploads.py`
- `apps/api/tests/test_members.py`
- `apps/api/tests/test_migrations.py`
- `apps/api/tests/test_models_constraints.py`
- `apps/api/tests/test_platform.py`
- `apps/api/tests/test_platform_ops.py`
- `apps/api/tests/test_quotas.py`
- `apps/api/tests/test_seed_demo.py`
- `apps/api/tests/test_self_service_signup.py`
- `apps/api/tests/test_tenant_data.py`
- `apps/api/tests/test_tenant_route_matrix.py`
- `apps/api/tests/test_tenants.py`
- `apps/api/tests/test_widget_appearance.py`
- `apps/api/tests/test_widget_public.py`
- `apps/web/app/app/[tenant]/bots/[botId]/conversations/page.tsx`
- `apps/web/app/app/[tenant]/bots/[botId]/install/page.tsx`
- `apps/web/app/app/[tenant]/bots/[botId]/knowledge/page.tsx`
- `apps/web/app/app/[tenant]/bots/[botId]/playground/page.tsx`
- `apps/web/app/app/[tenant]/bots/[botId]/settings/page.tsx`
- `apps/web/app/app/[tenant]/inbox/[conversation]/page.tsx`
- `apps/web/app/app/[tenant]/page.tsx`
- `apps/web/app/app/[tenant]/settings/data/page.tsx`
- `apps/web/app/app/[tenant]/settings/members/page.tsx`
- `apps/web/app/app/[tenant]/settings/requests/page.tsx`
- `apps/web/app/platform/change-requests/page.tsx`
- `apps/web/app/platform/clients/[clientId]/page.tsx`
- `apps/web/app/platform/page.tsx`
- `apps/web/app/register/page.tsx`
- `apps/web/lib/api.ts`
- `apps/web/lib/app-header.tsx`
- `apps/web/lib/bot-workspace-nav.tsx`
- `apps/web/lib/change-requests.tsx`
- `apps/web/lib/session.tsx`
- `apps/web/screenshots/capture.spec.ts`
- `apps/web/tests/contacts.spec.ts`
- `apps/web/tests/dashboard.spec.ts`
- `apps/web/tests/e2e-helpers.ts`
- `apps/web/tests/install.spec.ts`
- `apps/web/tests/knowledge.spec.ts`
- `apps/web/tests/overview.spec.ts`
- `apps/web/tests/platform.spec.ts`
- `apps/web/tests/playground.spec.ts`
- `apps/web/tests/roles-control.spec.ts`
- `apps/web/tests/staff-helpers.ts`
- `apps/web/tests/ui-characterization.spec.ts`
- `apps/web/tests/ui-redesign.spec.ts`
- `apps/web/tests/widget.spec.ts`
- `docs/06-AUTHORIZATION-AND-SECURITY.md`
- `docs/18-EXPECTED-BEHAVIOUR.md`
- `implementation/DEMO-SEED.md`
- `implementation/MANUAL-TEST.md`
- `implementation/PHASE-01/ROLES-OPERATOR-REPORT.md`
