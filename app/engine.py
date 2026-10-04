"""
ClaimOS Unified Engine
Reconstructs excursions, flags evidence gaps (including dock-clean trap),
assigns preliminary liability attribution, and computes Carmack deadlines.
Supports both ClaimOS and imported MVP APIs without external dependencies.
"""

from __future__ import annotations
import csv
import io
from dataclasses import dataclass, asdict
from datetime import datetime, timedelta, timezone
from typing import Optional, Any, Union


def parse_dt(val: Any) -> datetime:
    """Robust timezone-aware datetime parser."""
    if isinstance(val, datetime):
        if val.tzinfo is None:
            return val.replace(tzinfo=timezone.utc)
        return val.astimezone(timezone.utc)
    if isinstance(val, str):
        val_clean = val.strip().replace("Z", "+00:00")
        # Handle space separated formats e.g. '2026-09-28 16:30'
        if " " in val_clean and "T" not in val_clean:
            val_clean = val_clean.replace(" ", "T")
        # Handle missing seconds
        parts = val_clean.split("T")
        if len(parts) == 2 and len(parts[1].split(":")) == 2:
            val_clean = f"{val_clean}:00"
        dt = datetime.fromisoformat(val_clean)
        if dt.tzinfo is None:
            return dt.replace(tzinfo=timezone.utc)
        return dt.astimezone(timezone.utc)
    raise ValueError(f"Cannot parse datetime: {val}")


@dataclass
class Shipment:
    shipment_id: str
    commodity: str
    declared_value: float
    spec_min_c: float
    spec_max_c: float
    origin_temp_c: Optional[float]
    bol_setpoint_c: Optional[float]
    departure: datetime
    delivery: datetime
    carrier: str
    notice_deadline: Optional[datetime] = None


class ReadingsRow:
    __slots__ = ("timestamp", "temperature_c")

    def __init__(self, ts: datetime, temp: float):
        self.timestamp = ts
        self.temperature_c = temp

    def __getitem__(self, item):
        return getattr(self, item)


class ReadingsSeries:
    def __init__(self, values: list):
        self._values = values

    def min(self):
        return min(self._values) if self._values else None

    def max(self):
        return max(self._values) if self._values else None

    def __iter__(self):
        return iter(self._values)

    def __len__(self):
        return len(self._values)


class ReadingsTable:
    """Lightweight DataFrame-like container using Python stdlib."""
    def __init__(self, rows: list[ReadingsRow]):
        self._rows = sorted(rows, key=lambda r: r.timestamp)

    @property
    def empty(self) -> bool:
        return len(self._rows) == 0

    def __len__(self) -> int:
        return len(self._rows)

    def __iter__(self):
        return iter(self._rows)

    @property
    def temperature_c(self) -> ReadingsSeries:
        return ReadingsSeries([r.temperature_c for r in self._rows])

    @property
    def timestamp(self) -> ReadingsSeries:
        return ReadingsSeries([r.timestamp for r in self._rows])

    @property
    def iloc(self):
        class ILocIndexer:
            def __init__(self, parent):
                self._p = parent

            def __getitem__(self, idx):
                return self._p._rows[idx]
        return ILocIndexer(self)

    def filter(self, predicate) -> ReadingsTable:
        return ReadingsTable([r for r in self._rows if predicate(r)])


def load_logger(path_or_content: Union[str, io.StringIO]) -> ReadingsTable:
    """Loads logger CSV with timestamp and temperature_c (or temp_c/temp)."""
    rows = []
    content = ""
    if isinstance(path_or_content, io.StringIO):
        content = path_or_content.getvalue()
    elif "\n" in path_or_content or "\r" in path_or_content:
        content = path_or_content
    else:
        with open(path_or_content, "r", encoding="utf-8", errors="replace") as f:
            content = f.read()

    reader = csv.DictReader(io.StringIO(content))

    # Normalize column names
    field_map = {}
    if reader.fieldnames:
        for f in reader.fieldnames:
            clean = f.strip().lower()
            if clean in ("timestamp", "time", "date", "at"):
                field_map["timestamp"] = f
            elif clean in ("temperature_c", "temp_c", "temp", "temperature", "deg_c"):
                field_map["temperature_c"] = f

    if "timestamp" not in field_map or "temperature_c" not in field_map:
        raise ValueError("Logger CSV missing required columns: timestamp, temperature_c")

    for line in reader:
        ts_val = line.get(field_map["timestamp"])
        temp_val = line.get(field_map["temperature_c"])
        if ts_val and temp_val is not None and temp_val.strip() != "":
            try:
                ts = parse_dt(ts_val)
                temp = float(temp_val.strip())
                rows.append(ReadingsRow(ts, temp))
            except (ValueError, TypeError):
                continue

    return ReadingsTable(rows)


def parse_logger_events(
    csv_text_or_file: str,
    departure: Optional[datetime] = None,
    delivery: Optional[datetime] = None
) -> list[dict]:
    """
    Universal CSV parser. Supports:
    1. 2-col CSV: timestamp, temperature_c
    2. 5-col CSV: timestamp, temp_c, party, type, note
    Auto-assigns party & event type relative to departure/delivery windows.
    """
    reader = csv.DictReader(io.StringIO(csv_text_or_file.strip()))
    if not reader.fieldnames:
        return []

    norm_fields = {f.strip().lower(): f for f in reader.fieldnames if f}
    ts_key = next((norm_fields[k] for k in ["timestamp", "time", "at"] if k in norm_fields), None)
    temp_key = next((norm_fields[k] for k in ["temperature_c", "temp_c", "temp", "temperature"] if k in norm_fields), None)
    party_key = norm_fields.get("party")
    type_key = norm_fields.get("type")
    note_key = norm_fields.get("note")

    events = []
    dep_dt = parse_dt(departure) if departure else None
    del_dt = parse_dt(delivery) if delivery else None

    for r in reader:
        if not ts_key or not r.get(ts_key):
            continue
        try:
            at_dt = parse_dt(r[ts_key])
        except Exception:
            continue

        raw_temp = r.get(temp_key) if temp_key else None
        temp_val = float(raw_temp) if raw_temp and raw_temp.strip().lower() not in ("none", "null", "") else None

        # Auto-infer party and type if not explicitly provided
        if party_key and r.get(party_key):
            party = r[party_key].strip().lower()
        else:
            if dep_dt and at_dt < dep_dt:
                party = "shipper"
            elif del_dt and at_dt >= del_dt:
                party = "receiver"
            else:
                party = "carrier"

        if type_key and r.get(type_key):
            ev_type = r[type_key].strip().lower()
        else:
            if dep_dt and abs((at_dt - dep_dt).total_seconds()) < 60:
                ev_type = "depart"
            elif del_dt and abs((at_dt - del_dt).total_seconds()) < 60:
                ev_type = "delivery"
            else:
                ev_type = "reading"

        note = r.get(note_key, "") if note_key else ""

        events.append({
            "at": at_dt.isoformat(),
            "type": ev_type,
            "party": party,
            "temp_c": temp_val,
            "note": note
        })

    return events


def find_excursions(events: list[dict], spec_min: float, spec_max: float) -> list[dict]:
    readings = [e for e in events if e.get("temp_c") is not None and e.get("at")]
    readings.sort(key=lambda e: parse_dt(e["at"]))

    excursions = []
    current = None

    for r in readings:
        temp = float(r["temp_c"])
        dt = parse_dt(r["at"])
        party = r.get("party") or "carrier"
        is_out = (temp < spec_min) or (temp > spec_max)

        if is_out:
            if current is None:
                current = {
                    "start": dt.isoformat(),
                    "end": dt.isoformat(),
                    "peak_c": temp,
                    "low_c": temp,
                    "party": party,
                    "type": r.get("type", "reading"),
                    "readings": 1,
                }
            else:
                current["end"] = dt.isoformat()
                current["readings"] += 1
                if temp > current["peak_c"]:
                    current["peak_c"] = temp
                if temp < current["low_c"]:
                    current["low_c"] = temp
        else:
            if current is not None:
                current["end"] = dt.isoformat()
                excursions.append(current)
                current = None

    if current is not None:
        excursions.append(current)

    return excursions


def find_gaps(events: list[dict]) -> list[dict]:
    gaps = []
    readings = [e for e in events if e.get("temp_c") is not None and e.get("at")]
    readings.sort(key=lambda e: parse_dt(e["at"]))

    for i in range(len(readings) - 1):
        t1 = parse_dt(readings[i]["at"])
        t2 = parse_dt(readings[i + 1]["at"])
        hrs = round((t2 - t1).total_seconds() / 3600.0, 1)
        if hrs > 2.0:  # Flag gaps > 2 hours
            kind = "long_gap" if hrs > 4.0 else "timeline_gap"
            gaps.append({
                "kind": "long_gap" if hrs > 4.0 else "timeline_gap",
                "from": t1.isoformat(),
                "to": t2.isoformat(),
                "hours": hrs,
                "why": f"Telemetry gap of {hrs}h between consecutive readings",
            })

    for e in events:
        if (e.get("type") or "").lower() in ("handoff", "relay", "transfer") and e.get("temp_c") is None:
            at_str = str(e.get("at", ""))
            gaps.append({
                "kind": "null_temp",
                "from": at_str,
                "to": at_str,
                "hours": 0.0,
                "why": f"Handoff by {e.get('party', 'party')} without temperature verification",
            })

    return gaps


def attribute(shipment: dict, events: list[dict]) -> dict:
    """Core ClaimOS pure functional analysis interface."""
    spec_min = float(shipment.get("spec_min_c", 2.0))
    spec_max = float(shipment.get("spec_max_c", 8.0))
    bol_setpoint = shipment.get("bol_setpoint_c")
    bol_setpoint = float(bol_setpoint) if bol_setpoint is not None else None
    origin_pulp = shipment.get("origin_pulp_c")
    origin_pulp = float(origin_pulp) if origin_pulp is not None else None

    # Excursions and gaps
    excursions = find_excursions(events, spec_min, spec_max)
    gaps = find_gaps(events)

    # Missing documents
    doc_kinds = set(shipment.get("documents") or [])
    missing_docs = []
    if bol_setpoint is None:
        missing_docs.append("bol_setpoint")
    if origin_pulp is None:
        missing_docs.append("origin_pulp")
    if "bol" not in doc_kinds:
        missing_docs.append("bol")
    if "logger" not in doc_kinds:
        missing_docs.append("logger")
    if "pod" not in doc_kinds:
        missing_docs.append("pod")

    # Dock clean trap:
    # Excursion exists, and last delivery event is within range
    dock_clean_trap = False
    delivery_events = [
        e for e in sorted(events, key=lambda x: parse_dt(x["at"]))
        if (e.get("type") or "").lower() == "delivery" and e.get("temp_c") is not None
    ]
    delivery_temp_c = None
    if delivery_events:
        last_del = delivery_events[-1]
        delivery_temp_c = float(last_del["temp_c"])
        if excursions and spec_min <= delivery_temp_c <= spec_max:
            dock_clean_trap = True

    # Preliminary Attribution Rules in order
    if bol_setpoint is None:
        attr = "disputed"
        rule = "No setpoint recorded on bill of lading."
        reason = "No temperature setpoint on bill of lading; carrier will deny instruction existed"
    elif origin_pulp is not None and not (spec_min <= origin_pulp <= spec_max):
        attr = "shipper"
        rule = "Origin temperature was already outside product specification."
        reason = f"Origin pulp ({origin_pulp} C) outside spec ({spec_min}-{spec_max} C) at tender (warm loading)"
    elif origin_pulp is None:
        attr = "disputed"
        rule = "Origin pulp temperature missing from tender record."
        reason = "Origin pulp temperature missing from tender record"
    elif not excursions:
        attr = "no_claim"
        rule = "No out-of-spec reading identified during carrier custody."
        reason = "All readings within spec; no excursion detected"
    else:
        # Determine timing of excursions relative to tender / departure
        tender_dt = parse_dt(shipment["tender_at"]) if shipment.get("tender_at") else None
        depart_events = [
            e for e in events
            if (e.get("type") or "").lower() in ("depart", "departure") and e.get("at")
        ]
        depart_dt = parse_dt(depart_events[0]["at"]) if depart_events else tender_dt

        carrier_excursions = []
        pre_tender_excursions = []

        for ex in excursions:
            st = parse_dt(ex["start"])
            if tender_dt and st < tender_dt:
                pre_tender_excursions.append(ex)
            else:
                carrier_excursions.append(ex)

        if carrier_excursions:
            attr = "carrier"
            rule = "Out-of-spec reading occurred after departure while carrier had custody."
            reason = "Excursion starts after departure while carrier had custody; origin and setpoint in spec"
        elif pre_tender_excursions:
            attr = "shipper"
            rule = "Excursion only occurred prior to tender."
            reason = "Excursion only occurred prior to tender"
        else:
            attr = "disputed"
            rule = "Custody transition overlap during excursion."
            reason = "Custody transition overlap during excursion"

    # Carmack deadline
    now = shipment.get("now")
    if now is None:
        now = datetime.now(timezone.utc)
    else:
        now = parse_dt(now)

    tender_dt = parse_dt(shipment.get("tender_at", now))
    deadline_days = int(shipment.get("claim_deadline_days", 9))
    deadline_dt = tender_dt + timedelta(days=deadline_days)
    hours_left = round((deadline_dt - now).total_seconds() / 3600.0, 1)

    notice_sent = bool(shipment.get("notice_sent", False))
    deadline_risk = (hours_left < 48.0) and not notice_sent

    peak_c = None
    all_readings = [float(e["temp_c"]) for e in events if e.get("temp_c") is not None]
    if all_readings:
        peak_c = max(all_readings)

    # Evidence gaps list for presentation
    evidence_gaps = []
    long_gaps = [g for g in gaps if g["kind"] == "long_gap"]
    if long_gaps:
        evidence_gaps.append(f"{len(long_gaps)} logger timeline gap(s) greater than 4 hours.")
    if bol_setpoint is None:
        evidence_gaps.append("Bill of lading has no temperature setpoint.")
    if origin_pulp is None:
        evidence_gaps.append("Origin tender pulp temperature not recorded.")
    if dock_clean_trap:
        evidence_gaps.append("Dock-clean trap: cargo recovered to within spec at delivery dock.")
    evidence_gaps.append("Reefer/controller download not supplied; request it within 48h to corroborate setpoint.")

    return {
        "attribution": attr,
        "rule": rule,
        "reason": reason,
        "excursions": excursions,
        "gaps": gaps,
        "missing_docs": missing_docs,
        "evidence_gaps": evidence_gaps,
        "dock_clean_trap": dock_clean_trap,
        "deadline_at": deadline_dt.strftime("%Y-%m-%d %H:%M UTC"),
        "hours_to_deadline": hours_left,
        "deadline_risk": deadline_risk,
        "peak_c": peak_c,
        "delivery_temp_c": delivery_temp_c,
    }


def analyze(shipment: Shipment, readings: ReadingsTable) -> dict:
    """Imported MVP compatibility interface."""
    events = []
    for r in readings:
        events.append({
            "at": r.timestamp.isoformat(),
            "temp_c": r.temperature_c,
            "party": "carrier",
            "type": "reading"
        })

    payload = {
        "reference": shipment.shipment_id,
        "commodity": shipment.commodity,
        "declared_value_usd": shipment.declared_value,
        "spec_min_c": shipment.spec_min_c,
        "spec_max_c": shipment.spec_max_c,
        "origin_pulp_c": shipment.origin_temp_c,
        "bol_setpoint_c": shipment.bol_setpoint_c,
        "tender_at": shipment.departure.isoformat(),
        "carrier": shipment.carrier,
        "claim_deadline_days": 9,
        "documents": ["bol", "logger"] if shipment.bol_setpoint_c is not None else ["logger"],
        "now": datetime.now(timezone.utc)
    }

    res = attribute(payload, events)

    # Format output dictionary matching imported MVP schema
    attr_title = res["attribution"].capitalize()
    if res["attribution"] == "no_claim":
        attr_title = "No claim"

    delivery_temp = float(readings.iloc[-1].temperature_c) if len(readings) > 0 else 0.0

    return {
        "shipment": asdict(shipment),
        "attribution": attr_title,
        "rule": res["rule"],
        "excursions": res["excursions"],
        "peak_c": res["peak_c"] or 0.0,
        "delivery_temp_c": delivery_temp,
        "evidence_gaps": res["evidence_gaps"],
        "timeline_gaps": res["gaps"],
        "has_claim_signal": attr_title in {"Carrier", "Shipper", "Disputed"},
    }


def draft_notice(shipment: dict, analysis: dict) -> str:
    peak = analysis.get("peak_c")
    peak_txt = f"{peak} C" if peak is not None else "outside spec"
    return (
        f"To {shipment.get('carrier') or 'Carrier'}: Shipment {shipment.get('reference')} was tendered "
        f"in apparent good condition at {shipment.get('origin_pulp_c')} C against a BOL setpoint of "
        f"{shipment.get('bol_setpoint_c')} C and spec {shipment.get('spec_min_c')}–{shipment.get('spec_max_c')} C. "
        f"Readings show product at {peak_txt} after departure. Receiver has quarantined the load. "
        f"We hold the carrier for temperature damage up to ${float(shipment.get('declared_value_usd') or 0):,.0f} "
        f"and request the reefer download within 48 hours. This notice is inside the contractual window. "
        f"Preliminary operational summary, not a legal determination."
    )
