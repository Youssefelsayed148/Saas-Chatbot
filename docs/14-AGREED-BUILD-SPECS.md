# Agreed build specs
Behaviour the owner has specified in design review for parts that need exact parameters. The coding agent builds exactly what is written here; anything missing is TBD and the agent stops and asks. Add an entry (date, decision, rationale) as each spec is agreed. Nothing is copied from other repositories.

| Area | Spec | Status |
|---|---|---|
| File parsing (PDF, DOCX, TXT, MD, CSV) | libraries, per-format extraction rules, size limits | TBD (agree before P2-03) |
| Chunking | strategy, size, overlap, metadata kept per chunk | TBD (before P2-03) |
| Embeddings | model, dimension, batching, language handling (ADR-005) | TBD (before P2-02) |
| Retrieval | keyword + semantic search, score fusion, top-k, thresholds | TBD (before P3-01) |
| Answer generation | model/provider, prompt structure, citation format, abstention rule | TBD (before P3-02) |
| Analytics | metrics and views shown to clients | TBD (before P4-05) |
