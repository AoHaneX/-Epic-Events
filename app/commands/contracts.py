"""Display contracts and optional signature or payment filters."""

from app.database import SessionLocal
from app.services.contracts import list_contracts
from app.services.contracts import create_contract, update_contract
from app.auth_session import get_current_user
from app.commands import (
    CommandInputError, ask_identifier, boolean_value, collect_fields,
    date_value, money_value, nullable,
)


def show_list(*, unsigned: bool = False, unpaid: bool = False) -> None:
    with SessionLocal() as session:
        contracts = list_contracts(session, unsigned=unsigned, unpaid=unpaid)

    if not contracts:
        print("Aucun contrat correspondant.")
        return

    for contract in contracts:
        client = contract.client
        print(f"Contrat #{contract.id}")
        print(f"Client : {client.full_name} (#{client.id})")
        print(f"Entreprise : {client.company_name}")
        print(f"Email du client : {client.email}")
        print(f"Téléphone du client : {client.phone}")
        print(
            f"Commercial : {client.sales_contact.full_name} "
            f"(#{client.sales_contact_id})"
        )
        print(f"Montant total : {contract.total_amount:.2f}")
        print(f"Restant à payer : {contract.remaining_amount:.2f}")
        print(f"Création : {contract.created_at:%d/%m/%Y %H:%M}")
        print(f"Statut : {'Signé' if contract.is_signed else 'Non signé'}")
        print()


def main(action="list", **options) -> None:
    if action == "list":
        show_list(**options)
        return
    if action == "create":
        values = collect_fields(options, [
            ("client_id", "Identifiant du client", int),
            ("total_amount", "Montant total", money_value),
            ("remaining_amount", "Restant à payer", money_value),
            ("is_signed", "Contrat signé (oui/non)", boolean_value),
            ("signed_at", "Signature (AAAA-MM-JJTHH:MM, vide si non signé)", nullable(date_value)),
        ])
        with SessionLocal.begin() as session:
            actor = get_current_user(session)
            contract = create_contract(session, actor, **values)
    else:
        contract_id = options.pop("id", None)
        if contract_id is None:
            contract_id = ask_identifier("Identifiant du contrat")
        if not options:
            raise CommandInputError("Indique au moins un champ à modifier (voir contracts update --help).")
        with SessionLocal.begin() as session:
            actor = get_current_user(session)
            contract = update_contract(session, actor, contract_id, **options)
    print(f"Contrat #{contract.id} {'créé' if action == 'create' else 'modifié'}.")
