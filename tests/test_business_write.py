import io
import unittest
from contextlib import redirect_stderr, redirect_stdout
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from unittest.mock import patch

from sqlalchemy import func, select, text
from sqlalchemy.dialects.mysql import BIGINT
from sqlalchemy.ext.compiler import compiles

from test_business_read import BusinessReadFixture
from app.models import Client, Contract, Employee, Event
from app.permissions import AuthorizationError
from app.security import PasswordPolicyError, verify_password
from app.services import contracts, employees, events
import epicevents


@compiles(BIGINT, "sqlite")
def sqlite_bigint(element, compiler, **kwargs):
    # SQLite autoincrement requires the exact INTEGER type name.
    return "INTEGER"


class BusinessWriteFixture(BusinessReadFixture):
    def setUp(self):
        super().setUp()
        with self.engine.connect() as connection:
            connection.execute(text("PRAGMA foreign_keys=ON"))
        self.date = datetime(2026, 10, 10, 10)

    def actor(self, session, employee_id=1):
        return session.get(Employee, employee_id)

    def new_contract(self, session, **changes):
        values = dict(client_id=10, total_amount="1000.00", remaining_amount="250.00",
                      is_signed=True, signed_at=self.date)
        values.update(changes)
        return contracts.create_contract(session, self.actor(session), **values)

    def event_values(self, contract_id):
        return dict(contract_id=contract_id, name=" Rencontre ",
                    contact_name="Invité", contact_email=" Guest@Example.Invalid ",
                    contact_phone=None, start_at=self.date,
                    end_at=self.date + timedelta(hours=2), location=" Paris ",
                    attendees_count=0, notes="Accueil")

    def new_event(self, session):
        contract = self.new_contract(session)
        return events.create_event(session, self.actor(session, 2),
                                   **self.event_values(contract.id))

    def assert_no_writes(self):
        for statement in self.statements:
            self.assertFalse(statement.lstrip().upper().startswith(
                ("INSERT", "UPDATE", "DELETE")), statement)


class EmployeeWriteTests(BusinessWriteFixture):
    def test_create_update_department_and_normalization(self):
        with self.SessionLocal.begin() as session:
            manager = self.actor(session)
            employee = employees.create_employee(
                session, manager, full_name=" Nouveau ", email=" New@Example.Invalid ",
                password="Strong-password-2026", role_code=" sales ")
            employee_id = employee.id
            self.assertEqual(employee.full_name, "Nouveau")
            self.assertEqual(employee.email, "new@example.invalid")
            self.assertTrue(verify_password(employee.password_hash, "Strong-password-2026")[0])
            employees.update_employee(session, manager, employee, role_code="support",
                                      full_name="Support Nouveau", email=" Changed@Example.Invalid ")
        with self.SessionLocal() as session:
            employee = session.get(Employee, employee_id)
            self.assertEqual(employee.role.code, "SUPPORT")
            self.assertEqual(employee.email, "changed@example.invalid")
            self.assertEqual(employee.full_name, "Support Nouveau")

    def test_invalid_creates_do_not_write(self):
        cases = [
            ({"full_name": " "}, employees.EmployeeValidationError),
            ({"full_name": None}, employees.EmployeeValidationError),
            ({"email": ""}, employees.EmployeeValidationError),
            ({"email": "invalid"}, employees.EmployeeValidationError),
            ({"email": " EMPLOYEE2@EXAMPLE.INVALID "}, employees.DuplicateEmailError),
            ({"role_code": "UNKNOWN"}, employees.UnknownRoleError),
            ({"password": "short"}, PasswordPolicyError),
        ]
        for changes, expected in cases:
            with self.subTest(changes=tuple(changes)):
                with self.SessionLocal.begin() as session:
                    values = dict(full_name="New", email="new@example.invalid",
                                  password="Strong-password-2026", role_code="SALES")
                    values.update(changes)
                    with self.assertRaises(expected):
                        employees.create_employee(session, self.actor(session), **values)
                    self.assertFalse(session.new)
        self.assert_no_writes()

    def test_failed_update_is_atomic_even_when_caught_and_committed(self):
        for changes, error in [
            ({"full_name": "Changed", "email": "changed@example.invalid", "role_code": "UNKNOWN"}, employees.UnknownRoleError),
            ({"full_name": " "}, employees.EmployeeValidationError),
            ({"email": None}, employees.EmployeeValidationError),
            ({"email": "employee4@example.invalid"}, employees.DuplicateEmailError),
        ]:
            with self.subTest(changes=changes):
                with self.SessionLocal.begin() as session:
                    target = self.actor(session, 2)
                    with self.assertRaises(error):
                        employees.update_employee(session, self.actor(session), target, **changes)
                    self.assertFalse(session.dirty)
                with self.SessionLocal() as session:
                    self.assertEqual(self.actor(session, 2).full_name, "Commercial Alpha")
        self.assert_no_writes()

    def test_last_manager_demotion_is_atomic(self):
        with self.SessionLocal.begin() as session:
            manager = self.actor(session)
            with self.assertRaises(AuthorizationError):
                employees.update_employee(session, manager, manager,
                                          full_name="Changed", role_code="SALES")
            self.assertEqual(manager.full_name, "Manager")
            self.assertEqual(manager.role.code, "MANAGEMENT")
            self.assertFalse(session.dirty)
        self.assert_no_writes()

    def test_last_manager_deletion_and_deactivation_are_blocked(self):
        for operation in (employees.delete_employee, employees.deactivate_employee):
            with self.subTest(operation=operation.__name__):
                with self.SessionLocal.begin() as session:
                    manager = self.actor(session)
                    with self.assertRaises(AuthorizationError):
                        operation(session, manager, manager)
        self.assert_no_writes()

    def test_demotion_allowed_with_another_active_manager(self):
        with self.SessionLocal.begin() as session:
            manager = self.actor(session)
            employees.update_employee(session, manager, self.actor(session, 7), role_code="MANAGEMENT")
            employees.update_employee(session, manager, manager, role_code="SALES")
            self.assertEqual(manager.role.code, "SALES")

    def test_deactivate_delete_and_linked_employee_protection(self):
        with self.SessionLocal.begin() as session:
            manager = self.actor(session)
            with self.assertRaises(employees.EmployeeValidationError):
                employees.delete_employee(session, manager, self.actor(session, 2))
            employees.deactivate_employee(session, manager, self.actor(session, 2))
            self.assertFalse(self.actor(session, 2).is_active)
            employees.delete_employee(session, manager, self.actor(session, 7))
            self.assertIsNone(session.get(Employee, 7))

    def test_unauthorized_employee_operations_do_not_write(self):
        for actor_id in (2, 3, 6):
            with self.subTest(actor_id=actor_id):
                with self.SessionLocal.begin() as session:
                    actor, target = self.actor(session, actor_id), self.actor(session, 7)
                    for operation in (employees.update_employee, employees.deactivate_employee, employees.delete_employee):
                        with self.assertRaises(AuthorizationError):
                            operation(session, actor, target)
                    with self.assertRaises(AuthorizationError):
                        employees.create_employee(session, actor, full_name="New", email="new@example.invalid",
                                                  password="Strong-password-2026", role_code="SALES")
        self.assert_no_writes()

    def test_initial_manager_validates_and_bootstrap_cannot_repeat(self):
        with self.SessionLocal.begin() as session:
            for model in (Event, Contract, Client, Employee):
                session.query(model).delete(synchronize_session=False)
        with self.SessionLocal.begin() as session:
            with self.assertRaises(employees.EmployeeValidationError):
                employees.create_initial_manager(session, full_name=" ", email="x@example.invalid",
                                                 password="Strong-password-2026")
            manager = employees.create_initial_manager(session, full_name=" First ",
                                                       email=" FIRST@EXAMPLE.INVALID ", password="Strong-password-2026")
            self.assertEqual(manager.role.code, "MANAGEMENT")
            self.assertEqual(manager.email, "first@example.invalid")
            with self.assertRaises(AuthorizationError):
                employees.create_initial_manager(session, full_name="Second", email="second@example.invalid",
                                                 password="Strong-password-2026")


class ContractWriteTests(BusinessWriteFixture):
    def test_create_and_update_all_fields(self):
        with self.SessionLocal.begin() as session:
            contract = self.new_contract(session)
            self.assertEqual(contract.total_amount, Decimal("1000.00"))
            contract_id = contract.id
            contracts.update_contract(session, self.actor(session), contract.id, client_id=20,
                                      total_amount="200.50", remaining_amount="0", is_signed=False, signed_at=None)
            self.assertEqual(contract.client.id, 20)
        with self.SessionLocal() as session:
            contract = session.get(Contract, contract_id)
            self.assertEqual(contract.client_id, 20)
            self.assertEqual(contract.total_amount, Decimal("200.50"))
            self.assertIsNone(contract.signed_at)
            self.assertFalse(contract.is_signed)

    def test_invalid_amounts_and_signature_do_not_write(self):
        cases = [
            {"total_amount": "-1"}, {"remaining_amount": "-1"},
            {"remaining_amount": "1001"}, {"total_amount": "NaN"},
            {"total_amount": "Infinity"}, {"total_amount": "bad"},
            {"total_amount": "10.001"}, {"total_amount": "10000000000"},
            {"total_amount": None}, {"is_signed": False}, {"signed_at": None},
            {"is_signed": "false"}, {"signed_at": datetime.now(timezone.utc)},
        ]
        for changes in cases:
            with self.subTest(changes=changes):
                with self.SessionLocal.begin() as session:
                    with self.assertRaises(contracts.ContractValidationError):
                        self.new_contract(session, **changes)
                    self.assertFalse(session.new)
                    self.assertFalse(session.dirty)
        self.assert_no_writes()

    def test_sales_can_only_move_between_own_clients(self):
        with self.SessionLocal.begin() as session:
            session.add(Client(id=30, full_name="Other", email="other@example.invalid",
                               phone="0123456789", company_name="Other", sales_contact_id=2))
            session.flush()
            actor = self.actor(session, 2)
            contract = contracts.update_contract(session, actor, 100, client_id=30)
            self.assertEqual(contract.client.id, 30)
        self.statements.clear()
        with self.SessionLocal.begin() as session:
            with self.assertRaises(AuthorizationError):
                contracts.update_contract(session, self.actor(session, 2), 100,
                                          client_id=20, total_amount="2000")
            self.assertFalse(session.dirty)
            with self.assertRaises(AuthorizationError):
                contracts.update_contract(session, self.actor(session, 2), 400, client_id=10)
        self.assert_no_writes()

    def test_invalid_future_values_and_missing_relations_are_atomic(self):
        for changes, error in [
            ({"client_id": 20, "total_amount": "10"}, contracts.ContractValidationError),
            ({"client_id": None}, contracts.ContractValidationError),
            ({"client_id": 9999}, contracts.ClientNotFoundError),
            ({"is_signed": True}, contracts.ContractValidationError),
        ]:
            with self.subTest(changes=changes):
                with self.SessionLocal.begin() as session:
                    with self.assertRaises(error):
                        contracts.update_contract(session, self.actor(session), 100, **changes)
                    self.assertFalse(session.dirty)
                    self.assertEqual(session.get(Contract, 100).client_id, 10)
        self.assert_no_writes()

    def test_omitted_signature_retained_explicit_none_validated(self):
        with self.SessionLocal.begin() as session:
            contract = contracts.update_contract(session, self.actor(session), 300, remaining_amount=0)
            date = contract.signed_at
            with self.assertRaises(contracts.ContractValidationError):
                contracts.update_contract(session, self.actor(session), 300, signed_at=None)
            self.assertEqual(contract.signed_at, date)
            self.assertFalse(session.dirty)

    def test_unauthorized_and_not_found(self):
        with self.SessionLocal.begin() as session:
            for actor_id in (2, 3, 6):
                with self.assertRaises(AuthorizationError):
                    contracts.create_contract(session, self.actor(session, actor_id), client_id=10,
                                              total_amount=10, remaining_amount=10)
            for actor_id in (3, 6):
                with self.assertRaises(AuthorizationError):
                    contracts.update_contract(session, self.actor(session, actor_id), 100, total_amount=2000)
            with self.assertRaises(contracts.ContractNotFoundError):
                contracts.update_contract(session, self.actor(session), 9999, remaining_amount=0)
            with self.assertRaises(contracts.ClientNotFoundError):
                self.new_contract(session, client_id=9999)
        self.assert_no_writes()


class EventWriteTests(BusinessWriteFixture):
    def test_creation_for_signed_contract_without_support(self):
        with self.SessionLocal.begin() as session:
            record = self.new_event(session)
            event_id = record.id
            self.assertEqual(record.name, "Rencontre")
            self.assertEqual(record.contact_email, "guest@example.invalid")
            self.assertIsNone(record.support_contact_id)
        with self.SessionLocal() as session:
            self.assertEqual(session.get(Event, event_id).attendees_count, 0)

    def test_unsigned_duplicate_and_other_sales_are_refused(self):
        with self.SessionLocal.begin() as session:
            for contract_id, actor_id in ((100, 2), (200, 4), (300, 2), (400, 4), (500, 2)):
                with self.subTest(contract=contract_id):
                    with self.assertRaises((AuthorizationError, events.EventValidationError)):
                        events.create_event(session, self.actor(session, actor_id), **self.event_values(contract_id))
            with self.assertRaises(events.ContractNotFoundError):
                events.create_event(session, self.actor(session, 2), **self.event_values(9999))
        self.assert_no_writes()

    def test_invalid_event_fields_do_not_write(self):
        with self.SessionLocal.begin() as session:
            contract_id = self.new_contract(session).id
        self.statements.clear()
        for changes in (
            {"name": " "}, {"location": ""}, {"end_at": self.date},
            {"attendees_count": -1}, {"attendees_count": 1.5}, {"attendees_count": True},
            {"contact_email": None, "contact_phone": " "}, {"contact_email": "invalid"},
            {"start_at": None}, {"start_at": self.date.replace(tzinfo=timezone.utc)},
            {"notes": "é" * 40000},
        ):
            with self.subTest(fields=tuple(changes)):
                with self.SessionLocal.begin() as session:
                    values = self.event_values(contract_id)
                    values.update(changes)
                    with self.assertRaises(events.EventValidationError):
                        events.create_event(session, self.actor(session, 2), **values)
                    self.assertFalse(session.new)
                    self.assertFalse(session.dirty)
        self.assert_no_writes()

    def test_support_updates_all_general_fields_and_clears_nullable_fields(self):
        with self.SessionLocal.begin() as session:
            record = events.update_event(
                session, self.actor(session, 3), 1000, name="Updated", contact_name=None,
                contact_email=None, contact_phone="0123456789", start_at=self.date,
                end_at=self.date + timedelta(hours=4), location="Lyon", attendees_count=12, notes=None)
            self.assertEqual(record.name, "Updated")
            self.assertIsNone(record.contact_name)
            self.assertIsNone(record.contact_email)
            self.assertIsNone(record.notes)
        with self.SessionLocal() as session:
            record = session.get(Event, 1000)
            self.assertEqual((record.location, record.attendees_count, record.contact_phone), ("Lyon", 12, "0123456789"))

    def test_assign_and_remove_support(self):
        with self.SessionLocal.begin() as session:
            manager = self.actor(session)
            record = events.update_event(session, manager, 3000, support_contact_id=7)
            self.assertEqual(record.support_contact_id, 7)
            self.assertEqual(record.support_contact.id, 7)
            events.update_event(session, manager, 3000, support_contact_id=None)
            self.assertIsNone(record.support_contact_id)
            self.assertIsNone(record.support_contact)

    def test_invalid_support_does_not_mutate_event(self):
        for support_id, error in ((2, events.EventValidationError), (6, events.EventValidationError),
                                  (9999, events.EmployeeNotFoundError)):
            with self.subTest(support=support_id):
                with self.SessionLocal.begin() as session:
                    with self.assertRaises(error):
                        events.update_event(session, self.actor(session), 1000, support_contact_id=support_id)
                    self.assertEqual(session.get(Event, 1000).support_contact_id, 3)
                    self.assertFalse(session.dirty)
        self.assert_no_writes()

    def test_assignment_does_not_normalize_unrequested_general_fields(self):
        with self.SessionLocal.begin() as session:
            record = session.get(Event, 3000)
            record.name = "  Original  "
            record.notes = "  Notes  "
            session.flush()
            events.update_event(session, self.actor(session), 3000, support_contact_id=7)
            self.assertEqual(record.name, "  Original  ")
            self.assertEqual(record.notes, "  Notes  ")

    def test_contract_replacement_and_permissions(self):
        with self.SessionLocal.begin() as session:
            contract = self.new_contract(session)
            record = events.update_event(session, self.actor(session), 1000, contract_id=contract.id)
            self.assertEqual(record.contract.id, contract.id)
            self.assertEqual(record.contract_id, contract.id)
        self.statements.clear()
        with self.SessionLocal.begin() as session:
            for actor_id in (2, 3, 6):
                with self.assertRaises(AuthorizationError):
                    events.update_event(session, self.actor(session, actor_id), 1000, contract_id=200)
            for contract_id, error in ((100, events.EventValidationError), (300, events.EventValidationError),
                                       (9999, events.ContractNotFoundError), (None, events.EventValidationError)):
                with self.assertRaises(error):
                    events.update_event(session, self.actor(session), 1000, contract_id=contract_id)
                self.assertFalse(session.dirty)
        self.assert_no_writes()

    def test_field_permissions_and_atomic_failures(self):
        with self.SessionLocal.begin() as session:
            for actor_id, changes in (
                (1, {"name": "Changed"}), (2, {"name": "Changed"}), (5, {"name": "Changed"}),
                (3, {"support_contact_id": 5}), (3, {"support_contact_id": None}),
                (1, {"support_contact_id": 5, "notes": "Changed"}),
            ):
                with self.subTest(actor_id=actor_id, changes=changes):
                    with self.assertRaises(AuthorizationError):
                        events.update_event(session, self.actor(session, actor_id), 1000, **changes)
                    self.assertFalse(session.dirty)
            with self.assertRaises(events.EventValidationError):
                events.update_event(session, self.actor(session, 3), 1000, name="Changed", contact_email=None)
            self.assertEqual(session.get(Event, 1000).name, "Rencontre 1000")
            self.assertFalse(session.dirty)
            with self.assertRaises(events.EventNotFoundError):
                events.update_event(session, self.actor(session), 9999, support_contact_id=3)
        self.assert_no_writes()


class TransactionAndCommandTests(BusinessWriteFixture):
    def test_rollback_after_flushed_creations(self):
        with self.assertRaisesRegex(RuntimeError, "abort"):
            with self.SessionLocal.begin() as session:
                employees.create_employee(session, self.actor(session), full_name="New", email="new@example.invalid",
                                          password="Strong-password-2026", role_code="SALES")
                self.new_event(session)
                raise RuntimeError("abort")
        with self.SessionLocal() as session:
            for model, count in ((Employee, 7), (Contract, 5), (Event, 3)):
                self.assertEqual(session.scalar(select(func.count()).select_from(model)), count)

    def test_rollback_after_flushed_updates(self):
        with self.assertRaisesRegex(RuntimeError, "abort"):
            with self.SessionLocal.begin() as session:
                employees.update_employee(session, self.actor(session), self.actor(session, 7), full_name="Changed")
                contracts.update_contract(session, self.actor(session), 100, client_id=20)
                events.update_event(session, self.actor(session), 1000, support_contact_id=None)
                raise RuntimeError("abort")
        with self.SessionLocal() as session:
            self.assertEqual(self.actor(session, 7).full_name, "Support sans événement")
            self.assertEqual(session.get(Contract, 100).client_id, 10)
            self.assertEqual(session.get(Event, 1000).support_contact_id, 3)

    def run_cli(self, *arguments):
        from app.commands import contracts as contract_commands, events as event_commands, employees as employee_commands
        output, errors = io.StringIO(), io.StringIO()
        with (patch.object(contract_commands, "SessionLocal", self.SessionLocal),
              patch.object(event_commands, "SessionLocal", self.SessionLocal),
              patch.object(employee_commands, "SessionLocal", self.SessionLocal),
              patch("sys.argv", ["epicevents.py", *arguments]),
              patch("builtins.input", side_effect=AssertionError("Unexpected prompt")),
              redirect_stdout(output), redirect_stderr(errors)):
            try:
                epicevents.main()
                code = 0
            except SystemExit as error:
                code = error.code
        return code, output.getvalue(), errors.getvalue()

    def test_new_commands_commit_and_preserve_omitted_values(self):
        self.login(1)
        code, output, errors = self.run_cli("contracts", "create", "--client-id", "10", "--total-amount", "10.50",
                                           "--remaining-amount", "5", "--no-signed", "--signed-at", "none")
        self.assertEqual(code, 0, errors)
        self.assertIn("créé", output)
        code, _, errors = self.run_cli("employees", "update", "7", "--role-code", "SALES")
        self.assertEqual(code, 0, errors)
        code, _, errors = self.run_cli("events", "update", "1000", "--support-contact-id", "none")
        self.assertEqual(code, 0, errors)
        with self.SessionLocal() as session:
            self.assertEqual(self.actor(session, 7).role.code, "SALES")
            record = session.get(Event, 1000)
            self.assertIsNone(record.support_contact_id)
            self.assertEqual(record.notes, "Prévoir un accueil.")

    def test_employee_create_password_never_printed(self):
        self.login(1)
        with patch("app.commands.employees.getpass", return_value="Strong-password-2026"):
            code, output, errors = self.run_cli("employees", "create", "--full-name", "New", "--email",
                                               "new@example.invalid", "--role-code", "SALES")
        self.assertEqual(code, 0, errors)
        self.assertNotIn("Strong-password", output + errors)
        self.assertNotIn("argon2", output + errors)

    def test_event_cli_create_assign_and_update(self):
        with self.SessionLocal.begin() as session:
            contract_id = self.new_contract(session).id
        self.login(2)
        code, _, errors = self.run_cli(
            "events", "create", "--contract-id", str(contract_id), "--name", "CLI Event",
            "--contact-name", "none", "--contact-email", "contact@example.invalid", "--contact-phone", "none",
            "--start-at", "2026-10-10T10:00", "--end-at", "2026-10-10T12:00",
            "--location", "Paris", "--attendees-count", "12", "--notes", "none")
        self.assertEqual(code, 0, errors)
        with self.SessionLocal() as session:
            event_id = session.scalar(select(Event.id).where(Event.contract_id == contract_id))
        self.login(1)
        code, _, errors = self.run_cli("events", "update", str(event_id), "--support-contact-id", "3")
        self.assertEqual(code, 0, errors)
        self.login(3)
        code, _, errors = self.run_cli("events", "update", str(event_id), "--notes", "Prévoir café")
        self.assertEqual(code, 0, errors)
        with self.SessionLocal() as session:
            record = session.get(Event, event_id)
            self.assertEqual(record.notes, "Prévoir café")
            self.assertEqual(record.support_contact_id, 3)
            self.assertEqual(record.name, "CLI Event")

    def test_employee_interactive_create_and_password_confirmation(self):
        from app.commands import employees as command

        self.login(1)
        with (patch.object(command, "SessionLocal", self.SessionLocal),
              patch("builtins.input", side_effect=["Interactive", "interactive@example.invalid", "SALES"]),
              patch.object(command, "getpass", return_value="Strong-password-2026"),
              redirect_stdout(io.StringIO())):
            command.main("create")
        with self.SessionLocal() as session:
            self.assertIsNotNone(session.scalar(select(Employee).where(Employee.email == "interactive@example.invalid")))
        with patch.object(command, "getpass", side_effect=["Strong-password-2026", "different"]):
            with self.assertRaises(ValueError):
                command.ask_confirmed_password()

    def test_new_list_routes_and_nullable_values(self):
        self.login(1)
        for entity in ("contracts", "events", "employees"):
            code, _, errors = self.run_cli(entity, "list")
            self.assertEqual(code, 0, errors)
        code, _, errors = self.run_cli("contracts", "update", "300", "--no-signed", "--signed-at", "none")
        self.assertEqual(code, 0, errors)
        with self.SessionLocal() as session:
            record = session.get(Contract, 300)
            self.assertFalse(record.is_signed)
            self.assertIsNone(record.signed_at)

    def test_cli_business_failure_rolls_back_without_success_message(self):
        self.login(1)
        code, output, errors = self.run_cli("contracts", "update", "100", "--client-id", "20", "--total-amount", "5")
        self.assertEqual(code, 1)
        self.assertEqual(output, "")
        self.assertIn("dépasse", errors)
        with self.SessionLocal() as session:
            self.assertEqual(session.get(Contract, 100).client_id, 10)
        self.assert_no_writes()

    def test_malformed_cli_values_rejected_before_commands(self):
        for arguments in (("contracts", "create", "--total-amount", "abc"),
                          ("events", "update", "1000", "--start-at", "invalid")):
            code, output, _ = self.run_cli(*arguments)
            self.assertEqual(code, 2)
            self.assertEqual(output, "")
        self.assert_no_writes()

    def test_missing_login_blocks_write(self):
        code, output, errors = self.run_cli("contracts", "update", "100", "--remaining-amount", "0")
        self.assertEqual(code, 1)
        self.assertEqual(output, "")
        self.assertIn("login", errors)
        self.assert_no_writes()


if __name__ == "__main__":
    unittest.main()
