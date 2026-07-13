"""Production database-schema readiness guard (D-083).

Cloud Run must not make an image ready when the database is behind the Alembic head packaged
with that image. An older image may, however, see a revision it does not know after an additive
migration; that is the normal rollback case and remains allowed.
"""

from __future__ import annotations

import logging
import os

from alembic.config import Config
from alembic.runtime.migration import MigrationContext
from alembic.script import ScriptDirectory
from sqlalchemy import Engine

logger = logging.getLogger(__name__)


class SchemaBehindError(RuntimeError):
    """The database is at a revision known to this image but older than its packaged head."""


def ensure_schema_ready(engine: Engine, config: Config) -> None:
    """Fail when `engine` is behind the Alembic head described by `config`.

    The repository intentionally has one linear migration head. A DB revision unknown to the
    image is treated as newer and allowed so an already-migrated database does not prevent an
    older compatible image from cold-starting during rollback.
    """
    script = ScriptDirectory.from_config(config)
    code_heads = tuple(script.get_heads())
    if len(code_heads) != 1:
        raise RuntimeError(f"schema guard requires one Alembic head; found {code_heads!r}")

    with engine.connect() as conn:
        db_heads = tuple(MigrationContext.configure(conn).get_current_heads())

    if db_heads == code_heads:
        return
    if not db_heads:
        raise SchemaBehindError(
            f"database has no Alembic revision; packaged head is {code_heads[0]}"
        )

    known_revisions = {revision.revision for revision in script.walk_revisions()}
    unknown = [revision for revision in db_heads if revision not in known_revisions]
    if len(unknown) == len(db_heads):
        logger.warning(
            "database revision %s is newer than this image's known migration graph; "
            "allowing rollback startup",
            ",".join(unknown),
        )
        return

    raise SchemaBehindError(
        f"database revision {','.join(db_heads)} is behind packaged Alembic head {code_heads[0]}; "
        "run the production migration before deploying"
    )


def ensure_configured_schema_ready(engine: Engine) -> None:
    """Run the guard when `VJA_ALEMBIC_INI` is configured (the production image sets it).

    Local development and tests remain opt-in because they may construct intentionally partial
    schemas. The container always points this at `/app/alembic.ini`, so production cannot skip it.
    """
    config_path = os.environ.get("VJA_ALEMBIC_INI")
    if config_path:
        ensure_schema_ready(engine, Config(config_path))
