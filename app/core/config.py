from functools import lru_cache
from os import getenv

from dotenv import load_dotenv
from pydantic import BaseModel


class Settings(BaseModel):
    app_name: str = "SAP User Tracker API"
    database_url: str
    auth_secret_key: str = "change-this-secret-key"
    auth_default_password: str = "Pannipitiya@123"
    auth_token_hours: int = 12
    auth_admin_email: str = "priyanthas.cblms@cbllk.com"


@lru_cache
def get_settings() -> Settings:
    load_dotenv()
    database_url = getenv("DATABASE_URL")

    if not database_url:
        raise ValueError("DATABASE_URL is missing from the .env file")

    return Settings(
        database_url=database_url,
        auth_secret_key=getenv("AUTH_SECRET_KEY", "change-this-secret-key"),
        auth_default_password=getenv("AUTH_DEFAULT_PASSWORD", "Pannipitiya@123"),
        auth_token_hours=int(getenv("AUTH_TOKEN_HOURS", "12")),
        auth_admin_email=getenv("AUTH_ADMIN_EMAIL", "priyanthas.cblms@cbllk.com").lower(),
    )
