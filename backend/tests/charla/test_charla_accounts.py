"""Accounts: usernames, registration, one-tap links, limits, sessions and the kill switch (CONTRACT.md §4.2, §5.1–§5.5)."""

from __future__ import annotations

import pytest

from app.charla import accounts, common
from app.charla import email as mailer
from app.db.connection import connect

MIN = 60 * 1000


@pytest.fixture
def outbox(monkeypatch) -> mailer.EmailOutbox:
    """A fresh outbox that nothing drains, so tests can read what register queued."""
    fresh = mailer.EmailOutbox()
    monkeypatch.setattr(mailer, "outbox", fresh)
    return fresh


def register(client, username: str, email: str, **kwargs):
    return client.post("/api/charla/register", json={"username": username, "email": email}, **kwargs)


def set_verification(on: bool) -> None:
    common.ensure_state_row()
    with connect() as conn:
        conn.execute("UPDATE charla_state SET verification_on = ? WHERE id = 1", (int(on),))


def attendee_count(email: str) -> int:
    with connect() as conn:
        return conn.execute("SELECT COUNT(*) FROM charla_attendees WHERE email = ?", (email,)).fetchone()[0]


# --- usernames ---------------------------------------------------------------------------------


def test_normalization_strips_accents_case_and_spaces():
    assert accounts.normalize_username("José  P") == accounts.normalize_username(" jose p ") == "jose p"
    assert accounts.normalize_username("MUÑOZ") == "munoz"
    assert accounts.clean_username("  José \t  P ") == "José P"
    assert accounts.clean_username("José") == "José"  # decomposed input is shown composed


@pytest.mark.parametrize(
    ("raw", "message"),
    [
        ("a", accounts.MSG_LENGTH),
        ("   ", accounts.MSG_LENGTH),
        ("x" * 25, accounts.MSG_LENGTH),
        ("hola!", accounts.MSG_CHARS),
        ("ana@x", accounts.MSG_CHARS),
        ("ana\U0001f600", accounts.MSG_CHARS),
        ("Muñoz_1.x-y", None),
        ("  José   P  ", None),
        ("x" * 24, None),
    ],
)
def test_username_errors(raw, message):
    assert accounts.username_error(raw) == message


def test_username_endpoint(charla_client):
    ok = charla_client.get("/api/charla/username", params={"u": "José P"}).json()
    assert ok == {"valid": True, "available": True, "message": None, "suggestion": None}
    bad = charla_client.get("/api/charla/username", params={"u": "a"}).json()
    assert bad == {"valid": False, "available": False, "message": "Usa entre 2 y 24 caracteres.", "suggestion": None}
    chars = charla_client.get("/api/charla/username", params={"u": "a?b"}).json()
    assert chars["valid"] is False
    assert chars["message"] == "Usa solo letras, números, espacios, punto, guion o guion bajo."


def test_taken_name_gets_409_with_suggestion(charla_client, enter, outbox):
    enter("José P", "jose@empresa.com")
    enter("José P2", "jose2@empresa.com")

    check = charla_client.get("/api/charla/username", params={"u": "jose  p"}).json()
    assert check["valid"] is True and check["available"] is False
    assert check["suggestion"] == "jose p3"
    assert check["message"] == "Ese nombre ya está en uso. Prueba con otro, por ejemplo «jose p3»."

    res = register(charla_client, "JOSÉ P", "otro@empresa.com")
    assert res.status_code == 409
    assert res.json()["detail"] == "Ese nombre ya está en uso. Prueba con otro, por ejemplo «JOSÉ P3»."
    assert attendee_count("otro@empresa.com") == 0


def test_suggestion_stays_within_24_characters(charla_client, enter, outbox):
    enter("x" * 24, "long@empresa.com")
    check = charla_client.get("/api/charla/username", params={"u": "X" * 24}).json()
    assert check["suggestion"] == "X" * 23 + "2"


def test_same_email_can_reregister_and_switch_names(charla_client, clock, outbox):
    assert register(charla_client, "Ana", "ana@empresa.com").status_code == 200
    # The owner sees their own name as available.
    check = charla_client.get("/api/charla/username", params={"u": "ana", "email": " ANA@empresa.com "}).json()
    assert check["available"] is True

    clock.advance(30_000)
    again = register(charla_client, "ana", "  Ana@Empresa.com ")
    assert again.status_code == 200, again.text
    assert again.json()["email"] == "ana@empresa.com"
    assert again.json()["username"] == "ana"
    assert attendee_count("ana@empresa.com") == 1

    clock.advance(30_000)
    assert register(charla_client, "Ana B", "ana@empresa.com").status_code == 200
    # The old name is free again for someone else.
    assert register(charla_client, "Ana", "otra@empresa.com").status_code == 200


def test_stale_reservation_is_released_after_30_minutes(charla_client, clock, outbox):
    assert register(charla_client, "Luz", "luz@empresa.com").status_code == 200
    assert register(charla_client, "luz", "otra@empresa.com").status_code == 409

    clock.advance(30 * MIN)  # the unverified link expired and there is no session
    check = charla_client.get("/api/charla/username", params={"u": "Luz"}).json()
    assert check["available"] is True
    res = register(charla_client, "luz", "otra@empresa.com")
    assert res.status_code == 200, res.text
    assert attendee_count("luz@empresa.com") == 0  # the stale row was deleted


def test_verified_name_stays_taken_after_its_link_expires(charla_client, clock, enter, outbox):
    enter("Luz", "luz@empresa.com")
    clock.advance(60 * MIN)
    assert register(charla_client, "Luz", "otra@empresa.com").status_code == 409


# --- registration and links --------------------------------------------------------------------


def test_register_sends_link_then_verify_and_status_let_in(charla_client, bearer, outbox):
    res = register(charla_client, "  José   P ", "Jose@Empresa.com")
    assert res.status_code == 200, res.text
    body = res.json()
    assert body["status"] == "link_sent"
    assert body["email"] == "jose@empresa.com"
    assert body["username"] == "José P"
    assert body["resend_in_s"] == 30
    assert body["pending"] and body["dev_link_token"]

    queued = list(outbox._queue)
    assert len(queued) == 1
    assert queued[0].to == "jose@empresa.com" and queued[0].username == "José P"
    assert queued[0].link == f"http://testserver/charla/entrar/#v={body['dev_link_token']}"

    status = charla_client.get("/api/charla/register/status", params={"p": body["pending"]})
    assert status.json() == {"status": "waiting"}

    verified = charla_client.post("/api/charla/verify", json={"v": body["dev_link_token"]})
    assert verified.status_code == 200, verified.text
    assert verified.json()["username"] == "José P"

    first = charla_client.get("/api/charla/register/status", params={"p": body["pending"]}).json()
    second = charla_client.get("/api/charla/register/status", params={"p": body["pending"]}).json()
    assert first["status"] == second["status"] == "in"
    assert first["username"] == "José P"
    tokens = {verified.json()["token"], first["token"], second["token"]}
    assert len(tokens) == 3  # every call opens its own session

    for token in tokens:
        me = charla_client.get("/api/charla/me", headers=bearer(token))
        assert me.status_code == 200, me.text
        assert me.json()["me"]["username"] == "José P"
        assert me.json()["me"]["verified"] is True


def test_link_is_reusable_until_it_expires(charla_client, clock, outbox):
    body = register(charla_client, "Reuso", "reuso@empresa.com").json()
    link = {"v": body["dev_link_token"]}
    assert charla_client.post("/api/charla/verify", json=link).status_code == 200
    clock.advance(29 * MIN)
    assert charla_client.post("/api/charla/verify", json=link).status_code == 200

    clock.advance(1 * MIN)
    expired = charla_client.post("/api/charla/verify", json=link)
    assert expired.status_code == 400
    assert expired.json()["detail"] == "Este enlace expiró o no es válido. Pide uno nuevo."
    status = charla_client.get("/api/charla/register/status", params={"p": body["pending"]})
    assert status.status_code == 404
    assert status.json()["detail"] == "Este registro expiró. Vuelve a escribir tu correo."


def test_new_register_replaces_the_old_link(charla_client, clock, outbox):
    old = register(charla_client, "Nuevo", "nuevo@empresa.com").json()
    clock.advance(30_000)
    new = register(charla_client, "Nuevo", "nuevo@empresa.com").json()
    assert charla_client.post("/api/charla/verify", json={"v": old["dev_link_token"]}).status_code == 400
    assert charla_client.get("/api/charla/register/status", params={"p": old["pending"]}).status_code == 404
    assert charla_client.post("/api/charla/verify", json={"v": new["dev_link_token"]}).status_code == 200


def test_invalid_input_errors(charla_client, outbox):
    bad_email = register(charla_client, "Ana", "ana@empresa")
    assert bad_email.status_code == 400
    assert bad_email.json()["detail"] == "Revisa el correo: necesitamos uno válido para el enlace."
    assert register(charla_client, "Ana", "ana empresa@x.co").status_code == 400
    bad_name = register(charla_client, "A", "ana@empresa.com")
    assert bad_name.status_code == 400 and bad_name.json()["detail"] == "Usa entre 2 y 24 caracteres."
    assert charla_client.post("/api/charla/register", json={}).status_code == 400

    assert charla_client.post("/api/charla/verify", json={"v": "nope"}).status_code == 400
    assert charla_client.post("/api/charla/verify", json={}).status_code == 400
    assert charla_client.get("/api/charla/register/status", params={"p": "nope"}).status_code == 404
    assert charla_client.get("/api/charla/register/status").status_code == 404
    assert not outbox._queue


def test_link_origin_comes_from_public_url_or_forwarded_proto(charla_client, clock, monkeypatch, outbox):
    register(charla_client, "Proxy", "proxy@empresa.com", headers={"X-Forwarded-Proto": "https"})
    assert outbox._queue[-1].link.startswith("https://testserver/charla/entrar/#v=")

    monkeypatch.setenv("CHARLA_PUBLIC_URL", "https://charla.example.com/")
    clock.advance(30_000)
    register(charla_client, "Proxy", "proxy@empresa.com")
    assert outbox._queue[-1].link.startswith("https://charla.example.com/charla/entrar/#v=")


# --- resend limits -----------------------------------------------------------------------------


def test_resend_cooldown_is_30_seconds(charla_client, clock, outbox):
    assert register(charla_client, "Paco", "paco@empresa.com").status_code == 200
    soon = register(charla_client, "Paco", "paco@empresa.com")
    assert soon.status_code == 429
    assert soon.json()["detail"] == "Espera 30 s para pedir otro enlace."
    clock.advance(10_500)
    assert register(charla_client, "Paco", "paco@empresa.com").json()["detail"] == "Espera 20 s para pedir otro enlace."
    clock.advance(19_500)
    assert register(charla_client, "Paco", "paco@empresa.com").status_code == 200


def test_at_most_five_sends_per_hour(charla_client, clock, outbox):
    for _ in range(5):
        assert register(charla_client, "Cinco", "cinco@empresa.com").status_code == 200
        clock.advance(30_000)
    capped = register(charla_client, "Cinco", "cinco@empresa.com")
    assert capped.status_code == 429
    assert capped.json()["detail"] == "Ya pediste varios enlaces. Intenta en unos minutos."
    assert len(outbox._queue) == 5

    clock.advance(60 * MIN - 5 * 30_000)  # one hour after the first send
    assert register(charla_client, "Cinco", "cinco@empresa.com").status_code == 200


# --- sessions ----------------------------------------------------------------------------------


def test_sessions_and_401(charla_client, enter, bearer, outbox):
    first = enter("Sesion", "sesion@empresa.com")
    assert charla_client.get("/api/charla/me", headers=bearer(first)).status_code == 200

    assert accounts.attendee_for_token(first)["email"] == "sesion@empresa.com"
    assert accounts.attendee_for_token("nope") is None
    assert accounts.attendee_for_token(None) is None

    for headers in ({}, bearer("nope")):
        res = charla_client.get("/api/charla/me", headers=headers)
        assert res.status_code == 401
        assert res.json()["detail"] == "Tu sesión expiró. Vuelve a registrarte."
    assert charla_client.get("/api/charla/me", params={"t": first}).status_code == 200

    accounts.reset_accounts()
    assert charla_client.get("/api/charla/me", headers=bearer(first)).status_code == 401
    assert attendee_count("sesion@empresa.com") == 0


def test_two_sessions_are_both_valid(charla_client, bearer, outbox):
    link = {"v": register(charla_client, "Dos", "dos@empresa.com").json()["dev_link_token"]}
    phone = charla_client.post("/api/charla/verify", json=link).json()["token"]
    laptop = charla_client.post("/api/charla/verify", json=link).json()["token"]
    assert phone != laptop
    for token in (phone, laptop):
        me = charla_client.get("/api/charla/me", headers=bearer(token)).json()["me"]
        assert me["username"] == "Dos"


# --- kill switch and bus -----------------------------------------------------------------------


def test_verification_off_lets_people_straight_in(charla_client, bearer, outbox):
    set_verification(False)
    res = register(charla_client, "Rapido", "rapido@empresa.com")
    assert res.status_code == 200, res.text
    body = res.json()
    assert body["status"] == "in" and body["username"] == "Rapido"
    me = charla_client.get("/api/charla/me", headers=bearer(body["token"])).json()["me"]
    assert me["username"] == "Rapido" and me["verified"] is False
    assert not outbox._queue
    # No cooldown applies when no email is sent, and the name is now held.
    assert register(charla_client, "Rapido", "rapido@empresa.com").json()["status"] == "in"
    assert register(charla_client, "rapido", "otro@empresa.com").status_code == 409


def test_waiting_tab_gets_in_when_verification_turns_off(charla_client, bearer, outbox):
    body = register(charla_client, "Espera", "espera@empresa.com").json()
    assert charla_client.get("/api/charla/register/status", params={"p": body["pending"]}).json() == {"status": "waiting"}
    set_verification(False)
    status = charla_client.get("/api/charla/register/status", params={"p": body["pending"]}).json()
    assert status["status"] == "in"
    assert charla_client.get("/api/charla/me", headers=bearer(status["token"])).json()["me"]["verified"] is False


def test_account_changes_bump_only_the_admin_bus(charla_client, outbox):
    public, admin = common.bus.public_version, common.bus.admin_version
    body = register(charla_client, "Bus", "bus@empresa.com").json()
    charla_client.post("/api/charla/verify", json={"v": body["dev_link_token"]})
    charla_client.get("/api/charla/register/status", params={"p": body["pending"]})
    assert common.bus.public_version == public
    assert common.bus.admin_version >= admin + 4  # register, its queued email, verify, status
