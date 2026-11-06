from sqlalchemy import select

from test_business_write import BusinessWriteFixture
from app.main import initialize_database
from app.models import Role
from app.services.employees import create_initial_manager


class DatabaseInitializationTests(BusinessWriteFixture):
    def seed_database(self):
        pass

    def test_empty_database_can_bootstrap_manager(self):
        self.engine.dispose()
        initialize_database(self.engine)
        with self.SessionLocal.begin() as session:
            self.assertEqual(set(session.scalars(select(Role.code))),
                             {"MANAGEMENT", "SALES", "SUPPORT"})
            manager = create_initial_manager(
                session, full_name="Initial manager", email="manager@example.invalid",
                password="Strong-password-2026")
            self.assertEqual(manager.role.code, "MANAGEMENT")

    def test_repeated_initialization_preserves_existing_roles(self):
        with self.SessionLocal.begin() as session:
            session.add(Role(id=42, code="MANAGEMENT", name="Existing management"))
        initialize_database(self.engine)
        initialize_database(self.engine)
        with self.SessionLocal() as session:
            roles = list(session.scalars(select(Role)))
            self.assertEqual(len(roles), 3)
            manager_role = session.get(Role, 42)
            self.assertEqual(manager_role.code, "MANAGEMENT")
            self.assertEqual(manager_role.name, "Existing management")
