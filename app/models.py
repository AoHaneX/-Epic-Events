"""Modèles SQLAlchemy du CRM Epic Events."""

from __future__ import annotations

from datetime import datetime
from decimal import Decimal

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    DateTime,
    ForeignKey,
    Index,
    Numeric,
    String,
    Text,
    func,
    text,
)
from sqlalchemy.dialects.mysql import BIGINT, INTEGER
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base


MYSQL_TABLE_OPTIONS = {
    "mysql_engine": "InnoDB",
    "mysql_charset": "utf8mb4",
    "mysql_collate": "utf8mb4_0900_ai_ci",
}

MANAGEMENT_ROLE = "MANAGEMENT"
SALES_ROLE = "SALES"
SUPPORT_ROLE = "SUPPORT"
ROLE_CODES = (MANAGEMENT_ROLE, SALES_ROLE, SUPPORT_ROLE)


class Employee(Base):
    """Collaborateur : données communes aux trois départements.

    Héritage par tables jointes : chaque collaborateur a une ligne ici et une
    ligne dans la table de sa spécialité (managers, sales_employees,
    support_employees). La colonne ``role`` indique laquelle.
    """

    __tablename__ = "employees"
    __table_args__ = (
        CheckConstraint(
            "role IN ('MANAGEMENT', 'SALES', 'SUPPORT')",
            name="chk_employees_role",
        ),
        Index("idx_employees_role", "role"),
        MYSQL_TABLE_OPTIONS,
    )

    id: Mapped[int] = mapped_column(
        BIGINT(unsigned=True), primary_key=True, autoincrement=True
    )
    full_name: Mapped[str] = mapped_column(String(150), nullable=False)
    email: Mapped[str] = mapped_column(String(254), unique=True, nullable=False)
    password_hash: Mapped[str] = mapped_column(String(255), nullable=False)
    role: Mapped[str] = mapped_column(String(20), nullable=False)
    is_active: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=True, server_default=text("1")
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime, nullable=False, server_default=func.current_timestamp()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime,
        nullable=False,
        server_default=func.current_timestamp(),
        onupdate=func.current_timestamp(),
    )

    __mapper_args__ = {"polymorphic_on": "role", "polymorphic_abstract": True}


def _specialization_id() -> Mapped[int]:
    """Clé primaire d'une spécialité, qui est aussi la clé du collaborateur."""
    return mapped_column(
        BIGINT(unsigned=True),
        ForeignKey("employees.id", ondelete="CASCADE", onupdate="RESTRICT"),
        primary_key=True,
    )


class Manager(Employee):
    """Membre du département gestion."""

    __tablename__ = "managers"
    __table_args__ = MYSQL_TABLE_OPTIONS
    __mapper_args__ = {"polymorphic_identity": MANAGEMENT_ROLE}

    id: Mapped[int] = _specialization_id()


class SalesEmployee(Employee):
    """Commercial : il suit des clients."""

    __tablename__ = "sales_employees"
    __table_args__ = MYSQL_TABLE_OPTIONS
    __mapper_args__ = {"polymorphic_identity": SALES_ROLE}

    id: Mapped[int] = _specialization_id()
    clients: Mapped[list[Client]] = relationship(back_populates="sales_contact")


class SupportEmployee(Employee):
    """Membre du support : il organise des événements."""

    __tablename__ = "support_employees"
    __table_args__ = MYSQL_TABLE_OPTIONS
    __mapper_args__ = {"polymorphic_identity": SUPPORT_ROLE}

    id: Mapped[int] = _specialization_id()
    events: Mapped[list[Event]] = relationship(back_populates="support_contact")


EMPLOYEE_CLASSES: dict[str, type[Employee]] = {
    MANAGEMENT_ROLE: Manager,
    SALES_ROLE: SalesEmployee,
    SUPPORT_ROLE: SupportEmployee,
}


class Client(Base):
    __tablename__ = "clients"
    __table_args__ = (
        Index("idx_clients_sales_contact_id", "sales_contact_id"),
        {
            "mysql_engine": "InnoDB",
            "mysql_charset": "utf8mb4",
            "mysql_collate": "utf8mb4_0900_ai_ci",
        },
    )

    id: Mapped[int] = mapped_column(
        BIGINT(unsigned=True), primary_key=True, autoincrement=True
    )
    full_name: Mapped[str] = mapped_column(String(150), nullable=False)
    email: Mapped[str] = mapped_column(String(254), unique=True, nullable=False)
    phone: Mapped[str] = mapped_column(String(32), nullable=False)
    company_name: Mapped[str] = mapped_column(String(200), nullable=False)
    sales_contact_id: Mapped[int] = mapped_column(
        BIGINT(unsigned=True),
        ForeignKey("sales_employees.id", ondelete="RESTRICT", onupdate="RESTRICT"),
        nullable=False,
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime, nullable=False, server_default=func.current_timestamp()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime,
        nullable=False,
        server_default=func.current_timestamp(),
        onupdate=func.current_timestamp(),
    )
    last_contact_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)

    sales_contact: Mapped[SalesEmployee] = relationship(
        back_populates="clients",
        foreign_keys=[sales_contact_id],
    )
    contracts: Mapped[list[Contract]] = relationship(back_populates="client")


class Contract(Base):
    __tablename__ = "contracts"
    __table_args__ = (
        CheckConstraint(
            "total_amount >= 0 "
            "AND remaining_amount >= 0 "
            "AND remaining_amount <= total_amount",
            name="chk_contracts_amounts",
        ),
        CheckConstraint(
            "(is_signed = 0 AND signed_at IS NULL) "
            "OR (is_signed = 1 AND signed_at IS NOT NULL)",
            name="chk_contracts_signature",
        ),
        Index("idx_contracts_client_id", "client_id"),
        Index("idx_contracts_status", "is_signed", "remaining_amount"),
        {
            "mysql_engine": "InnoDB",
            "mysql_charset": "utf8mb4",
            "mysql_collate": "utf8mb4_0900_ai_ci",
        },
    )

    id: Mapped[int] = mapped_column(
        BIGINT(unsigned=True), primary_key=True, autoincrement=True
    )
    client_id: Mapped[int] = mapped_column(
        BIGINT(unsigned=True),
        ForeignKey("clients.id", ondelete="RESTRICT", onupdate="RESTRICT"),
        nullable=False,
    )
    total_amount: Mapped[Decimal] = mapped_column(Numeric(12, 2), nullable=False)
    remaining_amount: Mapped[Decimal] = mapped_column(Numeric(12, 2), nullable=False)
    is_signed: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False, server_default=text("0")
    )
    signed_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime, nullable=False, server_default=func.current_timestamp()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime,
        nullable=False,
        server_default=func.current_timestamp(),
        onupdate=func.current_timestamp(),
    )

    client: Mapped[Client] = relationship(back_populates="contracts")
    event: Mapped[Event | None] = relationship(back_populates="contract", uselist=False)


class Event(Base):
    __tablename__ = "events"
    __table_args__ = (
        CheckConstraint("end_at > start_at", name="chk_events_dates"),
        CheckConstraint(
            "contact_email IS NOT NULL OR contact_phone IS NOT NULL",
            name="chk_events_contact",
        ),
        Index("idx_events_support_contact_id", "support_contact_id"),
        Index("idx_events_start_at", "start_at"),
        {
            "mysql_engine": "InnoDB",
            "mysql_charset": "utf8mb4",
            "mysql_collate": "utf8mb4_0900_ai_ci",
        },
    )

    id: Mapped[int] = mapped_column(
        BIGINT(unsigned=True), primary_key=True, autoincrement=True
    )
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    contract_id: Mapped[int] = mapped_column(
        BIGINT(unsigned=True),
        ForeignKey("contracts.id", ondelete="RESTRICT", onupdate="RESTRICT"),
        unique=True,
        nullable=False,
    )
    support_contact_id: Mapped[int | None] = mapped_column(
        BIGINT(unsigned=True),
        ForeignKey("support_employees.id", ondelete="SET NULL", onupdate="RESTRICT"),
        nullable=True,
    )
    contact_name: Mapped[str | None] = mapped_column(String(150), nullable=True)
    contact_email: Mapped[str | None] = mapped_column(String(254), nullable=True)
    contact_phone: Mapped[str | None] = mapped_column(String(32), nullable=True)
    start_at: Mapped[datetime] = mapped_column(DateTime, nullable=False)
    end_at: Mapped[datetime] = mapped_column(DateTime, nullable=False)
    location: Mapped[str] = mapped_column(String(500), nullable=False)
    attendees_count: Mapped[int] = mapped_column(INTEGER(unsigned=True), nullable=False)
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime, nullable=False, server_default=func.current_timestamp()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime,
        nullable=False,
        server_default=func.current_timestamp(),
        onupdate=func.current_timestamp(),
    )

    contract: Mapped[Contract] = relationship(back_populates="event")
    support_contact: Mapped[SupportEmployee | None] = relationship(
        back_populates="events",
        foreign_keys=[support_contact_id],
    )
