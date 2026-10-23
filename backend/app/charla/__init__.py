"""Live talk ("charla"): registration, the quiz room and the presenter API.

The shared contract is planning/charla/CONTRACT.md. Modules:
- common.py   clock, secrets, the change bus, auth guards (shared by everything below)
- content.py  questions, themes and timings
- accounts.py usernames, registration, one-tap email links, sessions
- email.py    the Resend outbox
- room.py     the room state machine, scoring, ranking, views, CSV
- classify.py open-answer themes (LLM + keyword fallback)
"""
