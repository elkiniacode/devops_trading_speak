# frontend-presenter plan
(23 Oct: now owns the whole charla frontend: shell, registro, sala, presenter)
- [x] T1 Read the contract, the shared charla lib and the Presentador design
- [x] T2 Pure presenter logic (phase labels, control gating, ranking cut, timers) with tests
- [x] T10 Shell: finish the lib, keep stream.ts and its tests green (Node 25 localStorage polyfill in vitest.setup.ts)
- [x] T11 Shell: datos/page.tsx draft Ley 1581 policy (BORRADOR · PENDIENTE DE REVISIÓN)
- [x] T12 Registro + Entrar: finish their tests (stable mocked router fixed an infinite loop)
- [x] T13 Sala: all 7 views, tester testids (sala/data-view, sala-option-i, sala-result, sala-username), tests
- [x] T14 Phone-flow typecheck + tests, report to team-lead and tester
- [x] T3 Key gate (session key, #key= hash, 401 handling) and page wrapper
- [x] T4 Stage, header and tabs (SALA / RANKING / monitor links, clock, live dot)
- [x] T5 Left script, centre question panel and controls with 409 toast (tester's pres-* testids)
- [x] T6 Right column (open answers, counts, emails, verification, export, resets)
- [x] T7 Ranking tab, projection mode, QR overlay (only /charla/qr.png + URL text, no qrcode pkg; uninstall qrcode) and keyboard shortcuts
- [x] T8 Component tests (gate/401, controls per phase, ranking/projection, QR), typecheck
- [x] T9 Milestone report to team-lead
