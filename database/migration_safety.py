"""Validate explicit Alembic targets before any connection is opened."""

import os
import tempfile
from pathlib import Path

from sqlalchemy.engine import make_url

REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
FORBIDDEN_DATABASE = (REPOSITORY_ROOT / "agencyforge.db").resolve()
TEMP_ROOT = Path(tempfile.gettempdir()).resolve()


def migration_database_url() -> str:
    """Require an explicit and safely scoped migration target."""
    raw_url = os.environ.get("DATABASE_URL")
    if not raw_url:
        raise RuntimeError(
            "Set DATABASE_URL explicitly before running database migrations."
        )

    url = make_url(raw_url)
    allow_non_tmp = os.environ.get("ALLOW_NON_TMP_MIGRATIONS") == "1"
    if url.get_backend_name() == "sqlite":
        database = url.database
        if not database or database == ":memory:":
            raise RuntimeError("Migrations require a persistent SQLite database file.")
        path = Path(database).expanduser()
        if not path.is_absolute():
            path = Path.cwd() / path
        # resolve() follows existing symlink parents, preventing an apparently
        # temporary path from redirecting a migration into a protected file.
        path = path.resolve(strict=False)
        if path == FORBIDDEN_DATABASE or path.name == "agencyforge.db":
            raise RuntimeError("Migrations refuse the protected agencyforge.db file.")
        try:
            path.relative_to(REPOSITORY_ROOT)
            in_repository = True
        except ValueError:
            in_repository = False
        if in_repository and not allow_non_tmp:
            raise RuntimeError(
                "SQLite migrations refuse repository databases unless "
                "ALLOW_NON_TMP_MIGRATIONS=1 is explicitly set."
            )
        if not path.is_relative_to(TEMP_ROOT) and not allow_non_tmp:
            raise RuntimeError(
                f"SQLite migrations are limited to {TEMP_ROOT} unless "
                "ALLOW_NON_TMP_MIGRATIONS=1 is explicitly set."
            )
    elif not allow_non_tmp:
        raise RuntimeError(
            "Non-SQLite migrations require explicit ALLOW_NON_TMP_MIGRATIONS=1."
        )
    if url.get_backend_name() == "postgresql" and url.drivername == "postgresql":
        return url.set(drivername="postgresql+psycopg").render_as_string(
            hide_password=False
        )
    return raw_url
