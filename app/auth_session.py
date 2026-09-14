"""JWT session management for Epic Events."""

from __future__ import annotations

import json
import os
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import TYPE_CHECKING

import jwt
from dotenv import load_dotenv
from jwt import ExpiredSignatureError, InvalidTokenError

if TYPE_CHECKING:
    from sqlalchemy.orm import Session

    from app.models import Employee


load_dotenv()

ALGORITHM = "HS256"
ACCESS_TOKEN_TYPE = "access"
REFRESH_TOKEN_TYPE = "refresh"
DEFAULT_ACCESS_TOKEN_MINUTES = 15
DEFAULT_REFRESH_TOKEN_DAYS = 7
SESSION_FILE = Path(
    os.getenv(
        "EPIC_EVENTS_SESSION_FILE",
        Path.home() / ".epic_events" / "session.json",
    )
)


class AuthSessionError(RuntimeError):
    pass


def _jwt_secret() -> str:
    secret = os.getenv("JWT_SECRET")
    if not secret:
        raise AuthSessionError("La variable JWT_SECRET est absente.")
    if len(secret) < 32:
        raise AuthSessionError("JWT_SECRET doit contenir au moins 32 caractères.")
    return secret


def _positive_int_setting(name: str, default: int) -> int:
    try:
        value = int(os.getenv(name, str(default)))
    except ValueError as error:
        raise AuthSessionError(f"La variable {name} doit être un entier.") from error

    if value <= 0:
        raise AuthSessionError(f"La variable {name} doit être positive.")
    return value


def _create_token(employee_id: int, token_type: str, lifetime: timedelta) -> str:
    issued_at = datetime.now(timezone.utc)
    payload = {
        "sub": str(employee_id),
        "type": token_type,
        "iat": issued_at,
        "exp": issued_at + lifetime,
    }
    return jwt.encode(payload, _jwt_secret(), algorithm=ALGORITHM)


def _create_access_token(employee_id: int) -> str:
    minutes = _positive_int_setting(
        "ACCESS_TOKEN_MINUTES",
        DEFAULT_ACCESS_TOKEN_MINUTES,
    )
    return _create_token(
        employee_id,
        ACCESS_TOKEN_TYPE,
        timedelta(minutes=minutes),
    )


def _create_refresh_token(employee_id: int) -> str:
    days = _positive_int_setting(
        "REFRESH_TOKEN_DAYS",
        DEFAULT_REFRESH_TOKEN_DAYS,
    )
    return _create_token(
        employee_id,
        REFRESH_TOKEN_TYPE,
        timedelta(days=days),
    )


def _decode_token(token: str, expected_type: str) -> int:
    try:
        payload = jwt.decode(
            token,
            _jwt_secret(),
            algorithms=[ALGORITHM],
            options={"require": ["sub", "type", "iat", "exp"]},
        )
    except ExpiredSignatureError:
        raise
    except InvalidTokenError as error:
        raise AuthSessionError("Jeton invalide.") from error

    if payload.get("type") != expected_type:
        raise AuthSessionError("Type de jeton invalide.")

    try:
        return int(payload["sub"])
    except (TypeError, ValueError) as error:
        raise AuthSessionError("Utilisateur du jeton invalide.") from error


def _save_tokens(access_token: str, refresh_token: str) -> None:
    try:
        SESSION_FILE.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
        SESSION_FILE.write_text(
            json.dumps(
                {
                    "access_token": access_token,
                    "refresh_token": refresh_token,
                },
                indent=2,
            ),
            encoding="utf-8",
        )
        SESSION_FILE.chmod(0o600)
    except OSError as error:
        raise AuthSessionError("Impossible d'enregistrer la session.") from error


def _load_tokens() -> tuple[str, str]:
    try:
        data = json.loads(SESSION_FILE.read_text(encoding="utf-8"))
        access_token = data["access_token"]
        refresh_token = data["refresh_token"]
    except FileNotFoundError as error:
        raise AuthSessionError("Aucune session. Lance la commande login.") from error
    except (OSError, json.JSONDecodeError, KeyError, TypeError) as error:
        raise AuthSessionError("Le fichier de session est invalide.") from error

    if (
        not isinstance(access_token, str)
        or not access_token
        or not isinstance(refresh_token, str)
        or not refresh_token
    ):
        raise AuthSessionError("Le fichier de session est invalide.")
    return access_token, refresh_token


def start_session(employee_id: int) -> None:
    _save_tokens(
        _create_access_token(employee_id),
        _create_refresh_token(employee_id),
    )


def clear_session() -> None:
    try:
        SESSION_FILE.unlink(missing_ok=True)
    except OSError as error:
        raise AuthSessionError("Impossible de supprimer la session.") from error


def _employee_id_from_session() -> int:
    access_token, refresh_token = _load_tokens()

    try:
        return _decode_token(access_token, ACCESS_TOKEN_TYPE)
    except ExpiredSignatureError:
        try:
            employee_id = _decode_token(refresh_token, REFRESH_TOKEN_TYPE)
        except (ExpiredSignatureError, AuthSessionError) as error:
            clear_session()
            raise AuthSessionError(
                "La session a expiré. Reconnecte-toi."
            ) from error

        _save_tokens(_create_access_token(employee_id), refresh_token)
        return employee_id
    except AuthSessionError:
        clear_session()
        raise


def get_current_user(session: Session) -> Employee:
    from sqlalchemy import select

    from app.models import Employee

    employee_id = _employee_id_from_session()
    employee = session.scalar(select(Employee).where(Employee.id == employee_id))

    if employee is None or not employee.is_active:
        clear_session()
        raise AuthSessionError("Compte introuvable ou désactivé.")

    return employee
