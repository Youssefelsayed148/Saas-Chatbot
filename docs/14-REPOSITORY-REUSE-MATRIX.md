# Reuse matrix — what we take from Retrivo and Rabbit Hole
Both repos are owned by the product owner: no license review needed (ADR-012). They stay read-only references. We port LOGIC, never schema, branding, global state or credentials. Every port gets a row below (filled in during P2-01 and as each port happens).

| Source | Take (logic) | Leave behind |
|---|---|---|
| **Rabbit Hole** | Simple RAG pattern: search the docs locally instead of calling an embedding API; free-model reply flow; grounding/citation approach | Global tables, locks, branded prompts, anything single-tenant |
| **Retrivo** | Raw-data onboarding path: parsing, chunking, embeddings pipeline; hybrid (keyword) + semantic search; retrieval ranking; analytics views/metrics | Its full chatbot/UI/bot-management, legacy schema, brand data, untrusted fetch logic, global caches |
| **ManyOsirisChat** | Nothing in MVP | Everything (see docs/17) |

## Port record (one row per port — fill in P2-01 onward)
| # | Source repo + path + commit | Functionality | Dependencies / risks | Decision (port / adapt / rewrite / reject) | Target module | Test evidence |
|---|---|---|---|---|---|---|
| 1 | _TBD in P2-01_ | | | | | |

## Porting rules
1. Read the source file(s) fully before copying anything; note commit SHA.
2. Strip tenant-unaware globals; add `tenant_id`/`bot_id` and revision filters.
3. Add tests that fail if tenant filters are removed.
4. No credentials, prompts with client branding, or client data are copied.
5. Dependency additions (parsers, embedding libs) are recorded in DECISIONS.md.
