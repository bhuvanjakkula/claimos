"""
ClaimOS One-Page Freight Claim PDF Pack Generator
Built with ReportLab.
"""

from __future__ import annotations
import io
from typing import Any
from reportlab.lib.pagesizes import letter
from reportlab.lib import colors
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.platypus import (
    SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle, KeepTogether, HRFlowable
)
from reportlab.lib.units import inch


def generate_claim_pdf(shipment: dict, analysis: dict, events: list[dict], documents: list[dict]) -> bytes:
    """
    Generates a high-density, professional 1-page operational claim pack.
    """
    buffer = io.BytesIO()

    # 0.5 inch margins to ensure dense, clean single-page fit
    doc = SimpleDocTemplate(
        buffer,
        pagesize=letter,
        leftMargin=32,
        rightMargin=32,
        topMargin=28,
        bottomMargin=28
    )

    styles = getSampleStyleSheet()

    # Custom styles
    title_style = ParagraphStyle(
        'DocTitle',
        parent=styles['Heading1'],
        fontName='Helvetica-Bold',
        fontSize=14,
        leading=16,
        textColor=colors.HexColor('#0f172a'),
        spaceAfter=0
    )
    subtitle_style = ParagraphStyle(
        'DocSubTitle',
        parent=styles['Normal'],
        fontName='Helvetica',
        fontSize=8,
        leading=10,
        textColor=colors.HexColor('#64748b')
    )
    section_heading = ParagraphStyle(
        'SecHead',
        parent=styles['Heading2'],
        fontName='Helvetica-Bold',
        fontSize=9,
        leading=11,
        textColor=colors.HexColor('#1e293b'),
        spaceBefore=5,
        spaceAfter=3
    )
    cell_bold = ParagraphStyle(
        'CellBold',
        fontName='Helvetica-Bold',
        fontSize=7.5,
        leading=9,
        textColor=colors.HexColor('#0f172a')
    )
    cell_text = ParagraphStyle(
        'CellText',
        fontName='Helvetica',
        fontSize=7.5,
        leading=9,
        textColor=colors.HexColor('#334155')
    )
    badge_style = ParagraphStyle(
        'BadgeText',
        fontName='Helvetica-Bold',
        fontSize=8,
        leading=10,
        textColor=colors.white,
        alignment=1
    )
    notice_text_style = ParagraphStyle(
        'NoticeText',
        fontName='Courier',
        fontSize=6.5,
        leading=8,
        textColor=colors.HexColor('#1e293b')
    )
    footer_style = ParagraphStyle(
        'FooterText',
        fontName='Helvetica-Oblique',
        fontSize=7,
        leading=9,
        textColor=colors.HexColor('#64748b'),
        alignment=1
    )

    elements = []

    # 1. Header with Reference, Claim Deadline, and Attribution Badge
    ref = shipment.get("reference", "SHP-UNKNOWN")
    attr_key = analysis.get("attribution", "disputed")
    attr_label = analysis.get("attribution_label", "Disputed")
    declared_val = f"${shipment.get('declared_value_usd', 0):,.2f} USD"
    commodity = shipment.get("commodity", "Refrigerated Goods")

    badge_bg = "#dc2626" if attr_key == "carrier" else ("#ea580c" if attr_key == "shipper" else ("#0284c7" if attr_key == "no_claim" else "#d97706"))

    header_data = [
        [
            Paragraph(f"<b>CLAIMOS COLD-CHAIN RECOVERY PACK</b><br/><font color='#475569'>Shipment Reference: <b>{ref}</b> | Commodity: {commodity}</font>", title_style),
            Paragraph(f"<b>PRELIMINARY ATTRIBUTION</b><br/><font color='{badge_bg}'><b>{attr_label.upper()}</b></font><br/><font size=6 color='#64748b'>Carmack Window: {shipment.get('claim_deadline_days', 9)} Days</font>", ParagraphStyle('HRight', parent=styles['Normal'], alignment=2, fontSize=8, leading=10))
        ]
    ]
    t_header = Table(header_data, colWidths=[380, 168])
    t_header.setStyle(TableStyle([
        ('VALIGN', (0,0), (-1,-1), 'MIDDLE'),
        ('BOTTOMPADDING', (0,0), (-1,-1), 2),
        ('TOPPADDING', (0,0), (-1,-1), 0),
    ]))
    elements.append(t_header)
    elements.append(HRFlowable(width="100%", thickness=1, color=colors.HexColor('#cbd5e1'), spaceBefore=4, spaceAfter=4))

    # 2. Key Metadata Grid (Parties & Cold Chain Baseline)
    parties_text = (
        f"<b>Carrier:</b> {shipment.get('carrier')}<br/>"
        f"<b>Broker:</b> {shipment.get('broker') or 'None (Direct)'}<br/>"
        f"<b>Shipper:</b> {shipment.get('shipper')}<br/>"
        f"<b>Receiver:</b> {shipment.get('receiver')}"
    )
    spec_min = shipment.get('spec_min_c')
    spec_max = shipment.get('spec_max_c')
    setpoint = shipment.get('bol_setpoint_c')
    setpoint_str = f"{setpoint} °C" if setpoint is not None else "<font color='#dc2626'><b>MISSING</b></font>"
    origin_pulp = shipment.get('origin_pulp_c')
    origin_pulp_str = f"{origin_pulp} °C" if origin_pulp is not None else "<font color='#dc2626'><b>MISSING</b></font>"

    baseline_text = (
        f"<b>Contract Specification:</b> {spec_min} °C to {spec_max} °C<br/>"
        f"<b>BOL Temperature Setpoint:</b> {setpoint_str}<br/>"
        f"<b>Origin Tender Pulp:</b> {origin_pulp_str}<br/>"
        f"<b>Declared Cargo Value:</b> <b>{declared_val}</b>"
    )

    meta_table = Table([
        [
            Paragraph("<b>Custody Chain & Parties</b>", section_heading),
            Paragraph("<b>Contract Temperature Baseline</b>", section_heading)
        ],
        [
            Paragraph(parties_text, cell_text),
            Paragraph(baseline_text, cell_text)
        ]
    ], colWidths=[274, 274])
    meta_table.setStyle(TableStyle([
        ('BACKGROUND', (0,0), (-1,-1), colors.HexColor('#f8fafc')),
        ('BOX', (0,0), (-1,-1), 0.5, colors.HexColor('#e2e8f0')),
        ('INNERGRID', (0,0), (-1,-1), 0.5, colors.HexColor('#e2e8f0')),
        ('TOPPADDING', (0,0), (-1,-1), 3),
        ('BOTTOMPADDING', (0,0), (-1,-1), 4),
        ('LEFTPADDING', (0,0), (-1,-1), 6),
        ('RIGHTPADDING', (0,0), (-1,-1), 6),
    ]))
    elements.append(meta_table)

    # 3. Attribution Reason & Dock Clean Trap Callout
    elements.append(Spacer(1, 4))
    reason_text = f"<b>Attribution Rationale:</b> {analysis.get('reason', '')}"
    if analysis.get('dock_clean_trap'):
        reason_text += " <font color='#b91c1c'><b>[DOCK-CLEAN TRAP ACTIVE: Dock temperature was in range at delivery, but continuous telemetry confirms prior in-transit thermal abuse].</b></font>"
    
    t_reason = Table([[Paragraph(reason_text, cell_text)]], colWidths=[548])
    t_reason.setStyle(TableStyle([
        ('BACKGROUND', (0,0), (-1,-1), colors.HexColor('#fef2f2') if attr_key == 'carrier' else colors.HexColor('#fffbeb')),
        ('BOX', (0,0), (-1,-1), 0.5, colors.HexColor('#f87171') if attr_key == 'carrier' else colors.HexColor('#fcd34d')),
        ('TOPPADDING', (0,0), (-1,-1), 3),
        ('BOTTOMPADDING', (0,0), (-1,-1), 3),
        ('LEFTPADDING', (0,0), (-1,-1), 6),
        ('RIGHTPADDING', (0,0), (-1,-1), 6),
    ]))
    elements.append(t_reason)

    # 4. Excursion Analysis Table
    elements.append(Paragraph("<b>Thermal Excursion Findings</b>", section_heading))
    excursions = analysis.get("excursions", [])
    exc_rows = [
        [
            Paragraph("<b>Start Window</b>", cell_bold),
            Paragraph("<b>Resolution</b>", cell_bold),
            Paragraph("<b>Peak Temp</b>", cell_bold),
            Paragraph("<b>Duration</b>", cell_bold),
            Paragraph("<b>Opening Party</b>", cell_bold),
            Paragraph("<b>Direction</b>", cell_bold)
        ]
    ]
    if excursions:
        for ex in excursions[:3]:  # Top 3
            exc_rows.append([
                Paragraph(str(ex.get("start_at", ""))[:16].replace("T", " "), cell_text),
                Paragraph(str(ex.get("end_at", ""))[:16].replace("T", " "), cell_text),
                Paragraph(f"<b><font color='#dc2626'>{ex.get('peak_c')} °C</font></b>", cell_bold),
                Paragraph(f"{ex.get('duration_hours', 'N/A')} hrs", cell_text),
                Paragraph(str(ex.get("opening_party", "")).capitalize(), cell_text),
                Paragraph(str(ex.get("direction", "")).upper(), cell_text)
            ])
    else:
        exc_rows.append([
            Paragraph("No thermal excursions detected against contract specification.", cell_text),
            "", "", "", "", ""
        ])

    t_exc = Table(exc_rows, colWidths=[105, 105, 70, 70, 100, 98])
    t_exc.setStyle(TableStyle([
        ('BACKGROUND', (0,0), (-1,0), colors.HexColor('#f1f5f9')),
        ('GRID', (0,0), (-1,-1), 0.5, colors.HexColor('#cbd5e1')),
        ('TOPPADDING', (0,0), (-1,-1), 2),
        ('BOTTOMPADDING', (0,0), (-1,-1), 2),
        ('LEFTPADDING', (0,0), (-1,-1), 4),
        ('RIGHTPADDING', (0,0), (-1,-1), 4),
        ('SPAN', (0,1), (-1,1)) if not excursions else ('VALIGN', (0,0), (-1,-1), 'MIDDLE')
    ]))
    elements.append(t_exc)

    # 5. Evidence Gaps & Missing Documents Table
    elements.append(Paragraph("<b>Evidence Gaps That Risk Claim Loss</b>", section_heading))
    gaps = analysis.get("gaps", [])
    gap_rows = [
        [
            Paragraph("<b>Severity</b>", cell_bold),
            Paragraph("<b>Category</b>", cell_bold),
            Paragraph("<b>Vulnerability Title</b>", cell_bold),
            Paragraph("<b>Impact & Operational Remedy</b>", cell_bold)
        ]
    ]
    if gaps:
        for g in gaps[:4]:  # Top 4 gaps
            sev = g.get("severity", "MEDIUM")
            sev_color = "#dc2626" if sev == "CRITICAL" else ("#ea580c" if sev == "HIGH" else "#475569")
            gap_rows.append([
                Paragraph(f"<font color='{sev_color}'><b>{sev}</b></font>", cell_bold),
                Paragraph(g.get("category", "General"), cell_text),
                Paragraph(f"<b>{g.get('title', '')}</b>", cell_text),
                Paragraph(g.get("description", ""), cell_text)
            ])
    else:
        gap_rows.append([
            Paragraph("<font color='#16a34a'><b>CLEAR</b></font>", cell_bold),
            Paragraph("Documentation", cell_text),
            Paragraph("No critical evidence gaps detected", cell_text),
            Paragraph("Telemetry timeline and required shipping documents are intact.", cell_text)
        ])

    t_gap = Table(gap_rows, colWidths=[65, 85, 140, 258])
    t_gap.setStyle(TableStyle([
        ('BACKGROUND', (0,0), (-1,0), colors.HexColor('#f1f5f9')),
        ('GRID', (0,0), (-1,-1), 0.5, colors.HexColor('#cbd5e1')),
        ('TOPPADDING', (0,0), (-1,-1), 2),
        ('BOTTOMPADDING', (0,0), (-1,-1), 2),
        ('LEFTPADDING', (0,0), (-1,-1), 4),
        ('RIGHTPADDING', (0,0), (-1,-1), 4),
    ]))
    elements.append(t_gap)

    # 6. Draft Notice Summary / 48-Hour Demand Excerpt
    elements.append(Paragraph("<b>48-Hour Carrier Notice Demand (Carmack Reservation of Rights)</b>", section_heading))
    notice_text = (
        f"DEMAND TO {shipment.get('carrier', 'CARRIER')}: Complete unedited digital reefer download (.txt/.csv/.dat) "
        f"and operational event log required within 48 hours. Product was tendered within specification [{spec_min}–{spec_max}°C] "
        f"and sustained excursion to peak {analysis.get('peak_excursion_temp', 'N/A')}°C while under carrier custody. "
        f"Notice is hereby given holding carrier liable up to declared cargo value {declared_val}."
    )
    t_notice = Table([[Paragraph(notice_text, notice_text_style)]], colWidths=[548])
    t_notice.setStyle(TableStyle([
        ('BACKGROUND', (0,0), (-1,-1), colors.HexColor('#f8fafc')),
        ('BOX', (0,0), (-1,-1), 0.5, colors.HexColor('#94a3b8')),
        ('TOPPADDING', (0,0), (-1,-1), 3),
        ('BOTTOMPADDING', (0,0), (-1,-1), 3),
        ('LEFTPADDING', (0,0), (-1,-1), 5),
        ('RIGHTPADDING', (0,0), (-1,-1), 5),
    ]))
    elements.append(t_notice)

    # 7. Mandatory Legal Notice Footer
    elements.append(Spacer(1, 4))
    elements.append(Paragraph(
        "Preliminary operational summary, not a legal determination. Generated autonomously by ClaimOS Freight Recovery Engine.",
        footer_style
    ))

    doc.build(elements)
    pdf_bytes = buffer.getvalue()
    buffer.close()
    return pdf_bytes
