from sqlalchemy import create_engine
from sqlalchemy.orm import DeclarativeBase

from app.config import Settings


class Base(DeclarativeBase):
    pass


def make_engine(settings: Settings):
    return create_engine(
        settings.database_url.get_secret_value(),
        pool_pre_ping=True,
        connect_args={"connect_timeout": 3, "options": "-c statement_timeout=5000 -c timezone=UTC"},
        hide_parameters=True,
    )
