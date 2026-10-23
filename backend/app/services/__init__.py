"""Business logic shared by the REST routes and the LLM (CONTRACTS.md §3.3).

These are the only code paths that change trades, positions or the watchlist. Each one
raises a ValueError subclass whose message is safe to show to users.
"""
