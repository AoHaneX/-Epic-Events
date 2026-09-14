"""Création et gestion des comptes collaborateurs."""

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.auth import normalize_email
from app.models import Employee, Role
from app.permissions import AuthorizationError, can_manage_employees, require
from app.security import hash_password


class DuplicateEmailError(ValueError):
    """Un collaborateur utilise déjà cette adresse email."""


class UnknownRoleError(ValueError):
    """Le rôle demandé n'existe pas dans la table roles."""


def _email_already_exists(session: Session, email: str) -> bool:
    return session.scalar(
        select(Employee.id).where(Employee.email == normalize_email(email))
    ) is not None


def _get_role(session: Session, role_code: str) -> Role:
    normalized_code = role_code.strip().upper()
    role = session.scalar(select(Role).where(Role.code == normalized_code))
    if role is None:
        raise UnknownRoleError(f"Rôle inconnu : {normalized_code}")
    return role


def create_initial_manager(
    session: Session,
    *,
    full_name: str,
    email: str,
    password: str,
) -> Employee:
    """Crée le tout premier compte, uniquement si la table employees est vide."""
    employee_count = session.scalar(select(func.count()).select_from(Employee))
    if employee_count != 0:
        raise AuthorizationError(
            "Le compte initial existe déjà. Utilise un manager authentifié."
        )

    manager = Employee(
        full_name=full_name.strip(),
        email=normalize_email(email),
        password_hash=hash_password(password),
        role=_get_role(session, "MANAGEMENT"),
        is_active=True,
    )
    session.add(manager)
    session.flush()
    return manager


def create_employee(
    session: Session,
    actor: Employee,
    *,
    full_name: str,
    email: str,
    password: str,
    role_code: str,
) -> Employee:
    require(
        can_manage_employees(actor),
        "Seule l'équipe de gestion peut créer un collaborateur.",
    )

    normalized_email = normalize_email(email)
    if _email_already_exists(session, normalized_email):
        raise DuplicateEmailError("Cette adresse email est déjà utilisée.")

    employee = Employee(
        full_name=full_name.strip(),
        email=normalized_email,
        password_hash=hash_password(password),
        role=_get_role(session, role_code),
        is_active=True,
    )
    session.add(employee)
    session.flush()
    return employee


def update_employee(
    session: Session,
    actor: Employee,
    employee: Employee,
    *,
    full_name: str | None = None,
    email: str | None = None,
    role_code: str | None = None,
) -> Employee:
    require(
        can_manage_employees(actor),
        "Seule l'équipe de gestion peut modifier un collaborateur.",
    )

    if email is not None:
        normalized_email = normalize_email(email)
        existing_id = session.scalar(
            select(Employee.id).where(
                Employee.email == normalized_email,
                Employee.id != employee.id,
            )
        )
        if existing_id is not None:
            raise DuplicateEmailError("Cette adresse email est déjà utilisée.")
        employee.email = normalized_email

    if full_name is not None:
        employee.full_name = full_name.strip()

    if role_code is not None:
        new_role = _get_role(session, role_code)
        if new_role.id != employee.role_id:
            _protect_last_manager(session, employee)
            employee.role = new_role

    session.flush()
    return employee


def change_password(
    session: Session,
    actor: Employee,
    employee: Employee,
    new_password: str,
) -> None:
    require(
        actor.id == employee.id or can_manage_employees(actor),
        "Un collaborateur ne peut changer que son propre mot de passe.",
    )
    employee.password_hash = hash_password(new_password)
    session.flush()


def deactivate_employee(
    session: Session,
    actor: Employee,
    employee: Employee,
) -> None:
    """Suppression logique recommandée pour préserver les relations historiques."""
    require(
        can_manage_employees(actor),
        "Seule l'équipe de gestion peut désactiver un collaborateur.",
    )
    require(actor.id != employee.id, "Tu ne peux pas désactiver ton propre compte.")
    _protect_last_manager(session, employee)
    employee.is_active = False
    session.flush()


def delete_employee(
    session: Session,
    actor: Employee,
    employee: Employee,
) -> None:
    """Supprime physiquement un compte sans relations; sinon préférer la désactivation."""
    require(
        can_manage_employees(actor),
        "Seule l'équipe de gestion peut supprimer un collaborateur.",
    )
    require(actor.id != employee.id, "Tu ne peux pas supprimer ton propre compte.")
    _protect_last_manager(session, employee)
    session.delete(employee)


def _protect_last_manager(session: Session, employee: Employee) -> None:
    if employee.role.code != "MANAGEMENT" or not employee.is_active:
        return

    other_manager_count = session.scalar(
        select(func.count())
        .select_from(Employee)
        .join(Role, Employee.role_id == Role.id)
        .where(
            Role.code == "MANAGEMENT",
            Employee.is_active.is_(True),
            Employee.id != employee.id,
        )
    )
    if other_manager_count == 0:
        raise AuthorizationError(
            "Impossible de retirer ou désactiver le dernier manager actif."
        )
