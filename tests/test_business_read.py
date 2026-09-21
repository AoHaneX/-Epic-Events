import io
import os
import re
import secrets
import tempfile
import unittest
from contextlib import redirect_stderr, redirect_stdout
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest.mock import Mock, patch

import jwt
from sqlalchemy import create_engine, event
from sqlalchemy.orm import sessionmaker

import epicevents


# Database imports need settings; keep these tests independent of local secrets.
with patch.dict(
    os.environ,
    {
        "DB_USER": "test_user",
        "DB_PASSWORD": "test_password",
        "DB_HOST": "127.0.0.1",
        "DB_PORT": "3306",
        "DB_NAME": "epic_events_test",
        "SQL_ECHO": "false",
    },
), patch("dotenv.load_dotenv"):
    from app import auth_session
    from app.database import Base
    from app.models import Client, Contract, Employee, Event, Role
    from app.permissions import AuthorizationError
    from app.services import clients, contracts, events


class BusinessReadFixture(unittest.TestCase):
    def setUp(self) -> None:
        self.secret = secrets.token_urlsafe(48)
        settings = patch.dict(
            os.environ,
            {
                "JWT_SECRET": self.secret,
                "ACCESS_TOKEN_MINUTES": "15",
                "REFRESH_TOKEN_DAYS": "7",
            },
        )
        settings.start()
        self.addCleanup(settings.stop)

        temp = tempfile.TemporaryDirectory(prefix="epic-read-tests-")
        self.addCleanup(temp.cleanup)
        self.session_file = Path(temp.name) / "session.json"
        session_path = patch.object(auth_session, "SESSION_FILE", self.session_file)
        session_path.start()
        self.addCleanup(session_path.stop)

        self.engine = create_engine("sqlite+pysqlite:///:memory:")
        self.addCleanup(self.engine.dispose)
        Base.metadata.create_all(self.engine)
        self.SessionLocal = sessionmaker(
            bind=self.engine, expire_on_commit=False, autoflush=False
        )
        self.seed_database()
        self.statements = []
        event.listen(self.engine, "before_cursor_execute", self.record_statement)

    def record_statement(
        self, connection, cursor, statement, parameters, context, executemany
    ) -> None:
        self.statements.append(statement)

    def seed_database(self) -> None:
        date = datetime(2026, 10, 1, 14, 0)
        with self.SessionLocal.begin() as session:
            roles = [
                Role(id=1, code="MANAGEMENT", name="Gestion"),
                Role(id=2, code="SALES", name="Commercial"),
                Role(id=3, code="SUPPORT", name="Support"),
            ]
            session.add_all(roles)
            employees = [
                (1, "Manager", 1, True),
                (2, "Commercial Alpha", 2, True),
                (3, "Support Alpha", 3, True),
                (4, "Commercial Beta", 2, True),
                (5, "Support Beta", 3, True),
                (6, "Compte désactivé", 3, False),
                (7, "Support sans événement", 3, True),
            ]
            for employee_id, name, role_id, active in employees:
                session.add(Employee(
                    id=employee_id,
                    full_name=name,
                    email=f"employee{employee_id}@example.invalid",
                    password_hash="unused-test-hash",
                    role_id=role_id,
                    is_active=active,
                ))
            for client_id, name, sales_id in [
                (20, "Client Beta", 4), (10, "Client Alpha", 2)
            ]:
                session.add(Client(
                    id=client_id,
                    full_name=name,
                    email=f"client{client_id}@example.invalid",
                    phone="+33 100000000",
                    company_name=f"Entreprise {client_id}",
                    sales_contact_id=sales_id,
                    created_at=date,
                    updated_at=date,
                    last_contact_at=date if client_id == 10 else None,
                ))
            for contract_id, client_id, signed, remaining in [
                (500, 20, True, 0),
                (400, 20, False, 0),
                (300, 10, True, 25),
                (200, 20, True, 0),
                (100, 10, False, 100),
            ]:
                session.add(Contract(
                    id=contract_id,
                    client_id=client_id,
                    total_amount=1000,
                    remaining_amount=remaining,
                    is_signed=signed,
                    signed_at=date if signed else None,
                    created_at=date,
                ))
            for event_id, contract_id, support_id in [
                (3000, 500, None), (2000, 300, 5), (1000, 200, 3)
            ]:
                session.add(Event(
                    id=event_id,
                    name=f"Rencontre {event_id}",
                    contract_id=contract_id,
                    support_contact_id=support_id,
                    contact_name="Contact Invité" if event_id == 1000 else None,
                    contact_email="contact@example.invalid" if event_id == 1000 else None,
                    contact_phone=None if event_id == 1000 else "+33 200000000",
                    start_at=date,
                    end_at=date + timedelta(hours=3),
                    location="Salle de réunion",
                    attendees_count=20,
                    notes="Prévoir un accueil." if event_id == 1000 else None,
                ))

    def login(self, employee_id: int = 3) -> None:
        auth_session.start_session(employee_id)

    def assert_no_business_read(self) -> None:
        for statement in self.statements:
            self.assertIsNone(
                re.search(r"\b(?:from|join)\s+(clients|contracts|events)\b",
                          statement, re.IGNORECASE),
                statement,
            )


class BusinessReadTests(BusinessReadFixture):
    def test_all_roles_can_read_all_records_in_id_order(self) -> None:
        for employee_id in (1, 2, 3):
            with self.subTest(employee_id=employee_id):
                self.login(employee_id)
                with self.SessionLocal() as session:
                    self.assertEqual(
                        [row.id for row in clients.list_clients(session)], [10, 20]
                    )
                    self.assertEqual(
                        [row.id for row in contracts.list_contracts(session)],
                        [100, 200, 300, 400, 500],
                    )
                    self.assertEqual(
                        [row.id for row in events.list_events(session)],
                        [1000, 2000, 3000],
                    )

    def test_general_filters_are_available_to_all_roles(self) -> None:
        for employee_id in (1, 2, 3):
            with self.subTest(employee_id=employee_id):
                self.login(employee_id)
                with self.SessionLocal() as session:
                    self.assertEqual(
                        [row.id for row in contracts.list_contracts(session, unsigned=True)],
                        [100, 400],
                    )
                    self.assertEqual(
                        [row.id for row in contracts.list_contracts(session, unpaid=True)],
                        [100, 300],
                    )
                    self.assertEqual(
                        [row.id for row in events.list_events(session, without_support=True)],
                        [3000],
                    )

    def test_contract_filters_combine_with_and(self) -> None:
        self.login()
        with self.SessionLocal() as session:
            rows = contracts.list_contracts(session, unsigned=True, unpaid=True)
        self.assertEqual([row.id for row in rows], [100])

    def test_mine_uses_the_authenticated_support_id(self) -> None:
        for employee_id, expected in [(3, [1000]), (5, [2000]), (7, [])]:
            with self.subTest(employee_id=employee_id):
                self.login(employee_id)
                with self.SessionLocal() as session:
                    rows = events.list_events(session, mine=True)
                self.assertEqual([row.id for row in rows], expected)

    def test_other_roles_cannot_use_mine(self) -> None:
        for employee_id in (1, 2):
            with self.subTest(employee_id=employee_id):
                self.login(employee_id)
                with self.SessionLocal() as session:
                    with self.assertRaises(AuthorizationError):
                        events.list_events(session, mine=True)
        self.assert_no_business_read()

    def test_event_filters_are_incompatible_in_the_service(self) -> None:
        self.login()
        with self.SessionLocal() as session:
            with self.assertRaises(ValueError):
                events.list_events(session, mine=True, without_support=True)
        self.assert_no_business_read()

    def test_authentication_failures_block_business_queries(self) -> None:
        now = datetime.now(timezone.utc)
        expired = {}
        for token_type in ("access", "refresh"):
            expired[token_type] = jwt.encode(
                {
                    "sub": "3", "type": token_type,
                    "iat": now - timedelta(days=8),
                    "exp": now - timedelta(days=1),
                },
                self.secret,
                algorithm="HS256",
            )
        for state in ("missing", "invalid", "expired", "disabled", "unknown"):
            for service in (clients.list_clients, contracts.list_contracts, events.list_events):
                with self.subTest(state=state, service=service.__name__):
                    auth_session.clear_session()
                    if state == "invalid":
                        auth_session._save_tokens("invalid", "invalid")
                    elif state == "expired":
                        auth_session._save_tokens(expired["access"], expired["refresh"])
                    elif state == "disabled":
                        self.login(6)
                    elif state == "unknown":
                        self.login(999)
                    self.statements.clear()
                    with self.SessionLocal() as session:
                        with self.assertRaises(auth_session.AuthSessionError):
                            service(session)
                    self.assert_no_business_read()

    def test_denied_read_permission_blocks_business_queries(self) -> None:
        self.login()
        for module, service in [
            (clients, clients.list_clients),
            (contracts, contracts.list_contracts),
            (events, events.list_events),
        ]:
            with self.subTest(service=service.__name__):
                self.statements.clear()
                with patch.object(module, "can_read_business_data", return_value=False):
                    with self.SessionLocal() as session:
                        with self.assertRaises(AuthorizationError):
                            service(session)
                self.assert_no_business_read()

    def test_relationships_remain_available_after_session_closes(self) -> None:
        self.login()
        with self.SessionLocal() as session:
            client_rows = clients.list_clients(session)
            contract_rows = contracts.list_contracts(session)
            event_rows = events.list_events(session)
        self.assertEqual(client_rows[0].sales_contact.full_name, "Commercial Alpha")
        self.assertEqual(contract_rows[1].client.sales_contact.full_name, "Commercial Beta")
        self.assertEqual(event_rows[0].contract.client.full_name, "Client Beta")
        self.assertEqual(event_rows[0].contact_name, "Contact Invité")
        self.assertEqual(event_rows[0].support_contact.full_name, "Support Alpha")
        self.assertIsNone(event_rows[2].support_contact)

    def test_empty_business_tables_return_empty_lists(self) -> None:
        with self.SessionLocal.begin() as session:
            for model in (Event, Contract, Client):
                session.query(model).delete(synchronize_session=False)
        self.login()
        with self.SessionLocal() as session:
            self.assertEqual(clients.list_clients(session), [])
            self.assertEqual(contracts.list_contracts(session), [])
            self.assertEqual(events.list_events(session), [])

    def test_reads_do_not_write_to_the_database(self) -> None:
        self.login()
        with self.SessionLocal() as session:
            clients.list_clients(session)
            contracts.list_contracts(session)
            events.list_events(session)
        self.assertTrue(self.statements)
        for statement in self.statements:
            self.assertTrue(statement.lstrip().upper().startswith("SELECT"), statement)


class BusinessCommandTests(BusinessReadFixture):
    def run_command(self, *arguments):
        from app.commands import list_clients, list_contracts, list_events

        output = io.StringIO()
        errors = io.StringIO()
        with (
            patch.object(list_clients, "SessionLocal", self.SessionLocal),
            patch.object(list_contracts, "SessionLocal", self.SessionLocal),
            patch.object(list_events, "SessionLocal", self.SessionLocal),
            patch("sys.argv", ["epicevents.py", *arguments]),
            redirect_stdout(output),
            redirect_stderr(errors),
        ):
            try:
                epicevents.main()
                code = 0
            except SystemExit as error:
                code = error.code
        return code, output.getvalue(), errors.getvalue()

    def test_client_output_contains_business_fields(self) -> None:
        self.login()
        code, output, errors = self.run_command("list-clients")
        self.assertEqual(code, 0, errors)
        for value in (
            "Client #10 : Client Alpha", "Client #20 : Client Beta",
            "Entreprise 10", "client10@example.invalid", "+33 100000000",
            "Création : 01/10/2026 14:00", "Dernière mise à jour : 01/10/2026 14:00",
            "Dernier contact : 01/10/2026 14:00", "Dernier contact : Non renseigné",
            "Commercial Alpha", "Commercial Beta",
        ):
            self.assertIn(value, output)
        self.assertNotIn("unused-test-hash", output)

    def test_contract_output_and_combined_filters(self) -> None:
        self.login(2)
        code, output, errors = self.run_command("list-contracts", "--unsigned", "--unpaid")
        self.assertEqual(code, 0, errors)
        for value in (
            "Contrat #100", "Client Alpha", "Commercial Alpha", "Entreprise 10",
            "client10@example.invalid", "+33 100000000", "Montant total : 1000.00",
            "Restant à payer : 100.00", "Création : 01/10/2026 14:00",
            "Statut : Non signé",
        ):
            self.assertIn(value, output)
        for contract_id in (200, 300, 400, 500):
            self.assertNotIn(f"Contrat #{contract_id}", output)

    def test_event_output_distinguishes_client_and_contact(self) -> None:
        self.login(3)
        code, output, errors = self.run_command("list-events", "--mine")
        self.assertEqual(code, 0, errors)
        for value in (
            "Événement #1000 : Rencontre 1000", "Contrat : #200",
            "Client : Client Beta (#20)", "Contact de l'événement : Contact Invité",
            "contact@example.invalid", "Téléphone du contact : Non renseigné",
            "Début : 01/10/2026 14:00", "Fin : 01/10/2026 17:00",
            "Support : Support Alpha (#3)", "Lieu : Salle de réunion",
            "Participants : 20", "Notes : Prévoir un accueil.",
        ):
            self.assertIn(value, output)
        self.assertNotIn("Rencontre 2000", output)
        self.assertNotIn("Rencontre 3000", output)

    def test_event_without_support_and_optional_values(self) -> None:
        self.login(1)
        code, output, errors = self.run_command("list-events", "--without-support")
        self.assertEqual(code, 0, errors)
        for value in (
            "Événement #3000", "Support : Non attribué",
            "Contact de l'événement : Non renseigné", "Email du contact : Non renseigné",
            "Téléphone du contact : +33 200000000", "Notes : Aucune",
        ):
            self.assertIn(value, output)
        self.assertNotIn("Rencontre 1000", output)

    def test_empty_results_have_clear_messages(self) -> None:
        with self.SessionLocal.begin() as session:
            for model in (Event, Contract, Client):
                session.query(model).delete(synchronize_session=False)
        self.login()
        for command, message in [
            ("list-clients", "Aucun client enregistré."),
            ("list-contracts", "Aucun contrat correspondant."),
            ("list-events", "Aucun événement correspondant."),
        ]:
            with self.subTest(command=command):
                code, output, errors = self.run_command(command)
                self.assertEqual(code, 0, errors)
                self.assertEqual(output.strip(), message)

    def test_missing_session_returns_error_without_data(self) -> None:
        for command in ("list-clients", "list-contracts", "list-events"):
            with self.subTest(command=command):
                code, output, errors = self.run_command(command)
                self.assertEqual(code, 1)
                self.assertEqual(output, "")
                self.assertIn("login", errors)
        self.assert_no_business_read()

    def test_mine_refused_to_non_support_without_data(self) -> None:
        self.login(1)
        code, output, errors = self.run_command("list-events", "--mine")
        self.assertEqual(code, 1)
        self.assertEqual(output, "")
        self.assertIn("réservé", errors)
        self.assert_no_business_read()


class CommandRoutingTests(unittest.TestCase):
    def test_existing_commands_still_receive_no_arguments(self) -> None:
        for command in ("login", "logout", "status", "create-employee", "create-manager"):
            with self.subTest(command=command):
                module = Mock()
                with (
                    patch("sys.argv", ["epicevents.py", command]),
                    patch.object(epicevents, "import_module", return_value=module) as importer,
                ):
                    epicevents.main()
                importer.assert_called_once_with(epicevents.COMMANDS[command])
                module.main.assert_called_once_with()

    def test_options_are_forwarded_to_the_correct_command(self) -> None:
        cases = [
            (["list-clients"], {}),
            (["list-contracts"], {"unsigned": False, "unpaid": False}),
            (["list-contracts", "--unsigned"], {"unsigned": True, "unpaid": False}),
            (["list-contracts", "--unpaid"], {"unsigned": False, "unpaid": True}),
            (["list-contracts", "--unsigned", "--unpaid"], {"unsigned": True, "unpaid": True}),
            (["list-events"], {"without_support": False, "mine": False}),
            (["list-events", "--without-support"], {"without_support": True, "mine": False}),
            (["list-events", "--mine"], {"without_support": False, "mine": True}),
        ]
        for arguments, expected in cases:
            with self.subTest(arguments=arguments):
                module = Mock()
                with (
                    patch("sys.argv", ["epicevents.py", *arguments]),
                    patch.object(epicevents, "import_module", return_value=module) as importer,
                ):
                    epicevents.main()
                importer.assert_called_once_with(epicevents.COMMANDS[arguments[0]])
                module.main.assert_called_once_with(**expected)

    def test_invalid_arguments_are_rejected_before_loading_commands(self) -> None:
        cases = [
            [], ["unknown"], ["login", "--mine"], ["list-clients", "--unsigned"],
            ["list-contracts", "--mine"], ["list-events", "--unknown"],
            ["list-events", "--without-support", "--mine"],
        ]
        for arguments in cases:
            with self.subTest(arguments=arguments):
                with (
                    patch("sys.argv", ["epicevents.py", *arguments]),
                    patch.object(epicevents, "import_module") as importer,
                    redirect_stderr(io.StringIO()),
                ):
                    with self.assertRaises(SystemExit) as error:
                        epicevents.main()
                self.assertEqual(error.exception.code, 2)
                importer.assert_not_called()

    def test_existing_error_handling_is_preserved(self) -> None:
        for exception in (PermissionError, RuntimeError, ValueError):
            with self.subTest(exception=exception):
                module = Mock()
                module.main.side_effect = exception("Accès refusé pour le test.")
                errors = io.StringIO()
                with (
                    patch("sys.argv", ["epicevents.py", "status"]),
                    patch.object(epicevents, "import_module", return_value=module),
                    redirect_stderr(errors),
                ):
                    with self.assertRaises(SystemExit) as error:
                        epicevents.main()
                self.assertEqual(error.exception.code, 1)
                self.assertIn("Accès refusé pour le test.", errors.getvalue())


if __name__ == "__main__":
    unittest.main()
