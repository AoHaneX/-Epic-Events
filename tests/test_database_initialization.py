from sqlalchemy import inspect

from test_business_write import BusinessWriteFixture
from app.main import initialize_database
from app.models import Manager
from app.services.employees import create_initial_manager


class DatabaseInitializationTests(BusinessWriteFixture):
    def seed_database(self):
        pass

    def test_empty_database_can_bootstrap_manager(self):
        initialize_database(self.engine)
        tables = set(inspect(self.engine).get_table_names())
        self.assertEqual(tables, {
            "employees", "managers", "sales_employees", "support_employees",
            "clients", "contracts", "events",
        })
        with self.SessionLocal.begin() as session:
            manager = create_initial_manager(
                session, full_name="Initial manager", email="manager@example.invalid",
                password="Strong-password-2026")
            self.assertIsInstance(manager, Manager)
            self.assertEqual(manager.role, "MANAGEMENT")

    def test_repeated_initialization_preserves_existing_data(self):
        with self.SessionLocal.begin() as session:
            create_initial_manager(session, full_name="Existing", email="existing@example.invalid",
                                   password="Strong-password-2026")
        initialize_database(self.engine)
        initialize_database(self.engine)
        with self.SessionLocal() as session:
            managers = list(session.query(Manager))
            self.assertEqual([manager.full_name for manager in managers], ["Existing"])
