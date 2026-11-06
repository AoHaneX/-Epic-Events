"""Client commands: list, create and update."""

from app.auth_session import get_current_user
from app.commands import (
    CommandInputError, ask_identifier, collect_fields, date_value, nullable,
)
from app.database import SessionLocal
from app.services.clients import create_client, list_clients, update_client


def show_list() -> None:
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


def main(action="list", **options) -> None:
    if action == "list":
        show_list()
        return
    if action == "create":
        values = collect_fields(options, [
            ("full_name", "Nom complet", str),
            ("email", "Email", str),
            ("phone", "Téléphone", str),
            ("company_name", "Entreprise", str),
            ("last_contact_at", "Dernier contact (AAAA-MM-JJTHH:MM, vide si aucun)", nullable(date_value)),
        ])
        with SessionLocal.begin() as session:
            actor = get_current_user(session)
            client = create_client(session, actor, **values)
    else:
        client_id = options.pop("id", None)
        if client_id is None:
            client_id = ask_identifier("Identifiant du client")
        if not options:
            raise CommandInputError("Indique au moins un champ à modifier (voir clients update --help).")
        with SessionLocal.begin() as session:
            actor = get_current_user(session)
            client = update_client(session, actor, client_id, **options)
    print(f"Client #{client.id} {'créé' if action == 'create' else 'modifié'}.")
