"""R0: the dashboard playground behaves like the website widget.

One shared code path: buffered and streamed playground turns (and the widget)
end in ``visitor_chat_turn`` → ``chat_answer``. These tests pin the parity:
the same reconciliation of a model refusal, interleaved exchange history that
skips refused/failed turns, the new trace fields, per-user playground threads,
"New session" and the newest-100 thread read. Stub/scripted models only.
"""

import re
from collections.abc import Iterator
from typing import Any
from uuid import UUID

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import text
from sqlalchemy.orm import Session as OrmSession

import tests.retrieval_helpers as _rh  # noqa: F401 - registers the corpus fixture
from app.chat.conversations import append_message, messages_of
from app.chat.history import history_for_turn
from app.core.config import Settings
from app.db.models import Conversation
from tests.conftest import csrf_headers
from tests.retrieval_helpers import retrieval_settings
from tests.test_chat_streaming import ScriptedModel, chunks_of, parse_sse, reply_json
from tests.test_conversations import chat_ready_corpus, stub_enabled_app  # noqa: F401

corpus = _rh.corpus

QUESTION = "What does your warranty cover?"
OK_TEXT = "The warranty covers parts and labour for two years."
SECRET = "SECRET MODEL TEXT"


class RecordingModel(ScriptedModel):
    """Answers (``ok``) or refuses (``refuse``) per generation call, buffered and
    streamed alike, and records every generation prompt."""

    def __init__(self, modes: list[str]) -> None:
        super().__init__(self._script, buffered=self._buffered)
        self.modes = list(modes)
        self.calls: list[list[dict[str, str]]] = []
        self._next = "ok"

    def _reply(self, ids: list[str]) -> str:
        if self._next == "refuse":
            return reply_json(ids, SECRET, can_answer=False, cite=True)
        return reply_json(ids, OK_TEXT)

    def _script(self, ids: list[str]) -> list[str]:
        return chunks_of(self._reply(ids))

    def _buffered(self, ids: list[str]) -> str:
        return self._reply(ids)

    def _begin(self, messages: list[dict[str, str]]) -> None:
        self.calls.append([dict(message) for message in messages])
        self._next = self.modes.pop(0) if self.modes else "ok"

    def complete(self, messages: list[dict[str, str]], *, json_mode: bool, max_tokens: int) -> str:
        if json_mode:
            self._begin(messages)
        return super().complete(messages, json_mode=json_mode, max_tokens=max_tokens)

    def stream_complete(self, messages: list[dict[str, str]], *, max_tokens: int) -> Iterator[str]:
        self._begin(messages)
        return super().stream_complete(messages, max_tokens=max_tokens)


@pytest.fixture
def install_model(monkeypatch: pytest.MonkeyPatch) -> Any:
    def install(model: ScriptedModel) -> None:
        monkeypatch.setattr("app.chat.models.model_from_settings", lambda settings, bot=None: model)

    return install


def base_of(users: Any, bot_id: str) -> str:
    return f"/api/v1/tenants/{users.tenant_id}/bots/{bot_id}"


def buffered(client: TestClient, base: str, question: str = QUESTION) -> dict[str, Any]:
    response = client.post(
        f"{base}/playground/messages", json={"text": question}, headers=csrf_headers(client)
    )
    assert response.status_code == 201, response.text
    return dict(response.json())


def streamed(client: TestClient, base: str, question: str = QUESTION) -> dict[str, Any]:
    response = client.post(
        f"{base}/playground/messages/stream",
        json={"text": question},
        headers=csrf_headers(client),
    )
    assert response.status_code == 200, response.text
    events = parse_sse(response.text)
    assert events[-1][0] == "done" and "error" not in [name for name, _ in events]
    return dict(events[-1][1])


def shape(turn: dict[str, Any]) -> dict[str, Any]:
    ai = turn["ai_message"]
    return {
        "kind": turn["kind"],
        "text": ai["text"],
        "citations": ai["citations"],
        "can_answer": ai["can_answer"],
        "needs_human": ai["needs_human"],
    }


def traces_of(client: TestClient, base: str) -> dict[str, dict[str, Any]]:
    response = client.get(f"{base}/rag/traces")
    assert response.status_code == 200
    return {row["message_id"]: row["trace"] for row in response.json()["traces"]}


# --- reconciliation parity -----------------------------------------------------


def test_same_input_gives_the_same_reply_on_both_paths(
    stub_enabled_app: FastAPI,  # noqa: F811
    chat_ready_corpus: dict[str, Any],  # noqa: F811
    install_model: Any,
) -> None:
    users = chat_ready_corpus["users_a"]
    staff = users.as_user("staff")
    base = base_of(users, chat_ready_corpus["bot_main"])
    install_model(RecordingModel([]))
    first = buffered(staff, base)
    second = streamed(staff, base)
    assert first["kind"] == "answer" and shape(first) == shape(second)
    assert shape(first)["text"] == OK_TEXT and len(shape(first)["citations"]) == 1

    # The playground trace carries the same new fields for both turns.
    traces = traces_of(staff, base)
    left, right = (traces[turn["ai_message"]["id"]] for turn in (first, second))
    for key in (
        "prompt_version",
        "parsed_ok",
        "model_can_answer",
        "model_source_count",
        "kept_source_count",
        "reconciled",
    ):
        assert key in left and key in right
    assert left["parsed_ok"] is True and left["model_can_answer"] is True
    assert left["kept_source_count"] == right["kept_source_count"] == 1
    assert left["reconciled"] is False and right["reconciled"] is False
    assert left["history_count"] == 0 and right["history_count"] == 1
    assert "messages" not in left and "prompt" not in left  # no prompt text is stored


def test_model_refusal_with_sources_shows_no_sources_on_either_path(
    stub_enabled_app: FastAPI,  # noqa: F811
    chat_ready_corpus: dict[str, Any],  # noqa: F811
    install_model: Any,
) -> None:
    users = chat_ready_corpus["users_a"]
    staff = users.as_user("staff")
    base = base_of(users, chat_ready_corpus["bot_main"])
    install_model(RecordingModel(["refuse", "refuse"]))
    first = buffered(staff, base)
    second = streamed(staff, base)
    for turn in (first, second):
        assert turn["kind"] == "cannot_confirm"
        assert turn["ai_message"]["citations"] == []
        assert turn["ai_message"]["can_answer"] is False
        assert turn["ai_message"]["needs_human"] is True
        assert SECRET not in turn["ai_message"]["text"]
    assert shape(first) == shape(second)
    traces = traces_of(staff, base)
    for turn in (first, second):
        trace = traces[turn["ai_message"]["id"]]
        assert trace["reconciled"] is True
        assert trace["model_can_answer"] is False
        assert trace["kept_source_count"] == 0


# --- history shape -------------------------------------------------------------


def test_history_is_interleaved_skips_refusals_and_never_touches_evidence(
    stub_enabled_app: FastAPI,  # noqa: F811
    chat_ready_corpus: dict[str, Any],  # noqa: F811
    install_model: Any,
) -> None:
    users = chat_ready_corpus["users_a"]
    staff = users.as_user("staff")
    base = base_of(users, chat_ready_corpus["bot_main"])
    model = RecordingModel(["ok", "refuse", "ok", "ok", "ok", "ok"])
    install_model(model)
    send = [buffered, buffered, streamed, buffered, streamed, buffered]
    for call in send:
        call(staff, base)
    assert len(model.calls) == 6

    def roles(messages: list[dict[str, str]]) -> list[str]:
        return [message["role"] for message in messages]

    assert roles(model.calls[0]) == ["system", "user"]
    assert roles(model.calls[1]) == ["system", "user", "assistant", "user"]
    # Turn 3 comes after the refused turn 2: the refusal exchange is skipped, so
    # its prompt is exactly turn 2's (a refused earlier turn changes nothing).
    assert model.calls[2] == model.calls[1]
    assert roles(model.calls[3]) == ["system", "user", "assistant", "user", "assistant", "user"]
    # Never more than three exchanges, however long the conversation.
    for messages in model.calls[4:]:
        assert roles(messages) == ["system"] + ["user", "assistant"] * 3 + ["user"]
    last = model.calls[-1]
    assistant_texts = [m["content"] for m in last if m["role"] == "assistant"]
    assert assistant_texts == [OK_TEXT] * 3  # reply text only
    for message in last[1:]:
        assert SECRET not in message["content"]
        assert not re.search(r"[0-9a-f]{8}-[0-9a-f]{4}-", message["content"])  # no chunk ids
    # History carries conversation only: the system prompt (rules + Evidence)
    # is identical to the first turn's for the same question.
    assert last[0] == model.calls[0][0]
    assert last[-1]["content"] == QUESTION


# --- sessions ------------------------------------------------------------------


def test_new_session_starts_empty_and_history_does_not_cross_it(
    stub_enabled_app: FastAPI,  # noqa: F811
    chat_ready_corpus: dict[str, Any],  # noqa: F811
    install_model: Any,
    db: OrmSession,
) -> None:
    users = chat_ready_corpus["users_a"]
    staff = users.as_user("staff")
    base = base_of(users, chat_ready_corpus["bot_main"])
    model = RecordingModel([])
    install_model(model)
    old = buffered(staff, base)
    assert len(staff.get(f"{base}/playground/conversation").json()["messages"]) == 2

    fresh = staff.post(f"{base}/playground/conversation/new", headers=csrf_headers(staff))
    assert fresh.status_code == 200, fresh.text
    assert (
        fresh.json()["messages"] == [] and fresh.json()["conversation_id"] != old["conversation_id"]
    )
    assert staff.get(f"{base}/playground/conversation").json()["messages"] == []
    db.expire_all()
    status = db.execute(
        text("SELECT status FROM conversations WHERE id = CAST(:c AS uuid)"),
        {"c": old["conversation_id"]},
    ).scalar_one()
    assert status == "resolved"

    after = streamed(staff, base)
    assert after["conversation_id"] == fresh.json()["conversation_id"]
    assert [m["role"] for m in model.calls[-1]] == ["system", "user"]  # no carried history
    # Viewers cannot reset the thread.
    viewer = users.as_user("viewer")
    assert (
        viewer.post(f"{base}/playground/conversation/new", headers=csrf_headers(viewer)).status_code
        == 403
    )


def test_two_staff_users_get_separate_threads_on_the_same_bot(
    stub_enabled_app: FastAPI,  # noqa: F811
    chat_ready_corpus: dict[str, Any],  # noqa: F811
    install_model: Any,
) -> None:
    from app.db.session import get_engine

    users = chat_ready_corpus["users_a"]
    base = base_of(users, chat_ready_corpus["bot_main"])
    install_model(RecordingModel([]))
    other = users.as_user("editor")
    with get_engine().begin() as conn:
        conn.execute(
            text("UPDATE users SET is_platform_staff = true WHERE id = CAST(:u AS uuid)"),
            {"u": users.users["editor"]["id"]},
        )
    first = buffered(users.as_user("staff"), base)
    second = streamed(other, base)
    assert first["conversation_id"] != second["conversation_id"]
    for client, turn in ((users.as_user("staff"), first), (other, second)):
        thread = client.get(f"{base}/playground/conversation").json()
        assert thread["conversation_id"] == turn["conversation_id"]
        assert [m["id"] for m in thread["messages"]][0] == turn["visitor_message"]["id"]
        assert thread["message_count"] == 2
    # Resetting one user's thread leaves the other user's thread alone.
    mine = users.as_user("staff")
    mine.post(f"{base}/playground/conversation/new", headers=csrf_headers(mine))
    assert other.get(f"{base}/playground/conversation").json()["message_count"] == 2


def test_playground_stream_is_staff_only_and_tenant_scoped(
    stub_enabled_app: FastAPI,  # noqa: F811
    chat_ready_corpus: dict[str, Any],  # noqa: F811
    install_model: Any,
) -> None:
    users = chat_ready_corpus["users_a"]
    base = base_of(users, chat_ready_corpus["bot_main"])
    install_model(RecordingModel([]))
    path = f"{base}/playground/messages/stream"
    for role in ("viewer", "editor", "admin"):
        client = users.as_user(role)
        response = client.post(path, json={"text": QUESTION}, headers=csrf_headers(client))
        assert response.status_code == 403
    foreign = chat_ready_corpus["users_b"].as_user("staff")
    hidden = foreign.post(
        f"/api/v1/tenants/{chat_ready_corpus['users_b'].tenant_id}/bots/"
        f"{chat_ready_corpus['bot_main']}/playground/messages/stream",
        json={"text": QUESTION},
        headers=csrf_headers(foreign),
    )
    assert hidden.status_code == 404  # tenant A's bot id under tenant B is not found


# --- history builder and thread read (DB level) --------------------------------


def make_thread(db: OrmSession, corpus: dict[str, Any]) -> Conversation:
    thread = Conversation(
        tenant_id=corpus["users_a"].tenant_id,
        bot_id=UUID(corpus["bot_main"]),
        channel="website",
        mode="ai",
        status="open",
        source="playground",
    )
    db.add(thread)
    db.flush()
    return thread


def test_history_builder_rules(db: OrmSession, corpus: dict[str, Any]) -> None:
    from datetime import UTC, datetime, timedelta

    settings = retrieval_settings(chat_history_exchanges=3)
    thread = make_thread(db, corpus)

    def exchange(question: str, **reply: Any) -> None:
        append_message(db, thread, sender_type="visitor", text=question)
        if reply:
            append_message(db, thread, sender_type="ai", **reply)

    append_message(db, thread, sender_type="visitor", text="ancient")
    append_message(db, thread, sender_type="ai", text="ANCIENT", can_answer=True)
    db.execute(
        text("UPDATE messages SET created_at = :t WHERE conversation_id = CAST(:c AS uuid)"),
        {"t": datetime.now(UTC) - timedelta(days=31), "c": str(thread.id)},
    )
    exchange("a", text="A", can_answer=True)
    exchange("b", text="REFUSED", can_answer=False, needs_human=True)  # refusal: skipped
    exchange("c")  # no AI reply: skipped
    exchange("d", text="BUSY", can_answer=False, needs_human=True)  # failure: skipped
    append_message(db, thread, sender_type="visitor", text="e")
    append_message(db, thread, sender_type="agent", text="HUMAN", sender_user_id=None)
    exchange("f", text="F", can_answer=True)
    exchange("g", text="G", can_answer=True)
    exchange("h", text="H", can_answer=True)
    current = append_message(db, thread, sender_type="visitor", text="now")

    history = history_for_turn(db, thread, settings=settings, exclude_message_id=current.id)
    assert [m["content"] for m in history.messages] == ["f", "F", "g", "G", "h", "H"]
    assert [m["role"] for m in history.messages] == ["user", "assistant"] * 3
    assert history.exchanges == 3 and history.skipped == 0  # the scan stops at three
    wide = history_for_turn(
        db,
        thread,
        settings=retrieval_settings(chat_history_exchanges=10),
        exclude_message_id=current.id,
    )
    contents = [m["content"] for m in wide.messages]
    assert contents == ["a", "A", "f", "F", "g", "G", "h", "H"]  # no refusals, no human text
    assert "HUMAN" not in contents and "ancient" not in contents  # outside the window
    assert wide.exchanges == 4 and wide.skipped == 4  # b, c, d, e
    off = history_for_turn(
        db,
        thread,
        settings=retrieval_settings(chat_history_exchanges=0),
        exclude_message_id=current.id,
    )
    assert off.messages == []


def test_messages_of_returns_the_newest_100_in_order(
    db: OrmSession, corpus: dict[str, Any]
) -> None:
    settings: Settings = retrieval_settings()
    thread = make_thread(db, corpus)
    for index in range(105):
        append_message(db, thread, sender_type="visitor", text=f"m{index:03d}")
    rows = messages_of(db, thread, settings=settings)
    assert [row.text for row in rows] == [f"m{index:03d}" for index in range(5, 105)]
    assert len(messages_of(db, thread, settings=settings, limit=3)) == 3
