import os
import subprocess
import sys
import uuid
from collections.abc import Generator
from pathlib import Path

import pytest
from sqlalchemy import Connection, Engine, create_engine, inspect, text
from sqlalchemy.engine import make_url
from sqlalchemy.exc import IntegrityError

from app.core.config import settings
from app.core.db import engine as app_engine

BACKEND_DIR = Path(__file__).resolve().parents[2]
# Last revision in which privilege is still stored in user.is_superuser
PREVIOUS_REVISION = "fe56fa70289e"
# The revision under test: adds user.role and drops user.is_superuser
ROLE_REVISION = "4f7c2d9e8a13"


@pytest.fixture
def scratch_engine() -> Generator[Engine]:
    """
    Engine for a throwaway database that exists for one test.

    The migrations never touch the database shared by the rest of the suite.
    """
    name = f"migration_test_{uuid.uuid4().hex}"
    url = make_url(str(settings.DATABASE_URL)).set(database=name)
    admin_engine = app_engine.execution_options(isolation_level="AUTOCOMMIT")
    engine = create_engine(url)
    with admin_engine.connect() as connection:
        connection.execute(text(f'CREATE DATABASE "{name}"'))
    try:
        yield engine
    finally:
        engine.dispose()
        with admin_engine.connect() as connection:
            connection.execute(text(f'DROP DATABASE "{name}" WITH (FORCE)'))


def run_alembic(engine: Engine, *args: str) -> None:
    """
    Run the Alembic CLI against the engine's database, as prestart.sh does.

    It runs in a subprocess of the same interpreter, with DATABASE_URL
    overridden, so app/alembic/env.py is used unchanged.
    """
    database_url = engine.url.render_as_string(hide_password=False)
    try:
        subprocess.run(
            [sys.executable, "-m", "alembic", *args],
            cwd=BACKEND_DIR,
            env={**os.environ, "DATABASE_URL": database_url},
            check=True,
            capture_output=True,
            text=True,
        )
    except subprocess.CalledProcessError as error:
        pytest.fail(f"alembic {' '.join(args)} failed:\n{error.stderr}")


def upgrade(engine: Engine, revision: str) -> None:
    run_alembic(engine, "upgrade", revision)


def downgrade(engine: Engine, revision: str) -> None:
    run_alembic(engine, "downgrade", revision)


def user_columns(engine: Engine) -> dict[str, str | None]:
    """Column names of the user table, mapped to their server defaults."""
    return {
        column["name"]: column["default"]
        for column in inspect(engine).get_columns("user")
    }


def insert_user(connection: Connection, **columns: object) -> None:
    values = {"id": uuid.uuid4(), "hashed_password": "not-a-real-hash", **columns}
    names = ", ".join(values)
    placeholders = ", ".join(f":{name}" for name in values)
    connection.execute(
        text(f'INSERT INTO "user" ({names}) VALUES ({placeholders})'), values
    )


def test_upgrade_maps_superusers_to_admin_and_keeps_is_active(
    scratch_engine: Engine,
) -> None:
    upgrade(scratch_engine, PREVIOUS_REVISION)
    with scratch_engine.begin() as connection:
        insert_user(
            connection,
            email="active-superuser@example.com",
            is_active=True,
            is_superuser=True,
        )
        insert_user(
            connection,
            email="inactive-superuser@example.com",
            is_active=False,
            is_superuser=True,
        )
        insert_user(
            connection,
            email="normal-user@example.com",
            is_active=True,
            is_superuser=False,
        )

    upgrade(scratch_engine, ROLE_REVISION)

    assert "is_superuser" not in user_columns(scratch_engine)
    with scratch_engine.connect() as connection:
        rows = connection.execute(text('SELECT email, role, is_active FROM "user"'))
        users = {email: (role, is_active) for email, role, is_active in rows}
    assert users == {
        "active-superuser@example.com": ("admin", True),
        "inactive-superuser@example.com": ("admin", False),
        "normal-user@example.com": ("member", True),
    }


def test_insert_without_role_gets_member(scratch_engine: Engine) -> None:
    upgrade(scratch_engine, "head")

    with scratch_engine.begin() as connection:
        insert_user(connection, email="no-role@example.com", is_active=True)

    with scratch_engine.connect() as connection:
        role = connection.execute(text('SELECT role FROM "user"')).scalar_one()
    assert role == "member"


def test_unknown_role_is_rejected(scratch_engine: Engine) -> None:
    upgrade(scratch_engine, "head")

    with pytest.raises(IntegrityError, match="ck_user_role"):
        with scratch_engine.begin() as connection:
            insert_user(
                connection,
                email="unknown-role@example.com",
                is_active=True,
                role="superuser",
            )


def test_downgrade_restores_is_superuser_only_for_admins(
    scratch_engine: Engine,
) -> None:
    upgrade(scratch_engine, ROLE_REVISION)
    with scratch_engine.begin() as connection:
        insert_user(connection, email="admin@example.com", is_active=True, role="admin")
        insert_user(
            connection,
            email="inactive-admin@example.com",
            is_active=False,
            role="admin",
        )
        insert_user(
            connection, email="manager@example.com", is_active=True, role="manager"
        )
        insert_user(
            connection, email="member@example.com", is_active=True, role="member"
        )

    downgrade(scratch_engine, PREVIOUS_REVISION)

    columns = user_columns(scratch_engine)
    assert "role" not in columns
    # The original column had no server default; the downgrade must not leave one
    assert columns["is_superuser"] is None
    with scratch_engine.connect() as connection:
        rows = connection.execute(
            text('SELECT email, is_superuser, is_active FROM "user"')
        )
        users = {
            email: (is_superuser, is_active) for email, is_superuser, is_active in rows
        }
    assert users == {
        "admin@example.com": (True, True),
        "inactive-admin@example.com": (True, False),
        "manager@example.com": (False, True),
        "member@example.com": (False, True),
    }
