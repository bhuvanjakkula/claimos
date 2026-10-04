from datetime import datetime, timedelta, timezone
from app.engine import attribute, Shipment, load_logger, analyze

NOW = datetime(2026, 10, 4, tzinfo=timezone.utc)

def ship(**kw):
    base = dict(spec_min_c=2, spec_max_c=8, bol_setpoint_c=5, origin_pulp_c=4.6,
                declared_value_usd=1000, carrier="C", reference="X", tender_at="2026-09-28T06:10:00+00:00",
                claim_deadline_days=9, notice_sent=False, documents=["bol", "logger", "pod"], now=NOW)
    base.update(kw)
    return base

def test_delivery_in_range_keeps_excursion():
    events = [
        {"at": "2026-09-28T06:10:00+00:00", "type": "tender", "party": "shipper", "temp_c": 4.6},
        {"at": "2026-09-28T06:40:00+00:00", "type": "depart", "party": "carrier", "temp_c": 4.8},
        {"at": "2026-09-28T18:40:00+00:00", "type": "reading", "party": "carrier", "temp_c": 12.8},
        {"at": "2026-09-29T09:30:00+00:00", "type": "delivery", "party": "receiver", "temp_c": 6.4},
    ]
    a = attribute(ship(), events)
    assert a["attribution"] == "carrier"
    assert a["excursions"]
    assert a["dock_clean_trap"] is True

def test_missing_setpoint_disputed():
    events = [
        {"at": "2026-09-28T06:10:00+00:00", "type": "tender", "party": "shipper", "temp_c": 4.2},
        {"at": "2026-09-28T12:00:00+00:00", "type": "reading", "party": "carrier", "temp_c": 13},
    ]
    a = attribute(ship(bol_setpoint_c=None), events)
    assert a["attribution"] == "disputed"

def test_warm_origin_shipper():
    events = [{"at": "2026-09-28T06:10:00+00:00", "type": "tender", "party": "shipper", "temp_c": 11}]
    a = attribute(ship(origin_pulp_c=11, spec_min_c=0, spec_max_c=4), events)
    assert a["attribution"] == "shipper"

def test_clean_load_no_claim():
    events = [
        {"at": "2026-09-28T06:10:00+00:00", "type": "tender", "party": "shipper", "temp_c": 4},
        {"at": "2026-09-28T08:00:00+00:00", "type": "delivery", "party": "receiver", "temp_c": 5},
    ]
    a = attribute(ship(), events)
    assert a["attribution"] == "no_claim"

def test_long_gap_and_null_handoff():
    events = [
        {"at": "2026-09-28T06:00:00+00:00", "type": "reading", "party": "carrier", "temp_c": 4},
        {"at": "2026-09-28T12:30:00+00:00", "type": "reading", "party": "carrier", "temp_c": 5},
        {"at": "2026-09-28T13:00:00+00:00", "type": "handoff", "party": "broker", "temp_c": None, "note": "no download"},
    ]
    a = attribute(ship(), events)
    kinds = {g["kind"] for g in a["gaps"]}
    assert "long_gap" in kinds
    assert "null_temp" in kinds

def test_deadline_risk():
    tender = NOW - timedelta(days=8)
    events = [
        {"at": tender.isoformat(), "type": "tender", "party": "shipper", "temp_c": 4},
        {"at": (tender + timedelta(hours=5)).isoformat(), "type": "reading", "party": "carrier", "temp_c": 12},
    ]
    a = attribute(ship(tender_at=tender.isoformat(), notice_sent=False), events)
    assert a["deadline_risk"] is True


# --- Imported MVP Test Suite Tests ---
def mvp_shipment(**kw):
    d = dict(
        shipment_id="SHP-88421",
        commodity="Biologics",
        declared_value=186000,
        spec_min_c=2,
        spec_max_c=8,
        origin_temp_c=4.6,
        bol_setpoint_c=5,
        departure=datetime(2026, 9, 28, 17, tzinfo=timezone.utc),
        delivery=datetime(2026, 9, 29, 12, tzinfo=timezone.utc),
        carrier="Carrier"
    )
    d.update(kw)
    return Shipment(**d)

def test_sample_attributes_carrier():
    r = analyze(mvp_shipment(), load_logger("sample_data/SHP-88421_logger.csv"))
    assert r["attribution"] == "Carrier"
    assert r["peak_c"] == 12.8

def test_missing_setpoint_is_disputed():
    r = analyze(mvp_shipment(bol_setpoint_c=None), load_logger("sample_data/SHP-88421_logger.csv"))
    assert r["attribution"] == "Disputed"

def test_warm_origin_attributes_shipper():
    r = analyze(mvp_shipment(origin_temp_c=9.0), load_logger("sample_data/SHP-88421_logger.csv"))
    assert r["attribution"] == "Shipper"
