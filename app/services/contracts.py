"""Authenticated access to contract records."""

from sqlalchemy import select
from sqlalchemy.orm import Session, joinedload

from app.auth_session import get_current_user
from app.models import Client, Contract
from app.permissions import can_read_business_data, require


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
