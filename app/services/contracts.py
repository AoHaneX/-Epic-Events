"""Contract reading, creation and updates."""

from datetime import datetime
from decimal import Decimal, InvalidOperation

from app.monitoring import queue_audit

from sqlalchemy import select
from sqlalchemy.orm import Session, joinedload

from app.auth_session import get_current_user
from app.models import Client, Contract, Employee
from app.services import BusinessError, validate_identifier
from app.permissions import (
    can_create_contract,
    can_read_business_data,
    can_reassign_contract_client,
    can_update_contract,
    require,
)


_UNSET = object()


class ContractValidationError(BusinessError):
    pass


class ContractNotFoundError(BusinessError):
    pass


class ClientNotFoundError(BusinessError):
    pass


def list_contracts(
    session: Session,
    *,
    unsigned: bool = False,
    unpaid: bool = False,
) -> list[Contract]:
    actor = get_current_user(session)
    require(
        can_read_business_data(actor),
        "Tu n'es pas autorisé à consulter les contrats.",
    )
    statement = (
        select(Contract)
        .options(joinedload(Contract.client).joinedload(Client.sales_contact))
        .order_by(Contract.id)
    )
    if unsigned:
        statement = statement.where(Contract.is_signed.is_(False))
    if unpaid:
        statement = statement.where(Contract.remaining_amount > 0)
    return list(session.scalars(statement).all())


def _get_client(session: Session, client_id: int) -> Client:
    if type(client_id) is not int or client_id <= 0:
        raise ContractValidationError("L'identifiant du client doit être un entier positif.")
    client = session.get(Client, client_id)
    if client is None:
        raise ClientNotFoundError(f"Client #{client_id} introuvable.")
    return client


def _amount(value, label: str) -> Decimal:
    try:
        amount = Decimal(str(value))
    except (InvalidOperation, ValueError) as error:
        raise ContractValidationError(f"{label} : montant invalide.") from error
    if not amount.is_finite() or not Decimal(0) <= amount <= Decimal("9999999999.99"):
        raise ContractValidationError(f"{label} : montant hors limites (0 à 9999999999.99).")
    if amount != amount.quantize(Decimal("0.01")):
        raise ContractValidationError(f"{label} : deux décimales maximum.")
    return amount.quantize(Decimal("0.01"))


def _validate_values(total_amount, remaining_amount, is_signed, signed_at):
    total = _amount(total_amount, "Montant total")
    remaining = _amount(remaining_amount, "Restant à payer")
    if remaining > total:
        raise ContractValidationError("Le restant à payer dépasse le montant total.")
    if type(is_signed) is not bool:
        raise ContractValidationError("Le statut de signature doit être un booléen.")
    if is_signed:
        if not isinstance(signed_at, datetime) or signed_at.tzinfo is not None:
            raise ContractValidationError("Un contrat signé exige une date sans fuseau horaire.")
    elif signed_at is not None:
        raise ContractValidationError("Un contrat non signé ne doit pas avoir de date de signature.")
    return total, remaining


def create_contract(
    session: Session,
    actor: Employee,
    *,
    client_id: int,
    total_amount,
    remaining_amount,
    is_signed: bool = False,
    signed_at: datetime | None = None,
) -> Contract:
    require(can_create_contract(actor), "Seul Management peut créer un contrat.")
    client = _get_client(session, client_id)
    total, remaining = _validate_values(
        total_amount, remaining_amount, is_signed, signed_at
    )
    contract = Contract(
        client=client,
        total_amount=total,
        remaining_amount=remaining,
        is_signed=is_signed,
        signed_at=signed_at,
    )
    session.add(contract)
    session.flush()
    if is_signed:
        queue_audit(session, "contract.signed", actor.id, contract.id)
    return contract


def update_contract(
    session: Session,
    actor: Employee,
    contract_id: int,
    *,
    client_id=_UNSET,
    total_amount=_UNSET,
    remaining_amount=_UNSET,
    is_signed=_UNSET,
    signed_at=_UNSET,
) -> Contract:
    validate_identifier(contract_id, ContractValidationError)
    contract = session.scalar(
        select(Contract).options(joinedload(Contract.client))
        .where(Contract.id == contract_id).with_for_update()
    )
    if contract is None:
        raise ContractNotFoundError(f"Contrat #{contract_id} introuvable.")
    require(can_update_contract(actor, contract), "Tu ne peux pas modifier ce contrat.")
    client = contract.client if client_id is _UNSET else _get_client(session, client_id)
    if client.id != contract.client_id:
        require(
            can_reassign_contract_client(actor, client),
            "Tu ne peux pas déplacer un contrat vers le client d'un autre commercial.",
        )
    total = contract.total_amount if total_amount is _UNSET else total_amount
    remaining = contract.remaining_amount if remaining_amount is _UNSET else remaining_amount
    signed = contract.is_signed if is_signed is _UNSET else is_signed
    date = contract.signed_at if signed_at is _UNSET else signed_at
    total, remaining = _validate_values(total, remaining, signed, date)

    newly_signed = signed and not contract.is_signed
    contract.client = client
    contract.total_amount = total
    contract.remaining_amount = remaining
    contract.is_signed = signed
    contract.signed_at = date
    session.flush()
    if newly_signed:
        queue_audit(session, "contract.signed", actor.id, contract.id)
    return contract
