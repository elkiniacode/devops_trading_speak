"""The room (CONTRACT.md §4.4, §5.7–§5.9, §6): transitions, answers, scoring, ranking and views."""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from app.charla import common, content, room
from app.db.connection import connect

Q0_RIGHT = content.QUESTIONS[0].answer  # 2
Q0_WRONG = (Q0_RIGHT + 1) % 4


@pytest.fixture
def act(charla_client, admin):
    """``act(name, json=None) -> response`` for POST /api/charla/admin/<name>."""
    return lambda name, json=None: charla_client.post(f"/api/charla/admin/{name}", headers=admin, json=json)


@pytest.fixture
def me(charla_client, bearer):
    """``me(token) -> §6.1 body`` from GET /api/charla/me."""

    def _me(token: str) -> dict:
        res = charla_client.get("/api/charla/me", headers=bearer(token))
        assert res.status_code == 200, res.text
        return res.json()

    return _me


@pytest.fixture
def answer(charla_client, bearer):
    """``answer(token, step, choice=None, text=None) -> response``."""

    def _answer(token: str, step: int, choice: int | None = None, text: str | None = None):
        body: dict = {"step": step}
        if choice is not None:
            body["choice"] = choice
        if text is not None:
            body["text"] = text
        return charla_client.post("/api/charla/answer", headers=bearer(token), json=body)

    return _answer


def state() -> dict:
    with connect() as conn:
        return dict(conn.execute("SELECT * FROM charla_state WHERE id = 1").fetchone())


def assert_409(res, message: str) -> None:
    assert res.status_code == 409, res.text
    assert res.json() == {"detail": message}


# --- scoring -----------------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("correct", "elapsed", "points"),
    [(True, 0, 1000), (True, 10_000, 750), (True, 20_000, 500), (True, 25_000, 500), (True, -5, 1000),
     (True, 2_000, 950), (False, 0, 0), (False, 20_000, 0)],
)
def test_quiz_points(correct, elapsed, points):
    assert content.quiz_points(correct, elapsed) == points


# --- transitions -------------------------------------------------------------------------------


def test_transitions_and_their_409_messages(charla_client, act, clock):
    assert state()["step"] == 0 and state()["phase"] == "idle"
    assert_409(act("close"), room.NOT_OPEN)
    assert_409(act("reveal"), room.NOT_OPEN)

    before = common.bus.public_version
    assert act("launch").json() == {"ok": True}
    s = state()
    assert s["phase"] == "open" and s["opened_at_ms"] == clock.now
    assert s["deadline_ms"] == clock.now + content.QUESTION_MS
    assert common.bus.public_version > before

    assert_409(act("launch"), room.ALREADY_OPEN)
    assert_409(act("reveal"), room.CLOSE_FIRST)
    assert_409(act("next"), room.CLOSE_FIRST)
    assert_409(act("goto", {"step": 3}), room.CLOSE_FIRST)

    assert act("close").status_code == 200
    assert state()["phase"] == "closed"
    assert_409(act("close"), room.NOT_OPEN)
    assert_409(act("launch"), room.ALREADY_LAUNCHED)

    assert act("reveal").status_code == 200
    assert state()["phase"] == "revealed"
    assert act("reveal").status_code == 200  # a second R does nothing
    assert state()["phase"] == "revealed"
    assert_409(act("launch"), room.ALREADY_LAUNCHED)

    before = common.bus.public_version
    assert act("next").status_code == 200
    s = state()
    assert (s["step"], s["phase"], s["opened_at_ms"], s["deadline_ms"]) == (1, "idle", None, None)
    assert common.bus.public_version > before

    assert act("goto", {"step": 7}).status_code == 200
    assert act("launch").status_code == 200
    assert state()["deadline_ms"] == clock.now + content.OPEN_MS
    assert act("close").status_code == 200

    assert act("goto", {"step": 9}).status_code == 400
    assert act("goto", {"step": -1}).status_code == 400
    assert act("goto", {"step": 8}).status_code == 200
    assert act("launch").status_code == 200  # closing step: raises the WhatsApp prompt, stays idle
    s = state()
    assert s["phase"] == "idle" and s["phone_prompt"] == 1
    assert act("next").status_code == 200
    assert state()["step"] == 8  # never past the closing step


def test_reset_step_deletes_only_the_current_step(charla_client, act, enter, answer):
    token = enter("Ana", "ana@example.com")
    act("launch")
    assert answer(token, 0, Q0_RIGHT).status_code == 200
    act("close")
    act("reveal")
    act("next")
    act("launch")
    assert answer(token, 1, 0).status_code == 200
    act("close")

    assert act("reset-step").status_code == 200
    s = state()
    assert (s["step"], s["phase"], s["deadline_ms"]) == (1, "idle", None)
    with connect() as conn:
        steps = [r["step"] for r in conn.execute("SELECT step FROM charla_answers")]
    assert steps == [0]
    assert act("launch").status_code == 200  # can run again
    assert answer(token, 1, 0).status_code == 200


def test_reset_step_works_while_open(charla_client, act):
    act("launch")
    assert act("reset-step").status_code == 200
    assert state()["phase"] == "idle"


def test_phone_now_and_verification(charla_client, act):
    assert act("phone-now").status_code == 200
    assert state()["phone_prompt"] == 1
    assert act("verification", {"on": False}).status_code == 200
    assert common.verification_on() is False
    assert act("verification", {"on": True}).status_code == 200
    assert common.verification_on() is True


# --- auto-close and the phone prompt -----------------------------------------------------------


def test_auto_close_after_deadline_plus_grace(charla_client, act, clock):
    act("launch")
    clock.advance(content.QUESTION_MS + content.GRACE_MS - 1)
    room.tick()
    assert state()["phase"] == "open"
    assert room.public_view(None)["state"]["remaining_ms"] == 0  # the grace window shows 0
    clock.advance(1)
    room.tick()
    assert state()["phase"] == "closed"


def test_phone_prompt_appears_at_bogota_time(charla_client, clock, monkeypatch):
    # The fake clock starts at 2027-01-15 08:00 UTC, which is 03:00 in Bogotá.
    monkeypatch.setenv("CHARLA_PHONE_AT", "03:01")
    room.tick()
    assert state()["phone_prompt"] == 0
    clock.advance(60_000)
    room.tick()
    assert state()["phone_prompt"] == 1


def test_phone_prompt_off(charla_client, clock):
    clock.advance(24 * 3600 * 1000)
    room.tick()  # CHARLA_PHONE_AT=off (charla_env)
    assert state()["phone_prompt"] == 0


# --- answers -----------------------------------------------------------------------------------


def test_answer_rules(charla_client, act, enter, answer, clock):
    ana = enter("Ana", "ana@example.com")
    beto = enter("Beto", "beto@example.com")
    caro = enter("Caro", "caro@example.com")

    assert_409(answer(ana, 0, Q0_RIGHT), room.QUESTION_CLOSED)  # before launch
    act("launch")
    assert_409(answer(ana, 1, 0), room.QUESTION_CLOSED)  # not the current step
    assert answer(ana, 0, 7).status_code == 400
    assert answer(ana, 0, 7).json() == {"detail": room.BAD_CHOICE}
    assert answer(ana, 0).json() == {"detail": room.BAD_CHOICE}

    res = answer(ana, 0, Q0_RIGHT)
    assert res.status_code == 200 and res.json() == {"accepted": True}  # nothing about correctness
    assert_409(answer(ana, 0, Q0_WRONG), room.ALREADY_ANSWERED)

    clock.advance(content.QUESTION_MS + 1000)  # past the deadline, inside the grace window
    assert answer(beto, 0, Q0_RIGHT).status_code == 200
    clock.advance(content.GRACE_MS)  # now past deadline + grace, even if no tick ran yet
    assert_409(answer(caro, 0, Q0_RIGHT), room.QUESTION_CLOSED)

    with connect() as conn:
        rows = {r["ms"]: (r["points"], r["correct"]) for r in conn.execute("SELECT * FROM charla_answers")}
    assert rows == {0: (1000, 1), content.QUESTION_MS + 1000: (500, 1)}


def test_answer_after_close_is_409(charla_client, act, enter, answer):
    token = enter("Ana", "ana@example.com")
    act("launch")
    act("close")
    assert_409(answer(token, 0, Q0_RIGHT), room.QUESTION_CLOSED)


def test_answer_needs_a_session(charla_client):
    res = charla_client.post("/api/charla/answer", json={"step": 0, "choice": 1})
    assert res.status_code == 401


def test_open_answer_rules_theme_and_result(charla_client, act, enter, answer, me):
    ana = enter("Ana", "ana@example.com")
    beto = enter("Beto", "beto@example.com")
    act("goto", {"step": content.OPEN_STEP})
    act("launch")
    assert answer(ana, 7, text="  corto  ").json() == {"detail": room.SHORT_TEXT}
    assert answer(ana, 7, text="x" * (content.OPEN_MAX_CHARS + 1)).status_code == 400
    assert answer(ana, 7, text="  Conciliar facturas de proveedores  ").status_code == 200
    assert_409(answer(ana, 7, text="Otra respuesta distinta"), room.ALREADY_ANSWERED)

    view = me(ana)
    assert view["me"]["answer"] == {"step": 7, "choice": None, "text": "Conciliar facturas de proveedores"}
    assert view["state"]["question"]["options"] == []
    assert view["state"]["question"]["placeholder"] == content.OPEN_PLACEHOLDER

    admin = room.admin_view()
    assert len(admin["quotes"]) == 1
    quote = admin["quotes"][0]
    assert quote["username"] == "Ana" and quote["text"] == "Conciliar facturas de proveedores"
    assert quote["theme"] in content.THEMES  # mock mode stores the keyword theme right away
    assert [t["name"] for t in admin["themes"]] == list(content.THEMES)
    assert sum(t["count"] for t in admin["themes"]) == 1
    assert admin["distribution"] is None

    act("close")
    act("reveal")
    view = me(ana)
    assert view["state"]["reveal"] == {"answer": None, "why": None, "distribution": None}
    assert view["me"]["result"] == {"correct": None, "points": content.OPEN_POINTS}
    assert view["me"]["score"] == content.OPEN_POINTS
    assert me(beto)["me"]["result"] == {"correct": None, "points": 0}


def test_classify_failure_never_breaks_the_answer(charla_client, act, enter, answer, monkeypatch):
    from app.charla import classify

    def boom(answer_id: str) -> None:
        raise RuntimeError("down")

    monkeypatch.setattr(classify, "schedule", boom)
    token = enter("Ana", "ana@example.com")
    act("goto", {"step": content.OPEN_STEP})
    act("launch")
    assert answer(token, 7, text="Responder cotizaciones").status_code == 200


def test_answer_bumps_admin_and_attendee_versions_only(charla_client, act, enter, answer):
    token = enter("Ana", "ana@example.com")
    attendee_id = charla_client.get("/api/charla/me", headers={"Authorization": f"Bearer {token}"}).json()["me"][
        "attendee_id"
    ]
    act("launch")
    public, admin, mine = common.bus.public_version, common.bus.admin_version, room.attendee_version(attendee_id)
    answer(token, 0, Q0_RIGHT)
    assert common.bus.public_version == public
    assert common.bus.admin_version > admin
    assert room.attendee_version(attendee_id) == mine + 1


# --- views: no correctness before the reveal ---------------------------------------------------


def test_no_correctness_before_reveal(charla_client, act, enter, answer, me, clock):
    ana = enter("Ana", "ana@example.com")
    beto = enter("Beto", "beto@example.com")
    act("launch")
    clock.advance(2000)
    answer(ana, 0, Q0_RIGHT)
    answer(beto, 0, Q0_WRONG)

    view = me(ana)
    s = view["state"]
    assert (s["step"], s["kind"], s["phase"], s["number"], s["total_quiz"]) == (0, "quiz", "open", 1, 7)
    assert s["remaining_ms"] == content.QUESTION_MS - 2000 and s["duration_ms"] == content.QUESTION_MS
    assert s["question"] == {"text": content.QUESTIONS[0].text, "options": list(content.QUESTIONS[0].options),
                             "placeholder": None}
    assert s["reveal"] is None and s["room_count"] == 2 and s["phone_prompt"] is False
    assert view["me"]["answer"] == {"step": 0, "choice": Q0_RIGHT, "text": None}
    assert view["me"]["result"] is None and view["me"]["score"] == 0

    act("close")
    view = me(ana)
    assert view["state"]["remaining_ms"] is None and view["state"]["reveal"] is None
    assert view["me"]["result"] is None and view["me"]["score"] == 0

    act("reveal")
    view = me(ana)
    distribution = [0, 0, 0, 0]
    distribution[Q0_RIGHT] += 1
    distribution[Q0_WRONG] += 1
    assert view["state"]["reveal"] == {"answer": Q0_RIGHT, "why": content.QUESTIONS[0].why,
                                       "distribution": distribution}
    assert view["me"]["result"] == {"correct": True, "points": 950}
    assert (view["me"]["score"], view["me"]["rank"]) == (950, 1)
    assert me(beto)["me"]["result"] == {"correct": False, "points": 0}
    assert me(beto)["me"]["rank"] == 2

    act("next")  # step 0 is behind us: still settled, but `answer`/`result` are about step 1 now
    view = me(ana)
    assert view["me"]["answer"] is None and view["me"]["result"] is None
    assert view["me"]["score"] == 950

    act("launch")
    view = me(beto)
    assert view["me"]["score"] == 0 and view["state"]["number"] == 2


def test_unanswered_quiz_result_after_reveal(charla_client, act, enter, me):
    token = enter("Ana", "ana@example.com")
    act("launch")
    act("close")
    act("reveal")
    view = me(token)["me"]
    assert view["answer"] is None
    assert view["result"] == {"correct": False, "points": 0}


def test_closing_step_view(charla_client, act, enter, me):
    token = enter("Ana", "ana@example.com")
    act("goto", {"step": content.CLOSING_STEP})
    s = me(token)["state"]
    assert (s["kind"], s["number"], s["question"], s["duration_ms"]) == ("closing", None, None, None)


def test_public_view_without_attendee(charla_client):
    assert room.public_view(None)["me"] is None


# --- ranking -----------------------------------------------------------------------------------


def test_ranking_tie_break_and_hidden(charla_client, act, enter, answer, me, clock):
    tokens = {}
    for name in ("Ana", "Beto", "Caro", "Dani"):  # registered one second apart: Ana first
        tokens[name] = enter(name, f"{name.lower()}@example.com")
        clock.advance(1000)
    act("launch")
    clock.advance(10)
    answer(tokens["Beto"], 0, Q0_RIGHT)  # 1000 points, 10 ms
    answer(tokens["Caro"], 0, Q0_RIGHT)  # 1000 points, 10 ms, registered after Beto
    clock.advance(5)
    answer(tokens["Ana"], 0, Q0_RIGHT)  # still 1000 points (rounding), but 15 ms
    answer(tokens["Dani"], 0, Q0_WRONG)

    order = [r["username"] for r in room.admin_view()["ranking"]]
    assert order == ["Ana", "Beto", "Caro", "Dani"]  # nothing settled yet: registration order
    assert {r["score"] for r in room.admin_view()["ranking"]} == {0}

    act("close")
    act("reveal")
    ranking = room.admin_view()["ranking"]
    assert [(r["rank"], r["username"], r["score"], r["correct"]) for r in ranking] == [
        (1, "Beto", 1000, 1), (2, "Caro", 1000, 1), (3, "Ana", 1000, 1), (4, "Dani", 0, 0)]
    assert me(tokens["Ana"])["me"]["rank"] == 3

    beto_id = ranking[0]["attendee_id"]
    assert act("hide", {"attendee_id": beto_id, "hidden": True}).status_code == 200
    ranking = room.admin_view()["ranking"]
    assert [(r["rank"], r["username"], r["hidden"]) for r in ranking] == [
        (1, "Caro", False), (2, "Ana", False), (3, "Dani", False), (4, "Beto", True)]
    assert me(tokens["Beto"])["me"]["rank"] is None
    assert me(tokens["Ana"])["me"]["rank"] == 2

    assert act("hide", {"attendee_id": beto_id, "hidden": False}).status_code == 200
    assert room.admin_view()["ranking"][0]["username"] == "Beto"
    assert act("hide", {"attendee_id": "nope", "hidden": True}).status_code == 404
    assert act("hide", {"hidden": True}).status_code == 400


def test_hide_quote(charla_client, act, enter, answer):
    token = enter("Ana", "ana@example.com")
    act("goto", {"step": content.OPEN_STEP})
    act("launch")
    answer(token, 7, text="Calificar leads de ventas")
    answer_id = room.admin_view()["quotes"][0]["answer_id"]
    assert act("hide", {"answer_id": answer_id, "hidden": True}).status_code == 200
    view = room.admin_view()
    assert view["quotes"][0]["hidden"] is True
    assert sum(t["count"] for t in view["themes"]) == 0  # hidden quotes leave the theme chart


# --- phone ---------------------------------------------------------------------------------------


def test_phone(charla_client, enter, me, bearer):
    ana = enter("Ana", "ana@example.com")
    beto = enter("Beto", "beto@example.com")
    post = lambda token, body: charla_client.post("/api/charla/phone", headers=bearer(token), json=body)  # noqa: E731

    assert me(ana)["me"]["phone_status"] == "none"
    assert post(ana, {"phone": "300 123 456", "consent": True}).json() == {"detail": room.BAD_PHONE}
    assert post(ana, {"phone": "200 123 4567", "consent": True}).json() == {"detail": room.BAD_PHONE}
    assert post(ana, {"phone": "300 123 4567", "consent": False}).json() == {"detail": room.NO_CONSENT}
    assert post(ana, {"phone": "+57 300-123-4567", "consent": True}).json() == {"ok": True}
    assert me(ana)["me"]["phone_status"] == "given"
    with connect() as conn:
        row = conn.execute("SELECT phone, phone_consent_at FROM charla_attendees WHERE username = 'Ana'").fetchone()
    assert row["phone"] == "3001234567" and row["phone_consent_at"]

    assert post(beto, {"skip": True}).json() == {"ok": True}
    assert me(beto)["me"]["phone_status"] == "skipped"
    assert room.admin_view()["counts"]["with_phone"] == 1
    assert charla_client.post("/api/charla/phone", json={"skip": True}).status_code == 401


# --- admin -------------------------------------------------------------------------------------


def test_admin_view_shape(charla_client, act, enter, answer):
    token = enter("Ana", "ana@example.com")
    act("launch")
    answer(token, 0, Q0_RIGHT)
    view = room.admin_view()
    assert set(view) == {"version", "server_now_ms", "state", "script", "counts", "distribution", "themes",
                         "quotes", "ranking", "email"}
    assert {"verification_on", "phone_prompt_at", "deadline_ms", "opened_at_ms", "room_count"} <= set(view["state"])
    assert view["state"]["phone_prompt_at"] is None  # CHARLA_PHONE_AT=off
    assert len(view["script"]) == content.STEPS
    assert view["script"][0]["answer"] == Q0_RIGHT and len(view["script"][0]["options"]) == 4
    assert view["script"][7] == {"step": 7, "kind": "open", "title": content.OPEN_QUESTION, "options": [],
                                 "answer": None, "why": None}
    assert view["counts"] == {"registered": 1, "active": 1, "verified": 1, "pending": 0, "with_phone": 0,
                              "answered": 1, "correct": 1}
    assert view["distribution"][Q0_RIGHT] == 1
    assert set(view["email"]) == {"queued", "sent", "failed", "last_error"}


def test_admin_auth(charla_client, monkeypatch):
    res = charla_client.post("/api/charla/admin/launch")
    assert res.status_code == 401 and res.json() == {"detail": "Clave de presentador incorrecta."}
    assert charla_client.post("/api/charla/admin/launch", headers={"X-Admin-Key": "wrong"}).status_code == 401
    assert charla_client.get("/api/charla/admin/stream?key=wrong").status_code == 401
    assert charla_client.post("/api/charla/admin/launch?key=test-admin").status_code == 200
    monkeypatch.delenv("CHARLA_ADMIN_KEY")
    assert charla_client.post("/api/charla/admin/close", headers={"X-Admin-Key": "test-admin"}).status_code == 503


def test_reset_requires_confirm(charla_client, act, enter, answer, bearer):
    token = enter("Ana", "ana@example.com")
    act("launch")
    answer(token, 0, Q0_RIGHT)
    act("close")
    act("next")
    act("verification", {"on": False})
    act("phone-now")

    assert act("reset", {"confirm": "reset"}).status_code == 400
    assert act("reset", {}).status_code == 400
    assert state()["step"] == 1

    assert act("reset", {"confirm": "RESET"}).json() == {"ok": True}
    s = state()
    assert (s["step"], s["phase"], s["verification_on"], s["phone_prompt"]) == (0, "idle", 1, 0)
    with connect() as conn:
        assert conn.execute("SELECT COUNT(*) FROM charla_answers").fetchone()[0] == 0
        assert conn.execute("SELECT COUNT(*) FROM charla_attendees").fetchone()[0] == 0
    assert charla_client.get("/api/charla/me", headers=bearer(token)).status_code == 401


def test_reclassify_returns_ok(charla_client, act):
    assert act("reclassify").json() == {"ok": True}


# --- restart -----------------------------------------------------------------------------------


def test_state_survives_restart_and_expired_question_closes(charla_env, charla_settings, make_app, clock, bearer):
    with TestClient(make_app(charla_settings)) as first:
        res = first.post("/api/charla/register", json={"username": "Ana", "email": "ana@example.com"})
        token = first.post("/api/charla/verify", json={"v": res.json()["dev_link_token"]}).json()["token"]
        headers = {"X-Admin-Key": "test-admin"}
        first.post("/api/charla/admin/next", headers=headers)
        first.post("/api/charla/admin/launch", headers=headers)
        assert first.post("/api/charla/answer", headers=bearer(token), json={"step": 1, "choice": 0}).status_code == 200

    clock.advance(content.QUESTION_MS + content.GRACE_MS + 5000)  # the server was down past the deadline
    with TestClient(make_app(charla_settings)) as second:
        view = second.get("/api/charla/me", headers=bearer(token)).json()
        assert (view["state"]["step"], view["state"]["phase"]) == (1, "closed")
        assert view["me"]["answer"] == {"step": 1, "choice": 0, "text": None}


def test_open_question_within_deadline_stays_open_after_restart(charla_env, charla_settings, make_app, clock):
    headers = {"X-Admin-Key": "test-admin"}
    with TestClient(make_app(charla_settings)) as first:
        first.post("/api/charla/admin/launch", headers=headers)
    clock.advance(5000)
    with TestClient(make_app(charla_settings)):
        view = room.public_view(None)
        assert view["state"]["phase"] == "open"
        assert view["state"]["remaining_ms"] == content.QUESTION_MS - 5000
