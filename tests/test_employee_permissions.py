import os
import unittest
from unittest.mock import Mock, patch

from sqlalchemy.orm import Session


# Imports require database settings, but these tests must not read local secrets.
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
    from app.models import Employee, Role
    from app.permissions import AuthorizationError
    from app.security import hash_password, verify_password
    from app.services.employees import change_password


class ChangePasswordPermissionsTests(unittest.TestCase):
    def setUp(self) -> None:
        self.old_password = "Initial-password-2026"
        self.new_password = "Updated-password-2026"
        self.original_hash = hash_password(self.old_password)

    def employee(
        self,
        employee_id: int = 1,
        role_code: str = "SALES",
        active: bool = True,
    ) -> Employee:
        return Employee(
            id=employee_id,
            full_name="Test Employee",
            email=f"employee{employee_id}@example.invalid",
            password_hash=self.original_hash,
            role=Role(code=role_code, name=role_code),
            is_active=active,
        )

    def assert_change_allowed(self, actor: Employee, target: Employee) -> None:
        session = Mock(spec=Session)

        change_password(session, actor, target, self.new_password)

        self.assertNotEqual(target.password_hash, self.original_hash)
        self.assertNotEqual(target.password_hash, self.new_password)
        self.assertTrue(verify_password(target.password_hash, self.new_password)[0])
        self.assertFalse(verify_password(target.password_hash, self.old_password)[0])
        session.flush.assert_called_once_with()

    def assert_change_denied(self, actor: Employee, target: Employee) -> None:
        session = Mock(spec=Session)
        original_hash = target.password_hash

        with self.assertRaises(AuthorizationError):
            change_password(session, actor, target, self.new_password)

        self.assertEqual(target.password_hash, original_hash)
        self.assertEqual(session.mock_calls, [])

    def test_active_employee_can_change_own_password(self) -> None:
        for role_code in ("MANAGEMENT", "SALES", "SUPPORT"):
            with self.subTest(role=role_code):
                employee = self.employee(role_code=role_code)
                self.assert_change_allowed(employee, employee)

    def test_disabled_employee_cannot_change_own_password(self) -> None:
        for role_code in ("MANAGEMENT", "SALES", "SUPPORT"):
            with self.subTest(role=role_code):
                employee = self.employee(role_code=role_code, active=False)
                self.assert_change_denied(employee, employee)

    def test_active_manager_can_change_another_password(self) -> None:
        for target_active in (True, False):
            with self.subTest(target_active=target_active):
                manager = self.employee(role_code="MANAGEMENT")
                target = self.employee(employee_id=2, active=target_active)
                self.assert_change_allowed(manager, target)

    def test_disabled_manager_cannot_change_another_password(self) -> None:
        manager = self.employee(role_code="MANAGEMENT", active=False)
        target = self.employee(employee_id=2)
        self.assert_change_denied(manager, target)

    def test_non_manager_cannot_change_another_password(self) -> None:
        for role_code in ("SALES", "SUPPORT"):
            with self.subTest(role=role_code):
                actor = self.employee(role_code=role_code)
                target = self.employee(employee_id=2)
                self.assert_change_denied(actor, target)


if __name__ == "__main__":
    unittest.main()
