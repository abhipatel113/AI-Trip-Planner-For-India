
from __future__ import annotations

import io

from reportlab.lib.enums import TA_LEFT, TA_RIGHT
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import mm
from reportlab.platypus import (
    HRFlowable,
    PageBreak,
    Paragraph,
    SimpleDocTemplate,
    Spacer,
    Table,
    TableStyle,
)
from reportlab.lib import colors

ORANGE = colors.HexColor("#EA6A20")
INK = colors.HexColor("#2B1D10")
MUTED = colors.HexColor("#6B6154")
RULE = colors.HexColor("#EFE6DB")


def _styles() -> dict[str, ParagraphStyle]:
    base = getSampleStyleSheet()["Normal"]
    return {
        "title": ParagraphStyle(
            "title",
            parent=base,
            fontName="Helvetica-Bold",
            fontSize=22,
            leading=26,
            textColor=ORANGE,
            spaceAfter=10,
        ),
        "meta": ParagraphStyle(
            "meta",
            parent=base,
            fontName="Helvetica",
            fontSize=10,
            textColor=MUTED,
            spaceAfter=10,
        ),
        "summary": ParagraphStyle(
            "summary",
            parent=base,
            fontName="Helvetica",
            fontSize=11,
            textColor=INK,
            leading=15,
            spaceAfter=10,
        ),
        "day": ParagraphStyle(
            "day",
            parent=base,
            fontName="Helvetica-Bold",
            fontSize=14,
            textColor=ORANGE,
        ),
        "cost": ParagraphStyle(
            "cost",
            parent=base,
            fontName="Helvetica",
            fontSize=10,
            textColor=MUTED,
            alignment=TA_RIGHT,
        ),
        "label": ParagraphStyle(
            "label",
            parent=base,
            fontName="Helvetica-Bold",
            fontSize=8,
            textColor=MUTED,
            leading=10,
        ),
        "body": ParagraphStyle(
            "body",
            parent=base,
            fontName="Helvetica",
            fontSize=11,
            textColor=INK,
            leading=15,
            alignment=TA_LEFT,
        ),
        "total": ParagraphStyle(
            "total",
            parent=base,
            fontName="Helvetica-Bold",
            fontSize=12,
            textColor=INK,
            spaceBefore=6,
        ),
    }


def _fmt_cost(v) -> str:
    try:
        return f"Rs. {int(v):,}"
    except (TypeError, ValueError):
        return f"Rs. {v}"


def build_pdf(itinerary: dict, meta: dict) -> bytes:
    """Return PDF bytes for the given itinerary + meta info."""
    buf = io.BytesIO()
    doc = SimpleDocTemplate(
        buf,
        pagesize=A4,
        leftMargin=18 * mm,
        rightMargin=18 * mm,
        topMargin=18 * mm,
        bottomMargin=18 * mm,
        title=f"Yatra — {meta.get('city', 'Trip')} itinerary",
    )
    s = _styles()
    flow: list = []

    flow.append(Paragraph(meta["city"], s["title"]))

    meta_bits = [
        f"{meta['days']} day{'s' if meta['days'] > 1 else ''}",
        f"Budget Rs. {meta['budget']}/day",
    ]
    if meta.get("style"):
        meta_bits.append(f"Style: {meta['style']}")
    if meta.get("diet"):
        meta_bits.append(f"Diet: {meta['diet']}")
    flow.append(Paragraph("  ·  ".join(meta_bits), s["meta"]))

    summary = itinerary.get("summary")
    if summary:
        flow.append(Paragraph(summary, s["summary"]))

    flow.append(HRFlowable(width="100%", color=RULE, spaceBefore=2, spaceAfter=10))

    grand_total = 0
    days = itinerary.get("days", []) or []

    for i, d in enumerate(days, start=1):
        cost = d.get("estimatedCost", 0) or 0
        try:
            grand_total += int(cost)
        except (TypeError, ValueError):
            pass

        header = Table(
            [[Paragraph(f"Day {i}", s["day"]), Paragraph(f"≈ {_fmt_cost(cost)}", s["cost"])]],
            colWidths=[None, 90],
        )
        header.setStyle(TableStyle([("VALIGN", (0, 0), (-1, -1), "BOTTOM")]))
        flow.append(header)
        flow.append(Spacer(1, 4))

        rows = []
        for label, key in (("MORNING", "morning"), ("AFTERNOON", "afternoon"), ("EVENING", "evening")):
            rows.append(
                [
                    Paragraph(label, s["label"]),
                    Paragraph(str(d.get(key, "") or "—"), s["body"]),
                ]
            )
        food = d.get("food") or []
        if food:
            food_html = "<br/>".join(f"• {item}" for item in food)
            rows.append([Paragraph("FOOD TO TRY", s["label"]), Paragraph(food_html, s["body"])])

        slot_table = Table(rows, colWidths=[70, None])
        slot_table.setStyle(
            TableStyle(
                [
                    ("VALIGN", (0, 0), (-1, -1), "TOP"),
                    ("BOTTOMPADDING", (0, 0), (-1, -1), 6),
                    ("TOPPADDING", (0, 0), (-1, -1), 2),
                ]
            )
        )
        flow.append(slot_table)

        if i < len(days):
            flow.append(Spacer(1, 6))
            flow.append(HRFlowable(width="100%", color=RULE, spaceAfter=8))

    flow.append(Spacer(1, 10))
    flow.append(Paragraph(f"Estimated total: {_fmt_cost(grand_total)}", s["total"]))

    def _footer(canvas, _doc):
        canvas.saveState()
        canvas.setFont("Helvetica", 8)
        canvas.setFillColor(MUTED)
        canvas.drawString(18 * mm, 10 * mm, f"Yatra · {meta['city']} itinerary")
        canvas.drawRightString(
            A4[0] - 18 * mm, 10 * mm, f"Page {_doc.page}"
        )
        canvas.restoreState()

    doc.build(flow, onFirstPage=_footer, onLaterPages=_footer)
    return buf.getvalue()


def pdf_filename(city: str, days: int) -> str:
    safe = "".join(c.lower() if c.isalnum() else "-" for c in city).strip("-") or "trip"
    return f"yatra-{safe}-{days}d.pdf"