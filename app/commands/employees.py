"""Employee commands."""

from getpass import getpass

from app.auth_session import get_current_user
from app.commands import CommandInputError, ask_identifier, collect_fields
from app.database import SessionLocal
from app.services import employees


def ask_confirmed_password() -> str:
    password = getpass("Mot de passe (12 caractères minimum) : ")
    confirmation = getpass("Confirme le mot de passe : ")
    if password != confirmation:
        raise CommandInputError("Les deux mots de passe sont différents.")
    return password


def main(action="create", **options) -> None:
    if action in ("create", "initial-manager"):
        fields = [
            ("full_name", "Nom complet", str),
            ("email", "Email", str),
        ]
        if action == "create":
            fields.append(("role_code", "Rôle (MANAGEMENT, SALES, SUPPORT)", str))
        values = collect_fields(options, fields)
        values["password"] = ask_confirmed_password()
        with SessionLocal.begin() as session:
            if action == "initial-manager":
                employee = employees.create_initial_manager(session, **values)
            else:
                actor = get_current_user(session)
                employee = employees.create_employee(session, actor, **values)
        print(f"Compte créé : {employee.email} ({employee.role.code})")
        return
    if action == "list":
        with SessionLocal() as session:
            actor = get_current_user(session)
            rows = employees.list_employees(session, actor)
        for employee in rows:
            print(f"#{employee.id} : {employee.full_name} — {employee.email} "
                  f"({employee.role.code}, {'actif' if employee.is_active else 'inactif'})")
        return
    employee_id = options.pop("id", None)
    if employee_id is None:
        employee_id = ask_identifier("Identifiant du collaborateur")
    if action == "update" and not options:
        raise CommandInputError("Indique au moins un champ à modifier (voir employees update --help).")
    new_password = ask_confirmed_password() if action == "password" else None
    with SessionLocal.begin() as session:
        actor = get_current_user(session)
        employee = employees.get_employee(session, employee_id)
        if action == "update":
            employees.update_employee(session, actor, employee, **options)
        elif action == "password":
            employees.change_password(session, actor, employee, new_password)
        elif action == "deactivate":
            employees.deactivate_employee(session, actor, employee)
        elif action == "delete":
            employees.delete_employee(session, actor, employee)
    print(f"Opération {action} effectuée sur le collaborateur #{employee_id}.")
