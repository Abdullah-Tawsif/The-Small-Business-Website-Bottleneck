"""Guarded adoption of a backed up legacy SQLite database copy."""

from __future__ import annotations

from pathlib import Path

from sqlalchemy import Engine, inspect

from database.database import Base
from models import ai_session, lead, package, user  # noqa: F401


def verify_legacy_schema(engine: Engine) -> None:
    """Verify the baseline application tables and columns before stamping."""
    inspector = inspect(engine)
    required_tables = set(Base.metadata.tables)
    present_tables = set(inspector.get_table_names())
    if not required_tables.issubset(present_tables):
        missing = ", ".join(sorted(required_tables - present_tables))
        raise RuntimeError(f"Legacy database is missing required tables: {missing}.")
    mismatches = []
    for table_name, table in Base.metadata.tables.items():
        required = {column.name for column in table.columns}
        if table_name == "ai_sessions":
            # These fields were added after the published legacy baseline.
            required -= {"owner_user_id", "guest_capability_hash", "expires_at"}
        present = {column["name"] for column in inspector.get_columns(table_name)}
        if not required.issubset(present):
            mismatches.append(table_name)
    if mismatches:
        raise RuntimeError(
            "Legacy database schema does not match the application baseline: "
            + ", ".join(mismatches)
        )


def row_counts(engine: Engine) -> dict[str, int]:
    """Return row counts for application tables for before/after comparison."""
    with engine.connect() as connection:
        return {
            table_name: int(connection.exec_driver_sql(
                f'SELECT COUNT(*) FROM "{table_name}"'
            ).scalar_one())
            for table_name in Base.metadata.tables
        }


def validate_adoption_paths(backup: Path, target: Path) -> tuple[Path, Path]:
    """Resolve and constrain source/target paths without following ambiguity."""
    backup = backup.expanduser().resolve(strict=True)
    target = target.expanduser().resolve(strict=False)
    if not backup.is_file():
        raise RuntimeError("The separately created legacy backup file is required.")
    if backup == target:
        raise RuntimeError("Adoption target must be a copy separate from the backup.")
    protected = (Path(__file__).resolve().parents[1] / "agencyforge.db").resolve()
    if backup == protected or target == protected or backup.name == "agencyforge.db":
        raise RuntimeError("The protected agencyforge.db file cannot be adopted.")
    if target.name != "agencyforge-legacy-import.sqlite":
        raise RuntimeError(
            "Use the distinct target filename agencyforge-legacy-import.sqlite."
        )
    if target.exists():
        raise RuntimeError("Adoption target already exists; preserve it and choose a new directory.")
    return backup, target
