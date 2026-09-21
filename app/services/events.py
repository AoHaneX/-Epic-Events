"""Authenticated access to event records."""

from sqlalchemy import select
from sqlalchemy.orm import Session, joinedload

from app.auth_session import get_current_user
from app.models import Contract, Event
from app.permissions import SUPPORT_ROLE, can_read_business_data, has_role, require


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
        raise ValueError(
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
