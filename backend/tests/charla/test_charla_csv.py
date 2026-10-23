"""GET /api/charla/admin/export.csv (CONTRACT.md §7): BOM, ';' separator, CRLF, header and rows."""

from __future__ import annotations

from app.charla import content, room

KINDS = [step.kind for step in content.SCRIPT]
Q, OPEN = KINDS.index("quiz"), KINDS.index("open")
HEADER = ("puesto;usuario;correo;verificado;celular;autoriza_whatsapp;puntaje;correctas;"
          + "".join(f"p{i};" for i in range(1, content.QUESTION_COUNT + 1)) + "registrado")


def test_csv_export(charla_client, admin, enter, bearer, clock):
    ana = enter("Ana", "ana@example.com")
    clock.advance(1000)
    beto = enter("Beto", "beto@example.com")
    act = lambda name, json=None: charla_client.post(f"/api/charla/admin/{name}", headers=admin, json=json)  # noqa: E731
    answer = lambda token, body: charla_client.post("/api/charla/answer", headers=bearer(token), json=body)  # noqa: E731

    right = content.SCRIPT[Q].answer
    act("launch")  # step 0 is a poll
    answer(ana, {"step": 0, "choice": 3})
    act("close")
    act("goto", {"step": Q})
    act("launch")
    answer(ana, {"step": Q, "choice": right})
    answer(beto, {"step": Q, "choice": (right + 1) % 4})
    act("close")
    act("goto", {"step": OPEN})
    act("launch")
    answer(beto, {"step": OPEN, "text": "=HYPERLINK(malo)"})
    charla_client.post("/api/charla/phone", headers=bearer(ana), json={"phone": "3001234567", "consent": True})

    assert charla_client.get("/api/charla/admin/export.csv").status_code == 401
    res = charla_client.get("/api/charla/admin/export.csv", headers=admin)
    assert res.status_code == 200
    assert res.headers["content-type"].startswith("text/csv")
    # The fake clock reads 2027-01-15 03:00 Bogotá (plus the second added above).
    assert res.headers["content-disposition"] == 'attachment; filename="charla-20270115-0300.csv"'

    raw = res.content
    assert raw.startswith(b"\xef\xbb\xbf")
    text = raw.decode("utf-8-sig")
    assert text.endswith("\r\n") and "\n" not in text.replace("\r\n", "")
    lines = text.split("\r\n")[:-1]
    assert lines[0] == HEADER
    ana_row, beto_row = (line.split(";") for line in lines[1:])
    assert ana_row[:8] == ["1", "Ana", "ana@example.com", "sí", "3001234567", "sí", "1000", "1"]
    assert ana_row[8] == "D"  # poll: the letter, no mark
    assert ana_row[8 + Q] == "ABCD"[right] + "✓" and ana_row[8 + OPEN] == ""
    assert beto_row[:8] == ["2", "Beto", "beto@example.com", "sí", "", "no", "100", "0"]
    assert beto_row[8] == "" and beto_row[8 + Q] == "ABCD"[(right + 1) % 4] + "✗"
    assert beto_row[8 + OPEN] == "'=HYPERLINK(malo)"  # formulas neutralised
    assert len(ana_row) == len(HEADER.split(";"))


def test_csv_empty_room():
    assert room.CSV_HEADER == HEADER.split(";")
