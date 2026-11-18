"""
Create a manager and a member for trying out the three access levels locally.

Run it by hand after scripts/prestart.sh, which creates the admin. It is never
run automatically, refuses to run outside development, and only ever adds
users: an account that already exists is left exactly as it is.
"""

import logging

from sqlmodel import Session

from app import crud
from app.core.config import settings
from app.core.db import engine
from app.core.permissions import Role
from app.models import UserCreate

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

DEMO_USERS = {
    "manager@example.com": Role.MANAGER,
    "member@example.com": Role.MEMBER,
}


def seed_demo_users(session: Session) -> None:
    for email, role in DEMO_USERS.items():
        if crud.get_user_by_email(session=session, email=email):
            logger.info("%s already exists, left unchanged", email)
            continue
        user_in = UserCreate(
            email=email, password=settings.FIRST_SUPERUSER_PASSWORD, role=role
        )
        crud.create_user(session=session, user_create=user_in)
        logger.info("%s created", email)


def log_logins(session: Session) -> None:
    logger.info(
        "Logins. Accounts created by prestart.sh or by this script use the"
        " password from FIRST_SUPERUSER_PASSWORD; older ones keep their own."
    )
    for email in (settings.FIRST_SUPERUSER, *DEMO_USERS):
        user = crud.get_user_by_email(session=session, email=email)
        if user is None:
            logger.info("  %s: missing, run scripts/prestart.sh first", email)
        else:
            status = "active" if user.is_active else "inactive"
            logger.info("  %s: %s, %s", email, user.role, status)


def main() -> None:
    if settings.FASTAPI_ENV != "development":
        raise SystemExit(
            "Demo users are only for local development (FASTAPI_ENV=development)."
        )
    with Session(engine) as session:
        seed_demo_users(session)
        log_logins(session)


if __name__ == "__main__":
    main()
