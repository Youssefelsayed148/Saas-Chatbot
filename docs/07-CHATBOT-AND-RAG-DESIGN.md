# Chatbot engine and RAG specification
## Runtime
Resolve tenant/bot from authenticated client request or public widget locator. Verify active bot and published knowledge revision. Normalize query, retrieve top candidate chunks with strict tenant/bot/revision filters, rerank if justified, construct source-bounded context, call configured model, validate citations, return answer or calibrated abstention. Store conversation and usage event with dedupe IDs.
## Quality
Answer only using authorized published content; distinguish direct evidence vs missing evidence; cite accessible source URLs; never fabricate prices, policies, inventory or contacts. Handle Arabic/English and mixed-language queries; evaluate on held-out grounded, unanswerable and prompt-injection cases. Record latency, retrieval hit rate, citation precision and cost per turn.
## Providers
Define LLMProvider and EmbeddingProvider interfaces; credentials from secret manager/environment, never tenant-visible. Provider/model/dimension and budgets are decisions, not defaults. Keep prompts versioned and per-bot configurable only within safe policy boundaries.
## Retrieval
Hybrid search: keyword (Postgres full-text) + semantic (pgvector) with score fusion, always filtered by tenant + bot + published revision. Embedding model and dimension: ADR-005 (open until P2-01); prefer local/Ollama over paid embedding APIs. First reply model: free model or Ollama behind `LLMProvider`.

## Specification status
Detailed retrieval, chunking and embedding parameters are agreed with the owner in design review and recorded in `docs/14-AGREED-BUILD-SPECS.md` before the ticket that needs them. Anything not yet recorded there is TBD: the agent stops and asks.
