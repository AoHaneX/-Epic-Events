"""Open a persistent Epic Events session."""

from getpass import getpass

from app.auth import AuthenticationError, authenticate
from app.auth_session import AuthSessionError, start_session
from app.database import SessionLocal


def main() -> None:
    email = input("Email       : ").strip()
    password = getpass("Mot de passe : ")

    try:
        with SessionLocal.begin() as session:
            employee = authenticate(session, email, password)
            employee_id = employee.id
            full_name = employee.full_name
            role_code = employee.role.code

        start_session(employee_id)
    except (AuthenticationError, AuthSessionError) as error:
        print(f"Échec de la connexion : {error}")
        raise SystemExit(1) from error

    print(f"Connexion réussie : {full_name} ({role_code})")


if __name__ == "__main__":
    main()
