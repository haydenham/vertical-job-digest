"""Database layer — SQLAlchemy Core engine, schema, and repositories.

SQLite locally and in tests; Postgres after the hosted deploy (D-025). The DB URL is
the only thing that changes between them (`VJA_DATABASE_URL`).
"""
