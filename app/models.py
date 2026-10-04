from datetime import datetime, timezone
from sqlalchemy import DateTime, Float, ForeignKey, Integer, String, Text
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship


class Base(DeclarativeBase):
    pass


class User(Base):
    __tablename__ = "users"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    email: Mapped[str] = mapped_column(String(120), unique=True, index=True)
    password_hash: Mapped[str] = mapped_column(String(256))
    mobile_number: Mapped[str] = mapped_column(String(32), default="")
    full_name: Mapped[str] = mapped_column(String(120), default="")
    company_name: Mapped[str] = mapped_column(String(120), default="")
    subscription_plan: Mapped[str] = mapped_column(String(32), default="free")  # free, pro, enterprise
    subscription_status: Mapped[str] = mapped_column(String(32), default="inactive")  # active, inactive, past_due
    monthly_amount_usd: Mapped[float] = mapped_column(Float, default=0.0)
    card_brand: Mapped[str] = mapped_column(String(32), default="")
    card_last4: Mapped[str] = mapped_column(String(8), default="")
    subscribed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    next_billing_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))

    invoices: Mapped[list["Invoice"]] = relationship(back_populates="user", cascade="all, delete-orphan", order_by="desc(Invoice.paid_at)")


class Invoice(Base):
    __tablename__ = "invoices"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"))
    invoice_number: Mapped[str] = mapped_column(String(64), unique=True)
    plan_name: Mapped[str] = mapped_column(String(64))
    amount_usd: Mapped[float] = mapped_column(Float)
    billing_cycle: Mapped[str] = mapped_column(String(32), default="Monthly")
    status: Mapped[str] = mapped_column(String(32), default="Paid")
    card_brand: Mapped[str] = mapped_column(String(32), default="Visa")
    card_last4: Mapped[str] = mapped_column(String(8), default="4242")
    paid_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))

    user: Mapped[User] = relationship(back_populates="invoices")


class Shipment(Base):
    __tablename__ = "shipments"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    reference: Mapped[str] = mapped_column(String(64), unique=True)
    commodity: Mapped[str] = mapped_column(String(120))
    spec_min_c: Mapped[float] = mapped_column(Float)
    spec_max_c: Mapped[float] = mapped_column(Float)
    bol_setpoint_c: Mapped[float | None] = mapped_column(Float, nullable=True)
    origin_pulp_c: Mapped[float | None] = mapped_column(Float, nullable=True)
    declared_value_usd: Mapped[float] = mapped_column(Float, default=0)
    carrier: Mapped[str] = mapped_column(String(120), default="")
    broker: Mapped[str] = mapped_column(String(120), default="")
    shipper: Mapped[str] = mapped_column(String(120), default="")
    receiver: Mapped[str] = mapped_column(String(120), default="")
    tender_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    claim_deadline_days: Mapped[int] = mapped_column(Integer, default=9)
    status: Mapped[str] = mapped_column(String(32), default="new")
    recovered_usd: Mapped[float] = mapped_column(Float, default=0)
    notes: Mapped[str] = mapped_column(Text, default="")
    notice: Mapped[str] = mapped_column(Text, default="")
    analysis_json: Mapped[str] = mapped_column(Text, default="")
    events: Mapped[list["Event"]] = relationship(back_populates="shipment", cascade="all, delete-orphan")
    documents: Mapped[list["Document"]] = relationship(back_populates="shipment", cascade="all, delete-orphan")


class Event(Base):
    __tablename__ = "events"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    shipment_id: Mapped[int] = mapped_column(ForeignKey("shipments.id"))
    at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    type: Mapped[str] = mapped_column(String(32))
    party: Mapped[str] = mapped_column(String(32), default="")
    temp_c: Mapped[float | None] = mapped_column(Float, nullable=True)
    note: Mapped[str] = mapped_column(Text, default="")
    shipment: Mapped[Shipment] = relationship(back_populates="events")


class Document(Base):
    __tablename__ = "documents"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    shipment_id: Mapped[int] = mapped_column(ForeignKey("shipments.id"))
    kind: Mapped[str] = mapped_column(String(32))
    filename: Mapped[str] = mapped_column(String(200))
    uploaded_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    shipment: Mapped[Shipment] = relationship(back_populates="documents")


class SupportEnquiry(Base):
    __tablename__ = "support_enquiries"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    ticket_id: Mapped[str] = mapped_column(String(32), unique=True, index=True)
    full_name: Mapped[str] = mapped_column(String(120), default="")
    email: Mapped[str] = mapped_column(String(120), index=True)
    mobile_number: Mapped[str] = mapped_column(String(32), default="")
    subject: Mapped[str] = mapped_column(String(200), default="")
    category: Mapped[str] = mapped_column(String(64), default="General Support")
    message: Mapped[str] = mapped_column(Text)
    contact_email_target: Mapped[str] = mapped_column(String(120), default="bjtmusic12@gmail.com")
    status: Mapped[str] = mapped_column(String(32), default="Open")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))

