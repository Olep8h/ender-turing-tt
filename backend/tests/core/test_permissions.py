from app.core.permissions import ROLE_PERMISSIONS, Role


def test_every_role_has_a_permissions_entry() -> None:
    # A role missing from the table is denied everything. This keeps a new
    # role from shipping without an explicit decision about what it may do.
    assert set(ROLE_PERMISSIONS) == set(Role)
