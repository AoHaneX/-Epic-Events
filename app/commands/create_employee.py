"""Crée un collaborateur après authentification d'un manager."""

from getpass import getpass

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.auth import authenticate
from app.commands.create_manager import ask_confirmed_password
from app.database import SessionLocal
from app.models import Role
from app.services.employees import create_employee


def ask_role(session: Session) -> str:
    roles = session.scalars(select(Role).order_by(Role.id)).all()
    if not roles:
        raise ValueError("Aucun rôle n'existe dans la table roles.")

    role_codes = {role.code for role in roles}
    print(f"Rôles possibles : {', '.join(sorted(role_codes))}")
    value = input("Rôle : ").strip().upper()
    if value not in role_codes:
        raise ValueError("Rôle inconnu.")
    return value


def main() -> None:
    print("Authentification du manager")
    manager_email = input("Email       : ").strip()
    manager_password = getpass("Mot de passe : ")

    with SessionLocal.begin() as session:
        actor = authenticate(session, manager_email, manager_password)

        print("\nNouveau collaborateur")
        full_name = input("Nom complet : ").strip()
        email = input("Email       : ").strip()
        role_code = ask_role(session)
        password = ask_confirmed_password()

        employee = create_employee(
            session,
            actor,
            full_name=full_name,
            email=email,
            password=password,
            role_code=role_code,
        )
        print(f"Compte créé : {employee.email} ({employee.role.code})")


if __name__ == "__main__":
    main()
