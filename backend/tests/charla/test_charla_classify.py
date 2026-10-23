"""Open-answer themes (CONTRACT.md §4.5): keyword rules, the LLM path and its fallbacks, schedule()."""

from __future__ import annotations

import asyncio
import sys
from types import ModuleType, SimpleNamespace

import pytest

from app import db
from app.charla import classify, common
from app.charla.classify import ThemeReply, classify_text, keyword_theme
from app.charla.content import OPEN_STEP, THEMES
from app.db.connection import connect, new_id, now_iso

DESIGN_SAMPLES = [  # Presentador.dc.html QUOTES
    ("Responder cotizaciones y hacer seguimiento a clientes que no contestan.", "Ventas y atención"),
    ("Conciliar facturas con los pagos del banco cada cierre de mes.", "Finanzas"),
    ("Programar rutas y avisar a los clientes del estado de su pedido.", "Operaciones"),
    ("Calificar candidatos y agendar entrevistas.", "Recursos humanos"),
    ("Crear el calendario de contenido y adaptarlo a cada red.", "Marketing"),
    ("Atender el WhatsApp de la empresa fuera de horario.", "Ventas y atención"),
    ("Revisar contratos y marcar cláusulas de riesgo.", "Otro"),
    ("Generar reportes de inventario y alertar faltantes.", "Operaciones"),
]
OPS_TEXT = "Programar rutas y avisar a los clientes del estado de su pedido."  # keywords say Operaciones


def fake_response(content):
    return SimpleNamespace(choices=[SimpleNamespace(message=SimpleNamespace(content=content))])


@pytest.fixture
def fake_litellm(monkeypatch):
    """Stand-in for the litellm module (the real one takes seconds to import and would call out)."""
    module = ModuleType("litellm")

    async def unexpected(**kwargs):
        raise AssertionError("the model must not be called")

    module.acompletion = unexpected
    monkeypatch.setitem(sys.modules, "litellm", module)
    return module


@pytest.fixture
def real_llm(monkeypatch):
    monkeypatch.setenv("LLM_MOCK", "false")
    monkeypatch.setenv("OPENROUTER_API_KEY", "test-key")


def replies_with(fake_litellm, content, calls: list | None = None) -> None:
    async def acompletion(**kwargs):
        if calls is not None:
            calls.append(kwargs)
        return fake_response(content)

    fake_litellm.acompletion = acompletion


@pytest.fixture
def charla_db(tmp_path, charla_env):
    db.init_db(tmp_path / "classify.db")
    yield
    db.close_db()


def add_answer(text: str | None, *, step: int = OPEN_STEP, theme: str | None = None) -> str:
    attendee_id, answer_id = new_id(), new_id()
    with connect() as conn:
        conn.execute(
            "INSERT INTO charla_attendees (id, username, username_key, email, created_at) VALUES (?, ?, ?, ?, ?)",
            (attendee_id, f"Ana {attendee_id[:6]}", f"ana {attendee_id[:6]}", f"{attendee_id}@x.co", now_iso()),
        )
        conn.execute(
            "INSERT INTO charla_answers (id, attendee_id, step, open_text, theme, ms, created_at)"
            " VALUES (?, ?, ?, ?, ?, ?, ?)",
            (answer_id, attendee_id, step, text, theme, 1000, now_iso()),
        )
    return answer_id


def theme_of(answer_id: str) -> str | None:
    with connect() as conn:
        return conn.execute("SELECT theme FROM charla_answers WHERE id = ?", (answer_id,)).fetchone()["theme"]


async def drain() -> None:
    while classify._tasks:
        await asyncio.gather(*list(classify._tasks))


# --- keyword rules ---------------------------------------------------------------------------


@pytest.mark.parametrize(("text", "theme"), DESIGN_SAMPLES)
def test_keyword_theme_matches_the_design_samples(text, theme):
    assert keyword_theme(text) == theme


@pytest.mark.parametrize(
    ("text", "theme"),
    [
        ("FACTURACIÓN ELECTRÓNICA", "Finanzas"),
        ("facturacion electronica", "Finanzas"),
        ("Liquidar la NÓMINA", "Recursos humanos"),
        ("Programar CAMPAÑAS en Instagram", "Marketing"),
        ("atención por whats app", "Ventas y atención"),
    ],
)
def test_keyword_theme_ignores_accents_and_case(text, theme):
    assert keyword_theme(text) == theme


@pytest.mark.parametrize("text", ["", "   ", "Revisar contratos", "Redactar actas de reuniones"])
def test_keyword_theme_falls_back_to_otro(text):
    assert keyword_theme(text) == "Otro"


def test_keyword_rules_are_whole_words_and_ties_go_to_the_earlier_theme():
    assert keyword_theme("Contratar personal para la planta") == "Recursos humanos"
    assert keyword_theme("Redactar correos") == "Otro"  # "red" must not match inside "redactar"
    assert keyword_theme("Pagos a proveedores") == "Finanzas"  # 1-1 with Operaciones: Finanzas comes first


def test_every_theme_but_otro_has_keyword_rules():
    assert set(classify._KEYWORDS) == set(THEMES) - {"Otro"}


# --- structured output -----------------------------------------------------------------------


def test_theme_reply_schema_is_strict():
    schema = ThemeReply.model_json_schema()
    assert schema["properties"]["theme"]["enum"] == list(THEMES)
    assert schema["additionalProperties"] is False
    assert schema["required"] == ["theme"]


def test_parse_theme_accepts_fenced_json():
    assert classify.parse_theme('```json\n{"theme": "Finanzas"}\n```') == "Finanzas"


# --- classify_text ---------------------------------------------------------------------------


async def test_llm_path_uses_the_cerebras_call_with_theme_reply(real_llm, fake_litellm):
    calls = []
    replies_with(fake_litellm, '{"theme": "Marketing"}', calls)

    assert await classify_text(OPS_TEXT) == "Marketing"  # the model wins over the keywords

    (kwargs,) = calls
    assert kwargs["model"] == "openrouter/openai/gpt-oss-120b"
    assert kwargs["response_format"] is ThemeReply
    assert kwargs["reasoning_effort"] == "low"
    assert kwargs["extra_body"] == {"provider": {"order": ["cerebras"]}}
    system, user = kwargs["messages"]
    assert system == {"role": "system", "content": classify.SYSTEM_PROMPT}
    assert user["role"] == "user" and OPS_TEXT in user["content"]
    assert all(theme in classify.SYSTEM_PROMPT for theme in THEMES)


@pytest.mark.parametrize(
    "content",
    [None, "", "no es json", '{"theme": "Legal"}', '{"theme": "marketing"}', '{"theme": "Marketing", "why": "x"}', "[]"],
)
async def test_malformed_or_invalid_replies_fall_back_to_keywords(real_llm, fake_litellm, content):
    replies_with(fake_litellm, content)
    assert await classify_text(OPS_TEXT) == "Operaciones"


async def test_provider_errors_fall_back_to_keywords(real_llm, fake_litellm):
    async def fails(**kwargs):
        raise ConnectionError("openrouter unreachable")

    fake_litellm.acompletion = fails
    assert await classify_text(OPS_TEXT) == "Operaciones"


async def test_timeouts_fall_back_to_keywords(real_llm, fake_litellm, monkeypatch):
    async def hangs(**kwargs):
        await asyncio.sleep(10)

    fake_litellm.acompletion = hangs
    monkeypatch.setattr(classify, "TIMEOUT_SECONDS", 0.05)
    assert await classify_text(OPS_TEXT) == "Operaciones"


@pytest.mark.parametrize("mock", ["true", None])
async def test_mock_and_unconfigured_modes_use_keywords_only(fake_litellm, monkeypatch, mock):
    if mock:
        monkeypatch.setenv("LLM_MOCK", mock)
    else:
        monkeypatch.delenv("LLM_MOCK", raising=False)
        monkeypatch.delenv("OPENROUTER_API_KEY", raising=False)
    assert await classify_text(OPS_TEXT) == "Operaciones"  # fake_litellm raises if it is called


async def test_blank_text_is_otro_without_calling_the_model(real_llm, fake_litellm):
    assert await classify_text("   ") == "Otro"


async def test_at_most_four_model_calls_in_flight(real_llm, fake_litellm):
    in_flight = peak = 0

    async def slow(**kwargs):
        nonlocal in_flight, peak
        in_flight += 1
        peak = max(peak, in_flight)
        await asyncio.sleep(0.02)
        in_flight -= 1
        return fake_response('{"theme": "Finanzas"}')

    fake_litellm.acompletion = slow
    themes = await asyncio.gather(*(classify_text(f"respuesta {i}") for i in range(10)))
    assert themes == ["Finanzas"] * 10
    assert peak == classify.CONCURRENCY == 4


# --- schedule and reclassify_pending ---------------------------------------------------------


def test_schedule_without_a_loop_stores_the_keyword_theme(charla_db):
    answer_id = add_answer("Conciliar facturas con los pagos del banco cada cierre de mes.")
    classify.schedule(answer_id)
    assert theme_of(answer_id) == "Finanzas"
    assert (common.bus.admin_version, common.bus.public_version) == (1, 0)


async def test_schedule_in_mock_mode_stores_the_theme_right_away(charla_db):
    answer_id = add_answer("Calificar candidatos y agendar entrevistas.")
    classify.schedule(answer_id)
    assert theme_of(answer_id) == "Recursos humanos"
    assert (common.bus.admin_version, common.bus.public_version) == (1, 0)


async def test_schedule_with_the_llm_runs_a_task(charla_db, real_llm, fake_litellm):
    replies_with(fake_litellm, '{"theme": "Marketing"}')
    answer_id = add_answer(OPS_TEXT)

    classify.schedule(answer_id)
    assert theme_of(answer_id) is None  # the request returns before the model answers
    await drain()

    assert theme_of(answer_id) == "Marketing"
    assert (common.bus.admin_version, common.bus.public_version) == (1, 0)


async def test_schedule_with_a_failing_llm_stores_the_keyword_theme(charla_db, real_llm, fake_litellm):
    async def fails(**kwargs):
        raise RuntimeError("boom")

    fake_litellm.acompletion = fails
    answer_id = add_answer(OPS_TEXT)
    classify.schedule(answer_id)
    await drain()
    assert theme_of(answer_id) == "Operaciones"


def test_schedule_never_raises(charla_db):
    classify.schedule("no-such-answer")
    assert common.bus.admin_version == 0  # nothing stored, nothing bumped

    db.close_db()
    classify.schedule("any")  # the database error is logged, not raised


async def test_schedule_never_raises_from_the_task(charla_db, real_llm, fake_litellm):
    replies_with(fake_litellm, '{"theme": "Finanzas"}')
    answer_id = add_answer(OPS_TEXT)
    classify.schedule(answer_id)
    db.close_db()  # the task's database read now fails
    await drain()
    assert common.bus.admin_version == 0


async def test_reclassify_pending_fills_only_missing_open_themes(charla_db):
    first = add_answer("Conciliar facturas con los pagos del banco.")
    second = add_answer("Revisar contratos y marcar cláusulas de riesgo.")
    done = add_answer("Calificar candidatos.", theme="Marketing")
    quiz = add_answer(None, step=0)
    empty = add_answer(None)

    assert await classify.reclassify_pending() == 2

    assert theme_of(first) == "Finanzas"
    assert theme_of(second) == "Otro"
    assert theme_of(done) == "Marketing"  # already classified: left alone
    assert theme_of(quiz) is None and theme_of(empty) is None
    assert (common.bus.admin_version, common.bus.public_version) == (2, 0)
    assert await classify.reclassify_pending() == 0


async def test_reclassify_pending_uses_the_llm(charla_db, real_llm, fake_litellm):
    replies_with(fake_litellm, '{"theme": "Operaciones"}')
    ids = [add_answer(f"Respuesta abierta número {i}") for i in range(6)]
    assert await classify.reclassify_pending() == 6
    assert {theme_of(i) for i in ids} == {"Operaciones"}
