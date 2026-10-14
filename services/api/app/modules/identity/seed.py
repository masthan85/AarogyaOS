from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.db import set_tenant
from app.modules.identity.models import Permission, Role, RolePermission
from app.modules.identity.permissions import PERMISSIONS, ROLES


def sync_reference_data(session: Session) -> None:
    """Idempotently make the DB match the permission catalogue."""
    set_tenant(session, None, bypass=True)
    existing_perms = set(session.scalars(select(Permission.key)))
    for key, description in PERMISSIONS.items():
        if key not in existing_perms:
            session.add(Permission(key=key, description=description))
    session.flush()

    roles = {r.key: r for r in session.scalars(select(Role))}
    for key, (name, is_platform, perms) in ROLES.items():
        role = roles.get(key)
        if role is None:
            role = Role(key=key, name=name, is_platform=is_platform)
            session.add(role)
            session.flush()
        granted = set(
            session.scalars(
                select(RolePermission.permission_key).where(RolePermission.role_id == role.id)
            )
        )
        for perm in perms:
            if perm not in granted:
                session.add(RolePermission(role_id=role.id, permission_key=perm))
        # Revoke grants removed from the catalogue.
        for stale in granted - set(perms):
            session.delete(session.get(RolePermission, (role.id, stale)))
    session.commit()
    from app.modules.languages.service import sync_languages

    sync_languages(session)
