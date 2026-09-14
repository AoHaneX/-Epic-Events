"""Display the current Epic Events session."""

from app.auth_session import AuthSessionError, get_current_user
from app.database import SessionLocal


def main() -> None:
    try:
        with SessionLocal() as session:
            employee = get_current_user(session)
            print(f"Utilisateur : {employee.full_name}")
            print(f"Email       : {employee.email}")
            print(f"Rôle        : {employee.role.code}")
    except AuthSessionError as error:
        print(f"Session indisponible : {error}")
        raise SystemExit(1) from error


if __name__ == "__main__":
    main()
