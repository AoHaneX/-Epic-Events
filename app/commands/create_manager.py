"""Crée le premier compte de gestion dans une base vide."""

from getpass import getpass

from app.database import SessionLocal
from app.services.employees import create_initial_manager


def ask_confirmed_password() -> str:
    password = getpass("Mot de passe (12 caractères minimum) : ")
    confirmation = getpass("Confirme le mot de passe              : ")
    if password != confirmation:
        raise ValueError("Les deux mots de passe sont différents.")
    return password


def main() -> None:
    print("Création du premier compte MANAGEMENT")
    full_name = input("Nom complet : ").strip()
    email = input("Email       : ").strip()
    password = ask_confirmed_password()

    with SessionLocal.begin() as session:
        manager = create_initial_manager(
            session,
            full_name=full_name,
            email=email,
            password=password,
        )
        print(f"Compte créé : {manager.email} ({manager.role.code})")


if __name__ == "__main__":
    main()
