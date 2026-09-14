"""Authentification des collaborateurs Epic Events."""

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import Employee
from app.security import hash_password, verify_password


class AuthenticationError(Exception):
    """Identifiants invalides ou compte désactivé."""

_DUMMY_HASH = hash_password("Compte-inexistant-uniquement-pour-verification")


def normalize_email(email: str) -> str:
    return email.strip().lower()


def authenticate(session: Session, email: str, password: str) -> Employee:
    """Authentifie un compte actif avec un message d'échec volontairement générique."""
    normalized_email = normalize_email(email)
    employee = session.scalar(
        select(Employee).where(Employee.email == normalized_email)
    )

    password_hash = employee.password_hash if employee else _DUMMY_HASH
    is_valid, new_hash = verify_password(password_hash, password)

    if employee is None or not employee.is_active or not is_valid:
        raise AuthenticationError("Email ou mot de passe incorrect.")

    if new_hash is not None:
        employee.password_hash = new_hash

    return employee

