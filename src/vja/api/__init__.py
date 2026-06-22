"""Read-only dashboard API (Phase 6 · B1, D-030/D-041).

A thin FastAPI surface over the nightly-computed DB: no live fetching, no LLM calls, no writes
(D-005, docs/11 §2). `create_app` builds the app; `api_main` runs it via uvicorn (`vja-api`).
"""

from vja.api.app import api_main, create_app

__all__ = ["api_main", "create_app"]
