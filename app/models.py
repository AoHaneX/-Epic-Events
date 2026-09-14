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


class Role(Base):
    """Rôle applicatif attribué à un ou plusieurs collaborateurs."""

    __tablename__ = "roles"
    __table_args__ = {
        "mysql_engine": "InnoDB",
        "mysql_charset": "utf8mb4",
        "mysql_collate": "utf8mb4_0900_ai_ci",
    }

    id: Mapped[int] = mapped_column(
        BIGINT(unsigned=True), primary_key=True, autoincrement=True
    )
    code: Mapped[str] = mapped_column(String(20), unique=True, nullable=False)
    name: Mapped[str] = mapped_column(String(100), unique=True, nullable=False)

    employees: Mapped[list[Employee]] = relationship(back_populates="role")


class Employee(Base):
    __tablename__ = "employees"
    __table_args__ = (
        Index("idx_employees_role_id", "role_id"),
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
    password_hash: Mapped[str] = mapped_column(String(255), nullable=False)
    role_id: Mapped[int] = mapped_column(
        BIGINT(unsigned=True),
        ForeignKey(
            "roles.id",
            name="fk_employees_role",
            ondelete="RESTRICT",
            onupdate="RESTRICT",
        ),
        nullable=False,
    )
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

    role: Mapped[Role] = relationship(back_populates="employees", lazy="joined")
    sales_clients: Mapped[list[Client]] = relationship(
        back_populates="sales_contact",
        foreign_keys="Client.sales_contact_id",
    )
    supported_events: Mapped[list[Event]] = relationship(
        back_populates="support_contact",
        foreign_keys="Event.support_contact_id",
    )


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
        ForeignKey("employees.id", ondelete="RESTRICT", onupdate="RESTRICT"),
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

    sales_contact: Mapped[Employee] = relationship(
        back_populates="sales_clients",
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
        ForeignKey("employees.id", ondelete="SET NULL", onupdate="RESTRICT"),
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
    support_contact: Mapped[Employee | None] = relationship(
        back_populates="supported_events",
        foreign_keys=[support_contact_id],
    )
