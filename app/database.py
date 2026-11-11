import os

from sqlalchemy import create_engine
from sqlalchemy.orm import DeclarativeBase, sessionmaker

from . import config  # noqa: F401  (asegura la carga del .env)

DEFAULT_DATABASE_URL = "postgresql+psycopg://tickets:tickets@localhost:5432/tickets"


def normalize_database_url(url: str) -> str:
    """Adapta las URLs de Render/Heroku al driver psycopg 3.

    Render entrega la conexión como ``postgresql://...`` (o ``postgres://...``),
    que SQLAlchemy interpretaría con psycopg2. El proyecto usa psycopg 3, así
    que se añade ``+psycopg`` al esquema.
    """
    if url.startswith("postgres://"):
        return "postgresql+psycopg://" + url[len("postgres://") :]
    if url.startswith("postgresql://"):
        return "postgresql+psycopg://" + url[len("postgresql://") :]
    return url


DATABASE_URL = normalize_database_url(os.getenv("DATABASE_URL", DEFAULT_DATABASE_URL))

# SQLite necesita desactivar la comprobación de hilo; PostgreSQL no.
connect_args = {"check_same_thread": False} if DATABASE_URL.startswith("sqlite") else {}

engine = create_engine(
    DATABASE_URL,
    connect_args=connect_args,
    pool_pre_ping=True,
)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)


class Base(DeclarativeBase):
    pass


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
