"""Règles d'autorisation centralisées du CRM Epic Events."""

from app.models import Client, Contract, Employee, Event


MANAGEMENT_ROLE = "MANAGEMENT"
SALES_ROLE = "SALES"
SUPPORT_ROLE = "SUPPORT"


class AuthorizationError(PermissionError):
    """Le collaborateur authentifié ne peut pas effectuer cette action."""


def require(condition: bool, message: str = "Action non autorisée.") -> None:
    if not condition:
        raise AuthorizationError(message)


def is_active(employee: Employee) -> bool:
    return employee.is_active


def has_role(employee: Employee, role_code: str) -> bool:
    """Vérifie qu'un collaborateur actif possède le rôle demandé."""
    return (
        is_active(employee)
        and employee.role is not None
        and employee.role.code == role_code
    )


def can_read_business_data(employee: Employee) -> bool:
    """Tous les collaborateurs actifs lisent clients, contrats et événements."""
    return is_active(employee)


def can_manage_employees(employee: Employee) -> bool:
    return has_role(employee, MANAGEMENT_ROLE)


def can_create_client(employee: Employee) -> bool:
    return has_role(employee, SALES_ROLE)


def can_update_client(employee: Employee, client: Client) -> bool:
    return (
        has_role(employee, SALES_ROLE)
        and client.sales_contact_id == employee.id
    )


def can_create_contract(employee: Employee) -> bool:
    return has_role(employee, MANAGEMENT_ROLE)


def can_update_contract(employee: Employee, contract: Contract) -> bool:
    if not is_active(employee):
        return False
    if has_role(employee, MANAGEMENT_ROLE):
        return True
    return (
        has_role(employee, SALES_ROLE)
        and contract.client.sales_contact_id == employee.id
    )


def can_create_event(employee: Employee, contract: Contract) -> bool:
    """Le commercial du client crée l'événement après signature du contrat."""
    return (
        has_role(employee, SALES_ROLE)
        and contract.client.sales_contact_id == employee.id
        and contract.is_signed
        and contract.event is None
    )


def can_assign_support(employee: Employee) -> bool:
    return has_role(employee, MANAGEMENT_ROLE)


def can_update_event(employee: Employee, event: Event) -> bool:
    """Un membre du support modifie uniquement les événements qui lui sont confiés."""
    return (
        has_role(employee, SUPPORT_ROLE)
        and event.support_contact_id == employee.id
    )
