"""Operational commands: `seed`, `create-platform-admin`, `purge-audio` (run on a schedule)."""

import getpass
import sys

from sqlalchemy import select

from app.core.config import get_settings
from app.core.db import create_db_engine, create_sessionmaker, set_tenant
from app.core.security import hash_password
from app.modules.identity.models import Role, User, UserRole
from app.modules.identity.seed import sync_reference_data


def main(argv: list[str]) -> int:
    settings = get_settings()
    sm = create_sessionmaker(create_db_engine(settings.database_url))
    command = argv[0] if argv else ""
    with sm() as session:
        if command == "purge-audio":
            from app.core.crypto import FieldCrypto
            from app.modules.interactions.retention import purge_due_audio
            from app.speech.audio_store import LocalEncryptedAudioStore

            store = LocalEncryptedAudioStore(
                settings.audio_store_path, FieldCrypto(settings.field_encryption_key)
            )
            print(f"Audio files removed: {purge_due_audio(session, store)}")
            return 0
        if command == "seed":
            sync_reference_data(session)
            print("Reference data synced")
            return 0
        if command == "create-platform-admin":
            email = input("Email: ").strip().lower()
            password = getpass.getpass("Password (min 12 chars): ")
            if len(password) < 12:
                print("Password too short")
                return 1
            sync_reference_data(session)
            set_tenant(session, None, bypass=True)
            if session.scalar(
                select(User).where(User.organisation_id.is_(None), User.email == email)
            ):
                print("User already exists")
                return 1
            user = User(
                organisation_id=None,
                email=email,
                full_name="Platform Administrator",
                password_hash=hash_password(password),
            )
            session.add(user)
            session.flush()
            role = session.scalar(select(Role).where(Role.key == "super_admin"))
            assert role is not None
            session.add(UserRole(user_id=user.id, role_id=role.id, organisation_id=None))
            session.commit()
            print("Platform administrator created")
            return 0
    print("Usage: python -m app.cli [seed|create-platform-admin|purge-audio]")
    return 2


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
