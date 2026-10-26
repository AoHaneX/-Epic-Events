"""Event reading, creation and updates."""

import re
from datetime import datetime

from sqlalchemy import select
from sqlalchemy.orm import Session, joinedload

from app.auth_session import get_current_user
from app.models import Contract, Event, Employee
from app.auth import normalize_email
from app.services import BusinessError, validate_identifier
from app.permissions import (
    SUPPORT_ROLE,
    can_assign_support,
    can_change_event_contract,
    can_create_event,
    can_read_business_data,
    can_update_event,
    has_role,
    require,
)


_UNSET = object()


class EventValidationError(BusinessError):
    pass


class EventNotFoundError(BusinessError):
    pass


class ContractNotFoundError(BusinessError):
    pass


class EmployeeNotFoundError(BusinessError):
    pass


def list_events(
    session: Session,
    *,
    without_support: bool = False,
    mine: bool = False,
) -> list[Event]:
    actor = get_current_user(session)
    require(
        can_read_business_data(actor),
        "Tu n'es pas autorisé à consulter les événements.",
    )
    if without_support and mine:
        raise EventValidationError(
            "Les filtres --without-support et --mine sont incompatibles."
        )
    if mine:
        require(
            has_role(actor, SUPPORT_ROLE),
            "Le filtre --mine est réservé à l'équipe support.",
        )

    statement = (
        select(Event)
        .options(
            joinedload(Event.contract).joinedload(Contract.client),
            joinedload(Event.support_contact),
        )
        .order_by(Event.id)
    )
    if without_support:
        statement = statement.where(Event.support_contact_id.is_(None))
    if mine:
        statement = statement.where(Event.support_contact_id == actor.id)
    return list(session.scalars(statement).all())


def _get_contract(session: Session, contract_id: int) -> Contract:
    if type(contract_id) is not int or contract_id <= 0:
        raise EventValidationError("L'identifiant du contrat doit être un entier positif.")
    contract = session.scalar(
        select(Contract).options(joinedload(Contract.client))
        .where(Contract.id == contract_id).with_for_update()
    )
    if contract is None:
        raise ContractNotFoundError(f"Contrat #{contract_id} introuvable.")
    return contract


def _validate_contract(session: Session, contract: Contract, event_id=None) -> None:
    if not contract.is_signed:
        raise EventValidationError("Le contrat doit être signé.")
    statement = select(Event.id).where(Event.contract_id == contract.id)
    if event_id is not None:
        statement = statement.where(Event.id != event_id)
    if session.scalar(statement.with_for_update()) is not None:
        raise EventValidationError("Un événement est déjà associé à ce contrat.")


def _get_support(session: Session, support_id: int | None) -> Employee | None:
    if support_id is None:
        return None
    if type(support_id) is not int or support_id <= 0:
        raise EventValidationError("L'identifiant du support doit être un entier positif.")
    support = session.get(Employee, support_id)
    if support is None:
        raise EmployeeNotFoundError(f"Collaborateur #{support_id} introuvable.")
    if not has_role(support, SUPPORT_ROLE):
        raise EventValidationError("Le collaborateur doit être actif et appartenir au Support.")
    return support


def _text(value, label: str, maximum: int, *, required=False):
    if value is None and not required:
        return None
    if not isinstance(value, str):
        raise EventValidationError(f"{label} : texte attendu.")
    value = value.strip()
    if not value:
        if required:
            raise EventValidationError(f"{label} est obligatoire.")
        return None
    if len(value) > maximum:
        raise EventValidationError(f"{label} : {maximum} caractères maximum.")
    return value


def _validate_values(values: dict) -> dict:
    values = values.copy()
    for field, label, maximum, required in (
        ("name", "Le nom", 200, True),
        ("location", "Le lieu", 500, True),
        ("contact_name", "Le nom du contact", 150, False),
        ("contact_email", "L'email du contact", 254, False),
        ("contact_phone", "Le téléphone du contact", 32, False),
        ("notes", "Les notes", 65535, False),
    ):
        values[field] = _text(values[field], label, maximum, required=required)
    if values["contact_email"] is not None:
        email = normalize_email(values["contact_email"])
        if not re.fullmatch(r"[^\s@]+@[^\s@.]+(?:\.[^\s@.]+)+", email):
            raise EventValidationError("L'email du contact est invalide.")
        values["contact_email"] = email
    if not values["contact_email"] and not values["contact_phone"]:
        raise EventValidationError("Un email ou un téléphone de contact est obligatoire.")
    for field in ("start_at", "end_at"):
        date = values[field]
        if not isinstance(date, datetime) or date.tzinfo is not None:
            raise EventValidationError("Les dates doivent être renseignées, sans fuseau horaire.")
    if values["end_at"] <= values["start_at"]:
        raise EventValidationError("La fin doit être postérieure au début.")
    count = values["attendees_count"]
    if type(count) is not int or not 0 <= count <= 4294967295:
        raise EventValidationError("Le nombre de participants doit être un entier positif ou nul.")
    if values["notes"] and len(values["notes"].encode("utf-8")) > 65535:
        raise EventValidationError("Les notes dépassent la capacité du champ texte.")
    return values


def create_event(
    session: Session,
    actor: Employee,
    *,
    contract_id: int,
    name: str,
    start_at: datetime,
    end_at: datetime,
    location: str,
    attendees_count: int,
    contact_name: str | None = None,
    contact_email: str | None = None,
    contact_phone: str | None = None,
    notes: str | None = None,
) -> Event:
    contract = _get_contract(session, contract_id)
    require(
        can_create_event(actor, contract),
        "Seul le commercial du client peut créer un événement sur un contrat signé sans événement.",
    )
    _validate_contract(session, contract)
    values = _validate_values(dict(
        name=name, contact_name=contact_name, contact_email=contact_email,
        contact_phone=contact_phone, start_at=start_at, end_at=end_at,
        location=location, attendees_count=attendees_count, notes=notes,
    ))
    event = Event(contract=contract, **values)
    session.add(event)
    session.flush()
    return event


def update_event(
    session: Session,
    actor: Employee,
    event_id: int,
    *,
    contract_id=_UNSET,
    support_contact_id=_UNSET,
    name=_UNSET,
    contact_name=_UNSET,
    contact_email=_UNSET,
    contact_phone=_UNSET,
    start_at=_UNSET,
    end_at=_UNSET,
    location=_UNSET,
    attendees_count=_UNSET,
    notes=_UNSET,
) -> Event:
    validate_identifier(event_id, EventValidationError)
    event = session.scalar(select(Event).where(Event.id == event_id).with_for_update())
    if event is None:
        raise EventNotFoundError(f"Événement #{event_id} introuvable.")
    changes = dict(
        name=name, contact_name=contact_name, contact_email=contact_email,
        contact_phone=contact_phone, start_at=start_at, end_at=end_at,
        location=location, attendees_count=attendees_count, notes=notes,
    )
    general_changes = any(value is not _UNSET for value in changes.values())
    if general_changes or (contract_id is _UNSET and support_contact_id is _UNSET):
        require(can_update_event(actor, event), "Seul le support affecté peut modifier ces informations.")
    if support_contact_id is not _UNSET:
        require(can_assign_support(actor), "Seul Management peut attribuer ou retirer le support.")
    if contract_id is not _UNSET:
        require(can_change_event_contract(actor), "Seul Management peut remplacer le contrat d'un événement.")

    contract = event.contract
    if contract_id is not _UNSET:
        contract = _get_contract(session, contract_id)
        _validate_contract(session, contract, event.id)
    support = event.support_contact
    if support_contact_id is not _UNSET:
        support = _get_support(session, support_contact_id)
    values = _validate_values({
        field: getattr(event, field) if value is _UNSET else value
        for field, value in changes.items()
    })

    if contract_id is not _UNSET:
        event.contract = contract
    if support_contact_id is not _UNSET:
        event.support_contact = support
    for field, value in values.items():
        if changes[field] is not _UNSET:
            setattr(event, field, value)
    session.flush()
    return event
