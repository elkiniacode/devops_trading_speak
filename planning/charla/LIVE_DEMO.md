# Live demo runbook: "Agentic Engineering" (Fri 23 Oct 2026, Bogotá)

This runbook covers what to open, in what order, and what to do when something breaks. Two things run on stage:
- **The room (the quiz):**
  - Attendees use the room app (`/charla/`) on their phones. Per Elkin's decision (23 Oct) it runs in **local Docker** (`Dockerfile` with the root `.env`) on the laptop; phones must be on the same Wi-Fi, or use a tunnel if remote access is needed. Railway is out of scope for this rehearsal.
  - You drive it from the presenter panel.
- **The agent dashboards:**
  - The agent monitor runs locally at `http://localhost:4800`.
  - It shows a live agent team working: AGENTES, HISTORIAL and HILOS.

Placeholders: `<PUBLIC>` is the room's public origin (the tunnel URL, or Railway's), and `<KEY>` is your `CHARLA_ADMIN_KEY`.

---

## 1. One hour before

1. **Check the room app** (the container is up and the tunnel answers): `curl <PUBLIC>/api/health` must return `{"status":"ok",...}`.
2. **Run the load test against `<PUBLIC>`.** From the repo root:
   ```
   uv run --project backend python test/load/charla_load.py --base <PUBLIC> --key <KEY> --n 40
   ```
   - It must print **PASS**: p95 launch→phone under 1.5 s, and p95 answer POST under 500 ms.
   - It turns email verification off, registers 40 fake attendees, runs Q1, and then **resets the room** (verification goes back on).
   - It refuses to run if real people have already registered. Don't pass `--force` once the doors are open.
3. **Open everything:**
   ```
   powershell -ExecutionPolicy Bypass -File scripts\start_charla.ps1 -PublicUrl <PUBLIC>
   ```
   This starts the monitor on :4800 if it isn't running, checks `<PUBLIC>/api/health`, and opens the presenter panel and AGENTES.
4. **Open the presenter at `<PUBLIC>/charla/presentador/#key=<KEY>`.** The key moves from the URL into the browser's storage. Check these:
   - The room is on step 1, idle.
   - The RANKING tab is empty.
   - Verification is ON.
   - The QR overlay (`Q`) opens `<PUBLIC>/charla/`.
5. **Test with your own phone:**
   - Scan the QR and register. The email arrives with "ENTRAR A LA SALA". Tap it, and the original tab enters the Sala by itself.
   - Then reset the room from the panel (it asks you to confirm), so the real ranking starts empty.

## 2. Running the quiz

| Key | Action | Notes |
|---|---|---|
| `L` | Launch the question | 20 s for each quiz question, 60 s for the open one. Phones show it within about half a second. |
| `C` | Close answers | It also closes on its own at the deadline, plus 1.5 s of grace. |
| `R` | Reveal | Only after it closes. Phones show CORRECTO / NO ERA ESA with points, and scores update. |
| `→` | Next step | Steps 1–7 are the quiz, 8 is the open question, 9 is the closing (WhatsApp prompt). |
| `P` | Projection mode | |
| `Q` | QR overlay | |

- **Wrong click:**
  - Go to any step with the script list on the left (answers are kept).
  - "Reiniciar pregunta" deletes the current step's answers and makes it launchable again.
- **Email is slow or bouncing:**
  - Turn verification OFF in the right-hand column.
  - New registrations then enter straight away (status `in`), and people still waiting get in on their next status poll.
- **Trolling in the open answers:** hide the answer or the attendee from the right-hand column. Projection mode only shows answers that aren't hidden.
- **At the end:**
  - Export the CSV (`<PUBLIC>/api/charla/admin/export.csv?key=<KEY>`) before any reset.
  - It's UTF-8 with a BOM and `;`-separated, so it opens directly in Excel.

## 3. The agent dashboards

- **Pages:**
  - `http://localhost:4800/Agentes.dc.html`: the architecture map, timers and tasks.
  - `Historial.dc.html`: each agent's steps.
  - `Hilos.dc.html`: the messages between agents.
- They need no internet: React, Babel and the fonts are vendored in `agent-monitor/web/vendor/`.
- **Following:**
  - Without `?run=`, every page follows the **newest live run**.
  - While no team is live, it shows "Esperando un equipo de agentes".
  - It switches by itself within about 5 s of a new team starting. Discovery runs every 2 s, and the pages refresh the run list every 4 s.
- **Picker:** at the top left, next to the logo.
  - "Seguir la sesión en vivo más reciente" follows the newest live run.
  - Choosing a run pins it (`?run=<id>` in the URL). Links between the three pages keep that choice.
- **Replay a finished run:** `Agentes.dc.html?run=<id>&replay=1&speed=20`. Use this if the live team is slow on stage.

### What the monitor can see
It reads Claude Code's own files under `~/.claude` and never controls the agents. Two kinds of team show up:
1. **Agent teams with a config:** `~/.claude/teams/<team>/config.json`. These work as before.
2. **Implicit session teams:** a normal Claude Code session that spawns **named** background agents (`Agent` with `name: "..."`).
   - It reads `~/.claude/projects/<project>/<session>/subagents/*.jsonl` and `.meta.json`.
   - The run is called `subagents-<session id>`.
   - The session itself is the lead, shown as **team-lead**; messages to `main` count as messages to the lead.
   - Unnamed helper agents (Explore, Plan) are left out.
   - Messages are shown with their delivery state, including the ones that reach a busy agent (queued `<agent-message from=…>` records, and the coordinator's "sent a message while you were working" notes).

For a team you start on stage:
- Paste the **Teammate block** from `agent-monitor/TEAM_RULES.md` into each spawn prompt, so each agent keeps `.agent-monitor/plans/<name>.md`.
- Have the lead write `.agent-monitor/layout.json` in the project (layers, cards, cables).

Without these, the map still works, but tasks are rebuilt from the messages.

## 4. If something breaks

| Symptom | Do this |
|---|---|
| The dashboards show an old or empty run | Pick "Seguir la sesión en vivo más reciente" in the picker, or open the page without `?run=`. |
| The monitor doesn't answer | In `C:\Users\elkin\projects\agent-monitor`, run `uv run python -m monitor`. It rebuilds every run from the transcripts. |
| The monitor started before the new code | Restart it (same command). Code changes in `monitor/` need a restart; changes in `web/` only need a page reload. |
| Phones stuck on "Revisa tu correo" | Turn verification OFF in the panel. |
| Phones show "Sin conexión" | They retry on their own, every 2 s on the stream and every 3 s by polling. Nothing to do unless the container or tunnel is down. |
| The tunnel or container is down | Restart the container (the SQLite volume keeps the room), start a new tunnel, then reopen the presenter on the new origin and show the QR (`Q`). |
| The LLM is down | Open-answer themes fall back to the keyword classifier automatically. |
| A question was launched by mistake | Close it, then "Reiniciar pregunta". |

## 5. Verified before the talk (local)

- Current verification (23 Oct 2026): local Docker image built successfully; `/api/health` and all `/charla/` pages returned 200; register-to-enter-to-answer-to-reveal passed; and the 40-attendee load test passed with launch-to-phone p95 722 ms and answer POST p95 61 ms. The room was reset afterward.

- The load test with 40 attendees against a local server: PASS. Every stream saw the launch and the reveal, launch→phone p95 was 546 ms, and answer POST p95 was 155 ms.
- The monitor:
  - With this swarm's session, it showed 11 agents (team-lead plus 10) and its messages.
  - Live follow, the waiting state and the picker switch were checked in a browser, with no external network requests.
  - `uv run pytest`: 357 passed.
  - Vitest: 249 passed. Playwright: 36 passed. Frontend and E2E typechecks: clean.
