import argparse
import io
import unittest
from contextlib import redirect_stderr, redirect_stdout
from unittest.mock import Mock, patch

from test_business_read import BusinessReadFixture
from app.commands import CommandInputError, ask_identifier, identifier_value
from app.services import contracts, employees, events
from sqlalchemy.exc import IntegrityError, OperationalError
import epicevents


class IdentifierTests(unittest.TestCase):
    def test_cli_rejects_invalid_identifiers_before_command_loading(self):
        for args in (
            ['employees', 'update', '0'], ['employees', 'delete', '-1'],
            ['contracts', 'update', '-2'], ['events', 'update', 'abc'],
            ['contracts', 'create', '--client-id', '0'],
            ['events', 'create', '--contract-id', '-1'],
            ['events', 'update', '1', '--support-contact-id', '0'],
        ):
            with self.subTest(args=args), patch('sys.argv', ['epicevents.py', *args]), patch.object(epicevents, 'import_module') as importer, redirect_stderr(io.StringIO()):
                with self.assertRaises(SystemExit) as error:
                    epicevents.main()
                self.assertEqual(error.exception.code, 2)
                importer.assert_not_called()

    def test_interactive_identifier_validation(self):
        for value in ('0', '-1', 'abc', '1.5', ''):
            with self.subTest(value=value), patch('builtins.input', return_value=value):
                with self.assertRaises(CommandInputError):
                    ask_identifier('Identifiant')
        with patch('builtins.input', return_value='12'):
            self.assertEqual(ask_identifier('Identifiant'), 12)

    def test_services_reject_invalid_ids_without_database_queries(self):
        for value in (0, -1, True, '1', None, 1.5):
            for service, args, exception in (
                (employees.get_employee, (value,), employees.EmployeeValidationError),
                (contracts.update_contract, (Mock(), value), contracts.ContractValidationError),
                (events.update_event, (Mock(), value), events.EventValidationError),
            ):
                with self.subTest(value=value, service=service.__name__):
                    session = Mock()
                    with self.assertRaises(exception):
                        service(session, *args)
                    self.assertEqual(session.mock_calls, [])


class DatabaseErrorTests(BusinessReadFixture):
    def test_database_error_is_readable_and_transaction_rolls_back(self):
        from app.commands import contracts as command
        from app.models import Contract

        self.login(1)
        for exception in (OperationalError, IntegrityError):
            failure = exception('PRIVATE SQL', {'password': 'PRIVATE PASSWORD'}, Exception('PRIVATE HOST'))
            original = command.update_contract

            def fail_after_write(*args, **kwargs):
                original(*args, **kwargs)
                raise failure

            output, errors = io.StringIO(), io.StringIO()
            with self.subTest(exception=exception), patch.object(command, 'SessionLocal', self.SessionLocal), patch.object(command, 'update_contract', side_effect=fail_after_write), patch('sys.argv', ['epicevents.py', 'contracts', 'update', '100', '--remaining-amount', '0']), redirect_stdout(output), redirect_stderr(errors):
                with self.assertRaises(SystemExit) as error:
                    epicevents.main()
            self.assertEqual(error.exception.code, 1)
            self.assertEqual(output.getvalue(), '')
            self.assertIn('Erreur :', errors.getvalue())
            self.assertNotIn('PRIVATE', errors.getvalue())
            self.assertNotIn('Traceback', errors.getvalue())
            with self.SessionLocal() as session:
                self.assertGreater(session.get(Contract, 100).remaining_amount, 0)
