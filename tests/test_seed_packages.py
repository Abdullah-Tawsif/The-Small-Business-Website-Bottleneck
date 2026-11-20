from sqlalchemy import create_engine, func, select
from sqlalchemy.orm import sessionmaker

import seed_packages as seed_module
from database.database import Base
from models.package import Package


def test_seed_packages_is_idempotent_and_preserves_existing_rows(
    monkeypatch,
    tmp_path,
):
    engine = create_engine(f"sqlite:///{tmp_path / 'package-seed.sqlite'}")
    Base.metadata.create_all(engine)
    test_sessions = sessionmaker(bind=engine, expire_on_commit=False)
    monkeypatch.setattr(seed_module, "SessionLocal", test_sessions)
    monkeypatch.setattr(seed_module, "verify_schema", lambda: None)

    try:
        seed_module.seed_packages()
        with test_sessions() as db:
            starter = db.scalar(
                select(Package).where(Package.slug == "starter-website")
            )
            starter.description = "Keep this operator-edited description."
            db.commit()

        seed_module.seed_packages()

        with test_sessions() as db:
            assert db.scalar(select(func.count()).select_from(Package)) == 4
            preserved = db.scalar(
                select(Package).where(Package.slug == "starter-website")
            )
            assert preserved.description == "Keep this operator-edited description."
    finally:
        engine.dispose()
