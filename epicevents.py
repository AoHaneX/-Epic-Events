"""Epic Events command-line entry point."""

import argparse
from app import monitoring
from importlib import import_module

from app.commands import CommandInputError, date_value, identifier_value, money_value, nullable


COMMANDS = {
    "login": "app.commands.login",
    "logout": "app.commands.logout",
    "status": "app.commands.session_info",
    "create-employee": "app.commands.employees",
    "create-manager": "app.commands.employees",
    "list-clients": "app.commands.clients",
    "list-contracts": "app.commands.contracts",
    "list-events": "app.commands.events",
}
LEGACY_ACTIONS = {
    "create-employee": "create", "create-manager": "initial-manager",
    "list-clients": "list", "list-contracts": "list", "list-events": "list",
}
ENTITIES = {
    "employees": ("list", "create", "update", "password", "deactivate", "delete"),
    "clients": ("list",),
    "contracts": ("list", "create", "update"),
    "events": ("list", "create", "update"),
}


def _add_filters(parser, entity):
    if entity == "contracts":
        parser.add_argument("--unsigned", action="store_true", help="Contrats non signés.")
        parser.add_argument("--unpaid", action="store_true", help="Contrats restant à payer.")
    elif entity == "events":
        filters = parser.add_mutually_exclusive_group()
        filters.add_argument("--without-support", action="store_true")
        filters.add_argument("--mine", action="store_true")


def _add_fields(parser, entity, action):
    if action not in ("create", "update"):
        return
    if entity == "employees":
        fields = [("full_name", str), ("email", str), ("role_code", str)]
    elif entity == "contracts":
        fields = [
            ("client_id", identifier_value), ("total_amount", money_value),
            ("remaining_amount", money_value), ("signed_at", nullable(date_value)),
        ]
        parser.add_argument(
            "--signed", dest="is_signed", action=argparse.BooleanOptionalAction,
            default=argparse.SUPPRESS,
        )
    else:
        fields = [
            ("contract_id", identifier_value), ("name", str),
            ("contact_name", nullable(str)), ("contact_email", nullable(str)),
            ("contact_phone", nullable(str)), ("start_at", date_value),
            ("end_at", date_value), ("location", str),
            ("attendees_count", int), ("notes", nullable(str)),
        ]
        if action == "update":
            fields.append(("support_contact_id", nullable(identifier_value)))
    for field, converter in fields:
        parser.add_argument(
            "--" + field.replace("_", "-"), type=converter,
            default=argparse.SUPPRESS,
        )


def _main() -> None:
    parser = argparse.ArgumentParser(
        prog="epicevents",
        description="CRM Epic Events. Utilise none pour effacer un champ nullable.",
    )
    subparsers = parser.add_subparsers(dest="command", required=True)
    for command in COMMANDS:
        command_parser = subparsers.add_parser(command)
        if command.startswith("list-"):
            _add_filters(command_parser, command.removeprefix("list-"))
    for entity, actions in ENTITIES.items():
        entity_parser = subparsers.add_parser(entity)
        action_parsers = entity_parser.add_subparsers(dest="action", required=True)
        for action in actions:
            action_parser = action_parsers.add_parser(action)
            if action == "list":
                _add_filters(action_parser, entity)
            elif action != "create":
                action_parser.add_argument("id", type=identifier_value, nargs="?")
            _add_fields(action_parser, entity, action)
    options = vars(parser.parse_args())
    command = options.pop("command")
    if command in ENTITIES:
        module_name = f"app.commands.{command}"
    else:
        module_name = COMMANDS[command]
        if command in LEGACY_ACTIONS:
            options["action"] = LEGACY_ACTIONS[command]
    from app.auth_session import AuthSessionError
    from app.permissions import AuthorizationError
    from app.security import PasswordPolicyError
    from app.services import BusinessError
    from sqlalchemy.exc import IntegrityError, SQLAlchemyError

    try:
        command_module = import_module(module_name)
        command_module.main(**options)
    except (AuthorizationError, AuthSessionError, BusinessError,
            CommandInputError, PasswordPolicyError) as error:
        parser.exit(1, f"Erreur : {error}\n")
    except IntegrityError as error:
        monitoring.capture_exception(error)
        parser.exit(1, "Erreur : données incompatibles avec la base (doublon ou relation invalide). Vérifie les valeurs saisies.\n")
    except SQLAlchemyError as error:
        monitoring.capture_exception(error)
        parser.exit(1, "Erreur : opération impossible dans la base de données. Vérifie la connexion et la configuration ; contacte un administrateur si le problème persiste.\n")


def main() -> None:
    monitoring.initialize()
    try:
        _main()
    except Exception as error:
        monitoring.capture_exception(error)
        raise
    finally:
        monitoring.flush()


if __name__ == "__main__":
    main()
