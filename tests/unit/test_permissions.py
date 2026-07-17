"""Permission catalog invariants (framework-free domain logic)."""

from visionroute.domain.permissions import (
    ROLE_LABELS_TR,
    ROLE_PERMISSIONS,
    Permission,
    RoleKey,
    role_has,
)


def test_every_role_has_a_turkish_label() -> None:
    for role in RoleKey:
        assert role in ROLE_LABELS_TR
        assert ROLE_LABELS_TR[role].strip()


def test_every_role_has_a_permission_set() -> None:
    for role in RoleKey:
        assert role in ROLE_PERMISSIONS


def test_owner_has_all_permissions() -> None:
    assert ROLE_PERMISSIONS[RoleKey.OWNER] == frozenset(Permission)


def test_auditor_is_read_only() -> None:
    for permission in ROLE_PERMISSIONS[RoleKey.AUDITOR]:
        assert permission.value.endswith(".read")


def test_role_has_helper() -> None:
    assert role_has(RoleKey.EVENT_REVIEWER, Permission.EVENTS_REVIEW)
    assert not role_has(RoleKey.ANALYST, Permission.EVENTS_REVIEW)
    assert not role_has(RoleKey.DRIVER, Permission.ORG_UPDATE)


def test_only_owner_and_admin_can_manage_members() -> None:
    managers = {role for role in RoleKey if Permission.ORG_MEMBERS_MANAGE in ROLE_PERMISSIONS[role]}
    assert managers == {RoleKey.OWNER, RoleKey.ADMIN}
