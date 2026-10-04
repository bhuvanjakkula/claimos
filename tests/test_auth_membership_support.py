import uuid
import pytest
from fastapi.testclient import TestClient
from app.main import app
from app.db import SessionLocal, init_db
from app.models import User, SupportEnquiry, Invoice

client = TestClient(app)

@pytest.fixture(autouse=True)
def setup_database():
    init_db()

def test_auth_pages_accessible():
    res = client.get("/auth")
    assert res.status_code == 200
    assert "Sign In" in res.text
    assert "Sign Up" in res.text
    assert "bjtmusic12@gmail.com" in res.text

def test_signup_with_email_password_mobile():
    unique_email = f"testuser_{uuid.uuid4().hex[:6]}@logistics.com"
    res = client.post("/auth/signup", data={
        "email": unique_email,
        "password": "securepassword123",
        "mobile_number": "+1 (555) 345-6789",
        "full_name": "Test Shipper",
        "company_name": "Test Reefer Co"
    }, follow_redirects=False)
    assert res.status_code == 303
    assert "claimos_session" in res.cookies

    # Verify user exists in db
    with SessionLocal() as db:
        u = db.query(User).filter(User.email == unique_email).first()
        assert u is not None
        assert u.mobile_number == "+1 (555) 345-6789"
        assert u.subscription_plan == "free"

def test_signin_with_email_and_mobile():
    # Login with email
    res1 = client.post("/auth/login", data={
        "login_id": "demo@coldchain.com",
        "password": "password123"
    }, follow_redirects=False)
    assert res1.status_code == 303
    assert "claimos_session" in res1.cookies

    # Login with mobile number
    res2 = client.post("/auth/login", data={
        "login_id": "+1 (555) 839-2041",
        "password": "password123"
    }, follow_redirects=False)
    assert res2.status_code == 303
    assert "claimos_session" in res2.cookies

def test_customer_support_enquiry_submission():
    res = client.post("/support/enquiry", data={
        "full_name": "Sarah Connor",
        "email": "sarah@biologics.com",
        "mobile_number": "+1 (555) 777-8888",
        "subject": "Dock Clean Defense on SHP-88421",
        "category": "Carrier Claim Escalation",
        "message": "Need immediate Carmack 48h pack review."
    }, follow_redirects=True)
    assert res.status_code == 200
    assert "Enquiry Successfully Dispatched" in res.text
    assert "bjtmusic12@gmail.com" in res.text

    with SessionLocal() as db:
        enq = db.query(SupportEnquiry).filter(SupportEnquiry.email == "sarah@biologics.com").first()
        assert enq is not None
        assert enq.contact_email_target == "bjtmusic12@gmail.com"
        assert enq.ticket_id.startswith("TKT-2026-")

def test_pro_membership_page_and_subscription():
    # Test membership page has USD monthly pricing
    res = client.get("/membership")
    assert res.status_code == 200
    assert "Customer Pro Membership" in res.text
    assert "199" in res.text
    assert "USD / month" in res.text
    assert "bjtmusic12@gmail.com" in res.text
    # Verify exact Stripe payment links are present
    assert "https://buy.stripe.com/test_fZu28j6mTeOVfbP7CfcjS04" in res.text
    assert "https://buy.stripe.com/test_14AdR1fXtgX37Jn7CfcjS05" in res.text
    assert "https://buy.stripe.com/test_cNi14feTp8qxd3H1dRcjS06" in res.text

    # Log in as test user
    login_res = client.post("/auth/login", data={
        "login_id": "testuser@logistics.com",
        "password": "securepassword123"
    }, follow_redirects=False)
    cookies = login_res.cookies

    # Subscribe to Pro Membership ($199/mo USD)
    sub_res = client.post("/membership/subscribe", data={
        "plan_name": "pro",
        "amount_usd": "199.00",
        "card_brand": "Visa",
        "card_last4": "4242"
    }, cookies=cookies, follow_redirects=True)
    assert sub_res.status_code == 200

    # Verify user state updated
    with SessionLocal() as db:
        u = db.query(User).filter(User.email == "testuser@logistics.com").first()
        assert u.subscription_plan == "pro"
        assert u.subscription_status == "active"
        assert u.monthly_amount_usd == 199.00
        assert len(u.invoices) >= 1

def test_first_web_page_shows_technology_utility_and_innovations():
    res = client.get("/")
    assert res.status_code == 200
    # Utility content
    assert "Why This Cold-Chain Technology is Essential" in res.text
    assert "Breakthrough Innovations" in res.text
    assert "35 Billion USD" in res.text
    assert "Dock-Clean" in res.text
    # Innovations
    assert "Precision Multi-Sensor Excursion Triangulation" in res.text
    assert "Dock-Clean Defense Counter-Strategy" in res.text
    assert "Automated Carmack 48-Hour Notice Dispatcher" in res.text
    assert "Court-Ready Forensic Claim Dossier" in res.text
    assert "Historical Dormant Freight Value Audit" in res.text
    assert "Zero-Loss Telematics Anti-Spoliation Vault" in res.text

def test_unpaid_visitor_cannot_access_dashboard_engine_functions():
    unpaid_client = TestClient(app)
    # 1. First web page shows Sign In / Sign Up and innovations showcase
    res = unpaid_client.get("/")
    assert res.status_code == 200
    assert "First Web Page Layer" in res.text
    assert "Sign In" in res.text

    # Unpaid visitor cannot access dashboard directly
    res_dash = unpaid_client.get("/dashboard", follow_redirects=False)
    assert res_dash.status_code == 303
    assert "login_required_for_dashboard" in res_dash.headers["location"]

    # 2. Ingest upload is blocked without paying
    res_upload = unpaid_client.post("/upload", data={
        "reference": "SHP-BLOCKED-1",
        "commodity": "Test Biologics",
        "spec_min_c": 2.0,
        "spec_max_c": 8.0,
        "declared_value_usd": 50000,
        "carrier": "Test Carrier",
    }, follow_redirects=False)
    assert res_upload.status_code == 303
    assert "/membership?msg=paid_membership_required" in res_upload.headers["location"]

    # 3. PDF claim pack download is blocked without paying
    res_pdf = unpaid_client.get("/shipment/SHP-88421/pdf", follow_redirects=False)
    assert res_pdf.status_code == 303
    assert "/membership?msg=paid_membership_required" in res_pdf.headers["location"]

    # 4. Notice generation is blocked without paying
    res_notice = unpaid_client.post("/shipment/SHP-88421/notice", data={"notice": "New Notice"}, follow_redirects=False)
    assert res_notice.status_code == 303
    assert "/membership?msg=paid_membership_required" in res_notice.headers["location"]

def test_paid_user_accesses_all_dashboard_engine_functions():
    # 1-Click demo access unlocks dashboard as paid customer
    res_unlock = client.post("/auth/demo-access", follow_redirects=False)
    assert res_unlock.status_code == 303
    cookies = res_unlock.cookies

    # 1. Dashboard indicates full unlocked access
    res_home = client.get("/dashboard", cookies=cookies)
    assert res_home.status_code == 200
    assert "Carmack Claim Engine Dashboard" in res_home.text
    assert "All Functions Operational" in res_home.text

    # 2. PDF pack generation works with 200 OK
    res_pdf = client.get("/shipment/SHP-88421/pdf", cookies=cookies)
    assert res_pdf.status_code == 200
    assert res_pdf.headers["content-type"] == "application/pdf"
    assert len(res_pdf.content) > 1000

def test_owner_keyless_access():
    res_owner = client.post("/auth/login", data={"login_id": "bhuvanjakkula@gmail.com", "password": ""}, follow_redirects=False)
    assert res_owner.status_code == 303
    assert "/dashboard" in res_owner.headers["location"]
    cookies = res_owner.cookies
    res_dash = client.get("/dashboard", cookies=cookies)
    assert res_dash.status_code == 200
    assert "Carmack Claim Engine Dashboard" in res_dash.text
    assert "Authorized Owner Access" in res_dash.text


