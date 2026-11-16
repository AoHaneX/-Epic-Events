"""Création et gestion des comptes collaborateurs."""

import re

from app.monitoring import queue_audit

from sqlalchemy import delete, insert, select, update
from sqlalchemy.orm import Session

from app.auth import normalize_email
from app.models import (
    EMPLOYEE_CLASSES,
    MANAGEMENT_ROLE,
    Employee,
    Manager,
    SalesEmployee,
    SupportEmployee,
)
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
    """Le rôle demandé ne correspond à aucun département."""


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


def _role_code(role_code: str) -> str:
    if not isinstance(role_code, str) or not role_code.strip():
        raise UnknownRoleError("Le rôle est obligatoire.")
    normalized_code = role_code.strip().upper()
    if normalized_code not in EMPLOYEE_CLASSES:
        raise UnknownRoleError(f"Rôle inconnu : {normalized_code}")
    return normalized_code


def create_initial_manager(
    session: Session,
    *,
    full_name: str,
    email: str,
    password: str,
) -> Employee:
    """Crée le tout premier compte, uniquement si la table employees est vide."""
    if session.scalar(select(Employee.id).limit(1).with_for_update()) is not None:
        raise AuthorizationError(
            "Le compte initial existe déjà. Utilise un manager authentifié."
        )

    manager = Manager(
        full_name=_validate_name(full_name),
        email=_validate_email(session, email),
        password_hash=hash_password(password),
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

    employee_class = EMPLOYEE_CLASSES[_role_code(role_code)]
    full_name = _validate_name(full_name)
    email = _validate_email(session, email)
    employee = employee_class(
        full_name=full_name,
        email=email,
        password_hash=hash_password(password),
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
    new_role = employee.role if role_code is _UNSET else _role_code(role_code)
    role_changes = new_role != employee.role
    if role_changes:
        _protect_last_manager(session, employee)
        _check_role_change_allowed(employee)

    actor_id = actor.id
    employee.full_name = new_name
    employee.email = new_email
    session.flush()
    if role_changes:
        employee = _move_to_role(session, employee, new_role)

    queue_audit(session, "employee.updated", actor_id, employee.id)
    return employee


def _check_role_change_allowed(employee: Employee) -> None:
    """Un rôle ne change que si l'ancien rôle n'a plus de responsabilités."""
    if isinstance(employee, SalesEmployee) and employee.clients:
        raise EmployeeValidationError(
            "Ce commercial suit encore des clients : impossible de changer son rôle."
        )
    if isinstance(employee, SupportEmployee) and employee.events:
        raise EmployeeValidationError(
            "Ce support est encore affecté à des événements : retire-le d'abord."
        )


def _move_to_role(session: Session, employee: Employee, new_role: str) -> Employee:
    """Déplace le collaborateur de la table de son ancien rôle vers la nouvelle.

    Avec l'héritage, la classe d'un objet ne peut pas changer : on supprime la
    ligne de l'ancienne spécialité, on insère celle de la nouvelle, puis on
    recharge le collaborateur sous sa nouvelle classe. Tout reste dans la même
    transaction : une erreur annule l'ensemble.
    """
    employee_id = employee.id
    old_table = type(employee).__table__
    new_class = EMPLOYEE_CLASSES[new_role]
    employees_table = Employee.__table__
    session.execute(delete(old_table).where(old_table.c.id == employee_id))
    session.execute(insert(new_class.__table__).values(id=employee_id))
    session.execute(
        update(employees_table)
        .where(employees_table.c.id == employee_id)
        .values(role=new_role)
    )
    session.expunge(employee)
    return session.get(new_class, employee_id)


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
    if (
        (isinstance(employee, SalesEmployee) and employee.clients)
        or (isinstance(employee, SupportEmployee) and employee.events)
    ):
        raise EmployeeValidationError(
            "Ce compte possède des clients ou événements. Désactive-le plutôt."
        )
    session.delete(employee)
    session.flush()
    queue_audit(session, "employee.deleted", actor.id, employee.id)


def _protect_last_manager(session: Session, employee: Employee) -> None:
    if employee.role != MANAGEMENT_ROLE or not employee.is_active:
        return

    # Verrouille tous les managers actifs : deux retraits simultanés
    # ne peuvent pas laisser l'entreprise sans manager.
    active_manager_ids = session.scalars(
        select(Employee.id)
        .where(Employee.role == MANAGEMENT_ROLE, Employee.is_active.is_(True))
        .with_for_update()
    ).all()
    if not any(manager_id != employee.id for manager_id in active_manager_ids):
        raise AuthorizationError(
            "Impossible de retirer ou désactiver le dernier manager actif."
        )
