"""Display events and optional support assignment filters."""

from app.database import SessionLocal
from app.services.events import list_events
from app.services.events import create_event, update_event
from app.auth_session import get_current_user
from app.commands import CommandInputError, ask_identifier, collect_fields, date_value, nullable


def show_list(*, without_support: bool = False, mine: bool = False) -> None:
    with SessionLocal() as session:
        events = list_events(session, without_support=without_support, mine=mine)

    if not events:
        print("Aucun événement correspondant.")
        return

    for event in events:
        client = event.contract.client
        print(f"Événement #{event.id} : {event.name}")
        print(f"Contrat : #{event.contract_id}")
        print(f"Client : {client.full_name} (#{client.id})")
        print(f"Contact de l'événement : {event.contact_name or 'Non renseigné'}")
        print(f"Email du contact : {event.contact_email or 'Non renseigné'}")
        print(f"Téléphone du contact : {event.contact_phone or 'Non renseigné'}")
        print(f"Début : {event.start_at:%d/%m/%Y %H:%M}")
        print(f"Fin : {event.end_at:%d/%m/%Y %H:%M}")
        support = (
            f"{event.support_contact.full_name} (#{event.support_contact_id})"
            if event.support_contact else "Non attribué"
        )
        print(f"Support : {support}")
        print(f"Lieu : {event.location}")
        print(f"Participants : {event.attendees_count}")
        print(f"Notes : {event.notes or 'Aucune'}")
        print()


def main(action="list", **options) -> None:
    if action == "list":
        show_list(**options)
        return
    if action == "create":
        values = collect_fields(options, [
            ("contract_id", "Identifiant du contrat", int),
            ("name", "Nom de l'événement", str),
            ("contact_name", "Nom du contact (facultatif)", nullable(str)),
            ("contact_email", "Email du contact (facultatif si téléphone)", nullable(str)),
            ("contact_phone", "Téléphone du contact (facultatif si email)", nullable(str)),
            ("start_at", "Début (AAAA-MM-JJTHH:MM)", date_value),
            ("end_at", "Fin (AAAA-MM-JJTHH:MM)", date_value),
            ("location", "Lieu", str),
            ("attendees_count", "Nombre de participants", int),
            ("notes", "Notes (facultatif)", nullable(str)),
        ])
        with SessionLocal.begin() as session:
            actor = get_current_user(session)
            event = create_event(session, actor, **values)
    else:
        event_id = options.pop("id", None)
        if event_id is None:
            event_id = ask_identifier("Identifiant de l'événement")
        if not options:
            raise CommandInputError("Indique au moins un champ à modifier (voir events update --help).")
        with SessionLocal.begin() as session:
            actor = get_current_user(session)
            event = update_event(session, actor, event_id, **options)
    print(f"Événement #{event.id} {'créé' if action == 'create' else 'modifié'}.")
