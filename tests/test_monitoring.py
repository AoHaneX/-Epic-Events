import io
import json
import os
import unittest
from contextlib import redirect_stderr
from unittest.mock import patch

from test_business_write import BusinessWriteFixture
from app import monitoring
from app.models import Employee
from app.services import employees, contracts
import epicevents
import sentry_sdk
from sentry_sdk.transport import Transport


class AuditTests(BusinessWriteFixture):
    def test_employee_actions_sent_only_after_commit(self):
        with patch.object(monitoring, 'publish') as publish:
            with self.SessionLocal.begin() as session:
                actor = self.actor(session)
                person = employees.create_employee(session, actor, full_name='New', email='new@example.invalid', password='Strong-password-2026', role_code='SUPPORT')
                employees.update_employee(session, actor, person, full_name='Changed')
                employees.change_password(session, actor, person, 'Other-password-2026')
                employees.deactivate_employee(session, actor, person)
                employees.delete_employee(session, actor, person)
                publish.assert_not_called()
            self.assertEqual([c.args[0] for c in publish.call_args_list], [
                'employee.created', 'employee.updated', 'employee.password_changed',
                'employee.deactivated', 'employee.deleted'])

    def test_rollback_discards_and_session_reuse_does_not_leak(self):
        with patch.object(monitoring, 'publish') as publish, self.SessionLocal() as session:
            employees.update_employee(session, self.actor(session), self.actor(session, 7), full_name='Changed')
            session.rollback()
            session.commit()
            publish.assert_not_called()

    def test_nested_commit_waits_and_nested_rollback_discards(self):
        with patch.object(monitoring, 'publish') as publish:
            with self.SessionLocal.begin() as session:
                with session.begin_nested():
                    employees.update_employee(session, self.actor(session), self.actor(session, 7), full_name='Changed')
                publish.assert_not_called()
                try:
                    with session.begin_nested():
                        employees.update_employee(session, self.actor(session), self.actor(session, 7), full_name='Discard')
                        raise RuntimeError('rollback')
                except RuntimeError:
                    pass
            self.assertEqual(publish.call_count, 1)

    def test_signature_transition_and_already_signed_creation(self):
        with patch.object(monitoring, 'publish') as publish:
            with self.SessionLocal.begin() as session:
                contract = self.new_contract(session)
                contracts.update_contract(session, self.actor(session), contract.id, remaining_amount=0)
                contracts.update_contract(session, self.actor(session), 100, is_signed=True, signed_at=self.date)
            self.assertEqual([c.args[0] for c in publish.call_args_list], ['contract.signed', 'contract.signed'])

    def test_failed_commit_does_not_publish(self):
        from sqlalchemy.exc import IntegrityError
        with patch.object(monitoring, 'publish') as publish:
            with self.assertRaises(IntegrityError):
                with self.SessionLocal.begin() as session:
                    employees.update_employee(session, self.actor(session), self.actor(session, 7), full_name='Changed')
                    session.add(Employee(full_name='Invalid'))
            publish.assert_not_called()


class SentryTests(unittest.TestCase):
    def test_disabled_without_dsn(self):
        with patch.object(monitoring, '_enabled', False), patch.object(monitoring, 'load_dotenv'), patch.dict(os.environ, {'SENTRY_DSN': ''}), patch.object(sentry_sdk, 'init') as initialize:
            monitoring.initialize()
            initialize.assert_not_called()

    def test_invalid_configuration_and_transport_do_not_break_application(self):
        with patch.object(monitoring, '_enabled', False), patch.object(monitoring, 'load_dotenv'), patch.dict(os.environ, {'SENTRY_DSN': 'secret'}), patch.object(sentry_sdk, 'init', side_effect=ValueError('secret')), redirect_stderr(io.StringIO()) as output:
            monitoring.initialize()
            self.assertNotIn('secret', output.getvalue())
        with patch.object(monitoring, '_enabled', True), patch.object(sentry_sdk, 'capture_event', side_effect=RuntimeError), patch.object(sentry_sdk, 'capture_exception', side_effect=RuntimeError), patch.object(sentry_sdk, 'flush', side_effect=RuntimeError):
            monitoring.publish('employee.created', 1, 2)
            monitoring.capture_exception(ValueError())
            monitoring.flush()

    def test_unexpected_exception_captured_once_and_flush_on_exit(self):
        failure = RuntimeError('secret')
        with patch.object(monitoring, 'initialize'), patch.object(monitoring, 'capture_exception') as capture, patch.object(monitoring, 'flush') as flush, patch.object(epicevents, '_main', side_effect=failure):
            with self.assertRaises(RuntimeError): epicevents.main()
            capture.assert_called_once_with(failure)
            flush.assert_called_once()
        with patch.object(monitoring, 'initialize'), patch.object(monitoring, 'capture_exception') as capture, patch.object(monitoring, 'flush'), patch.object(epicevents, '_main', side_effect=SystemExit(1)):
            with self.assertRaises(SystemExit): epicevents.main()
            capture.assert_not_called()

    def test_real_sdk_payload_is_private_without_network(self):
        envelopes = []
        class MemoryTransport(Transport):
            def capture_envelope(self, envelope): envelopes.append(envelope)

        with sentry_sdk.isolation_scope(), sentry_sdk.init(
            dsn='https://public@example.invalid/1', transport=MemoryTransport,
            default_integrations=False, auto_enabling_integrations=False,
            before_send=monitoring.before_send, include_local_variables=False,
            include_source_context=False,
        ), patch.object(monitoring, '_enabled', True):
            sentry_sdk.set_extra('password', 'PRIVATE_SECRET')
            sentry_sdk.set_user({'email': 'PRIVATE_EMAIL'})
            try:
                raise RuntimeError('PRIVATE_SQL_AND_PASSWORD')
            except RuntimeError as error:
                monitoring.capture_exception(error)
            monitoring.publish('employee.created', 1, 2)
            monitoring.flush()
        payloads = [item.payload.json for envelope in envelopes for item in envelope.items if item.type == 'event']
        self.assertEqual(len(payloads), 2)
        self.assertNotIn('PRIVATE', json.dumps(payloads))
        self.assertEqual(payloads[0]['exception']['values'][0]['type'], 'RuntimeError')
        self.assertEqual(payloads[1]['extra'], {'actor_id': 1, 'entity_id': 2})


if __name__ == '__main__': unittest.main()
