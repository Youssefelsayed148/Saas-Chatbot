# P3-01 REPORT — retrieval service (docs/14 §1, §2, §5)

Date: 2026-10-13. Status: DONE, locally verified.

## Query builder (`app/retrieval/query.py`)

- Tokenise `\\w+` (Unicode), lowercase, drop 1-char tokens and the stop-word lists (English + Arabic; Arabic possessives/everyday stop words included — «لديكم/لدينا/متى/كيف…»); OR-join into a `to_tsquery` string.
- **Arabic**: the question is ARABIC-NORMALISED BEFORE tokenising (diacritics would shatter `\\w` tokens — regression found by the eval, fixed); tokens matched against the normalised column with the `simple` config, adding the با-ال variants (with **and** without the leading «ال», both with `:*` prefixes so بحث عن «أسئلة» matches «الأسئلة الشائعة» and a bare verb matches its conjugated form via `تفتح:*` → «تفتحون»).
- English: `to_tsquery('english', …)` over `fts_en` (english config over title+heading+text).

## Service (`app/retrieval/service.py`)

- One pass = always filter **tenant + bot + published revision + language**, query the pre-indexed GIN tsvector column (NEVER recomputes `to_tsvector` on chunk text — docs/14 §5), rank `ts_rank_cd` with `priority DESC` then order tie-breaks, keep **one best chunk per document** (`DISTINCT ON`), `top_k=8`.
- **Evidence shaping**: the best document is included WHOLE (may exceed the soft budget, capped by `max_evidence_chunks=8`); lower-ranked chunks join while they fit `final_k=4`; **small documents (total text ≤ 1500 chars) join whole only when they fit** (never split a rule from its conditions).
- **Cross-language fallback (ADR-014)**: question-language pass first; on zero hits a second pass runs with the bot's primary content language; `used_fallback` is surfaced to the chat service.
- **Always-include documents** (per-bot reserved slots, e.g. a contact page) join whole, ahead of ranked hits, bounded by the same hard cap.
- No embeddings, no vector column, no thresholds/boosts (ADR-005/§1).

## Tests (9, `tests/test_retrieval.py`)

Corpus seeded through the REAL ingest pipeline (EN hours + returns + AR FAQ + Q&A CSV; a decoy bot in the same tenant with its own published copy, an identical corpus in tenant B, and an unpublished "changed" draft — each filter has a decoy that would match if that filter were removed):
- tenants/bot/revision/language filters each hold (every filter violated by one decoy; a SQL join verifies every returned chunk lives in the exact tenant+bot+revision+language scope);
- Arabic normalisation + «ال» variants + `:*` prefix (diacritised and conjugated questions match);
- cross-language fallback returns the EN document for an AR-tagged bilingual question;
- best-document-whole / small-document-whole / budget / reserved-slot rules;
- `to_tsquery` builder unit rules (stop words, empty queries, deduping).

`text_norm` fix bundled with this ticket: the normalised Arabic text stored on chunks now covers **title + heading + body** (docs/14 §4: indexed text) so Arabic heading words (e.g. «ساعات العمل») match; earlier body-only normation missed them. Dedupe/no-op/reingest tests were re-run green after the change.

Commands: Linux checks image + Windows venv — ruff/format/mypy/pytest all green.
