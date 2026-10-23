# Charla contract: live-talk sections of FinAlly

This is the binding contract for the swarm that builds the live-talk sections. Build against it, and don't change it on your own. If something is missing or wrong, message **team-lead** with SendMessage. The lead updates this file and tells everyone affected.

- **Talk:** "Agentic Engineering", Fri 23 Oct 2026, afternoon, Bogotá. Elkin Camargo, IA Revolutions.
- **Audience:** 30–40 attendees on phones, possibly on mobile data only.
- **Visual spec:**
  - The pages: `C:\Users\elkin\Downloads\ia-revolutions-charla\ia-revolutions-charla\{Registro,Sala,Presentador}.dc.html`.
  - The visual system and copy: `CONTEXT.md` in the same folder.
  - Read-only: **never edit that folder**.
- **Plan:** `C:\Users\elkin\.claude\plans\i-want-to-implement-cuddly-milner.md`.
- **Language:** all UI copy and error messages are in Spanish (Colombia) and use no emojis.

---

## 0. The experience in one picture

```
Phone:  QR ─▶ /charla/  (username + email ─▶ ENTRAR)
             └▶ "Revisa tu correo" (waits, polls status every 2 s)
        Email: [ENTRAR A LA SALA] ─▶ /charla/entrar/#v=<link-token>  (verifies, gets its own session)
             └▶ the original tab gets approved and enters /charla/sala/ on its own
        Sala: wait ─▶ question ─▶ "Respuesta registrada" ─▶ (presenter reveals) result ─▶ … ─▶ open ─▶ phone ─▶ end
Laptop: /charla/presentador/  (key gate) launches, closes, reveals, next; ranking; projection; QR
        tabs AGENTES / HISTORIAL / HILOS ─▶ http://localhost:4800 (agent-monitor, separate project)
```

- **No password, code or consent checkbox.** The session token in localStorage is the "auto-filled password".
- **`CHARLA_ONLY=true` (cloud):**
  - Only `/api/health` and `/api/charla/*` exist.
  - `GET /` redirects (307) to `/charla/`.
  - FinAlly's other routers aren't mounted.

## 1. Environment variables (`backend/app/config.py`, already written by the lead)

| Var | Reader | Default | Meaning |
|---|---|---|---|
| `CHARLA_ONLY` | `Settings.charla_only` | false | Mount only the health and charla routers; `/` → `/charla/` |
| `CHARLA_ADMIN_KEY` | `charla_admin_key()` | "" | Presenter key. Empty → admin API returns 503 |
| `CHARLA_SECRET` | `charla_secret()` | random per process | HMAC key for every stored secret |
| `RESEND_API_KEY`, `CHARLA_EMAIL_FROM` | `resend_settings()` | "", `IA Revolutions <onboarding@resend.dev>` | Email. No key → log the link instead of sending |
| `CHARLA_EMAIL_RPS` | `charla_email_rps()` | 2 | Outbox send rate |
| `CHARLA_PHONE_AT` | `charla_phone_at()` | 15:50 | Bogotá time when the WhatsApp prompt appears by itself; `off` turns it off |
| `CHARLA_DEV_LINKS` | `charla_dev_links()` | false | Return `dev_link_token` from register (tests). Ignored if Resend is configured |
| `CHARLA_PUBLIC_URL` | `charla_public_url()` | "" | Origin for email links. Empty → derive it from the request (`request.base_url`) |
| `LLM_MOCK`, `OPENROUTER_API_KEY` | `llm_mode()` | | Theme classification (mock → keyword classifier only) |

## 2. Content (`backend/app/charla/content.py`, written by the lead and owned by backend-room)

- **Steps 0–6** are `quiz`; `QUESTIONS[i]` holds `text`, 4 `options`, `answer` (an index) and `why`.
- **Step 7** is `open` (`OPEN_QUESTION`, `OPEN_PLACEHOLDER`, at most `OPEN_MAX_CHARS=280`).
- **Step 8** is `closing` (`CLOSING_TITLE`).
- **Durations:** `QUESTION_MS=20000`, `OPEN_MS=60000`, `GRACE_MS=1500`.
- **Scoring:** `quiz_points(correct, elapsed_ms)` = 500 + round(500 × remaining/20000), or 0 if wrong. A non-empty open answer earns `OPEN_POINTS=100`.
- **Themes:** `THEMES = ("Ventas y atención", "Finanzas", "Operaciones", "Marketing", "Recursos humanos", "Otro")`.
- **Helpers:** `kind_of(step)`, `title_of(step)` and `duration_ms(step)`.

## 3. Database (`backend/app/db/schema.py`, written by the lead)

Tables: `charla_attendees`, `charla_sessions`, `charla_answers` and `charla_state`. Read the SQL in schema.py.
- Use `connect()`, `transaction()`, `new_id()` and `now_iso()` from `app.db.connection`. The connection is shared under an RLock and runs in autocommit.
- **Usernames:** `username` is shown as typed (trimmed, with spaces collapsed). `username_key` is `normalize_username()`: NFKD with accents stripped, casefolded, spaces collapsed. It is UNIQUE.
- **Emails:** `email` is lowercased and trimmed, and UNIQUE.
- **Secrets are never stored in clear.** `link_hash`, `pending_hash` and `token_hash` are all `common.hash_secret(secret)`.
- **The `charla_state` row (`id=1`)** is created by `common.ensure_state_row()`. Call it at startup and in reset.
- **Answers:**
  - `charla_answers.choice` is the option index (0–3) as displayed.
  - `open_text` holds the open answer; its `theme` stays NULL until classified.
  - `ms` is the time from the question opening to the answer arriving, clamped at ≥ 0.
- **Time:** times in seconds are ISO strings (`*_at`). Room timing uses epoch ms (`*_ms`), always from `common.now_ms()`.

## 4. Backend modules and their Python interfaces

### 4.1 `app/charla/common.py` (lead, already written)
`now_ms()`, `new_secret()`, `hash_secret(v)`, `bus` (with `public_version`, `admin_version`, `bump(public=True)`), `ensure_state_row()`, `verification_on()`, `bearer_token(request)` and `require_admin` (a FastAPI dependency).
- **Bus rule:** call `common.bus.bump()` after any change phones must see.
  - That covers room state, reveals, the phone prompt, and a verification toggle; the last matters because the waiting page may need it.
  - Call `common.bus.bump(public=False)` for changes only the presenter needs: registrations, answers, themes, email stats, hides.

### 4.2 `app/charla/accounts.py` (backend-auth)
```python
USERNAME_RE  # 2-24 chars: letters (incl. accents/ñ), digits, space, . _ -
def clean_username(raw: str) -> str            # strip + collapse inner spaces
def normalize_username(raw: str) -> str        # uniqueness key
def username_error(raw: str) -> str | None     # Spanish message or None
def check_username(raw: str, email: str | None = None) -> dict   # §5.1 body
def register(username: str, email: str, *, base_url: str) -> dict  # §5.2 body; raises HTTPException
def pending_status(pending: str) -> dict       # §5.3 body; raises HTTPException(404)
def verify_link(link_token: str) -> dict       # §5.4 body; raises HTTPException(400)
def attendee_for_token(token: str | None) -> sqlite3.Row | None   # session -> attendee row
def current_attendee(request: Request) -> sqlite3.Row             # FastAPI dependency; 401 if none
def reset_accounts() -> None                   # wipe attendees + sessions (used by room.reset_all)
```
- **Username ownership.** A name is free unless another attendee holds it and that attendee is *active*.
  - **Active** means verified, or has a session, or has an unexpired link.
  - A stale row (unverified, with no sessions and an expired link) is deleted when someone else claims its name.
  - The same email may re-register with the same name, or switch to a name that's free.
- **Suggestions:** when a name is taken, return `suggestion`, the first free one of `"<name>2"…"<name>99"`, kept within 24 characters.
- **Links:**
  - `link_expires_at` is now + 30 min. The link is **reusable until it expires**.
  - Every successful `register` makes a new link, which replaces the old one, and a new `pending`.
- **Resend limits:** a 30 s cooldown per email between sends (429). At most 5 sends per email per rolling hour, tracked with `sends_window_start` (429).
- **Verification off** (`common.verification_on()` is false): `register` creates a session immediately and returns `status: "in"`. The attendee stays unverified.
- **After `verify_link`:** set `verified_at` and `pending_approved_at`, and create a new session for the clicking browser.
  - `pending_status` then returns `in` with a **new** session token each time it is called after approval. The tab stops polling after the first success.
  - Pending expires 30 min after the last register.
- **Bus:** registrations, verifications and new sessions → `bus.bump(public=False)`.

### 4.3 `app/charla/email.py` (backend-auth)
```python
class EmailOutbox:
    def enqueue(self, to: str, username: str, link: str) -> None   # never blocks, never raises
    async def run(self) -> None        # background task: sends at charla_email_rps(), honours 429 Retry-After, 2 retries
    def stats(self) -> dict            # {"queued": int, "sent": int, "failed": int, "last_error": str | None}
outbox: EmailOutbox                    # module singleton
```
- **Sending:** Resend `POST https://api.resend.com/emails` with `httpx.AsyncClient`, sending `from`, `to`, `subject`, `html` and `text`.
- **Subject:** `Entra a la charla, {username}`.
- **HTML:** dark (#070909), with the logo at `{base}/charla/logo.png`.
  - Headline "Un toque y entras a la sala".
  - One big teal button, **ENTRAR A LA SALA** (bg #5eead4, text #070909), linking to the link.
  - The plain link below it, and the line "Si no fuiste tú, ignora este correo."
  - Keep the HTML simple and email-safe: tables and inline styles.
- **No API key:** log `CHARLA LINK for <email>: <link>` at INFO and count it as sent.
- Stats changes → `bus.bump(public=False)`.

### 4.4 `app/charla/room.py` (backend-room)
```python
def startup() -> None                    # ensure_state_row(); an expired open question becomes closed
async def tick_loop() -> None            # every 0.25 s: tick()
def tick() -> None                       # auto-close at deadline; CHARLA_PHONE_AT prompt (Bogotá tz)
def launch() / close() / reveal() / next_step() / goto(step) / reset_step() / phone_now() -> None  # raise HTTPException(409) when not allowed
def set_verification(on: bool) -> None
def set_hidden(*, answer_id: str | None, attendee_id: str | None, hidden: bool) -> None
def reset_all() -> None                  # accounts.reset_accounts(); delete answers; state back to step 0 idle, verification on
def submit_answer(attendee_id: str, step: int, choice: int | None, text: str | None) -> None  # 409 rules in §5.7
def submit_phone(attendee_id: str, phone: str | None, consent: bool, skip: bool) -> None
def public_view(attendee: sqlite3.Row | None) -> dict   # §6.1 {"state":…, "me":…}
def admin_view() -> dict                                  # §6.2
def export_csv() -> str
```
- **Phase transitions:**
  - `launch`: idle → open. It sets `opened_at_ms` and `deadline_ms = now + duration` (quiz or open step).
    - At the closing step, `launch` just sets `phone_prompt=1` and leaves the phase idle.
  - `close`: open → closed. `reveal`: closed → revealed.
  - `next_step`: step + 1 (at most 8), phase idle, and clears `opened_at_ms` and `deadline_ms`.
  - `goto(step)`: like next_step, but to any step from 0 to 8. Answers are kept.
  - `reset_step`: deletes the current step's answers and sets the phase back to idle.
  - Every transition updates `updated_at` and bumps the bus (public).
- **Automatic phone prompt:** `tick()` sets `phone_prompt=1` once the Bogotá time is ≥ `charla_phone_at()` on the talk day. That's any day; it's a live demo. Phones never show the prompt while `phase=="open"`; `viewFor` handles that.
- **Open answers:** after storing one, call `classify.schedule(answer_id)`. That call must never raise into the request.
- **Settled points.** A step's points count toward `score` and `rank` only once the step is *settled*:
  - `step < state.step`, or
  - `step == state.step` with `phase == "revealed"`.
  - This keeps a score from leaking correctness before the reveal.
- **Ranking:** settled score descending, then total `ms` of correct answers ascending, then `created_at`. Hidden attendees are excluded from the projected ranking (admin `ranking` marks `hidden`).

### 4.5 `app/charla/classify.py` (llm)
```python
def keyword_theme(text: str) -> str                 # deterministic rules over THEMES, Spanish keywords
async def classify_text(text: str) -> str           # LLM (structured output ThemeReply) -> keyword fallback -> "Otro"
def schedule(answer_id: str) -> None                # create_task(classify one answer); stores theme; bus.bump(public=False)
async def reclassify_pending() -> int               # themes still NULL (startup + admin "reclassify")
```
- **Mode:** with `llm_mode()` equal to "mock" or "unconfigured", only `keyword_theme` is used. With "openrouter", the LLM is used.
- **Concurrency:** a semaphore of 4, and a 30 s timeout per call.
- **Schema:** `ThemeReply(theme: Literal[THEMES])` with `extra="forbid"`.
- **Shared client:** `app/llm/client.py` gets a keyword-only `response_format: type[BaseModel] = ChatReply` parameter on `complete()`. The default keeps chat unchanged.

### 4.6 HTTP layer
- **`app/api/charla_auth.py` (backend-auth):** §5.1–§5.5.
- **`app/api/charla_room.py` (backend-room):** §5.6–§5.9 and §7.
- All routes are `async def`, and each module defines `router = APIRouter()`.
- **`app/main.py` (backend-room):**
  - Include `health` and both charla routers always. Include watchlist, portfolio, the price stream and chat only when `not settings.charla_only`.
  - All of them go **before** the `/api/{path}` catch-all.
  - If `charla_only`, add `@app.get("/", include_in_schema=False) -> RedirectResponse("/charla/")` before the static mount.
  - In the lifespan, after `init_db`:
    - Call `room.startup()`.
    - Add tasks `room.tick_loop()`, `email.outbox.run()` and `classify.reclassify_pending()` to `tasks`.
    - Keep everything else, including the market and snapshots.

## 5. Public API (`/api/charla/*`)

Errors use FastAPI's `{"detail": "<Spanish message>"}`. Attendee calls carry `Authorization: Bearer <token>`.

### 5.1 `GET /api/charla/username?u=<name>&email=<optional>`
```json
{"valid": true, "available": false, "message": "Ese nombre ya está en uso. Prueba con otro, por ejemplo «José P2».", "suggestion": "José P2"}
```
- When valid and available, `message` is null.
- When invalid, `valid` is false and `message` is one of:
  - "Usa entre 2 y 24 caracteres."
  - "Usa solo letras, números, espacios, punto, guion o guion bajo."

### 5.2 `POST /api/charla/register` `{"username": "José P", "email": "jose@empresa.com"}`
- 200 when a link is sent:
  ```json
  {"status": "link_sent", "pending": "<secret>", "email": "jose@empresa.com", "username": "José P", "resend_in_s": 30, "dev_link_token": "<only when CHARLA_DEV_LINKS>"}
  ```
- 200 when verification is off:
  ```json
  {"status": "in", "token": "<session>", "username": "José P"}
  ```
- 400 for an invalid username (the message from §5.1), or "Revisa el correo: necesitamos uno válido para el enlace."
- 409: "Ese nombre ya está en uso. Prueba con otro, por ejemplo «José P2»."
- 429: "Espera {n} s para pedir otro enlace." or "Ya pediste varios enlaces. Intenta en unos minutos."
- The email link is `{base}/charla/entrar/#v=<link-token>`. `base` is `charla_public_url()`, or else the request's base URL without the trailing slash.

### 5.3 `GET /api/charla/register/status?p=<pending>`
- `{"status": "waiting"}`
- `{"status": "in", "token": "<new session>", "username": "José P"}`
- 404: "Este registro expiró. Vuelve a escribir tu correo."

### 5.4 `POST /api/charla/verify` `{"v": "<link-token>"}`
- 200: `{"token": "<new session>", "username": "José P"}`
- 400: "Este enlace expiró o no es válido. Pide uno nuevo."

### 5.5 `GET /api/charla/me` (Bearer)
- 200: `{"state": …, "me": …}`, the same body as the SSE payload §6.1.
- 401: "Tu sesión expiró. Vuelve a registrarte."

### 5.6 `GET /api/charla/stream?t=<token>` (SSE)
- Starts with `retry: 2000`.
- Sends `data: <§6.1 JSON>` immediately, then whenever `bus.public_version` changes. It also resends `me` after the attendee's own answer or phone, since `submit_*` bumps the admin bus and the stream also watches a per-attendee version kept by room.
- Polls every 0.5 s and sends `: keepalive` every 15 s.
- An invalid token gets a 401 before the stream opens.

### 5.7 `POST /api/charla/answer` (Bearer)
- Body: `{"step": 2, "choice": 1}` for a quiz, or `{"step": 7, "text": "…"}` for the open question.
- 200: `{"accepted": true}`. **Never** includes correctness.
- 409 when:
  - the step isn't the current one, or the phase isn't open, or it arrives after `deadline + GRACE_MS`: "La pregunta ya está cerrada."
  - the attendee already answered this step: "Ya respondiste esta pregunta."
- 400: "Elige una opción válida." or "Escribe al menos 8 caracteres." (open text: 8–280 after strip).

### 5.8 `POST /api/charla/phone` (Bearer)
- Body: `{"phone": "300 123 4567", "consent": true}` or `{"skip": true}`.
- 200: `{"ok": true}`.
- 400: "Escribe un celular colombiano de 10 dígitos." (digits only, 10 of them, starting with 3), or "Necesitamos tu autorización para escribirte por WhatsApp."

### 5.9 Admin API (`require_admin`: `X-Admin-Key` header or `?key=`): 401 "Clave de presentador incorrecta." or 503 when not configured
All of these are `POST` and return `{"ok": true}`; the change arrives over the admin stream.
- `/api/charla/admin/launch`, `/close`, `/reveal`, `/next`, `/reset-step`, `/phone-now`, `/reclassify`
- `/api/charla/admin/goto` `{"step": 3}`
- `/api/charla/admin/verification` `{"on": false}`
- `/api/charla/admin/hide` `{"answer_id": "…", "hidden": true}` or `{"attendee_id": "…", "hidden": true}`
- `/api/charla/admin/reset` `{"confirm": "RESET"}`. Anything else → 400.

409 messages:
- "Primero cierra la pregunta."
- "La pregunta ya está abierta."
- "Esta pregunta ya se lanzó. Usa reiniciar pregunta."
- "No hay pregunta abierta."

## 6. Payloads

### 6.1 Attendee view (SSE data and the `/me` body)
```json
{
  "state": {
    "version": 12, "server_now_ms": 1792700000000,
    "step": 2, "kind": "quiz", "phase": "open",
    "number": 3, "total_quiz": 7,
    "remaining_ms": 13450, "duration_ms": 20000,
    "question": {"text": "…", "options": ["…", "…", "…", "…"], "placeholder": null},
    "reveal": null,
    "phone_prompt": false,
    "room_count": 34
  },
  "me": {
    "attendee_id": "…", "username": "José P", "verified": true,
    "score": 1820, "rank": 5,
    "answer": {"step": 2, "choice": 1, "text": null},
    "result": null,
    "phone_status": "none"
  }
}
```
**`state`:**
- `kind` is `quiz`, `open` or `closing`.
- `phase` is `idle`, `open`, `closed` or `revealed`.
- `number` is 1–7 for a quiz and null otherwise.
- `remaining_ms` is non-null only while the phase is open; the client counts down locally from receipt.
- `question` is null for closing. For the open question, `options` is `[]` and `placeholder` is set.
- **`reveal`:** only when `phase == "revealed"`.
  - For a quiz: `{"answer": 1, "why": "…", "distribution": [3, 20, 5, 2]}`.
  - For the open question: `{"answer": null, "why": null, "distribution": null}`.
- `room_count` is the number of active attendees (verified or with a session).

**`me`:**
- `answer` is this attendee's answer to the **current** step, or null.
- `result` is only for the current step when `phase == "revealed"`. It is `{"correct": true, "points": 842}`, and for the open question `{"correct": null, "points": 100 | 0}`.
  - Once revealed, `result` is always present, even when the attendee didn't answer: a quiz gives `{correct:false, points:0}` and the open question `{correct:null, points:0}`. Use `me.answer == null` to tell "Se acabó el tiempo" apart from "No era esa".
- **Auto-close:** a question closes at `deadline + GRACE_MS`. During the grace window `remaining_ms` is 0.
- `score` and `rank` count settled steps only (§4.4).
- `phone_status` is `none`, `given` or `skipped`.
- `me` is null if there is no or an invalid token (`/me` returns 401 instead).

### 6.2 Admin view (admin SSE data)
```json
{
  "version": 40, "server_now_ms": 0,
  "state": { "…§6.1 state…": "", "verification_on": true, "phone_prompt_at": "15:50", "deadline_ms": 0, "opened_at_ms": 0 },
  "script": [{"step": 0, "kind": "quiz", "title": "…", "options": ["…"], "answer": 2, "why": "…"}],
  "counts": {"registered": 36, "active": 34, "verified": 31, "pending": 3, "with_phone": 12, "answered": 20, "correct": 15},
  "distribution": [3, 20, 5, 2],
  "themes": [{"name": "Ventas y atención", "count": 11}],
  "quotes": [{"answer_id": "…", "attendee_id": "…", "username": "José P", "text": "…", "theme": "Finanzas", "hidden": false, "created_at": "…"}],
  "ranking": [{"rank": 1, "attendee_id": "…", "username": "José P", "score": 4410, "correct": 6, "verified": true, "hidden": false}],
  "email": {"queued": 0, "sent": 31, "failed": 1, "last_error": null}
}
```
- `script` lists all 9 steps.
- `counts.answered` and `counts.correct` are for the current step.
- `distribution` is live for the current quiz step, or null.
- `themes` lists all 6, in `THEMES` order, counting the open step.
- `quotes` holds open answers, newest first.
- `ranking` holds the top 100.

### 6.3 `GET /api/charla/admin/stream?key=` (SSE)
- `data: <§6.2>` on connect, then whenever `bus.admin_version` changes, and at least every 1 s while a question is open, so the countdown stays honest.
- `retry: 2000`, with a 15 s keepalive.

## 7. CSV (`GET /api/charla/admin/export.csv?key=`)
- UTF-8 **with BOM**, `;` separator, CRLF line endings, and `Content-Disposition: attachment; filename="charla-<YYYYMMDD-HHMM>.csv"`.
- Columns: `puesto;usuario;correo;verificado;celular;autoriza_whatsapp;puntaje;correctas;p1..p7` (the chosen letter A–D plus ✓ or ✗), then `abierta;tema;registrado`.

## 8. Backend tests
- Put them in `backend/tests/charla/`, with **unique** file names starting `test_charla_`, and no `__init__.py`.
- The shared fixtures are in `backend/tests/charla/conftest.py` (lead): `charla_env`, `clock`, `charla_client`, `admin`, `enter`, `bearer`.
- Run them from `backend/` with `uv run pytest tests/charla -q`. Before you report done, run the whole suite with `uv run pytest -q`. It was 230 passed before this work.

## 9. Frontend

### 9.1 Routes (static export with `trailingSlash: true`, served by FastAPI)
| Route | Page file | Component (owner) |
|---|---|---|
| `/charla/` | `src/app/charla/page.tsx` | `src/components/charla/Registro.tsx` (frontend-registro) |
| `/charla/entrar/` | `src/app/charla/entrar/page.tsx` | `src/components/charla/Entrar.tsx` (frontend-registro) |
| `/charla/sala/` | `src/app/charla/sala/page.tsx` | `src/components/charla/Sala.tsx` (frontend-sala) |
| `/charla/presentador/` | `src/app/charla/presentador/page.tsx` | `src/components/charla/Presentador.tsx` (frontend-presenter) |
| `/charla/datos/` | `src/app/charla/datos/page.tsx` | (frontend-shell) |

- Pages are client components (`"use client"`) that render the component.
- Each component agent may add its own `*.module.css` next to its component.

### 9.2 Shared library `src/lib/charla/` (frontend-shell; `types.ts` written by the lead)
- **`types.ts`:** the TS mirror of §5–§6. Don't redefine these types elsewhere.
- **`api.ts`:**
  - `charlaApi.checkUsername(u, email?)`, `.register(username, email)`, `.status(pending)`, `.verify(v)`, `.me(token)`, `.answer(token, body)`, `.phone(token, body)`.
  - `adminApi(key)` with `.launch()`, `.close()`, `.reveal()`, `.next()`, `.goto(step)`, `.resetStep()`, `.phoneNow()`, `.reclassify()`, `.verification(on)`, `.hide(body)`, `.reset()`, plus `exportUrl` and `streamUrl`.
  - It uses `request` exported from `src/lib/api.ts`, and maps `ApiError(0)` to "Sin conexión. Revisa tu internet e intenta de nuevo."
- **`stream.ts`:** `connectCharlaStream(url, onData, onStatus) -> () => void`.
  - It uses EventSource with reconnect and status `connecting|live|reconnecting|offline`, modelled on `src/lib/priceStore.ts`.
  - It reconnects on `visibilitychange` (visible) and `online`.
  - It takes an optional `poll: () => Promise<data>` that runs every 3 s while not live.
  - Hook: `useCharlaStream<T>(url | null, poll?) -> {data: T | null, status, receivedAt}`. `receivedAt` is `performance.now()` at receipt, for local countdowns.
- **`session.ts`:** `getToken`, `setToken`, `clearToken`, `getPending`, `setPending`, `clearPending`, `getAdminKey`, `setAdminKey`, `getMonitorBase`, `setMonitorBase`, all wrapped in try/catch.
  - `setPending(info)` takes `{pending, email, username, sentAt}` (sentAt is epoch ms of the last send, for the resend countdown). `getPending()` returns that object or `null`.
  - Keys: `charla.token`, `charla.pending`, `charla.adminKey`, `charla.monitorBase`; the default monitor base is `http://localhost:4800`.
- **`validate.ts`:** `usernameError(u)` (same rules as §5.1, client-side), `emailError(e)`, `phoneError(p)`.
- **`views.ts`:** `viewFor(state, me)` returns one of `'wait' | 'question' | 'answered' | 'result' | 'open' | 'phone' | 'end'`:
  1. `me.phone_status == 'none'` and `state.phone_prompt` and `state.phase != 'open'` → `phone`
  2. `kind == 'closing'` → `end`
  3. phase idle → `wait`
  4. phase open: answered → `answered`; otherwise `question` for a quiz, `open` for the open question
  5. phase closed → `answered`. When `me.answer` is null, the view shows "Se acabó el tiempo".
  6. phase revealed → `result`
- **`format.ts`:** `fmtPoints(n)` → `toLocaleString('es-CO')`, `remainingSeconds(state, receivedAt)`.

### 9.3 Styles (frontend-shell: `src/app/charla/layout.tsx` and `src/app/charla/charla.css`)
- **Root:** the layout wraps its children in `<div className="charla" lang="es">`.
- **Fonts:** `@fontsource-variable/jetbrains-mono` (new dependency) plus the existing Archivo.
- **Tokens** on `.charla`:
  - backgrounds: `--c-bg` #070909, `--c-card` #0d1211, `--c-panel` #0a0d0c
  - borders: `--c-border` #1f2523, `--c-border-2` #2a312f
  - text: `--c-text` #f2f5f4, `--c-muted` #8b9491, `--c-muted-2` #b4bbb8, `--c-muted-3` #c9d1ce
  - accents: `--c-teal` #5eead4, `--c-teal-dark` #2c6b61, `--c-cyan` #22d3ee, `--c-fuchsia` #ff2bd6, `--c-amber` #f5a524, `--c-amber-dark` #5a4410, `--c-error` #ff7a7a
  - fonts: `--f-title` 'Archivo Variable', `--f-mono` 'JetBrains Mono Variable'
- **Body:** `body:has(.charla){background:#070909}`.
- **Classes**, each matching the `.dc.html` look:
  - `.holo` (animated hologram title) and `.rise`, `.pop`, `.pulse`, `.live` (animations).
  - `.c-label` (small mono caps), `.c-fld` (input), `.c-ta` (textarea).
  - `.c-btn` (primary teal), `.c-btn-ghost`, `.c-btn-link`, `.c-card`, `.c-err`.
  - `.c-col` (thin scrollbar), `.c-chip`.
  - Plus `prefers-reduced-motion` rules.
- **Assets:** `public/charla/logo.png`, copied from the design folder.

### 9.4 Weight and behaviour
- Charla pages must not import lightweight-charts, d3 or anything from `src/components/*` outside `charla/`. The target is under 250 KB gzipped of JS per route.
- **Presenter:** a 1440×810 stage scaled with `transform: scale(min(innerWidth/1440, innerHeight/810))`. The QR uses the npm `qrcode` package, added by frontend-presenter.
- **Keyboard shortcuts:** `L` launch, `C` close, `R` reveal, `→` next, `P` projection, `Q` QR.
- **Tests:** Vitest + React Testing Library, as `*.test.ts(x)` next to the code. Run `npm run test` and `npm run typecheck` from `frontend/`.

## 10. E2E and load (tester)
- **Setup:** `test/scripts/start-server.mjs` gets the env `CHARLA_ADMIN_KEY=e2e`, `CHARLA_DEV_LINKS=true`, `CHARLA_PHONE_AT=off` and an empty `RESEND_API_KEY`. The app keeps `charla_only` false in E2E, so the FinAlly specs still run.
- **Spec:** `test/tests/charla.spec.ts`.
- **Load test:** `test/load/charla_load.py`. It runs 40 attendees with verification off, against `--base` with `--key`.

## 11. Ownership (edit **only** your files; ask the owner for anything else)

**Update (23 Oct): the swarm was reduced to 3 agents.** The other agents are stopped, and their files now belong to these three:
- **backend-room** owns everything under backend-auth, backend-room, llm and devops.
- **frontend-presenter** owns everything under frontend-shell, frontend-registro, frontend-sala and frontend-presenter.
- **tester** owns everything under tester and monitor.

**Update (23 Oct): deployment is local only, with no Railway.** The app runs in Docker on Elkin's laptop at `http://localhost:8000`, using the root `.env`. The Railway files (`Dockerfile.railway`, `railway.json`, `.railwayignore`) are kept but not used for now. Phones can reach the app only on the same Wi-Fi.

The table below shows the original split, which is useful for reading each agent's plan file.

| Agent | Files |
|---|---|
| team-lead | this contract, `config.py`, `db/schema.py`, `charla/__init__.py`, `charla/common.py`, `tests/charla/conftest.py`, `src/lib/charla/types.ts`, `.agent-monitor/layout.json` |
| backend-auth | `charla/accounts.py`, `charla/email.py`, `api/charla_auth.py`, `tests/charla/test_charla_accounts*.py`, `test_charla_email.py` |
| backend-room | `charla/content.py`, `charla/room.py`, `api/charla_room.py`, `app/main.py`, `tests/charla/test_charla_room*.py`, `test_charla_only.py`, `test_charla_csv.py` |
| llm | `app/llm/client.py`, `charla/classify.py`, `tests/charla/test_charla_classify.py` |
| frontend-shell | `next.config.ts`, `src/lib/api.ts` (export `request` only), `src/lib/charla/*` except `types.ts`, `src/app/charla/layout.tsx`, `charla.css`, `src/app/charla/datos/`, `public/charla/*`, `package.json` and the lockfile (shared installs: you run `npm install` for others) |
| frontend-registro | `Registro.tsx`, `Entrar.tsx`, their CSS modules and tests, `src/app/charla/page.tsx`, `src/app/charla/entrar/` |
| frontend-sala | `Sala.tsx`, its CSS module and tests, `src/app/charla/sala/` |
| frontend-presenter | `Presentador.tsx` (split into `src/components/charla/presenter/*` if you like), its CSS and tests, `src/app/charla/presentador/` |
| devops | `Dockerfile.railway`, `railway.json`, `.railwayignore`, `scripts/start_charla.ps1`, Railway deploy |
| monitor | `C:\Users\elkin\projects\agent-monitor\web\*`, `planning/charla/LIVE_DEMO.md` |
| tester | `test/tests/charla.spec.ts`, `test/scripts/start-server.mjs` (env only), `test/load/*` |

- **Dependencies:** `npm install` changes are made only by **frontend-shell**. Ask them to add a package: `qrcode` and `@types/qrcode` for the presenter.
- **Python dependencies:** none are needed. `httpx` and `tzdata` are already present.
