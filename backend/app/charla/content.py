"""What the talk asks (CONTRACT.md §2): an ordered list of steps, the last one the closing.

Kinds: "poll" (options, no right answer, no points), "quiz" (options, one right answer),
"open" (free text) and "closing" (WhatsApp prompt + thanks).
The quiz answers are drafts for the speaker to review; correct options are spread across A-D.
"""

from __future__ import annotations

from dataclasses import dataclass

QUESTION_MS = 20_000  # quiz and poll answer window
OPEN_MS = 60_000  # open question window
GRACE_MS = 1_500  # answers arriving this late after the deadline still count (network latency)
OPEN_POINTS = 100
OPEN_MAX_CHARS = 280

THEMES = ("Ventas y atención", "Finanzas", "Operaciones", "Marketing", "Recursos humanos", "Otro")


@dataclass(frozen=True)
class Step:
    kind: str
    text: str
    options: tuple[str, ...] = ()
    answer: int | None = None  # index into options, quiz only
    why: str | None = None
    placeholder: str | None = None


def _poll(text: str, *options: str) -> Step:
    return Step("poll", text, options)


def _quiz(text: str, options: tuple[str, str, str, str], answer: int, why: str) -> Step:
    return Step("quiz", text, options, answer, why)


def _open(text: str, placeholder: str) -> Step:
    return Step("open", text, placeholder=placeholder)


SCRIPT: tuple[Step, ...] = (
    _poll("¿Cómo están?", "¡Con toda!", "Bien", "Con sueño", "Necesito café"),
    _poll("¿Has creado un agente?", "Sí, varios", "Sí, uno", "Lo he intentado", "Todavía no"),
    _open(
        "¿Crees que no existirán matemáticos dentro de 5 años? ¿Cómo se hará la matemática?",
        "Ej: seguirán existiendo, pero la IA hará las demostraciones…",
    ),
    _open(
        "¿Les ha pasado que una respuesta con IA les da peor de lo esperado?",
        "Ej: le pedí un resumen y se inventó datos…",
    ),
    _quiz(
        "¿Cuál es la última definición aceptada de agente?",
        ("Un chatbot con una voz más natural", "Un LLM que ejecuta herramientas en un bucle para lograr un objetivo",
         "Un programa que responde preguntas sobre documentos", "Cualquier modelo con más de 100 mil millones de parámetros"),
        1,
        "Herramientas + bucle + objetivo: el modelo actúa, observa el resultado y decide el siguiente paso.",
    ),
    _quiz(
        "¿Qué es YOLO?",
        ("Un modo en que el agente ejecuta todo sin pedir permiso", "Una técnica para gastar menos tokens",
         "Un framework de JavaScript", "Una métrica de precisión de modelos"),
        0,
        "You Only Live Once: máxima velocidad sin aprobaciones; úsalo solo en un entorno aislado.",
    ),
    _open("¿Cuál es uno de los trucos que usa la IA y cómo funciona?", "Ej: piensa paso a paso antes de responder…"),
    _quiz(
        "¿Cuáles son los dos aspectos clave a tener en cuenta cuando haces un sistema multiagente?",
        ("La velocidad y el precio del modelo", "El número de agentes y el tamaño del modelo",
         "El contexto de cada agente y la coordinación entre ellos", "La interfaz gráfica y la voz"),
        2,
        "Cada agente con contexto acotado, y contratos claros para que no se pisen.",
    ),
    _open("¿Cuáles son las 5 reglas necesarias para ser un buen desarrollador?", "Ej: trabajar en pasos pequeños, probar…"),
    _quiz(
        "¿Qué es un bead y por qué es revolucionario para los sistemas multiagente?",
        ("Un tipo de token más barato", "Un modelo pequeño que corre en el celular", "Un plugin para generar imágenes",
         "Una tarea con dependencias guardada en git que da memoria y coordinación a los agentes"),
        3,
        "Beads: los agentes retoman el trabajo entre sesiones y se reparten tareas sin pisarse.",
    ),
    _open("Explica cómo controlar cualquiera de los dos: un swarm o un orchestrator.", "Ej: un orquestador reparte tareas y revisa…"),
    _open(
        "¿En qué aspectos los sistemas multiagente son superiores a otros? ¿Y por qué se usan para el trading?",
        "Ej: trabajan en paralelo, cada uno vigila un mercado…",
    ),
    _open("¿Con qué te quedas de la charla?", "Ej: que hay que verificar todo lo que hace un agente…"),
    Step("closing", "Solicitud de celular y cierre"),
)

STEPS = len(SCRIPT)
CLOSING_STEP = STEPS - 1
QUESTION_COUNT = STEPS - 1  # every step but the closing one
THEMED_STEP: int | None = None  # open step whose answers get a THEMES label; none of the current ones fit


def kind_of(step: int) -> str:
    return SCRIPT[step].kind


def title_of(step: int) -> str:
    return SCRIPT[step].text


def duration_ms(step: int) -> int | None:
    kind = kind_of(step)
    return OPEN_MS if kind == "open" else None if kind == "closing" else QUESTION_MS


def quiz_points(correct: bool, elapsed_ms: int) -> int:
    """500 for a correct answer plus up to 500 for speed over the 20 s window; 0 when wrong."""
    if not correct:
        return 0
    remaining = max(0, QUESTION_MS - max(0, elapsed_ms))
    return 500 + round(500 * remaining / QUESTION_MS)
