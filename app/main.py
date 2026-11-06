from sqlalchemy import inspect, select, text
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from app.database import Base, engine
from app.models import Role


def initialize_database(bind) -> None:
    """Create missing tables and roles without replacing existing data."""
    Base.metadata.create_all(bind=bind)
    with Session(bind) as session, session.begin():
        existing_codes = set(session.scalars(select(Role.code)))
        for code, name in (
            ("MANAGEMENT", "Gestion"),
            ("SALES", "Commercial"),
            ("SUPPORT", "Support"),
        ):
            if code not in existing_codes:
                session.add(Role(code=code, name=name))


def check_database() -> None:
    """Crée les tables manquantes puis affiche l'état de la connexion."""
    initialize_database(engine)

    with engine.connect() as connection:
        current_user, database_name, version = connection.execute(
            text("SELECT CURRENT_USER(), DATABASE(), VERSION()")
        ).one()
        tables = inspect(connection).get_table_names()

    print("Connexion MySQL réussie.")
    print(f"Utilisateur : {current_user}")
    print(f"Base        : {database_name}")
    print(f"Version     : {version}")
    print(f"Tables      : {', '.join(tables) if tables else 'aucune'}")


if __name__ == "__main__":
    try:
        check_database()
    except (SQLAlchemyError, RuntimeError, ValueError) as error:
        print(f"Échec de la connexion : {error}")
        raise SystemExit(1) from error

