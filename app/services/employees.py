"""Création et gestion des comptes collaborateurs."""

import re

from app.monitoring import queue_audit

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.auth import normalize_email
from app.models import Employee, Role
from app.permissions import AuthorizationError, can_manage_employees, require
from app.security import hash_password
from app.services import BusinessError, validate_identifier


_UNSET = object()


class EmployeeValidationError(BusinessError):
    pass


class EmployeeNotFoundError(BusinessError):
    pass


class DuplicateEmailError(BusinessError):
    """Un collaborateur utilise déjà cette adresse email."""


class UnknownRoleError(BusinessError):
    """Le rôle demandé n'existe pas dans la table roles."""


def _validate_name(full_name: str) -> str:
    if not isinstance(full_name, str) or not full_name.strip():
        raise EmployeeValidationError("Le nom du collaborateur est obligatoire.")
    if len(full_name.strip()) > 150:
        raise EmployeeValidationError("Le nom ne doit pas dépasser 150 caractères.")
    return full_name.strip()


def _validate_email(session: Session, email: str, employee_id=None) -> str:
    if not isinstance(email, str):
        raise EmployeeValidationError("L'email est obligatoire.")
    email = normalize_email(email)
    if len(email) > 254 or not re.fullmatch(r"[^\s@]+@[^\s@.]+(?:\.[^\s@.]+)+", email):
        raise EmployeeValidationError("L'email est vide ou invalide.")
    statement = select(Employee.id).where(Employee.email == email)
    if employee_id is not None:
        statement = statement.where(Employee.id != employee_id)
    if session.scalar(statement) is not None:
        raise DuplicateEmailError("Cette adresse email est déjà utilisée.")
    return email


def list_employees(session: Session, actor: Employee) -> list[Employee]:
    require(can_manage_employees(actor), "Seul Management peut lister les collaborateurs.")
    return list(session.scalars(select(Employee).order_by(Employee.id)).all())


def get_employee(session: Session, employee_id: int) -> Employee:
    validate_identifier(employee_id, EmployeeValidationError)
    employee = session.get(Employee, employee_id)
    if employee is None:
        raise EmployeeNotFoundError(f"Collaborateur #{employee_id} introuvable.")
    return employee


def _get_role(session: Session, role_code: str) -> Role:
    if not isinstance(role_code, str) or not role_code.strip():
        raise UnknownRoleError("Le rôle est obligatoire.")
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
    role = _get_role(session, "MANAGEMENT")
    session.scalar(select(Role.id).where(Role.id == role.id).with_for_update())
    if session.scalar(select(Employee.id).limit(1).with_for_update()) is not None:
        raise AuthorizationError(
            "Le compte initial existe déjà. Utilise un manager authentifié."
        )

    manager = Employee(
        full_name=_validate_name(full_name),
        email=_validate_email(session, email),
        password_hash=hash_password(password),
        role=role,
        is_active=True,
    )
    session.add(manager)
    session.flush()
    queue_audit(session, "employee.created", manager.id, manager.id)
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

    employee = Employee(
        full_name=_validate_name(full_name),
        email=_validate_email(session, email),
        password_hash=hash_password(password),
        role=_get_role(session, role_code),
        is_active=True,
    )
    session.add(employee)
    session.flush()
    queue_audit(session, "employee.created", actor.id, employee.id)
    return employee


def update_employee(
    session: Session,
    actor: Employee,
    employee: Employee,
    *,
    full_name=_UNSET,
    email=_UNSET,
    role_code=_UNSET,
) -> Employee:
    require(
        can_manage_employees(actor),
        "Seule l'équipe de gestion peut modifier un collaborateur.",
    )

    new_name = employee.full_name if full_name is _UNSET else _validate_name(full_name)
    new_email = (
        employee.email if email is _UNSET
        else _validate_email(session, email, employee.id)
    )
    new_role = employee.role if role_code is _UNSET else _get_role(session, role_code)
    if new_role.id != employee.role_id:
        _protect_last_manager(session, employee)

    employee.full_name = new_name
    employee.email = new_email
    employee.role = new_role

    session.flush()
    queue_audit(session, "employee.updated", actor.id, employee.id)
    return employee


def change_password(
    session: Session,
    actor: Employee,
    employee: Employee,
    new_password: str,
) -> None:
    require(
        actor.is_active,
        "Un compte désactivé ne peut pas changer de mot de passe.",
    )
    require(
        actor.id == employee.id or can_manage_employees(actor),
        "Un collaborateur ne peut changer que son propre mot de passe.",
    )
    employee.password_hash = hash_password(new_password)
    session.flush()
    queue_audit(session, "employee.password_changed", actor.id, employee.id)


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
    queue_audit(session, "employee.deactivated", actor.id, employee.id)


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
    if employee.sales_clients or employee.supported_events:
        raise EmployeeValidationError(
            "Ce compte possède des clients ou événements. Désactive-le plutôt."
        )
    session.delete(employee)
    session.flush()
    queue_audit(session, "employee.deleted", actor.id, employee.id)


def _protect_last_manager(session: Session, employee: Employee) -> None:
    if employee.role.code != "MANAGEMENT" or not employee.is_active:
        return

    session.scalar(select(Role.id).where(Role.id == employee.role_id).with_for_update())
    other_manager_id = session.scalar(
        select(Employee.id)
        .where(
            Employee.role_id == employee.role_id,
            Employee.is_active.is_(True),
            Employee.id != employee.id,
        )
        .with_for_update()
    )
    if other_manager_id is None:
        raise AuthorizationError(
            "Impossible de retirer ou désactiver le dernier manager actif."
        )
