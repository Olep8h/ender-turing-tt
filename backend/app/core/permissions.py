"""
The access policy: roles, permissions and the rules that decide who may do what.

To change an access rule, change it here. Route handlers ask this module and
never mention a role themselves.
"""

from collections.abc import Sequence
from enum import StrEnum
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    # Type-only: app.models imports Role and Permission from this module
    from app.models import Item, User


class Role(StrEnum):
    ADMIN = "admin"
    MANAGER = "manager"
    MEMBER = "member"


class Permission(StrEnum):
    USERS_READ = "users:read"
    # Create, update and delete users, including their role and active status.
    # Also guards the admin utilities that can take over an account or send
    # mail: the password recovery email preview and the test email.
    USERS_MANAGE = "users:manage"
    METRICS_READ = "metrics:read"
    ITEMS_MANAGE_ANY = "items:manage_any"


ROLE_PERMISSIONS: dict[Role, frozenset[Permission]] = {
    Role.ADMIN: frozenset(
        {
            Permission.USERS_READ,
            Permission.USERS_MANAGE,
            Permission.METRICS_READ,
            Permission.ITEMS_MANAGE_ANY,
        }
    ),
    Role.MANAGER: frozenset({Permission.USERS_READ, Permission.METRICS_READ}),
    Role.MEMBER: frozenset(),
}


def permissions_for(role: Role) -> frozenset[Permission]:
    # Default deny: a role without an entry is allowed nothing
    return ROLE_PERMISSIONS.get(role, frozenset())


def has_permission(user: User, permission: Permission) -> bool:
    return permission in permissions_for(user.role)


def can_access_item(user: User, item: Item) -> bool:
    return item.owner_id == user.id or has_permission(user, Permission.ITEMS_MANAGE_ANY)


def can_delete_own_account(user: User) -> bool:
    return user.role != Role.ADMIN


def may_remove_active_admin(
    *, new_role: Role | None, new_is_active: bool | None
) -> bool:
    """
    Whether an update could end someone's time as an active admin.

    It looks only at the requested change (None means unchanged), not at the
    user's current state, so it can be asked before any row is locked.
    """
    return new_role not in (None, Role.ADMIN) or new_is_active is False


class LastAdminError(Exception):
    """The change would leave the system without an active admin."""


def ensure_active_admin_remains(
    active_admins: Sequence[User], *, leaving: User
) -> None:
    """
    Raise LastAdminError if `leaving` is the only active admin.

    `leaving` is a user who is about to be demoted, deactivated or deleted.
    `active_admins` must be read and locked in the same transaction as the
    change, so that concurrent requests cannot each remove a different admin.
    It is the only source of truth here: whether `leaving` is an active admin
    is decided by its presence in that locked list, not by its own attributes.
    """
    if [admin.id for admin in active_admins] == [leaving.id]:
        raise LastAdminError
