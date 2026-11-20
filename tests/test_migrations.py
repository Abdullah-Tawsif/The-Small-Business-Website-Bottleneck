from decimal import Decimal

import pytest
from alembic import command
from alembic.config import Config
from alembic.script import ScriptDirectory
from sqlalchemy import create_engine, inspect, select, text
from sqlalchemy.exc import OperationalError
from sqlalchemy.orm import Session

from database.database import Base
from database.adopt_legacy import adopt
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
    command.upgrade(alembic_config(), "4b0699abd0b3")
    engine = create_engine(database_url)
    with engine.begin() as connection:
        connection.exec_driver_sql("DROP TABLE alembic_version")
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
    with pytest.raises(RuntimeError, match="refuse|limited to"):
        migration_database_url()


def test_migration_temp_root_is_platform_aware(monkeypatch, tmp_path):
    import database.migration_safety as safety

    monkeypatch.setattr(safety, "TEMP_ROOT", tmp_path.resolve())
    target = tmp_path / "platform-temp.sqlite"
    monkeypatch.setenv("DATABASE_URL", f"sqlite:///{target}")
    assert migration_database_url()


def test_legacy_backup_copy_adoption_keeps_records_and_source(tmp_path, monkeypatch):
    backup = tmp_path / "separately-backed-up.sqlite"
    backup_url = f"sqlite:///{backup}"
    monkeypatch.setenv("DATABASE_URL", backup_url)
    command.upgrade(alembic_config(), "4b0699abd0b3")
    source_engine = create_engine(backup_url)
    with source_engine.begin() as connection:
        connection.exec_driver_sql("DROP TABLE alembic_version")
    with Session(source_engine) as session:
        session.add(
            Package(
                name="Backup preserved package",
                slug="backup-preserved-package",
                description="must survive adoption",
                min_price=Decimal("12.00"),
                max_price=Decimal("24.00"),
                currency="BDT",
                features=["backup-test"],
                is_active=True,
                display_order=1,
            )
        )
        session.commit()
    source_engine.dispose()

    target = tmp_path / "agencyforge-legacy-import.sqlite"
    adopt(backup, target)

    migrated = create_engine(f"sqlite:///{target}")
    source = create_engine(backup_url)
    try:
        with Session(migrated) as session:
            package = session.scalar(
                select(Package).where(Package.slug == "backup-preserved-package")
            )
            assert package is not None
            assert package.description == "must survive adoption"
        with source.connect() as connection:
            assert connection.exec_driver_sql(
                "SELECT COUNT(*) FROM sqlite_master "
                "WHERE type='table' AND name='alembic_version'"
            ).scalar_one() == 0
            assert connection.exec_driver_sql(
                "SELECT COUNT(*) FROM packages WHERE slug='backup-preserved-package'"
            ).scalar_one() == 1
    finally:
        migrated.dispose()
        source.dispose()


def test_legacy_adoption_rejects_invalid_schema_and_preserves_backup(tmp_path):
    from database.legacy_adoption import verify_legacy_schema

    backup = tmp_path / "invalid.sqlite"
    engine = create_engine(f"sqlite:///{backup}")
    with engine.begin() as connection:
        connection.exec_driver_sql("CREATE TABLE unrelated (value TEXT)")
    with pytest.raises(RuntimeError, match="missing required tables"):
        verify_legacy_schema(engine)
    with engine.connect() as connection:
        assert connection.exec_driver_sql(
            "SELECT name FROM sqlite_master WHERE type='table' AND name='unrelated'"
        ).scalar_one() == "unrelated"
    engine.dispose()


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
