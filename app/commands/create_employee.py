"""Create an employee with the current manager session."""

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.auth_session import get_current_user
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
    with SessionLocal.begin() as session:
        actor = get_current_user(session)

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
