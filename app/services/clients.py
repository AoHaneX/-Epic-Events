"""Authenticated access to client records."""

from sqlalchemy import select
from sqlalchemy.orm import Session, joinedload

from app.auth_session import get_current_user
from app.models import Client
from app.permissions import can_read_business_data, require


def list_clients(session: Session) -> list[Client]:
    actor = get_current_user(session)
    require(
        can_read_business_data(actor),
        "Tu n'es pas autorisé à consulter les clients.",
    )
    statement = (
        select(Client)
        .options(joinedload(Client.sales_contact))
        .order_by(Client.id)
    )
    return list(session.scalars(statement).all())
