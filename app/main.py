from sqlalchemy import inspect, text
from sqlalchemy.exc import SQLAlchemyError

from app.database import Base, engine
import app.models  # noqa: F401  # enregistre les modèles dans Base.metadata


def check_database() -> None:
    """Crée les tables manquantes puis affiche l'état de la connexion."""
    Base.metadata.create_all(bind=engine)

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

