"""Client reading, creation and updates."""

import re
from datetime import datetime

from sqlalchemy import select
from sqlalchemy.orm import Session, joinedload

from app.auth import normalize_email
from app.auth_session import get_current_user
from app.models import Client, Employee
from app.permissions import (
    can_create_client,
    can_read_business_data,
    can_update_client,
    require,
)
from app.services import BusinessError, validate_identifier


_UNSET = object()
_EMAIL_PATTERN = r"[^\s@]+@[^\s@.]+(?:\.[^\s@.]+)+"
_PHONE_PATTERN = r"\+?[0-9][0-9 .()-]*"


class ClientValidationError(BusinessError):
    pass


class ClientNotFoundError(BusinessError):
    pass


class DuplicateClientEmailError(ClientValidationError):
    pass


def list_clients(session: Session) -> list[Client]:
    actor = get_current_user(session)
    require(
        can_read_business_data(actor),
        "Vous ne possédez pas les droits pour consulter les clients.",
    )
    statement = (
        select(Client)
        .options(joinedload(Client.sales_contact))
        .order_by(Client.id)
    )
    return list(session.scalars(statement).all())


def _text(value, label: str, maximum: int) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ClientValidationError(f"{label} est obligatoire.")
    value = value.strip()
    if len(value) > maximum:
        raise ClientValidationError(f"{label} : {maximum} caractères maximum.")
    return value


def _email(session: Session, value, client_id=None) -> str:
    if not isinstance(value, str):
        raise ClientValidationError("L'email du client est obligatoire.")
    email = normalize_email(value)
    if len(email) > 254 or not re.fullmatch(_EMAIL_PATTERN, email):
        raise ClientValidationError("L'email du client est vide ou invalide.")
    statement = select(Client.id).where(Client.email == email)
    if client_id is not None:
        statement = statement.where(Client.id != client_id)
    if session.scalar(statement) is not None:
        raise DuplicateClientEmailError("Un client utilise déjà cette adresse email.")
    return email


def _phone(value) -> str:
    phone = _text(value, "Le téléphone", 32)
    digits = sum(character.isdigit() for character in phone)
    if not re.fullmatch(_PHONE_PATTERN, phone) or digits < 6:
        raise ClientValidationError(
            "Le téléphone ne doit contenir que des chiffres, espaces, + . ( ) - "
            "et au moins 6 chiffres."
        )
    return phone


def _last_contact(value) -> datetime | None:
    if value is None:
        return None
    if not isinstance(value, datetime) or value.tzinfo is not None:
        raise ClientValidationError("La date de dernier contact doit être sans fuseau horaire.")
    return value


def create_client(
    session: Session,
    actor: Employee,
    *,
    full_name: str,
    email: str,
    phone: str,
    company_name: str,
    last_contact_at: datetime | None = None,
) -> Client:
    """Un commercial crée un client, qui lui est automatiquement associé."""
    require(can_create_client(actor), "Seule l'équipe commerciale peut créer un client.")
    client = Client(
        full_name=_text(full_name, "Le nom du client", 150),
        email=_email(session, email),
        phone=_phone(phone),
        company_name=_text(company_name, "Le nom de l'entreprise", 200),
        last_contact_at=_last_contact(last_contact_at),
        sales_contact=actor,
    )
    session.add(client)
    session.flush()
    return client


def update_client(
    session: Session,
    actor: Employee,
    client_id: int,
    *,
    full_name=_UNSET,
    email=_UNSET,
    phone=_UNSET,
    company_name=_UNSET,
    last_contact_at=_UNSET,
) -> Client:
    """Le commercial responsable met à jour son client ; le rattachement ne change pas."""
    validate_identifier(client_id, ClientValidationError)
    client = session.scalar(select(Client).where(Client.id == client_id).with_for_update())
    if client is None:
        raise ClientNotFoundError(f"Client #{client_id} introuvable.")
    require(can_update_client(actor, client), "Tu ne peux modifier que tes propres clients.")

    values = {}
    if full_name is not _UNSET:
        values["full_name"] = _text(full_name, "Le nom du client", 150)
    if email is not _UNSET:
        values["email"] = _email(session, email, client.id)
    if phone is not _UNSET:
        values["phone"] = _phone(phone)
    if company_name is not _UNSET:
        values["company_name"] = _text(company_name, "Le nom de l'entreprise", 200)
    if last_contact_at is not _UNSET:
        values["last_contact_at"] = _last_contact(last_contact_at)

    for field, value in values.items():
        setattr(client, field, value)
    session.flush()
    return client
