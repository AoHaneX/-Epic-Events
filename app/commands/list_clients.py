"""Display all clients available to the authenticated employee."""

from app.database import SessionLocal
from app.services.clients import list_clients


def main() -> None:
    with SessionLocal() as session:
        clients = list_clients(session)

    if not clients:
        print("Aucun client enregistré.")
        return

    for client in clients:
        print(f"Client #{client.id} : {client.full_name}")
        print(f"Entreprise : {client.company_name}")
        print(f"Email : {client.email}")
        print(f"Téléphone : {client.phone}")
        print(f"Création : {client.created_at:%d/%m/%Y %H:%M}")
        print(f"Dernière mise à jour : {client.updated_at:%d/%m/%Y %H:%M}")
        last_contact = (
            client.last_contact_at.strftime("%d/%m/%Y %H:%M")
            if client.last_contact_at else "Non renseigné"
        )
        print(f"Dernier contact : {last_contact}")
        print(
            f"Commercial : {client.sales_contact.full_name} "
            f"(#{client.sales_contact_id})"
        )
        print()


if __name__ == "__main__":
    main()
