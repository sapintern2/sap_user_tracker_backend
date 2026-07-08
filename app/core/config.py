from functools import lru_cache
from os import getenv

from dotenv import load_dotenv
from pydantic import BaseModel


class Settings(BaseModel):
    app_name: str = "SAP User Tracker API"
    database_url: str


@lru_cache
def get_settings() -> Settings:
    load_dotenv()
    database_url = getenv("DATABASE_URL")

    if not database_url:
        raise ValueError("DATABASE_URL is missing from the .env file")

    return Settings(database_url=database_url)
