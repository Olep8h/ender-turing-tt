"""
Security-critical access rules for the three roles.

Expected results are written out as literals on purpose: they are the access
policy as the product defines it, not values derived from the code under test.
"""

from collections.abc import Callable, Generator

import pytest
from fastapi.testclient import TestClient
from httpx import Response
from sqlmodel import Session, col, select

from app import crud
from app.core.config import settings
from app.core.permissions import Role
from app.models import User, UserCreate
from tests.utils.item import create_random_item
from tests.utils.user import create_random_user, create_user_and_log_in
from tests.utils.utils import random_email, random_lower_string

API = settings.API_V1_STR
Headers = dict[str, str]


@pytest.fixture(autouse=True)
def no_outgoing_email(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("app.api.routes.users.send_email", lambda **_: None)
    monkeypatch.setattr("app.api.routes.utils.send_email", lambda **_: None)


# --- Role by endpoint matrix -------------------------------------------------


@pytest.fixture(scope="module")
def headers_by_role(client: TestClient, db: Session) -> dict[Role, Headers]:
    return {
        role: create_user_and_log_in(client=client, db=db, role=role)[1]
        for role in Role
    }


def new_user_payload() -> dict[str, str]:
    return {"email": random_email(), "password": random_lower_string()}


# Each request targets a user or an item that belongs to somebody else.
REQUESTS: dict[str, Callable[[TestClient, Headers, Session], Response]] = {
    "list users": lambda client, headers, _db: client.get(
        f"{API}/users/", headers=headers
    ),
    "read another user": lambda client, headers, db: client.get(
        f"{API}/users/{create_random_user(db).id}", headers=headers
    ),
    "create a user": lambda client, headers, _db: client.post(
        f"{API}/users/", headers=headers, json=new_user_payload()
    ),
    "update another user": lambda client, headers, db: client.patch(
        f"{API}/users/{create_random_user(db).id}",
        headers=headers,
        json={"full_name": "Changed"},
    ),
    "delete another user": lambda client, headers, db: client.delete(
        f"{API}/users/{create_random_user(db).id}", headers=headers
    ),
    "read metrics": lambda client, headers, _db: client.get(
        f"{API}/metrics/", headers=headers
    ),
    "send a test email": lambda client, headers, _db: client.post(
        f"{API}/utils/test-email/",
        headers=headers,
        params={"email_to": random_email()},
    ),
    # Asked for an unknown email: an allowed caller gets 404, which shows the
    # permission check passed. The success path is not usable here because the
    # template's handler sets an invalid response header name ("subject:").
    "read password recovery email": lambda client, headers, _db: client.post(
        f"{API}/password-recovery-html-content/{random_email()}", headers=headers
    ),
    "read another user's item": lambda client, headers, db: client.get(
        f"{API}/items/{create_random_item(db).id}", headers=headers
    ),
    "update another user's item": lambda client, headers, db: client.put(
        f"{API}/items/{create_random_item(db).id}",
        headers=headers,
        json={"title": "Changed"},
    ),
}

# (request, status for admin, status for manager, status for member)
ACCESS_MATRIX = [
    ("list users", 200, 200, 403),
    ("read another user", 200, 200, 403),
    ("create a user", 200, 403, 403),
    ("update another user", 200, 403, 403),
    ("delete another user", 200, 403, 403),
    ("read metrics", 200, 200, 403),
    ("send a test email", 201, 403, 403),
    ("read password recovery email", 404, 403, 403),
    ("read another user's item", 200, 403, 403),
    ("update another user's item", 200, 403, 403),
]


@pytest.mark.parametrize(
    ("request_name", "role", "expected_status"),
    [
        pytest.param(name, role, status, id=f"{role} - {name}")
        for name, admin, manager, member in ACCESS_MATRIX
        for role, status in (
            (Role.ADMIN, admin),
            (Role.MANAGER, manager),
            (Role.MEMBER, member),
        )
    ],
)
def test_access_matrix(
    client: TestClient,
    db: Session,
    headers_by_role: dict[Role, Headers],
    request_name: str,
    role: Role,
    expected_status: int,
) -> None:
    response = REQUESTS[request_name](client, headers_by_role[role], db)

    assert response.status_code == expected_status


# --- Changes reach users who already have a session --------------------------


def test_demotion_applies_to_an_existing_session(
    client: TestClient, db: Session, superuser_token_headers: Headers
) -> None:
    manager, headers = create_user_and_log_in(client=client, db=db, role=Role.MANAGER)
    assert client.get(f"{API}/users/", headers=headers).status_code == 200

    r = client.patch(
        f"{API}/users/{manager.id}",
        headers=superuser_token_headers,
        json={"role": "member"},
    )
    assert r.status_code == 200

    assert client.get(f"{API}/users/", headers=headers).status_code == 403
    me = client.get(f"{API}/users/me", headers=headers).json()
    assert me["role"] == "member"
    assert me["permissions"] == []


def assert_unauthenticated(response: Response) -> None:
    assert response.status_code == 401
    assert response.headers["WWW-Authenticate"] == "Bearer"


def test_deactivation_ends_an_existing_session(
    client: TestClient, db: Session, superuser_token_headers: Headers
) -> None:
    user, headers = create_user_and_log_in(client=client, db=db, role=Role.MEMBER)
    assert client.get(f"{API}/users/me", headers=headers).status_code == 200

    r = client.patch(
        f"{API}/users/{user.id}",
        headers=superuser_token_headers,
        json={"is_active": False},
    )
    assert r.status_code == 200

    assert_unauthenticated(client.get(f"{API}/users/me", headers=headers))


def test_deletion_ends_an_existing_session(
    client: TestClient, db: Session, superuser_token_headers: Headers
) -> None:
    user, headers = create_user_and_log_in(client=client, db=db, role=Role.MEMBER)

    r = client.delete(f"{API}/users/{user.id}", headers=superuser_token_headers)
    assert r.status_code == 200

    assert_unauthenticated(client.get(f"{API}/users/me", headers=headers))


def test_invalid_token_is_unauthenticated(client: TestClient) -> None:
    headers = {"Authorization": "Bearer not-a-valid-token"}

    assert_unauthenticated(client.get(f"{API}/users/me", headers=headers))


# --- No privilege escalation ---------------------------------------------------


def test_signup_cannot_set_role_or_active_status(
    client: TestClient, db: Session
) -> None:
    email = random_email()

    r = client.post(
        f"{API}/users/signup",
        json={
            "email": email,
            "password": random_lower_string(),
            "full_name": "Signup User",
            "role": "admin",
            "is_superuser": True,
            "is_active": False,
        },
    )

    assert r.status_code == 200
    user = crud.get_user_by_email(session=db, email=email)
    assert user
    assert user.role == Role.MEMBER
    assert user.is_active is True


def test_update_me_cannot_change_role_or_active_status(
    client: TestClient, db: Session
) -> None:
    user, headers = create_user_and_log_in(client=client, db=db, role=Role.MEMBER)

    r = client.patch(
        f"{API}/users/me",
        headers=headers,
        json={"full_name": "New Name", "role": "admin", "is_active": False},
    )

    assert r.status_code == 200
    db.refresh(user)
    assert user.full_name == "New Name"
    assert user.role == Role.MEMBER
    assert user.is_active is True


def test_private_create_user_cannot_set_role(client: TestClient, db: Session) -> None:
    email = random_email()

    r = client.post(
        f"{API}/private/users/",
        json={
            "email": email,
            "password": random_lower_string(),
            "full_name": "Private User",
            "role": "admin",
            "is_superuser": True,
        },
    )

    assert r.status_code == 200
    user = crud.get_user_by_email(session=db, email=email)
    assert user
    assert user.role == Role.MEMBER


@pytest.mark.parametrize("role", [Role.MANAGER, Role.MEMBER])
def test_non_admin_cannot_promote_themselves(
    client: TestClient, db: Session, role: Role
) -> None:
    user, headers = create_user_and_log_in(client=client, db=db, role=role)

    r = client.patch(f"{API}/users/{user.id}", headers=headers, json={"role": "admin"})

    assert r.status_code == 403
    db.refresh(user)
    assert user.role == role


@pytest.mark.parametrize("role", [Role.MANAGER, Role.MEMBER])
def test_non_admin_cannot_promote_another_user(
    client: TestClient, db: Session, role: Role
) -> None:
    _, headers = create_user_and_log_in(client=client, db=db, role=role)
    other_user = create_random_user(db)

    r = client.patch(
        f"{API}/users/{other_user.id}", headers=headers, json={"role": "admin"}
    )

    assert r.status_code == 403
    db.refresh(other_user)
    assert other_user.role == Role.MEMBER


# --- At least one active admin always remains ---------------------------------


@pytest.fixture
def only_active_admin(
    client: TestClient, db: Session
) -> Generator[tuple[User, Headers]]:
    """
    A new admin who is the only active admin while the test runs.

    The other admins in the shared test database are deactivated, not demoted,
    so the tests also show that inactive admins do not count.
    """
    other_admins = db.exec(
        select(User).where(User.role == Role.ADMIN, col(User.is_active))
    ).all()
    for admin in other_admins:
        admin.is_active = False
    db.add_all(other_admins)
    db.commit()
    try:
        yield create_user_and_log_in(client=client, db=db, role=Role.ADMIN)
    finally:
        for admin in other_admins:
            admin.is_active = True
        db.add_all(other_admins)
        db.commit()


def test_only_active_admin_cannot_demote_themselves(
    client: TestClient, db: Session, only_active_admin: tuple[User, Headers]
) -> None:
    admin, headers = only_active_admin

    r = client.patch(
        f"{API}/users/{admin.id}", headers=headers, json={"role": "member"}
    )

    assert r.status_code == 409
    db.refresh(admin)
    assert admin.role == Role.ADMIN


def test_only_active_admin_cannot_deactivate_themselves(
    client: TestClient, db: Session, only_active_admin: tuple[User, Headers]
) -> None:
    admin, headers = only_active_admin

    r = client.patch(
        f"{API}/users/{admin.id}", headers=headers, json={"is_active": False}
    )

    assert r.status_code == 409
    db.refresh(admin)
    assert admin.is_active is True


def test_only_active_admin_cannot_delete_themselves(
    client: TestClient, db: Session, only_active_admin: tuple[User, Headers]
) -> None:
    admin, headers = only_active_admin
    admin_id = admin.id

    by_id = client.delete(f"{API}/users/{admin_id}", headers=headers)
    as_me = client.delete(f"{API}/users/me", headers=headers)

    # An admin can never delete their own account, whether or not they are the
    # last one, so this is refused before the last-admin rule is consulted.
    assert by_id.status_code == 403
    assert as_me.status_code == 403
    db.expire_all()
    assert db.get(User, admin_id) is not None


def test_admin_can_demote_another_admin_while_one_remains(
    client: TestClient, db: Session, only_active_admin: tuple[User, Headers]
) -> None:
    _, headers = only_active_admin
    second_admin = crud.create_user(
        session=db,
        user_create=UserCreate(
            email=random_email(), password=random_lower_string(), role=Role.ADMIN
        ),
    )

    r = client.patch(
        f"{API}/users/{second_admin.id}", headers=headers, json={"role": "member"}
    )

    assert r.status_code == 200
    db.refresh(second_admin)
    assert second_admin.role == Role.MEMBER


def test_update_that_omits_role_keeps_the_role(
    client: TestClient, db: Session, superuser_token_headers: Headers
) -> None:
    admin = crud.create_user(
        session=db,
        user_create=UserCreate(
            email=random_email(), password=random_lower_string(), role=Role.ADMIN
        ),
    )

    r = client.patch(
        f"{API}/users/{admin.id}",
        headers=superuser_token_headers,
        json={"full_name": "Renamed"},
    )

    assert r.status_code == 200
    db.refresh(admin)
    assert admin.full_name == "Renamed"
    assert admin.role == Role.ADMIN
