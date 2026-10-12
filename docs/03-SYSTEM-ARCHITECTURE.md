# Architecture — modular monolith, not microservices
## Deployable units
1. `apps/web`: one Next.js app: public pages, client dashboard (`/app/...`) and later a role-guarded `/platform` area.
2. `apps/api`: one FastAPI backend with logical modules (`auth`, `tenants`, `bots`, `knowledge`, `ingestion`, `chat`, `widget`, `analytics`, `usage`, `provisioning`, `admin`). Business rules live in `service.py`; routers are thin.
3. Background jobs (from P2): durable `jobs` table in PostgreSQL, claimed atomically with lease + retry, executed by `python -m app.worker` — the SAME codebase and image as the API, started as a second process only when needed (ADR-011). No Redis, no separate worker app.
4. PostgreSQL + pgvector: one database, one Alembic history. Uploaded files stored on a replaceable storage interface (local disk in dev; object storage decided at ADR-007).
5. `packages/widget` (P4): small compiled embeddable loader + iframe UI, versioned asset URL. No per-customer deployments.
## Boundaries
Web → authenticated API; widget → restricted public API; API/worker → Postgres; ingestion → policy-restricted fetcher; chat → LLM/embedding provider interfaces. No frontend DB access.
## Tenant isolation (ADR-010)
Every tenant-owned table has `tenant_id`; composite FKs `(tenant_id, id)` prevent cross-tenant references; every service function takes a tenant context validated against the caller's membership; hidden resources return 404. Jobs carry tenant + bot IDs and re-validate on execution. Retrieval always filters tenant + bot + published revision. Tests for tenant A vs B accompany every tenant-owned endpoint.
## Development vs production
Local Docker Compose: db, api, web (+ worker from P2). Production host, storage, mail and AI vendors are TBD (ADR-007). No Kubernetes, Kafka, service mesh or cross-product entitlements.
## Evolution triggers
Add Redis only when measured need appears. Add object storage before retaining large uploads in production. Add a dedicated crawler sandbox/egress policy before allowing arbitrary public URL import in production. Security controls are not deferred because deployment is simple.
