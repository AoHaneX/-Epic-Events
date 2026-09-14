"""Epic Events command-line entry point."""

import argparse
from importlib import import_module


COMMANDS = {
    "login": "app.commands.login",
    "logout": "app.commands.logout",
    "status": "app.commands.session_info",
    "create-employee": "app.commands.create_employee",
    "create-manager": "app.commands.create_manager",
}


def main() -> None:
    parser = argparse.ArgumentParser(prog="epicevents")
    parser.add_argument("command", choices=COMMANDS)
    args = parser.parse_args()

    try:
        command_module = import_module(COMMANDS[args.command])
        command_module.main()
    except (PermissionError, RuntimeError, ValueError) as error:
        parser.exit(1, f"Erreur : {error}\n")


if __name__ == "__main__":
    main()
