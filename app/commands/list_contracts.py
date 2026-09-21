"""Display contracts and optional signature or payment filters."""

from app.database import SessionLocal
from app.services.contracts import list_contracts


def main(*, unsigned: bool = False, unpaid: bool = False) -> None:
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


if __name__ == "__main__":
    main()
