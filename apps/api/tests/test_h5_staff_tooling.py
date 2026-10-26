"""H5: draft preview (staff playground only), playground quota hygiene, Premium
fallback models, the widget poll hint and PDF page-break context.

Stub / mocked-HTTP models only; nothing here reads a key or calls a provider.
"""

import json
from datetime import UTC, datetime, timedelta
from typing import Any, cast
from uuid import UUID

import httpx
import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from pydantic import SecretStr, ValidationError
from sqlalchemy import select, text
from sqlalchemy.orm import Session as OrmSession

import tests.retrieval_helpers as _rh  # noqa: F401 - registers the corpus fixture
from app.chat.conversations import (
    get_or_create_conversation_for_session,
    resolve_preview_revision,
    visitor_chat_turn,
)
from app.chat.models import model_from_settings
from app.chat.providers import ExtractiveStubModel, OpenAICompatibleModel, ProviderError
from app.chat.streaming import evidence_ids
from app.core.config import Settings, get_settings
from app.core.errors import ApiError
from app.db.models import Bot, Conversation, FollowUp, Tenant, UsageEvent, VisitorSession
from app.knowledge.chunking import (
    page_break_splits_sentence,
    split_text,
    trailing_sentence,
)
from app.quotas.rag import monthly_usage
from app.quotas.service import usage_snapshot
from app.retrieval.hybrid import retrieve_hybrid
from app.widget.service import check_daily_message_quota, session_poll_hint
from tests.helpers import csrf_headers
from tests.knowledge_helpers import drain_jobs, start_ingestion, upload_sources
from tests.retrieval_helpers import TMP, retrieval_settings
from tests.test_chat import answer
from tests.test_widget_public import (
    _locator_of,
    _set_bot_status,
    client_session,
    rate_limited_settings,
)

corpus = _rh.corpus

DRAFT_ONLY = (
    "---\ntitle: Zephyr club\nsource_url: https://draft.example.com/zephyr\n"
    "language: en\npage_type: faq\n---\n\n"
    "# Zephyr club\n\n"
    "Members of the Zephyr club receive five percent cashback on every purchase.\n"
)
DRAFT_QUESTION = "How much cashback does the Zephyr club give?"
PUBLISHED_QUESTION = "What are your opening hours?"


def _engine() -> Any:
    from app.db.session import get_engine

    return get_engine()


@pytest.fixture
def draft_corpus(app: FastAPI, db: OrmSession, corpus: dict[str, Any]) -> dict[str, Any]:
    """The retrieval corpus plus a draft-only page (never published) on bot_main."""
    users = corpus["users_a"]
    upload = upload_sources(users, corpus["bot_main"], [("zephyr.md", DRAFT_ONLY.encode())], TMP)
    assert upload.status_code == 201, upload.text
    assert start_ingestion(users, corpus["bot_main"]).status_code == 202
    drain_jobs(_engine(), TMP)
    db.expire_all()
    app.dependency_overrides[get_settings] = lambda: rate_limited_settings()
    return corpus


def playground(
    client: TestClient, tenant_id: Any, bot_id: str, question: str, knowledge: str | None = None
) -> Any:
    body: dict[str, Any] = {"text": question}
    if knowledge is not None:
        body["knowledge"] = knowledge
    return client.post(
        f"/api/v1/tenants/{tenant_id}/bots/{bot_id}/playground/messages",
        json=body,
        headers=csrf_headers(client),
    )


def trace_of(db: OrmSession, message_id: str) -> dict[str, Any]:
    event = db.scalar(select(UsageEvent).where(UsageEvent.external_key == f"message:{message_id}"))
    assert event is not None
    trace = cast("dict[str, Any]", event.payload["rag_trace"])
    return trace


def widget_turn(app: FastAPI, locator: str, question: str) -> Any:
    session = client_session(app, locator)
    return TestClient(app).post(
        f"/api/public/v1/sessions/{session['session_id']}/messages",
        json={"text": question},
        headers={"X-Session-Token": session["token"]},
    )


def activate_widget(db: OrmSession, users: Any, bot_id: str) -> str:
    _set_bot_status(db, users, bot_id=bot_id, status="active")
    return _locator_of(db, bot_id)


# --- 1. draft preview -----------------------------------------------------------


def test_playground_draft_answers_from_the_draft_and_published_does_not(
    app: FastAPI, db: OrmSession, draft_corpus: dict[str, Any]
) -> None:
    users = draft_corpus["users_a"]
    staff = users.as_user("staff")
    bot_id = draft_corpus["bot_main"]

    draft = playground(staff, users.tenant_id, bot_id, DRAFT_QUESTION, "draft")
    assert draft.status_code == 201, draft.text
    assert draft.json()["kind"] == "answer"
    draft_trace = trace_of(db, draft.json()["ai_message"]["id"])
    published = db.scalar(
        text("SELECT id FROM knowledge_revisions WHERE bot_id = CAST(:b AS uuid) AND status = :s"),
        {"b": bot_id, "s": "published"},
    )
    draft_id = db.scalar(
        text("SELECT id FROM knowledge_revisions WHERE bot_id = CAST(:b AS uuid) AND status = :s"),
        {"b": bot_id, "s": "draft"},
    )
    assert draft_trace["revision_kind"] == "draft"
    assert draft_trace["revision_id"] == str(draft_id) != str(published)

    # The default (and "published") choice never sees the draft-only page.
    for knowledge in (None, "published"):
        live = playground(staff, users.tenant_id, bot_id, DRAFT_QUESTION, knowledge)
        assert live.status_code == 201, live.text
        assert live.json()["kind"] == "cannot_confirm"
        live_trace = trace_of(db, live.json()["ai_message"]["id"])
        assert live_trace["revision_kind"] == "published"
        assert live_trace["revision_id"] == str(published)


def test_playground_draft_without_a_draft_is_a_clear_409(
    app: FastAPI, db: OrmSession, corpus: dict[str, Any]
) -> None:
    users = corpus["users_b"]  # bot_b was published; its draft was consumed by publishing
    app.dependency_overrides[get_settings] = lambda: rate_limited_settings()
    response = playground(
        users.as_user("staff"), users.tenant_id, corpus["bot_b"], PUBLISHED_QUESTION, "draft"
    )
    assert response.status_code == 409
    assert response.json()["error"]["code"] == "NO_DRAFT_REVISION"


def test_widget_never_answers_from_the_draft(
    app: FastAPI, db: OrmSession, draft_corpus: dict[str, Any]
) -> None:
    users = draft_corpus["users_a"]
    locator = activate_widget(db, users, draft_corpus["bot_main"])
    response = widget_turn(app, locator, DRAFT_QUESTION)
    assert response.status_code == 201, response.text
    assert response.json()["kind"] == "cannot_confirm"
    ai_id = response.json()["ai_message"]["id"]
    assert trace_of(db, ai_id)["revision_kind"] == "published"
    # And the same published answer is still served.
    ok = widget_turn(app, locator, PUBLISHED_QUESTION)
    assert ok.json()["kind"] == "answer"


def test_a_website_conversation_cannot_be_given_a_preview_revision(
    app: FastAPI, db: OrmSession, draft_corpus: dict[str, Any]
) -> None:
    users = draft_corpus["users_a"]
    bot = db.get(Bot, UUID(draft_corpus["bot_main"]))
    assert bot is not None
    draft_id = resolve_preview_revision(
        db, tenant_id=users.tenant_id, bot_id=bot.id, knowledge="draft"
    )
    assert draft_id is not None
    session = VisitorSession(
        tenant_id=users.tenant_id,
        bot_id=bot.id,
        token_hash="x" * 64,
        expires_at=datetime.now(UTC) + timedelta(minutes=5),
    )
    db.add(session)
    db.flush()
    conversation = get_or_create_conversation_for_session(db, bot=bot, visitor_session=session)
    with pytest.raises(ApiError) as caught:
        visitor_chat_turn(
            db,
            tenant_id=users.tenant_id,
            bot=bot,
            conversation=conversation,
            question=DRAFT_QUESTION,
            model=ExtractiveStubModel(),
            settings=draft_corpus["settings"],
            preview_revision_id=draft_id,
        )
    assert caught.value.status_code == 403
    db.rollback()


def test_preview_retrieval_accepts_only_this_bots_draft(
    db: OrmSession, draft_corpus: dict[str, Any]
) -> None:
    users_a, users_b = draft_corpus["users_a"], draft_corpus["users_b"]
    bot_main = UUID(draft_corpus["bot_main"])
    draft = resolve_preview_revision(
        db, tenant_id=users_a.tenant_id, bot_id=bot_main, knowledge="draft"
    )
    assert draft is not None
    settings = draft_corpus["settings"]

    def run(tenant_id: UUID, bot_id: UUID, revision: UUID) -> Any:
        return retrieve_hybrid(
            db,
            tenant_id=tenant_id,
            bot_id=bot_id,
            revision_id=revision,
            question=DRAFT_QUESTION,
            question_language="en",
            settings=settings,
            preview=True,
        )

    assert run(users_a.tenant_id, bot_main, draft).evidence  # own draft
    published = db.scalar(
        text(
            "SELECT id FROM knowledge_revisions "
            "WHERE bot_id = CAST(:b AS uuid) AND status = 'published'"
        ),
        {"b": str(bot_main)},
    )
    assert isinstance(published, UUID)
    assert not run(users_a.tenant_id, bot_main, published).evidence  # not a draft
    # Tenant B (and its bot) can never read tenant A's draft by guessing the id.
    assert not run(users_b.tenant_id, UUID(draft_corpus["bot_b"]), draft).evidence
    assert not run(users_b.tenant_id, bot_main, draft).evidence
    assert not run(users_a.tenant_id, UUID(draft_corpus["bot_decoy"]), draft).evidence


def test_tenant_b_cannot_preview_tenant_a_draft_over_http(
    app: FastAPI, db: OrmSession, draft_corpus: dict[str, Any]
) -> None:
    users_b = draft_corpus["users_b"]
    response = playground(
        users_b.as_user("staff"),
        users_b.tenant_id,
        draft_corpus["bot_main"],  # tenant A's bot id, B's path
        DRAFT_QUESTION,
        "draft",
    )
    assert response.status_code == 404


# --- 2. quota hygiene -----------------------------------------------------------


def test_playground_turns_do_not_count_toward_message_quotas(
    app: FastAPI, db: OrmSession, draft_corpus: dict[str, Any]
) -> None:
    users = draft_corpus["users_a"]
    staff = users.as_user("staff")
    bot_id = UUID(draft_corpus["bot_main"])
    for _ in range(3):
        assert (
            playground(staff, users.tenant_id, str(bot_id), PUBLISHED_QUESTION).status_code == 201
        )

    # The turns stay visible in staff usage with a source label ...
    events = db.scalars(
        select(UsageEvent).where(UsageEvent.bot_id == bot_id, UsageEvent.kind == "message")
    ).all()
    assert len(events) == 3 and {e.payload["source"] for e in events} == {"playground"}
    reservations = [
        row
        for row in db.scalars(
            select(UsageEvent).where(UsageEvent.bot_id == bot_id, UsageEvent.kind == "ai_usage")
        )
        if row.payload["event_type"] == "message"
    ]
    assert len(reservations) == 3
    assert all(row.payload.get("source") == "playground" for row in reservations)

    # ... but neither the tenant monthly counter, the per-bot counter nor the
    # per-bot daily cap sees them.
    tenant = db.get(Tenant, users.tenant_id)
    assert tenant is not None
    assert usage_snapshot(db, tenant)["usage"]["monthly_messages"] == 0
    assert monthly_usage(db, users.tenant_id, bot_id)["monthly_messages"] == 0
    bot = db.get(Bot, bot_id)
    assert bot is not None
    check_daily_message_quota(db, bot, Settings.model_construct(widget_daily_message_cap=1))

    # A widget (website) turn does count, in all three.
    locator = activate_widget(db, users, str(bot_id))
    assert widget_turn(app, locator, PUBLISHED_QUESTION).status_code == 201
    db.expire_all()
    assert usage_snapshot(db, tenant)["usage"]["monthly_messages"] == 1
    assert monthly_usage(db, users.tenant_id, bot_id)["monthly_messages"] == 1
    with pytest.raises(ApiError) as caught:
        check_daily_message_quota(db, bot, Settings.model_construct(widget_daily_message_cap=1))
    assert caught.value.status_code == 429


def test_playground_is_not_blocked_by_an_exhausted_message_quota(
    app: FastAPI, db: OrmSession, draft_corpus: dict[str, Any]
) -> None:
    users = draft_corpus["users_a"]
    bot_id = draft_corpus["bot_main"]
    db.execute(
        text("UPDATE bots SET rag_limits = CAST(:v AS jsonb) WHERE id = CAST(:b AS uuid)"),
        {"v": json.dumps({"monthly_messages": 0}), "b": bot_id},
    )
    db.commit()
    assert (
        playground(users.as_user("staff"), users.tenant_id, bot_id, PUBLISHED_QUESTION).status_code
        == 201
    )
    locator = activate_widget(db, users, bot_id)
    blocked = widget_turn(app, locator, PUBLISHED_QUESTION)
    assert blocked.status_code == 429 and blocked.json()["error"]["code"] == "QUOTA_EXCEEDED"


# --- 3. Premium fallback --------------------------------------------------------


def premium_settings(**overrides: Any) -> Settings:
    values: dict[str, Any] = {
        "chat_stub_model": False,
        "chat_openai_api_key": SecretStr("sk-test"),
        "chat_openai_model": "gpt-main",
        "chat_openai_fallback_models": ["gpt-backup", "gpt-last"],
        "chat_openrouter_api_key": SecretStr("or-test"),
        "chat_free_model_chain": ["a:free", "b:free"],
    }
    values.update(overrides)
    return Settings.model_construct(**values)


def premium_bot(**fields: Any) -> Bot:
    values: dict[str, Any] = {
        "generation_provider": "openai",
        "generation_model": None,
        "tier": "premium",
        "config": {},
    }
    values.update(fields)
    return Bot(**values)


def test_premium_model_gets_the_ordered_fallback_list() -> None:
    model = model_from_settings(premium_settings(), premium_bot())
    assert isinstance(model, OpenAICompatibleModel)
    assert model.model == "gpt-main" and model.fallback_models == ["gpt-backup", "gpt-last"]
    assert model.free_only is False
    # A per-bot model override is the primary; a fallback equal to it is dropped.
    override = model_from_settings(premium_settings(), premium_bot(generation_model="gpt-backup"))
    assert isinstance(override, OpenAICompatibleModel)
    assert override.model == "gpt-backup" and override.fallback_models == ["gpt-last"]


def test_standard_tier_keeps_the_free_only_guard_and_ignores_the_premium_list() -> None:
    standard = Bot(generation_provider="openrouter", generation_model=None, tier="standard")
    model = model_from_settings(premium_settings(), standard)
    assert isinstance(model, OpenAICompatibleModel)
    assert model.free_only is True and model.fallback_models == ["b:free"]
    with pytest.raises(ApiError) as caught:
        model_from_settings(
            premium_settings(chat_free_model_chain=["a:free", "paid-model"]), standard
        )
    assert caught.value.code == "MODEL_NOT_FREE"


@pytest.mark.parametrize(
    "value",
    [["a", "a"], [" "], ["has space"], ["a", "b", "c", "d"]],
)
def test_fallback_list_is_validated(value: list[str]) -> None:
    with pytest.raises(ValidationError):
        Settings.model_validate({"chat_openai_fallback_models": value})


def _two_model_client(
    first: httpx.Response | Exception, second: httpx.Response | Exception
) -> tuple[OpenAICompatibleModel, list[str]]:
    seen: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        name = json.loads(request.content)["model"]
        seen.append(name)
        outcome = first if name == "gpt-main" else second
        if isinstance(outcome, Exception):
            raise outcome
        if outcome.status_code == 200 and name != "gpt-main":
            ids = evidence_ids(json.loads(request.content)["messages"][0]["content"])
            content = json.dumps(
                {"can_answer": True, "sources": sorted(ids)[:1], "answer": "Open 9 to 5."}
            )
            return httpx.Response(
                200, json={"choices": [{"message": {"content": content}, "finish_reason": "stop"}]}
            )
        return outcome

    model = OpenAICompatibleModel(
        base_url="https://llm.test/v1",
        api_key="sk-secret",
        model="gpt-main",
        fallback_models=["gpt-backup"],
        free_only=False,
        transport=httpx.MockTransport(handler),
    )
    return model, seen


@pytest.mark.parametrize(
    "failure",
    [
        httpx.Response(500, json={"error": {"message": "boom"}}),
        httpx.Response(429, json={"error": {"code": "rate_limit_exceeded"}}),
        httpx.Response(404, json={"error": {"code": "model_not_found"}}),
        httpx.ReadTimeout("slow"),
    ],
)
def test_a_failed_primary_moves_to_the_fallback_one_attempt_each(
    failure: httpx.Response | Exception,
) -> None:
    model, seen = _two_model_client(failure, httpx.Response(200))
    text_out = model.complete([{"role": "user", "content": "hi"}], json_mode=False, max_tokens=50)
    assert text_out and seen == ["gpt-main", "gpt-backup"]
    assert [a["model"] for a in model.attempt_log] == ["gpt-main", "gpt-backup"]
    assert model.attempt_log[-1]["outcome"] == "ok" and model.requests_used == 2
    assert model.model_used == "gpt-backup" and model.blocked is False


@pytest.mark.parametrize("status", [401, 402])
def test_auth_and_payment_blocks_never_fall_back(status: int) -> None:
    model, seen = _two_model_client(httpx.Response(status, json={"error": {}}), httpx.Response(200))
    with pytest.raises(ProviderError):
        model.complete([{"role": "user", "content": "hi"}], json_mode=False, max_tokens=50)
    assert seen == ["gpt-main"] and model.blocked is True
    assert model.attempt_log[0]["outcome"] == "blocked"
    with pytest.raises(ProviderError):  # still blocked for the rest of the turn
        model.complete([{"role": "user", "content": "hi"}], json_mode=False, max_tokens=50)
    assert seen == ["gpt-main"]


@pytest.mark.parametrize("status", [401, 402])
def test_streaming_blocks_never_fall_back_either(status: int) -> None:
    model, seen = _two_model_client(httpx.Response(status, json={"error": {}}), httpx.Response(200))
    with pytest.raises(ProviderError):
        list(model.stream_complete([{"role": "user", "content": "hi"}], max_tokens=50))
    assert seen == ["gpt-main"] and model.blocked is True


def test_a_served_fallback_does_not_hand_off(db: OrmSession, corpus: dict[str, Any]) -> None:
    model, seen = _two_model_client(httpx.Response(500, json={}), httpx.Response(200))
    reply = answer(db, corpus, model, PUBLISHED_QUESTION, tier="premium")
    assert seen == ["gpt-main", "gpt-backup"]
    assert reply.kind == "answer" and reply.can_answer is True and reply.needs_human is False
    assert reply.trace.get("provider_error") is None
    assert reply.trace["model"] == "gpt-backup"

    blocked, _ = _two_model_client(httpx.Response(401, json={}), httpx.Response(200))
    failed = answer(db, corpus, blocked, PUBLISHED_QUESTION, tier="premium")
    assert failed.kind == "busy" and failed.trace["provider_error"]["http_status"] == 401


# --- 4. widget poll hint --------------------------------------------------------


def test_poll_hint_follows_handoff_and_scheduled_follow_ups(
    app: FastAPI, db: OrmSession, draft_corpus: dict[str, Any]
) -> None:
    users = draft_corpus["users_a"]
    locator = activate_widget(db, users, draft_corpus["bot_main"])
    session = client_session(app, locator)
    client = TestClient(app)
    headers = {"X-Session-Token": session["token"]}
    url = f"/api/public/v1/sessions/{session['session_id']}/messages"

    def hint() -> str:
        response = client.get(url, headers=headers)
        assert response.status_code == 200
        return str(response.headers["X-Poll-Hint"])

    assert hint() == "idle"  # no conversation yet
    assert widget_turn_on(client, session, PUBLISHED_QUESTION).status_code == 201
    assert hint() == "idle"  # a plain AI answer: nothing more can arrive

    visitor = db.get(VisitorSession, UUID(session["session_id"]))
    assert visitor is not None
    conversation = db.scalar(select(Conversation).where(Conversation.session_id == visitor.id))
    assert conversation is not None
    conversation.mode, conversation.status = "human", "waiting_human"
    db.commit()
    assert hint() == "active"
    assert session_poll_hint(db, visitor_session=visitor) == "active"

    conversation.mode, conversation.status = "ai", "open"
    db.commit()
    assert hint() == "idle"
    follow_up = FollowUp(
        tenant_id=conversation.tenant_id,
        bot_id=conversation.bot_id,
        conversation_id=conversation.id,
        text="We will call you",
        send_at=datetime.now(UTC) + timedelta(hours=1),
        status="scheduled",
    )
    db.add(follow_up)
    db.commit()
    assert hint() == "active"
    follow_up.status = "delivered"
    db.commit()
    assert hint() == "idle"


def widget_turn_on(client: TestClient, session: dict[str, Any], question: str) -> Any:
    return client.post(
        f"/api/public/v1/sessions/{session['session_id']}/messages",
        json={"text": question},
        headers={"X-Session-Token": session["token"]},
    )


# --- 5. PDF page-break context --------------------------------------------------


def test_page_break_detection() -> None:
    assert page_break_splits_sentence("The warranty covers parts and", "labour for two years.")
    assert not page_break_splits_sentence("It ends here.", "labour for two years.")
    assert not page_break_splits_sentence("It ends here?", "labour")
    assert not page_break_splits_sentence("A heading without a stop", "Next Section Title")
    assert not page_break_splits_sentence("A list item", "1. Next item")
    assert not page_break_splits_sentence("", "labour")
    assert page_break_splits_sentence("ساعات العمل من التاسعة", "حتى الخامسة مساء.")
    assert not page_break_splits_sentence("انتهت الجملة؟", "حتى الخامسة")


def test_trailing_sentence_is_the_unfinished_tail() -> None:
    page = "First sentence. Second sentence. The warranty covers parts and"
    assert trailing_sentence(page) == "The warranty covers parts and"
    long_tail = "word " * 200
    carried = trailing_sentence(long_tail, max_chars=40)
    assert len(carried) <= 40 and not carried.startswith("ord")  # cut on a word boundary
    assert trailing_sentence("") == ""


def _plan(pages: list[str]) -> list[Any]:
    from types import SimpleNamespace

    from app.knowledge.ingest import plan_source
    from app.knowledge.parsing import ParsedPage, ParsedSection

    parsed = [
        ParsedPage(
            page_number=index,
            title=f"doc.pdf — Page {index}",
            text=page,
            sections=[ParsedSection(heading=None, text=page)],
        )
        for index, page in enumerate(pages, start=1)
    ]
    source = SimpleNamespace(kind="pdf")
    bot = SimpleNamespace(config={"default_language": "en"})
    _, documents = plan_source(source, parsed, bot, retrieval_settings())  # type: ignore[arg-type]
    return documents


def test_pdf_chunk_carries_the_split_sentence_and_keeps_its_own_page() -> None:
    documents = _plan(
        [
            "Intro line. The warranty covers parts and",
            "labour for two full years from purchase.",
        ]
    )
    second = documents[1]
    assert second.page_ref == "Page 2"  # the citation stays the page the text is on
    assert second.chunks[0].text.startswith("The warranty covers parts and labour")
    assert second.text == "labour for two full years from purchase."  # page text unchanged
    assert documents[0].chunks[0].text == "Intro line. The warranty covers parts and"


def test_pdf_pages_with_clean_breaks_are_not_changed() -> None:
    documents = _plan(["The first page ends cleanly.", "labour starts lowercase here."])
    assert documents[1].chunks[0].text == "labour starts lowercase here."
    documents = _plan(["It stops mid", "Heading Case Starts A New Part."])
    assert documents[1].chunks[0].text == "Heading Case Starts A New Part."


def test_carry_only_prefixes_the_first_chunk_of_a_long_page() -> None:
    long_page = "labour " + "alpha beta gamma. " * 200
    documents = _plan(["Coverage includes parts and", long_page])
    chunks = documents[1].chunks
    assert len(chunks) > 1
    assert chunks[0].text.startswith("Coverage includes parts and labour")
    assert not any(chunk.text.startswith("Coverage") for chunk in chunks[1:])
    assert split_text("x", 10, 2) == ["x"]
