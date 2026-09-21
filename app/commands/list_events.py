"""Display events and optional support assignment filters."""

from app.database import SessionLocal
from app.services.events import list_events


def main(*, without_support: bool = False, mine: bool = False) -> None:
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


if __name__ == "__main__":
    main()
