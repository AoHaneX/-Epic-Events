"""Teste l'authentification d'un collaborateur."""

from getpass import getpass

from app.auth import authenticate
from app.database import SessionLocal


def main() -> None:
    email = input("Email       : ").strip()
    password = getpass("Mot de passe : ")

    with SessionLocal.begin() as session:
        employee = authenticate(session, email, password)
        print(
            f"Connexion réussie : {employee.full_name} "
            f"({employee.role.code})"
        )


if __name__ == "__main__":
    main()
