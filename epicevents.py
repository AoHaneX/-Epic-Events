"""Epic Events command-line entry point."""

import argparse
from importlib import import_module


COMMANDS = {
    "login": "app.commands.login",
    "logout": "app.commands.logout",
    "status": "app.commands.session_info",
    "create-employee": "app.commands.create_employee",
    "create-manager": "app.commands.create_manager",
    "list-clients": "app.commands.list_clients",
    "list-contracts": "app.commands.list_contracts",
    "list-events": "app.commands.list_events",
}


def main() -> None:
    parser = argparse.ArgumentParser(prog="epicevents")
    subparsers = parser.add_subparsers(dest="command", required=True)
    for command in COMMANDS:
        command_parser = subparsers.add_parser(command)
        if command == "list-contracts":
            command_parser.add_argument(
                "--unsigned", action="store_true", help="Contrats non signés."
            )
            command_parser.add_argument(
                "--unpaid", action="store_true", help="Contrats restant à payer."
            )
        elif command == "list-events":
            filters = command_parser.add_mutually_exclusive_group()
            filters.add_argument(
                "--without-support",
                action="store_true",
                help="Événements sans support attribué.",
            )
            filters.add_argument(
                "--mine",
                action="store_true",
                help="Événements attribués au support connecté.",
            )
    options = vars(parser.parse_args())
    command = options.pop("command")

    try:
        command_module = import_module(COMMANDS[command])
        command_module.main(**options)
    except (PermissionError, RuntimeError, ValueError) as error:
        parser.exit(1, f"Erreur : {error}\n")


if __name__ == "__main__":
    main()
