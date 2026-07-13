from sqlalchemy.orm import Session

from app.core.allowed_users import ALLOWED_USERS
from app.core.auth import find_user_by_email, hash_password, normalize_email
from app.core.config import get_settings
from app.models.app_user import AppUser


def seed_allowed_users(db: Session) -> None:
    settings = get_settings()
    default_password_hash = hash_password(settings.auth_default_password)
    admin_email = normalize_email(settings.auth_admin_email)

    for allowed_user in ALLOWED_USERS:
        email = normalize_email(allowed_user["email"])
        role = "admin" if email == admin_email else "user"
        user = find_user_by_email(db, email)
        if user:
            user.name = allowed_user["name"]
            user.role = role
            user.is_active = True
            if user.must_change_password:
                user.password_hash = default_password_hash
            continue

        db.add(
            AppUser(
                email=email,
                name=allowed_user["name"],
                role=role,
                password_hash=default_password_hash,
                must_change_password=True,
                is_active=True,
            )
        )

    db.commit()
