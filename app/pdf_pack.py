import io
from datetime import datetime
from reportlab.lib import colors
from reportlab.lib.pagesizes import letter
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.units import inch
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle, PageBreak


def money(v):
    return f"${float(v or 0):,.0f}"


def dt(v):
    if hasattr(v, "strftime"):
        return v.strftime("%d %b %Y %H:%M")
    return str(v or "")


def build_claim_pdf(result: dict, output_path_or_buf):
    s = result.get("shipment", {})
    ref = s.get("reference") or s.get("shipment_id") or "SHP-UNKNOWN"
    carrier = s.get("carrier") or "Carrier"
    commodity = s.get("commodity") or "Refrigerated Cargo"
    val = s.get("declared_value") or s.get("declared_value_usd") or 0
    spec_min = s.get("spec_min_c", 2.0)
    spec_max = s.get("spec_max_c", 8.0)
    origin_temp = s.get("origin_pulp_c") if s.get("origin_pulp_c") is not None else s.get("origin_temp_c")
    bol_setpoint = s.get("bol_setpoint_c")
    deadline = result.get("deadline_at") or s.get("notice_deadline")
    peak_c = result.get("peak_c")
    delivery_temp = result.get("delivery_temp_c")

    styles = getSampleStyleSheet()
    small_style = ParagraphStyle(name="SmallText", parent=styles["BodyText"], fontSize=8.5, leading=11, textColor=colors.HexColor("#334155"))
    header_style = ParagraphStyle(name="DocHeader", parent=styles["Title"], fontSize=18, leading=22, textColor=colors.HexColor("#0f172a"))
    bold_style = ParagraphStyle(name="BoldCell", fontName="Helvetica-Bold", fontSize=8.5, leading=11, textColor=colors.HexColor("#0f172a"))
    val_style = ParagraphStyle(name="ValCell", fontName="Helvetica", fontSize=8.5, leading=11, textColor=colors.HexColor("#1e293b"))

    doc = SimpleDocTemplate(
        output_path_or_buf,
        pagesize=letter,
        rightMargin=36,
        leftMargin=36,
        topMargin=36,
        bottomMargin=36
    )

    story = [
        Paragraph("ClaimOS &bull; Cold-Chain Freight Claim Pack", header_style),
        Paragraph("Preliminary evidence package &mdash; Carmack operational summary, not a legal determination", styles["Italic"]),
        Spacer(1, 10)
    ]

    # Red Notice Deadline Callout
    if deadline:
        story += [
            Paragraph(f'<font color="#dc2626"><b>CARMACK NOTICE DEADLINE: {deadline}</b></font>', styles["Heading2"]),
            Spacer(1, 6)
        ]

    # Shipment Summary Table
    setpoint_txt = f"{bol_setpoint:.1f} °C" if bol_setpoint is not None else "<font color='red'><b>MISSING</b></font>"
    origin_txt = f"{origin_temp:.1f} °C" if origin_temp is not None else "<font color='red'><b>MISSING</b></font>"
    peak_txt = f"{peak_c:.1f} °C" if peak_c is not None else "In spec"
    delivery_txt = f"{delivery_temp:.1f} °C" if delivery_temp is not None else "Unknown"

    summary_data = [
        [Paragraph("Shipment Reference", bold_style), Paragraph(str(ref), val_style)],
        [Paragraph("Commodity", bold_style), Paragraph(str(commodity), val_style)],
        [Paragraph("Carrier / Broker", bold_style), Paragraph(f"{carrier} / {s.get('broker') or 'Direct'}", val_style)],
        [Paragraph("Declared Cargo Value", bold_style), Paragraph(money(val), bold_style)],
        [Paragraph("Product Specification", bold_style), Paragraph(f"{spec_min:.1f} to {spec_max:.1f} °C", val_style)],
        [Paragraph("Origin Tender Pulp", bold_style), Paragraph(origin_txt, val_style)],
        [Paragraph("BOL Temperature Setpoint", bold_style), Paragraph(setpoint_txt, val_style)],
        [Paragraph("Peak Observed Temp", bold_style), Paragraph(peak_txt, bold_style)],
        [Paragraph("Delivery Reading", bold_style), Paragraph(delivery_txt, val_style)],
    ]

    t_sum = Table(summary_data, colWidths=[150, 390])
    t_sum.setStyle(TableStyle([
        ("GRID", (0, 0), (-1, -1), 0.5, colors.HexColor("#cbd5e1")),
        ("BACKGROUND", (0, 0), (0, -1), colors.HexColor("#f8fafc")),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("TOPPADDING", (0, 0), (-1, -1), 4),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
    ]))
    story += [t_sum, Spacer(1, 12)]

    # Preliminary Attribution Banner
    attr = result.get("attribution", "Disputed")
    rule = result.get("rule") or result.get("reason") or ""
    attr_color = "#dc2626" if str(attr).lower() == "carrier" else ("#ea580c" if str(attr).lower() == "shipper" else "#7c3aed")

    story += [
        Paragraph(f'Preliminary Claim Attribution: <font color="{attr_color}"><b>{str(attr).upper()}</b></font>', styles["Heading2"]),
        Paragraph(str(rule), styles["BodyText"]),
        Spacer(1, 10)
    ]

    # Excursion Chronology Table
    story += [Paragraph("<b>Thermal Excursion Chronology</b>", styles["Heading3"])]
    excursions = result.get("excursions") or []
    if excursions:
        exc_rows = [["Start Window", "Resolution", "Peak", "Low", "Readings", "Custody"]]
        for ex in excursions:
            st = str(ex.get("start", ""))[:16].replace("T", " ")
            en = str(ex.get("end", ""))[:16].replace("T", " ")
            pk = f"{ex.get('peak_c', 0):.1f} °C"
            lw = f"{ex.get('low_c', 0):.1f} °C" if ex.get("low_c") is not None else "-"
            rd = str(ex.get("readings", 1))
            pty = str(ex.get("party", "carrier")).capitalize()
            exc_rows.append([st, en, pk, lw, rd, pty])

        t_exc = Table(exc_rows, colWidths=[110, 110, 75, 75, 70, 100])
        t_exc.setStyle(TableStyle([
            ("GRID", (0, 0), (-1, -1), 0.5, colors.HexColor("#cbd5e1")),
            ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#f1f5f9")),
            ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
            ("FONTSIZE", (0, 0), (-1, -1), 8),
            ("TOPPADDING", (0, 0), (-1, -1), 3),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 3),
        ]))
        story += [t_exc, Spacer(1, 10)]
    else:
        story += [Paragraph("No out-of-spec readings detected in telemetry.", styles["BodyText"]), Spacer(1, 10)]

    # Evidence Gaps & Trap Warnings
    story += [Paragraph("<b>Evidence Gaps & Operational Counter-Measures</b>", styles["Heading3"])]
    evidence_gaps = result.get("evidence_gaps") or []
    if result.get("dock_clean_trap"):
        evidence_gaps = ["<b>DOCK-CLEAN TRAP ACTIVE:</b> Product recovered to in-spec range at delivery dock, but unedited in-transit telemetry confirms critical thermal breach."] + list(evidence_gaps)

    if evidence_gaps:
        for eg in evidence_gaps:
            story.append(Paragraph(f"&bull; {eg}", small_style))
    else:
        story.append(Paragraph("&bull; No critical documentation gaps identified.", small_style))

    story += [Spacer(1, 12)]

    # Draft Preservation & Claim Notice
    story += [
        PageBreak(),
        Paragraph("Draft Evidence Preservation & Carrier Claim Notice", styles["Heading1"]),
        Spacer(1, 6),
        Paragraph(f"<b>To:</b> Claims Department, {carrier}", styles["BodyText"]),
        Paragraph(f"<b>Re:</b> Formal Notice of Cargo Damage & Evidence Preservation &mdash; Shipment {ref}", styles["BodyText"]),
        Paragraph(f"<b>Declared Value:</b> {money(val)} USD", styles["BodyText"]),
        Spacer(1, 10),
        Paragraph(
            f"This letter provides formal notice under 49 U.S.C. § 14706 (Carmack Amendment) holding {carrier} "
            f"fully responsible for thermal excursion and cargo damage sustained to shipment {ref}. Continuous telemetry records "
            f"temperature excursions reaching {peak_txt} while cargo was in carrier custody, contrary to the contracted "
            f"specification of {spec_min:.1f}–{spec_max:.1f} °C.",
            styles["BodyText"]
        ),
        Spacer(1, 10),
        Paragraph(
            "<b>EVIDENCE PRESERVATION DEMAND (48-HOUR REQUIREMENT):</b><br/>"
            "Pursuant to federal cold-chain preservation standards, you are hereby demanded to preserve and produce within 48 hours:<br/>"
            "1. Raw digital reefer download (.txt/.dat/.csv) covering pre-cooling through delivery.<br/>"
            "2. Complete reefer micro-controller event log (defrost cycles, power interruptions, alarm events).<br/>"
            "3. Driver route inspection sheets, equipment check records, and relay-yard transfer logs.",
            styles["BodyText"]
        ),
        Spacer(1, 10),
        Paragraph(
            f"Preliminary claim exposure is reserved up to the full declared shipment value of {money(val)} USD. "
            "No statement herein waives any rights, remedies, or claims under applicable tariffs or law.",
            styles["BodyText"]
        ),
        Spacer(1, 16),
        Paragraph("Generated by ClaimOS Cold-Chain Freight Recovery Engine. Human review required before mailing.", styles["Italic"])
    ]

    doc.build(story)
