"""What the talk asks (CONTRACT.md §2). Ported from Sala.dc.html.

The option order was reshuffled once so the correct answers aren't all "B".
"""

from __future__ import annotations

from dataclasses import dataclass

QUESTION_MS = 20_000  # quiz answer window
OPEN_MS = 60_000  # open question window
GRACE_MS = 1_500  # answers arriving this late after the deadline still count (network latency)
OPEN_POINTS = 100
OPEN_MAX_CHARS = 280

QUIZ_STEPS = 7
OPEN_STEP = 7
CLOSING_STEP = 8
STEPS = 9  # 0-6 quiz, 7 open, 8 closing (WhatsApp prompt + thanks)

THEMES = ("Ventas y atención", "Finanzas", "Operaciones", "Marketing", "Recursos humanos", "Otro")


@dataclass(frozen=True)
class Question:
    text: str
    options: tuple[str, str, str, str]
    answer: int  # index into options
    why: str


QUESTIONS: tuple[Question, ...] = (
    Question(
        "¿Qué diferencia a un agente de un chatbot?",
        ("Responde más rápido", "Tiene una voz más natural",
         "Decide pasos y usa herramientas para lograr un objetivo", "Solo funciona con documentos"),
        2,
        "Un agente planea, actúa con herramientas y verifica; un chatbot solo responde.",
    ),
    Question(
        "¿Para qué sirven las herramientas (tools) de un agente?",
        ("Para actuar sobre sistemas reales: leer, escribir, consultar", "Para decorar la respuesta",
         "Para reducir el costo del modelo", "Para evitar usar contexto"),
        0,
        "Las herramientas le dan manos al modelo: APIs, bases de datos, archivos.",
    ),
    Question(
        "¿Por qué dividir el trabajo en varios agentes con roles?",
        ("Porque un solo agente no existe", "Para gastar más tokens", "Para no necesitar revisión",
         "Para que cada uno tenga contexto y responsabilidad acotados"),
        3,
        "Roles claros reducen ruido de contexto y facilitan revisar cada entrega.",
    ),
    Question(
        "¿Qué pasa cuando el contexto de un agente se llena de ruido?",
        ("Responde mejor", "Pierde foco y comete más errores", "Se vuelve más barato",
         "Nada, el modelo filtra solo"),
        1,
        "El contexto es memoria de trabajo: lo irrelevante compite con lo importante.",
    ),
    Question(
        "¿Qué hace confiable el trabajo de un agente?",
        ("Confiar en que lo hizo bien", "Pedirle que se autoevalúe 3 veces",
         "Pruebas y revisión verificables antes de aceptar", "Usar el modelo más grande"),
        2,
        "Lo que no se puede verificar no se puede delegar.",
    ),
    Question(
        "¿Para qué sirve un contrato entre agentes (ej. CONTRACTS.md)?",
        ("Para documentar al final", "Para limitar el número de agentes", "Para guardar contraseñas",
         "Para acordar interfaces y evitar que se pisen"),
        3,
        "Backend y frontend trabajan en paralelo contra una interfaz acordada.",
    ),
    Question(
        "Una acción irreversible (borrar datos, pagar) debería…",
        ("Requerir aprobación humana", "Ejecutarse automáticamente", "Hacerse siempre de noche",
         "Delegarse al último agente"),
        0,
        "Autonomía con límites: lo irreversible pasa por una persona.",
    ),
)

OPEN_QUESTION = "¿Qué proceso de tu empresa te gustaría que hiciera un equipo de agentes?"
OPEN_PLACEHOLDER = "Ej: responder cotizaciones, conciliar facturas, calificar leads…"
CLOSING_TITLE = "Solicitud de celular y cierre"


def kind_of(step: int) -> str:
    """'quiz' for steps 0-6, 'open' for 7, 'closing' for 8."""
    if 0 <= step < QUIZ_STEPS:
        return "quiz"
    if step == OPEN_STEP:
        return "open"
    return "closing"


def title_of(step: int) -> str:
    kind = kind_of(step)
    if kind == "quiz":
        return QUESTIONS[step].text
    return OPEN_QUESTION if kind == "open" else CLOSING_TITLE


def duration_ms(step: int) -> int | None:
    kind = kind_of(step)
    return QUESTION_MS if kind == "quiz" else OPEN_MS if kind == "open" else None


def quiz_points(correct: bool, elapsed_ms: int) -> int:
    """500 for a correct answer plus up to 500 for speed over the 20 s window; 0 when wrong."""
    if not correct:
        return 0
    remaining = max(0, QUESTION_MS - max(0, elapsed_ms))
    return 500 + round(500 * remaining / QUESTION_MS)
