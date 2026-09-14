"""Hachage et vérification des mots de passe avec Argon2id."""

from argon2 import PasswordHasher
from argon2.exceptions import InvalidHashError, VerificationError


password_hasher = PasswordHasher()


class PasswordPolicyError(ValueError):
    """Le mot de passe ne respecte pas la politique de l'application."""


def validate_password(password: str) -> None:
    if len(password) < 12:
        raise PasswordPolicyError(
            "Le mot de passe doit contenir au moins 12 caractères."
        )
    if len(password) > 256:
        raise PasswordPolicyError(
            "Le mot de passe ne doit pas dépasser 256 caractères."
        )


def hash_password(password: str) -> str:
    """Valide puis hache un mot de passe. Le texte clair n'est jamais stocké."""
    validate_password(password)
    return password_hasher.hash(password)


def verify_password(password_hash: str, password: str) -> tuple[bool, str | None]:
    """Vérifie le mot de passe et retourne éventuellement un hash modernisé."""
    try:
        password_hasher.verify(password_hash, password)
    except (VerificationError, InvalidHashError):
        return False, None

    new_hash = None
    if password_hasher.check_needs_rehash(password_hash):
        new_hash = password_hasher.hash(password)

    return True, new_hash

