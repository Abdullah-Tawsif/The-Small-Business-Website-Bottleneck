"""Adopt a verified backup copy of an existing SQLite AgencyForge database.

Example:
    python -m database.adopt_legacy --backup /safe/backup.sqlite \
      --target /tmp/agencyforge-legacy-import.sqlite
"""

from __future__ import annotations

import argparse
import os
import shutil
from pathlib import Path

from alembic import command
from alembic.config import Config
from sqlalchemy import create_engine
from sqlalchemy.engine import URL

from database.legacy_adoption import (
    row_counts,
    validate_adoption_paths,
    verify_legacy_schema,
)
from database.migration_safety import REPOSITORY_ROOT

BASELINE = "4b0699abd0b3"


def adopt(backup: Path, target: Path, allow_non_temp: bool = False) -> None:
    """Copy a backup, verify it, stamp the baseline, upgrade and compare rows."""
    backup, target = validate_adoption_paths(backup, target)
    target.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(backup, target)
    database_url = URL.create("sqlite", database=str(target)).render_as_string(
        hide_password=False
    )
    old_database_url = os.environ.get("DATABASE_URL")
    old_allow_non_temp = os.environ.get("ALLOW_NON_TMP_MIGRATIONS")
    os.environ["DATABASE_URL"] = database_url
    if allow_non_temp:
        os.environ["ALLOW_NON_TMP_MIGRATIONS"] = "1"

    engine = create_engine(database_url)
    try:
        verify_legacy_schema(engine)
        before = row_counts(engine)
        config = Config(str(REPOSITORY_ROOT / "alembic.ini"))
        command.stamp(config, BASELINE)
        command.upgrade(config, "head")
        command.check(config)
        verify_legacy_schema(engine)
        after = row_counts(engine)
        if before != after:
            raise RuntimeError(
                f"Application row counts changed during adoption: {before} -> {after}."
            )
        print(f"Adoption verified: {target}")
        print(f"Application rows preserved: {after}")
    finally:
        engine.dispose()
        if old_database_url is None:
            os.environ.pop("DATABASE_URL", None)
        else:
            os.environ["DATABASE_URL"] = old_database_url
        if old_allow_non_temp is None:
            os.environ.pop("ALLOW_NON_TMP_MIGRATIONS", None)
        else:
            os.environ["ALLOW_NON_TMP_MIGRATIONS"] = old_allow_non_temp


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--backup", required=True, type=Path)
    parser.add_argument("--target", required=True, type=Path)
    parser.add_argument("--allow-non-temp", action="store_true")
    args = parser.parse_args()
    adopt(args.backup, args.target, args.allow_non_temp)


if __name__ == "__main__":
    main()
