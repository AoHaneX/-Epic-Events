"""Shared command-line input conversion."""

import argparse
from datetime import datetime
from decimal import Decimal, InvalidOperation


class CommandInputError(ValueError):
    pass


def date_value(value: str) -> datetime:
    try:
        return datetime.fromisoformat(value)
    except ValueError as error:
        raise argparse.ArgumentTypeError("Date attendue : AAAA-MM-JJTHH:MM.") from error


def money_value(value: str) -> Decimal:
    try:
        return Decimal(value)
    except InvalidOperation as error:
        raise argparse.ArgumentTypeError("Montant décimal attendu, par exemple 1200.50.") from error


def boolean_value(value: str) -> bool:
    if value.strip().lower() in ("oui", "yes", "true", "1"):
        return True
    if value.strip().lower() in ("non", "no", "false", "0"):
        return False
    raise argparse.ArgumentTypeError("Réponds oui ou non.")


def nullable(converter):
    def convert(value):
        return None if value.strip().lower() in ("", "none") else converter(value)
    return convert


def collect_fields(options: dict, fields: list) -> dict:
    values = options.copy()
    for field, label, converter in fields:
        if field not in values:
            try:
                values[field] = converter(input(f"{label} : ").strip())
            except (ValueError, argparse.ArgumentTypeError) as error:
                raise CommandInputError(f"{label} : {error}") from error
    return values


def ask_identifier(label: str) -> int:
    return collect_fields({}, [("id", label, int)])["id"]
