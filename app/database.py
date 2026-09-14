"""Configuration de la connexion SQLAlchemy à MySQL."""

import os

from dotenv import load_dotenv
from sqlalchemy import URL, create_engine
from sqlalchemy.orm import DeclarativeBase, sessionmaker


load_dotenv()


def required_env(name: str) -> str:
    """Retourne une variable d'environnement ou arrête clairement le démarrage."""
    value = os.getenv(name)
    if not value:
        raise RuntimeError(
            f"La variable {name} est absente. "
            "Copie .env.example vers .env puis complète ses valeurs."
        )
    return value


database_url = URL.create(
    drivername="mysql+pymysql",
    username=required_env("DB_USER"),
    password=required_env("DB_PASSWORD"),
    host=os.getenv("DB_HOST", "localhost"),
    port=int(os.getenv("DB_PORT", "3306")),
    database=os.getenv("DB_NAME", "epic_events"),
    query={"charset": "utf8mb4"},
)

engine = create_engine(
    database_url,
    echo=os.getenv("SQL_ECHO", "false").lower() == "true",
    pool_pre_ping=True,
)

SessionLocal = sessionmaker(
    bind=engine,
    autoflush=False,
    expire_on_commit=False,
)


class Base(DeclarativeBase):
    """Classe parente de tous les modèles ORM."""

