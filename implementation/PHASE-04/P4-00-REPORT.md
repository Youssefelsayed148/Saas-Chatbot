# P4-00 — P3 carry-overs (cross-script retrieval, environment guard, eval extension)

Evidence summary for the P4-00 checklist items. Exact commands and raw results live in
`PROGRESS.md` (per ticket execution notes).

## (1) Cross-script retrieval translation (ADR-014, docs/14 §2)

- `app/retrieval/service.py`: `retrieve()` accepts `translate_query: Callable[[str, str],
  str | None]`. When the question-language pass is empty and the question language differs
  from the bot's primary language, the fallback pass runs with the callback's translated
  query; any failure (and `None`) keeps the raw question. The applied query is recorded on
  `RetrievalResult.fallback_query`.
- `app/chat/service.py`: new `translate_query(model, question, target_language)` — ONE
  ChatModel call (`max_tokens=120`), single-line output guard, `ProviderError` swallowed.
  Independent of the conversation history, so it works on the FIRST message (condense()
  still returns None without history, and no condense call is made).
- The system prompt's user turn now appends a hint line with the fallback search query so
  the answer stays verifiable against the evidence it used (no template change — the
  versioned system template is untouched).

Tests (`tests/test_cross_script.py`, 3 passed):
- first-message Arabic over English-only content: the question-language pass is empty, the
  translate call runs exactly once, the fallback pass grounds the answer with citations
  and the reply language stays Arabic (`used_fallback is True`, exactly 1 non-json call).
- model failure (`FakeChatModel(raises=True)`): translate error swallowed, raw question
  runs the fallback pass, clean localized abstention (`cannot_confirm`).
- matching languages: no translate call at all (no history ⇒ no condense either).

## (2) Environment setting + production guard

- `Settings.environment` (`development|production|test`, default `development`).
- `app.core.config.validate_startup_settings()` raises `RuntimeError` when
  `chat_stub_model` is on and `environment=production`; `create_app()` calls it at startup.
- Tests (`tests/test_startup_guard.py`, 5 passed): production+stub refused by the
  validator AND by `create_app()` (monkeypatched settings); development/test + stub boot
  normally with a healthy `/health`.

## (3) Eval extension (docs/14 §10 evidence)

- `tests/eval/eval.jsonl` grew from 17 to 25 cases: +3 cross-language (English-only
  content, Arabic questions — the stub cannot translate, so each case carries a
  deterministic `stub_translation` stand-in exercised through the REAL translate-call
  path; a real-model rerun replaces it), +3 unanswerable, +2 prompt-injection cases whose
  directive lives INSIDE an uploaded document (`forbidden` phrases that must never appear
  in the reply).
- Corpus added: EN gift-wrapping page (target of the cross-language cases), an EN delivery
  page carrying an injected directive, and an AR support page carrying an Arabic directive.
- Runner injection verdict now checks case-declared forbidden phrases; cross-language
  verdict unchanged (used_fallback + grounded citations).
- Results (deterministic stub run, disposable DB `chatbot_dev_test`):
  grounded 8/8 (100% ≥ 90%), unanswerable 8/8 (100% ≥ 95%), injection 4/4 (100%),
  cross-language 3/5 — the 3 NEW cross-script cases pass; the 2 pre-existing
  bilingual-corpus cases remain the recorded P3 stub-run limitations (reproduced
  numerically in `implementation/PHASE-03/EVAL-REPORT.md`).
- **Real-model rerun: NOT PERFORMED — no OpenRouter key was provided for this session**
  (checked `.env` and the process environment; only database credentials are present).
  The generated `EVAL-REPORT.md` records this; the runner supports the rerun
  (`run_all(..., rerun_with_owner_key=True)` guarded by `CHAT_OPENROUTER_API_KEY`) so the
  numbers can be produced the moment a key is supplied — no paid call was made.

## Carried limitation

The 2 legacy bilingual cross-language cases trace to the same root: the Arabic question
shares content tokens with the Arabic corpus (e.g. `يوم`, prefix-matched) or drops the
bare-stem variant of a preposition-prefixed word («لاللسترجاع»),' so the same-language
hit/miss legitimately differs from the cross-script path. Real-model verification covers
them at the eval rerun.
