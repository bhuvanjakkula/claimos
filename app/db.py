import json
from datetime import datetime, timedelta, timezone
from pathlib import Path
from sqlalchemy import create_engine, select
from sqlalchemy.orm import sessionmaker
from app.models import Base, Document, Event, Shipment, User, Invoice, SupportEnquiry
from app.engine import attribute, draft_notice
from app.auth import hash_password

import os
import shutil

DATABASE_URL = os.environ.get("DATABASE_URL")
if DATABASE_URL:
    if DATABASE_URL.startswith("postgres://"):
        DATABASE_URL = DATABASE_URL.replace("postgres://", "postgresql://", 1)
    engine = create_engine(DATABASE_URL)
else:
    default_db = Path(__file__).resolve().parent.parent / "claimos.db"
    if os.environ.get("VERCEL"):
        DB_PATH = Path("/tmp") / "claimos.db"
        if not DB_PATH.exists() and default_db.exists():
            try:
                shutil.copyfile(default_db, DB_PATH)
            except Exception:
                pass
    else:
        DB_PATH = default_db
    engine = create_engine(f"sqlite:///{DB_PATH}", connect_args={"check_same_thread": False})
SessionLocal = sessionmaker(bind=engine, expire_on_commit=False)


def event_dicts(shipment: Shipment) -> list[dict]:
    rows = sorted(shipment.events, key=lambda e: e.at)
    return [{
        "at": e.at.isoformat(),
        "type": e.type,
        "party": e.party,
        "temp_c": e.temp_c,
        "note": e.note,
    } for e in rows]


def recompute(shipment: Shipment, now=None) -> dict:
    payload = {
        "reference": shipment.reference,
        "commodity": shipment.commodity,
        "spec_min_c": shipment.spec_min_c,
        "spec_max_c": shipment.spec_max_c,
        "bol_setpoint_c": shipment.bol_setpoint_c,
        "origin_pulp_c": shipment.origin_pulp_c,
        "declared_value_usd": shipment.declared_value_usd,
        "carrier": shipment.carrier,
        "tender_at": shipment.tender_at.isoformat() if shipment.tender_at else "",
        "claim_deadline_days": shipment.claim_deadline_days,
        "notice_sent": shipment.status in {"notice_sent", "recovered", "denied"},
        "documents": [d.kind for d in shipment.documents],
        "now": now or datetime.now(timezone.utc),
    }
    analysis = attribute(payload, event_dicts(shipment))
    shipment.analysis_json = json.dumps(analysis)
    if not shipment.notice:
        shipment.notice = draft_notice(payload, analysis)
    return analysis


OWNER_EMAIL = "bhuvanjakkula@gmail.com"


def seed_users(db):
    owner = db.scalar(select(User).where(User.email == OWNER_EMAIL.lower()))
    if not owner:
        owner_user = User(
            email=OWNER_EMAIL.lower(),
            password_hash=hash_password("owner-keyless-authenticated"),
            mobile_number="+1 (800) 555-0199",
            full_name="Platform Owner",
            company_name="ClaimOS Enterprise",
            subscription_plan="enterprise",
            subscription_status="active",
            monthly_amount_usd=0.0,
            subscribed_at=datetime.now(timezone.utc),
        )
        db.add(owner_user)
        db.commit()
    else:
        owner.subscription_status = "active"
        owner.subscription_plan = "enterprise"
        db.commit()

    # Ensure demo user is purged
    demo_user = db.scalar(select(User).where(User.email == "demo@coldchain.com"))
    if demo_user:
        db.delete(demo_user)
        db.commit()


def seed_support(db):
    if not db.scalar(select(SupportEnquiry.id).limit(1)):
        enq = SupportEnquiry(
            ticket_id="TKT-2026-8812",
            full_name="Marcus Vance",
            email="marcus.vance@freightops.com",
            mobile_number="+1 (555) 948-1120",
            subject="Urgent: Excursion Dispute Notice for SHP-88421",
            category="Carrier Claim Escalation",
            message="We received an objection from Northline Reefer asserting clean dock delivery temperature of 6.4C. We need urgent ClaimOS Carmack 48-hour reefer download demand pack to counter their defense.",
            contact_email_target="bjtmusic12@gmail.com",
            status="Replied",
            created_at=datetime.now(timezone.utc) - timedelta(days=1),
        )
        db.add(enq)
        db.commit()


def init_db():
    Base.metadata.create_all(engine)
    with SessionLocal() as db:
        seed_users(db)
        seed_support(db)
        if db.scalar(select(Shipment.id).limit(1)):
            return
        seed(db)
        db.commit()



def add_event(db, shipment, at, type_, party, temp, note):
    db.add(Event(shipment=shipment, at=at, type=type_, party=party, temp_c=temp, note=note))


def seed(db):
    now = datetime.now(timezone.utc)
    specs = [
        ("SHP-88421", "refrigerated biologics", 2, 8, 5, 4.6, 186000, "Northline Reefer", "Harbor Brokerage", "Helix Bio", "City Hospital Pharmacy", now - timedelta(days=3), "new", 0, ["bol"]),
        ("SHP-1002", "seafood", 0, 4, 2, 11, 42000, "Coastal Cold", "", "Pier Foods", "Metro Market", now - timedelta(days=40), "written_off", 0, ["bol", "pod"]),
        ("SHP-1003", "vaccines", 2, 8, None, 4.2, 310000, "Northline Reefer", "Harbor Brokerage", "Helix Bio", "Regional Clinic", now - timedelta(days=20), "denied", 0, ["logger"]),
        ("SHP-1004", "meal kits", 0, 5, 3, 3.1, 18500, "City Van", "", "Kitchen Co", "Home Drop", now - timedelta(days=15), "written_off", 0, ["bol", "logger", "pod"]),
        ("SHP-1005", "boxed meat", 0, 4, 2, 1.8, 76000, "Northline Reefer", "", "Packer Inc", "Retail DC", now - timedelta(days=8), "new", 0, ["bol"]),
        ("SHP-1006", "produce", 0, 6, 3, 2.4, 54000, "Green Mile", "", "Valley Growers", "Store 14", now - timedelta(days=30), "recovered", 40000, ["bol", "logger", "pod"]),
    ]
    for ref, commodity, lo, hi, setp, origin, value, carrier, broker, shipper, receiver, tender, status, recovered, docs in specs:
        s = Shipment(
            reference=ref, commodity=commodity, spec_min_c=lo, spec_max_c=hi,
            bol_setpoint_c=setp, origin_pulp_c=origin, declared_value_usd=value,
            carrier=carrier, broker=broker, shipper=shipper, receiver=receiver,
            tender_at=tender, status=status, recovered_usd=recovered,
        )
        db.add(s)
        db.flush()
        for kind in docs:
            db.add(Document(shipment=s, kind=kind, filename=f"{ref}-{kind}.pdf", uploaded_at=tender))
        _seed_events(db, s, tender)
        recompute(s, now=now)


def _seed_events(db, s: Shipment, tender):
    ref = s.reference
    if ref == "SHP-88421":
        rows = [
            (tender, "tender", "shipper", 4.6, "pulp temp recorded"),
            (tender + timedelta(minutes=30), "depart", "carrier", 4.8, "set point confirmed"),
            (tender + timedelta(hours=8), "reading", "carrier", 6.1, "in range"),
            (tender + timedelta(hours=12, minutes=30), "reading", "carrier", 11.4, "reefer alarm"),
            (tender + timedelta(hours=15), "reading", "carrier", 12.8, "still above spec"),
            (tender + timedelta(hours=19), "handoff", "broker", None, "relay yard, no logger download"),
            (tender + timedelta(hours=26), "reading", "carrier", 7.2, "recovered before delivery"),
            (tender + timedelta(hours=27, minutes=20), "delivery", "receiver", 6.4, "dock temp in range; quarantined after logger review"),
        ]
    elif ref == "SHP-1002":
        rows = [
            (tender, "tender", "shipper", 11.0, "warm at origin"),
            (tender + timedelta(hours=1), "depart", "carrier", 10.5, "loaded warm"),
            (tender + timedelta(hours=6), "delivery", "receiver", 9.0, "rejected at dock"),
        ]
    elif ref == "SHP-1003":
        rows = [
            (tender, "tender", "shipper", 4.2, "origin ok, no setpoint on BOL"),
            (tender + timedelta(hours=2), "depart", "carrier", 4.4, "departed"),
            (tender + timedelta(hours=10), "reading", "carrier", 13.0, "excursion, no BOL setpoint"),
            (tender + timedelta(hours=18), "delivery", "receiver", 9.5, "still high"),
        ]
    elif ref == "SHP-1004":
        rows = [
            (tender, "tender", "shipper", 3.1, "in spec"),
            (tender + timedelta(hours=2), "depart", "carrier", 3.0, "in spec"),
            (tender + timedelta(hours=5), "reading", "carrier", 3.4, "in spec"),
            (tender + timedelta(hours=8), "delivery", "receiver", 3.6, "accepted"),
        ]
    elif ref == "SHP-1005":
        rows = [
            (tender, "tender", "shipper", 1.8, "origin ok"),
            (tender + timedelta(hours=1), "depart", "carrier", 2.0, "departed"),
            (tender + timedelta(hours=7), "alarm", "carrier", 9.4, "compressor fault"),
            (tender + timedelta(hours=14), "delivery", "receiver", 8.1, "rejected"),
        ]
    else:
        rows = [
            (tender, "tender", "shipper", 2.4, "origin ok"),
            (tender + timedelta(hours=1), "depart", "carrier", 2.6, "departed"),
            (tender + timedelta(hours=9), "reading", "carrier", 10.2, "excursion"),
            (tender + timedelta(hours=16), "delivery", "receiver", 7.5, "rejected then partial recovery"),
        ]
    for at, type_, party, temp, note in rows:
        add_event(db, s, at, type_, party, temp, note)
