from decimal import Decimal

import pytest
from alembic import command
from alembic.config import Config
from alembic.script import ScriptDirectory
from sqlalchemy import create_engine, inspect, select, text
from sqlalchemy.exc import OperationalError
from sqlalchemy.orm import Session

from database.database import Base
from database.migration_safety import REPOSITORY_ROOT, migration_database_url
from models.package import Package


def alembic_config() -> Config:
    return Config(str(REPOSITORY_ROOT / "alembic.ini"))


def test_fresh_database_migrates_to_current_schema(tmp_path, monkeypatch):
    database_path = tmp_path / "fresh.sqlite"
    monkeypatch.setenv("DATABASE_URL", f"sqlite:///{database_path}")

    command.upgrade(alembic_config(), "head")

    engine = create_engine(f"sqlite:///{database_path}")
    try:
        inspector = inspect(engine)
        assert set(Base.metadata.tables).issubset(inspector.get_table_names())
        assert inspector.has_table("alembic_version")
        with engine.connect() as connection:
            revision = connection.exec_driver_sql(
                "SELECT version_num FROM alembic_version"
            ).scalar_one()
            query_plan = " ".join(
                str(row[3])
                for row in connection.exec_driver_sql(
                    "EXPLAIN QUERY PLAN SELECT * FROM leads "
                    "ORDER BY created_at DESC, id DESC LIMIT 100"
                )
            )
        assert revision == ScriptDirectory(
            str(REPOSITORY_ROOT / "migrations")
        ).get_current_head()
        assert "ix_leads_created_at_id" in query_plan
        assert "TEMP B-TREE" not in query_plan
        command.check(alembic_config())
    finally:
        engine.dispose()


def test_legacy_schema_adoption_and_upgrade_preserve_synthetic_records(
    tmp_path,
    monkeypatch,
):
    database_path = tmp_path / "legacy.sqlite"
    database_url = f"sqlite:///{database_path}"
    monkeypatch.setenv("DATABASE_URL", database_url)
    engine = create_engine(database_url)
    Base.metadata.create_all(engine)
    with engine.begin() as connection:
        connection.exec_driver_sql("DROP INDEX ix_leads_created_at_id")
    with Session(engine) as session:
        session.add(
            Package(
                name="Preserved synthetic package",
                slug="preserved-synthetic-package",
                description="created before migration adoption",
                min_price=Decimal("10.00"),
                max_price=Decimal("20.00"),
                currency="BDT",
                features=["synthetic"],
                is_active=True,
                display_order=99,
            )
        )
        session.commit()

    # Existing create_all databases are adopted at the exact baseline only
    # after an operator has verified schema parity; the additive index then
    # upgrades without rebuilding tables or changing records.
    command.stamp(alembic_config(), "4b0699abd0b3")
    command.upgrade(alembic_config(), "head")
    with Session(engine) as session:
        preserved = session.scalar(
            select(Package).where(Package.slug == "preserved-synthetic-package")
        )
        assert preserved is not None
        assert preserved.description == "created before migration adoption"
    command.downgrade(alembic_config(), "4b0699abd0b3")
    with Session(engine) as session:
        assert session.scalar(
            select(Package).where(Package.slug == "preserved-synthetic-package")
        ) is not None
    assert not any(
        index["name"] == "ix_leads_created_at_id"
        for index in inspect(engine).get_indexes("leads")
    )
    with pytest.raises(RuntimeError, match="cannot be downgraded"):
        command.downgrade(alembic_config(), "base")
    engine.dispose()


@pytest.mark.parametrize(
    "database_path",
    [
        REPOSITORY_ROOT / "agencyforge.db",
        REPOSITORY_ROOT / "temporary-test.sqlite",
    ],
)
def test_migration_target_guard_rejects_repository_databases(
    database_path,
    monkeypatch,
):
    # This test validates the guard before any connection is created.
    monkeypatch.setenv("DATABASE_URL", f"sqlite:///{database_path}")
    with pytest.raises(RuntimeError, match="refuse|limited to /tmp"):
        migration_database_url()


def test_migrations_require_explicit_database_url(monkeypatch):
    monkeypatch.delenv("DATABASE_URL", raising=False)
    with pytest.raises(RuntimeError, match="Set DATABASE_URL explicitly"):
        migration_database_url()
    with pytest.raises(RuntimeError, match="Set DATABASE_URL explicitly"):
        command.upgrade(alembic_config(), "head")


def test_conflicting_legacy_schema_fails_without_removing_existing_data(
    tmp_path,
    monkeypatch,
):
    database_path = tmp_path / "conflicting.sqlite"
    database_url = f"sqlite:///{database_path}"
    monkeypatch.setenv("DATABASE_URL", database_url)
    engine = create_engine(database_url)
    with engine.begin() as connection:
        connection.execute(
            text(
                "CREATE TABLE packages "
                "(id INTEGER PRIMARY KEY, marker TEXT NOT NULL)"
            )
        )
        connection.execute(
            text("INSERT INTO packages (id, marker) VALUES (1, 'preserve-me')")
        )

    with pytest.raises(OperationalError):
        command.upgrade(alembic_config(), "head")

    with engine.connect() as connection:
        marker = connection.execute(
            text("SELECT marker FROM packages WHERE id=1")
        ).scalar_one()
    assert marker == "preserve-me"
    engine.dispose()
