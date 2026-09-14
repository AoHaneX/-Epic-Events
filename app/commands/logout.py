"""Close the local Epic Events session."""

from app.auth_session import AuthSessionError, clear_session


def main() -> None:
    try:
        clear_session()
    except AuthSessionError as error:
        print(f"Échec de la déconnexion : {error}")
        raise SystemExit(1) from error

    print("Déconnexion réussie.")


if __name__ == "__main__":
    main()
