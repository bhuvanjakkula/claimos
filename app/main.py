import io
import json
import secrets
from datetime import datetime, timezone, timedelta
from pathlib import Path
from contextlib import asynccontextmanager

from fastapi import FastAPI, File, Form, Request, UploadFile, HTTPException
from fastapi.responses import HTMLResponse, RedirectResponse, Response
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from sqlalchemy import select

from app.db import SessionLocal, init_db, recompute
from app.engine import parse_dt, parse_logger_events
from app.models import Document, Event, Shipment, User, Invoice, SupportEnquiry
from app.auth import get_current_user, set_user_cookie, clear_user_cookie, hash_password, verify_password
from app.pdf_pack import build_claim_pdf

base = Path(__file__).parent


@asynccontextmanager
async def lifespan(app: FastAPI):
    init_db()
    yield


app = FastAPI(title="ClaimOS Freight Recovery Engine", lifespan=lifespan)
app.mount("/static", StaticFiles(directory=base / "static"), name="static")
templates = Jinja2Templates(directory=base / "templates")

# Initialize DB on import so tables and seeds exist immediately
init_db()


def load_analysis(shipment: Shipment) -> dict:
    if shipment.analysis_json:
        try:
            return json.loads(shipment.analysis_json)
        except Exception:
            pass
    return {}


OWNER_EMAIL = "bhuvanjakkula@gmail.com"


def is_paid_subscriber(user: User | None) -> bool:
    if not user:
        return False
    # Owner can access without paying money
    if user.email and user.email.lower() == OWNER_EMAIL.lower():
        return True
    return (
        user.subscription_status == "active"
        and user.subscription_plan in {"starter", "pro", "enterprise"}
        and user.monthly_amount_usd > 0
    )


# =========================================================================
# FIRST WEB PAGE LAYER: Sign Up, Sign In & Technology Innovations
# =========================================================================

@app.get("/", response_class=HTMLResponse)
@app.get("/api/index.py", response_class=HTMLResponse)
@app.get("/api/index", response_class=HTMLResponse)
@app.get("/api", response_class=HTMLResponse)
def first_layer_page(
    request: Request,
    mode: str = "signin",
    error: str = "",
    msg: str = "",
):
    with SessionLocal() as db:
        current_user = get_current_user(request, db)
        # If user is already an authenticated paid customer or owner, route to dashboard
        if current_user and is_paid_subscriber(current_user):
            return RedirectResponse("/dashboard", status_code=303)
        return templates.TemplateResponse(request, "first_layer.html", {
            "mode": mode,
            "error": error,
            "msg": msg,
            "current_user": current_user,
            "has_paid_access": False,
            "active_layer": "first_layer",
        })


@app.post("/", response_class=HTMLResponse)
@app.post("/api/index.py", response_class=HTMLResponse)
@app.post("/api/index", response_class=HTMLResponse)
@app.post("/api", response_class=HTMLResponse)
async def post_root_dispatcher(request: Request):
    return await auth_login(request)


# =========================================================================
# DASHBOARD LAYER: Carmack Claim Engine Console (Paid & Owner Access Only)
# =========================================================================

@app.get("/dashboard", response_class=HTMLResponse)
@app.get("/combined", response_class=HTMLResponse)
def dashboard_engine(
    request: Request,
    attribution: str = "",
    status: str = "",
    risk: str = "",
    ref: str = "",
    msg: str = "",
    error: str = "",
):
    with SessionLocal() as db:
        current_user = get_current_user(request, db)
        if not current_user:
            return RedirectResponse("/?msg=login_required_for_dashboard", status_code=303)
        if not is_paid_subscriber(current_user):
            return RedirectResponse("/membership?msg=paid_membership_required", status_code=303)

        has_paid_access = True
        all_shipments = db.scalars(select(Shipment).order_by(Shipment.tender_at.desc())).all()
        for s in all_shipments:
            recompute(s)
        db.commit()

        view = []
        for s in all_shipments:
            a = load_analysis(s)
            if attribution and a.get("attribution", "").lower() != attribution.lower():
                continue
            if status and s.status != status:
                continue
            if risk == "1" and not a.get("deadline_risk"):
                continue
            view.append({"s": s, "a": a})
        totals = {
            "value": sum(v["s"].declared_value_usd for v in view),
            "carrier": sum(1 for v in view if str(v["a"].get("attribution", "")).lower() == "carrier"),
            "recovered": sum(v["s"].recovered_usd for v in view),
        }

        # Actionable audit rows
        audit_rows = []
        for s in all_shipments:
            if s.status in ["written_off", "denied", "new"]:
                a = load_analysis(s)
                attr = str(a.get("attribution", "")).lower()
                if attr in {"carrier", "disputed"} and s.recovered_usd == 0:
                    audit_rows.append({"s": s, "a": a})
        audit_total = sum(x["s"].declared_value_usd for x in audit_rows)

        # Selected shipment for detail inspector
        all_refs = [s.reference for s in all_shipments]
        target_ref = ref.strip() if ref and ref.strip() else ("SHP-88421" if "SHP-88421" in all_refs else (all_refs[0] if all_refs else ""))
        selected_s = None
        selected_a = {}
        selected_events = []
        selected_docs = []
        if target_ref:
            selected_s = next((s for s in all_shipments if s.reference == target_ref), None)
            if selected_s:
                selected_a = load_analysis(selected_s)
                selected_events = sorted(selected_s.events, key=lambda e: e.at)
                selected_docs = list(selected_s.documents)

        return templates.TemplateResponse(request, "combined.html", {
            "rows": view,
            "totals": totals,
            "attribution": attribution,
            "status": status,
            "risk": risk,
            "audit_rows": audit_rows,
            "audit_total": audit_total,
            "all_refs": all_refs,
            "selected_ref": target_ref,
            "selected_s": selected_s,
            "selected_a": selected_a,
            "selected_events": selected_events,
            "selected_docs": selected_docs,
            "active_layer": "dashboard",
            "current_user": current_user,
            "has_paid_access": has_paid_access,
            "msg": msg,
            "error": error,
        })


@app.get("/shipment/{ref}", response_class=HTMLResponse)
def detail(request: Request, ref: str):
    with SessionLocal() as db:
        current_user = get_current_user(request, db)
        if not is_paid_subscriber(current_user):
            return RedirectResponse(f"/membership?msg=paid_membership_required&ref={ref}", status_code=303)
        s = db.scalar(select(Shipment).where(Shipment.reference == ref))
        if not s:
            return RedirectResponse("/", status_code=302)
        recompute(s)
        db.commit()
        events = sorted(s.events, key=lambda e: e.at)
        docs = list(s.documents)
        return templates.TemplateResponse(request, "detail.html", {
            "s": s,
            "a": load_analysis(s),
            "events": events,
            "docs": docs,
            "active_layer": "detail",
            "current_user": current_user,
        })


@app.post("/shipment/{ref}/notice")
def save_notice(request: Request, ref: str, notice: str = Form(...)):
    with SessionLocal() as db:
        current_user = get_current_user(request, db)
        if not is_paid_subscriber(current_user):
            return RedirectResponse(f"/membership?msg=paid_membership_required&ref={ref}", status_code=303)
        s = db.scalar(select(Shipment).where(Shipment.reference == ref))
        if s:
            s.notice = notice
            db.commit()
    return RedirectResponse(f"/?ref={ref}#layer-detail", status_code=303)


@app.post("/shipment/{ref}/status")
def set_status(request: Request, ref: str, status: str = Form(...), recovered_usd: str = Form("")):
    with SessionLocal() as db:
        current_user = get_current_user(request, db)
        if not is_paid_subscriber(current_user):
            return RedirectResponse(f"/membership?msg=paid_membership_required&ref={ref}", status_code=303)
        s = db.scalar(select(Shipment).where(Shipment.reference == ref))
        if s:
            s.status = status
            if recovered_usd and recovered_usd.strip():
                try:
                    s.recovered_usd = float(recovered_usd.strip())
                except ValueError:
                    pass
            recompute(s)
            db.commit()
    return RedirectResponse(f"/?ref={ref}#layer-detail", status_code=303)


@app.get("/shipment/{ref}/pdf")
def pdf(request: Request, ref: str):
    with SessionLocal() as db:
        current_user = get_current_user(request, db)
        if not is_paid_subscriber(current_user):
            return RedirectResponse(f"/membership?msg=paid_membership_required_for_pdf&ref={ref}", status_code=303)
        s = db.scalar(select(Shipment).where(Shipment.reference == ref))
        if not s:
            raise HTTPException(status_code=404, detail="Shipment not found")
        a = load_analysis(s)
        buf = io.BytesIO()
        result = {
            "shipment": {
                "reference": s.reference,
                "commodity": s.commodity,
                "declared_value_usd": s.declared_value_usd,
                "carrier": s.carrier,
                "broker": s.broker,
                "spec_min_c": s.spec_min_c,
                "spec_max_c": s.spec_max_c,
                "origin_pulp_c": s.origin_pulp_c,
                "bol_setpoint_c": s.bol_setpoint_c,
            },
            "attribution": a.get("attribution"),
            "rule": a.get("rule") or a.get("reason"),
            "deadline_at": a.get("deadline_at"),
            "peak_c": a.get("peak_c"),
            "delivery_temp_c": a.get("delivery_temp_c"),
            "excursions": a.get("excursions"),
            "evidence_gaps": a.get("evidence_gaps"),
            "dock_clean_trap": a.get("dock_clean_trap")
        }
        build_claim_pdf(result, buf)
        return Response(
            buf.getvalue(),
            media_type="application/pdf",
            headers={"Content-Disposition": f"inline; filename={ref}_claim_pack.pdf"}
        )


@app.get("/sample-data/download")
def download_sample_csv():
    csv_path = Path(__file__).resolve().parent.parent / "sample_data" / "SHP-88421_logger.csv"
    if csv_path.exists():
        with open(csv_path, "r", encoding="utf-8") as f:
            content = f.read()
        return Response(
            content=content,
            media_type="text/csv",
            headers={"Content-Disposition": "attachment; filename=SHP-88421_logger.csv"}
        )
    raise HTTPException(status_code=404, detail="Sample CSV not found")


@app.post("/upload")
async def upload(
    request: Request,
    reference: str = Form(...),
    commodity: str = Form(...),
    spec_min_c: float = Form(...),
    spec_max_c: float = Form(...),
    declared_value_usd: float = Form(...),
    carrier: str = Form(...),
    shipper: str = Form(""),
    receiver: str = Form(""),
    broker: str = Form(""),
    bol_setpoint_c: str = Form(""),
    origin_pulp_c: str = Form(""),
    tender_at: str = Form(""),
    logger: UploadFile | None = File(None),
    logger_text: str = Form(""),
):
    with SessionLocal() as db:
        current_user = get_current_user(request, db)
        if not is_paid_subscriber(current_user):
            return RedirectResponse("/membership?msg=paid_membership_required_to_ingest", status_code=303)
        tender = parse_dt(tender_at) if tender_at and tender_at.strip() else datetime.now(timezone.utc)
        ref = reference.strip()

        # Check existing reference
        existing = db.scalar(select(Shipment).where(Shipment.reference == ref))
        if existing:
            ref = f"{ref}-{int(datetime.now().timestamp())}"

        s = Shipment(
            reference=ref,
            commodity=commodity.strip(),
            spec_min_c=spec_min_c,
            spec_max_c=spec_max_c,
            bol_setpoint_c=float(bol_setpoint_c.strip()) if bol_setpoint_c and bol_setpoint_c.strip() else None,
            origin_pulp_c=float(origin_pulp_c.strip()) if origin_pulp_c and origin_pulp_c.strip() else None,
            declared_value_usd=declared_value_usd,
            carrier=carrier.strip(),
            shipper=shipper.strip(),
            receiver=receiver.strip(),
            broker=broker.strip(),
            tender_at=tender,
            status="new",
        )
        db.add(s)
        db.flush()

        text = ""
        filename = "logger.csv"
        if logger and logger.filename:
            file_bytes = await logger.read()
            text = file_bytes.decode("utf-8", errors="replace")
            filename = logger.filename
        elif logger_text and logger_text.strip():
            text = logger_text.strip()
            filename = f"pasted_logger_{ref}.csv"

        if text:
            parsed_events = parse_logger_events(text, departure=tender, delivery=tender + timedelta(hours=24))
            for ev in parsed_events:
                db.add(Event(
                    shipment=s,
                    at=parse_dt(ev["at"]),
                    type=ev.get("type", "reading"),
                    party=ev.get("party", "carrier"),
                    temp_c=ev.get("temp_c"),
                    note=ev.get("note", ""),
                ))
            db.add(Document(shipment=s, kind="logger", filename=filename, uploaded_at=datetime.now(timezone.utc)))

        recompute(s)
        db.commit()

    return RedirectResponse(f"/?ref={ref}#layer-detail", status_code=303)


# Compatibility endpoint for imported MVP /generate
@app.post("/generate")
async def generate_direct(
    request: Request,
    logger: UploadFile | None = File(None)
):
    with SessionLocal() as db:
        current_user = get_current_user(request, db)
        if not is_paid_subscriber(current_user):
            return RedirectResponse("/membership?msg=paid_membership_required", status_code=303)

    form = await request.form()
    ref = str(form.get("shipment_id") or form.get("reference") or "SHP-88421").strip()
    commodity = str(form.get("commodity") or "Refrigerated Biologics").strip()
    carrier = str(form.get("carrier") or "Carrier Logistics").strip()
    declared_val = float(form.get("declared_value") or form.get("declared_value_usd") or 0)
    spec_min = float(form.get("spec_min") or form.get("spec_min_c") or 2.0)
    spec_max = float(form.get("spec_max") or form.get("spec_max_c") or 8.0)
    origin_pulp = float(form["origin_temp"]) if form.get("origin_temp") else None
    bol_setpoint = float(form["bol_setpoint"]) if form.get("bol_setpoint") else None

    with SessionLocal() as db:
        existing = db.scalar(select(Shipment).where(Shipment.reference == ref))
        if existing:
            ref = f"{ref}-{int(datetime.now().timestamp())}"

        tender = datetime.now(timezone.utc) - timedelta(days=2)
        s = Shipment(
            reference=ref,
            commodity=commodity,
            spec_min_c=spec_min,
            spec_max_c=spec_max,
            bol_setpoint_c=bol_setpoint,
            origin_pulp_c=origin_pulp,
            declared_value_usd=declared_val,
            carrier=carrier,
            tender_at=tender,
            status="new"
        )
        db.add(s)
        db.flush()

        if logger and logger.filename:
            raw_text = (await logger.read()).decode("utf-8", errors="replace")
            events = parse_logger_events(raw_text, departure=tender, delivery=tender + timedelta(hours=24))
            for ev in events:
                db.add(Event(
                    shipment=s,
                    at=parse_dt(ev["at"]),
                    type=ev.get("type", "reading"),
                    party=ev.get("party", "carrier"),
                    temp_c=ev.get("temp_c"),
                    note=ev.get("note", "")
                ))
            db.add(Document(shipment=s, kind="logger", filename=logger.filename, uploaded_at=datetime.now(timezone.utc)))

        analysis = recompute(s)
        db.commit()

        buf = io.BytesIO()
        result = {
            "shipment": s.__dict__,
            "attribution": analysis.get("attribution"),
            "rule": analysis.get("rule"),
            "deadline_at": analysis.get("deadline_at"),
            "peak_c": analysis.get("peak_c"),
            "delivery_temp_c": analysis.get("delivery_temp_c"),
            "excursions": analysis.get("excursions"),
            "evidence_gaps": analysis.get("evidence_gaps"),
            "dock_clean_trap": analysis.get("dock_clean_trap")
        }
        build_claim_pdf(result, buf)

    return Response(
        buf.getvalue(),
        media_type="application/pdf",
        headers={"Content-Disposition": f"attachment; filename={ref}_claim_pack.pdf"}
    )


@app.get("/upload", response_class=HTMLResponse)
def upload_form(request: Request):
    with SessionLocal() as db:
        user = get_current_user(request, db)
        if not is_paid_subscriber(user):
            return RedirectResponse("/membership?msg=paid_membership_required_to_ingest", status_code=303)
        return templates.TemplateResponse(request, "upload.html", {"current_user": user})


@app.get("/audit", response_class=HTMLResponse)
def audit(request: Request):
    with SessionLocal() as db:
        user = get_current_user(request, db)
        if not is_paid_subscriber(user):
            return RedirectResponse("/membership?msg=paid_membership_required_for_audit", status_code=303)
        rows = db.scalars(select(Shipment).where(Shipment.status.in_(["written_off", "denied", "new"]))).all()
        actionable = []
        for s in rows:
            a = load_analysis(s)
            attr = str(a.get("attribution", "")).lower()
            if attr in {"carrier", "disputed"} and s.recovered_usd == 0:
                actionable.append({"s": s, "a": a})
        total = sum(x["s"].declared_value_usd for x in actionable)
        return templates.TemplateResponse(request, "audit.html", {
            "rows": actionable,
            "total": total,
            "current_user": user,
        })


@app.get("/about", response_class=HTMLResponse)
def about(request: Request):
    with SessionLocal() as db:
        user = get_current_user(request, db)
        return templates.TemplateResponse(request, "about.html", {"current_user": user})


# =========================================================================
# AUTHENTICATION ROUTES (Sign In / Sign Up)
# =========================================================================

@app.get("/auth", response_class=HTMLResponse)
@app.post("/auth", response_class=HTMLResponse)
async def auth_page(request: Request, mode: str = "signin", msg: str = "", error: str = ""):
    if request.method == "POST":
        return await auth_login(request)
    with SessionLocal() as db:
        user = get_current_user(request, db)
        if user and mode != "signup":
            return RedirectResponse("/", status_code=302)
        return templates.TemplateResponse(request, "auth.html", {
            "mode": mode,
            "msg": msg,
            "error": error,
            "current_user": user,
            "active_layer": "auth",
        })


@app.post("/auth/signup")
def auth_signup(
    request: Request,
    email: str = Form(...),
    password: str = Form(...),
    mobile_number: str = Form(...),
    full_name: str = Form(""),
    company_name: str = Form(""),
    activate_pro: str = Form(""),
):
    email_clean = email.strip().lower()
    mobile_clean = mobile_number.strip()
    if not email_clean or not password or not mobile_clean:
        return RedirectResponse("/auth?mode=signup&error=missing_fields", status_code=303)

    with SessionLocal() as db:
        # Check if owner registering
        if email_clean == OWNER_EMAIL.lower():
            existing = db.scalar(select(User).where(User.email == OWNER_EMAIL.lower()))
            if not existing:
                new_user = User(
                    email=OWNER_EMAIL.lower(),
                    password_hash=hash_password("owner-keyless-entry"),
                    mobile_number=mobile_clean,
                    full_name=full_name.strip() or "Platform Owner",
                    company_name=company_name.strip() or "ClaimOS Enterprise",
                    subscription_plan="enterprise",
                    subscription_status="active",
                    monthly_amount_usd=0.0,
                    subscribed_at=datetime.now(timezone.utc),
                )
                db.add(new_user)
                db.commit()
                db.refresh(new_user)
            else:
                existing.subscription_status = "active"
                existing.subscription_plan = "enterprise"
                db.commit()
                new_user = existing
            response = RedirectResponse("/dashboard?msg=owner_authenticated", status_code=303)
            set_user_cookie(response, new_user)
            return response

        existing = db.scalar(select(User).where(User.email == email_clean))
        if existing:
            return RedirectResponse("/auth?mode=signin&error=email_exists", status_code=303)

        new_user = User(
            email=email_clean,
            password_hash=hash_password(password),
            mobile_number=mobile_clean,
            full_name=full_name.strip() or email_clean.split("@")[0].title(),
            company_name=company_name.strip(),
            subscription_plan="free",
            subscription_status="inactive",
            monthly_amount_usd=0.0,
        )
        db.add(new_user)
        db.commit()
        db.refresh(new_user)

        # Strictly redirect new users to membership page to pay via Stripe before dashboard access
        response = RedirectResponse("/membership?msg=paid_membership_required", status_code=303)
        set_user_cookie(response, new_user)
        return response


@app.get("/owner-login")
@app.post("/owner-login")
def owner_direct_login():
    with SessionLocal() as db:
        user = db.scalar(select(User).where(User.email == OWNER_EMAIL.lower()))
        if not user:
            user = User(
                email=OWNER_EMAIL.lower(),
                password_hash=hash_password("owner-keyless-entry"),
                mobile_number="+1 (800) 555-0199",
                full_name="Platform Owner",
                company_name="ClaimOS Enterprise",
                subscription_plan="enterprise",
                subscription_status="active",
                monthly_amount_usd=0.0,
                subscribed_at=datetime.now(timezone.utc),
            )
            db.add(user)
            db.commit()
            db.refresh(user)
        else:
            user.subscription_status = "active"
            user.subscription_plan = "enterprise"
            db.commit()
        response = RedirectResponse("/dashboard?msg=owner_authenticated", status_code=303)
        set_user_cookie(response, user)
        return response


@app.get("/auth/login")
@app.post("/auth/login")
@app.get("/login")
@app.post("/login")
async def auth_login(
    request: Request,
    login_id: str | None = None,
    password: str | None = None,
    email: str | None = None,
):
    login_clean = (login_id if isinstance(login_id, str) else "") or (email if isinstance(email, str) else "")
    login_clean = login_clean.strip()
    pwd_clean = (password if isinstance(password, str) else "").strip()

    # Also check if JSON or form was passed in request
    if not login_clean:
        if request.method == "POST":
            content_type = request.headers.get("content-type", "")
            if "application/json" in content_type:
                try:
                    data = await request.json()
                    login_clean = str(data.get("login_id") or data.get("email") or "").strip()
                    if not pwd_clean:
                        pwd_clean = str(data.get("password") or "").strip()
                except Exception:
                    pass
            else:
                try:
                    form = await request.form()
                    login_clean = str(form.get("login_id") or form.get("email") or "").strip()
                    if not pwd_clean:
                        pwd_clean = str(form.get("password") or "").strip()
                except Exception:
                    pass

    # Query params fallback (for GET requests or URL parameters)
    if not login_clean:
        login_clean = str(request.query_params.get("login_id") or request.query_params.get("email") or "").strip()
        if not pwd_clean:
            pwd_clean = str(request.query_params.get("password") or "").strip()

    login_lower = login_clean.lower()

    # Platform Owner keyless access (bhuvanjakkula@gmail.com): email only, no password, no payment!
    if login_lower == OWNER_EMAIL.lower():
        return owner_direct_login()

    if not login_clean:
        return RedirectResponse("/auth?mode=signin", status_code=303)

    if not pwd_clean:
        return RedirectResponse("/auth?mode=signin&error=invalid_credentials", status_code=303)

    with SessionLocal() as db:
        user = db.scalar(
            select(User).where((User.email == login_lower) | (User.mobile_number == login_clean))
        )
        if not user or not verify_password(pwd_clean, user.password_hash):
            return RedirectResponse("/auth?mode=signin&error=invalid_credentials", status_code=303)

        if is_paid_subscriber(user):
            response = RedirectResponse("/dashboard?msg=logged_in", status_code=303)
        else:
            response = RedirectResponse("/membership?msg=paid_membership_required", status_code=303)
        set_user_cookie(response, user)
        return response


@app.get("/auth/signup")
def auth_signup_get():
    return RedirectResponse("/auth?mode=signup", status_code=303)


@app.get("/auth/logout")
def auth_logout():
    response = RedirectResponse("/auth?mode=signin&msg=logged_out", status_code=303)
    clear_user_cookie(response)
    return response


# =========================================================================
# CUSTOMER SUPPORT & ENQUIRY ROUTES (Contact: bjtmusic12@gmail.com)
# =========================================================================

@app.get("/support", response_class=HTMLResponse)
def support_page(request: Request, submitted: str = "", ticket: str = ""):
    with SessionLocal() as db:
        user = get_current_user(request, db)
        enquiries = db.scalars(
            select(SupportEnquiry).order_by(SupportEnquiry.created_at.desc()).limit(15)
        ).all()
        return templates.TemplateResponse(request, "support.html", {
            "current_user": user,
            "enquiries": enquiries,
            "submitted": submitted == "1",
            "ticket": ticket,
            "active_layer": "support",
        })


@app.post("/support/enquiry")
def submit_enquiry(
    request: Request,
    full_name: str = Form(...),
    email: str = Form(...),
    mobile_number: str = Form(...),
    subject: str = Form(...),
    category: str = Form("General Support"),
    message: str = Form(...),
):
    ticket_id = f"TKT-2026-{secrets.token_hex(3).upper()}"
    with SessionLocal() as db:
        enq = SupportEnquiry(
            ticket_id=ticket_id,
            full_name=full_name.strip(),
            email=email.strip(),
            mobile_number=mobile_number.strip(),
            subject=subject.strip(),
            category=category.strip(),
            message=message.strip(),
            contact_email_target="bjtmusic12@gmail.com",
            status="Open",
            created_at=datetime.now(timezone.utc),
        )
        db.add(enq)
        db.commit()
    return RedirectResponse(f"/support?submitted=1&ticket={ticket_id}", status_code=303)


# =========================================================================
# CUSTOMER PRO MEMBERSHIP ROUTES (USA Dollars / Month)
# =========================================================================

@app.get("/membership", response_class=HTMLResponse)
@app.get("/pro", response_class=HTMLResponse)
def membership_page(request: Request, msg: str = "", ref: str = ""):
    with SessionLocal() as db:
        user = get_current_user(request, db)
        has_paid_access = is_paid_subscriber(user)
        invoices = []
        if user:
            invoices = db.scalars(
                select(Invoice).where(Invoice.user_id == user.id).order_by(Invoice.paid_at.desc())
            ).all()
        return templates.TemplateResponse(request, "membership.html", {
            "current_user": user,
            "has_paid_access": has_paid_access,
            "invoices": invoices,
            "msg": msg,
            "ref": ref,
            "active_layer": "membership",
        })


STRIPE_CHECKOUT_URLS = {
    "starter": "https://buy.stripe.com/test_fZu28j6mTeOVfbP7CfcjS04",
    "pro": "https://buy.stripe.com/test_14AdR1fXtgX37Jn7CfcjS05",
    "enterprise": "https://buy.stripe.com/test_cNi14feTp8qxd3H1dRcjS06",
}


@app.get("/membership/subscribe")
@app.post("/membership/subscribe")
def subscribe_membership(
    request: Request,
    plan_name: str = "pro",
):
    plan_clean = plan_name.strip().lower()
    target_stripe_url = STRIPE_CHECKOUT_URLS.get(plan_clean, STRIPE_CHECKOUT_URLS["pro"])
    return RedirectResponse(target_stripe_url, status_code=303)


@app.post("/membership/cancel")
def cancel_membership(request: Request):
    with SessionLocal() as db:
        user = get_current_user(request, db)
        if user:
            user.subscription_plan = "free"
            user.subscription_status = "inactive"
            user.monthly_amount_usd = 0.0
            db.commit()
    return RedirectResponse("/membership?msg=cancelled", status_code=303)


@app.get("/membership/success")
def stripe_success(request: Request, plan: str = "pro"):
    plan_clean = plan.lower() if plan in {"starter", "pro", "enterprise"} else "pro"
    amounts = {"starter": 49.0, "pro": 199.0, "enterprise": 499.0}
    plan_names = {
        "starter": "ClaimOS Starter Cargo Plan",
        "pro": "ClaimOS Pro Recovery Plan",
        "enterprise": "ClaimOS Enterprise Fleet Plan",
    }
    with SessionLocal() as db:
        user = get_current_user(request, db)
        created_cookie_user = None
        if not user:
            user = User(
                email=f"customer_{secrets.token_hex(3)}@coldchain.com",
                password_hash=hash_password("stripe_paid_verified"),
                mobile_number="+1 (555) 789-0123",
                full_name="Stripe Verified Subscriber",
                subscription_plan=plan_clean,
                subscription_status="active",
                monthly_amount_usd=amounts[plan_clean],
                card_brand="Stripe Checkout",
                card_last4="4242",
                subscribed_at=datetime.now(timezone.utc),
                next_billing_at=datetime.now(timezone.utc) + timedelta(days=30),
            )
            db.add(user)
            db.flush()
            created_cookie_user = user
        else:
            user.subscription_plan = plan_clean
            user.subscription_status = "active"
            user.monthly_amount_usd = amounts[plan_clean]
            user.card_brand = "Stripe Checkout"
            user.card_last4 = "4242"
            user.subscribed_at = datetime.now(timezone.utc)
            user.next_billing_at = datetime.now(timezone.utc) + timedelta(days=30)

        inv = Invoice(
            user_id=user.id,
            invoice_number=f"STRIPE-{secrets.token_hex(4).upper()}",
            plan_name=plan_names[plan_clean],
            amount_usd=amounts[plan_clean],
            billing_cycle="Monthly (USD)",
            status="Paid via Stripe",
            card_brand="Stripe Checkout",
            card_last4="4242",
            paid_at=datetime.now(timezone.utc),
        )
        db.add(inv)
        db.commit()

        response = RedirectResponse("/dashboard?msg=stripe_payment_confirmed", status_code=303)
        if created_cookie_user:
            set_user_cookie(response, created_cookie_user)
        return response


