"""
Export service — generates PDF and CSV reports from meeting data.

All functions are pure (no I/O, no side effects) — data is passed in as
arguments, bytes are returned. This makes them trivially testable and
keeps the API layer thin.
"""

import csv
import io
import re

from reportlab.lib import colors
from reportlab.lib.pagesizes import letter
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import inch
from reportlab.platypus import (
    Paragraph,
    SimpleDocTemplate,
    Spacer,
    Table,
    TableStyle,
)

from app.models.meeting import MeetingInDB


def export_as_csv(meeting: MeetingInDB) -> bytes:
    """Generates a UTF-8 CSV with sections: metadata, summary, action items, decisions, keywords."""
    buf = io.StringIO()
    writer = csv.writer(buf)

    # Metadata
    writer.writerow(["Field", "Value"])
    writer.writerow(["Title", meeting.title])
    writer.writerow(["Status", meeting.status.value])
    writer.writerow(["Created", meeting.created_at.isoformat()])
    writer.writerow(["Sentiment", meeting.sentiment or ""])
    writer.writerow([])

    # Summary
    writer.writerow(["Summary"])
    writer.writerow([meeting.summary or ""])
    writer.writerow([])

    # Action Items
    writer.writerow(["Action Items"])
    writer.writerow(["Person", "Task", "Deadline"])
    for item in meeting.action_items:
        writer.writerow([item.person, item.task, item.deadline or ""])
    writer.writerow([])

    # Decisions
    writer.writerow(["Decisions"])
    for d in meeting.decisions:
        writer.writerow([d])
    writer.writerow([])

    # Keywords
    writer.writerow(["Keywords"])
    writer.writerow([", ".join(meeting.keywords)])

    return buf.getvalue().encode("utf-8")


def export_as_pdf(meeting: MeetingInDB) -> bytes:
    """Generates a PDF report with header, summary, action items, decisions, keywords, and transcript."""
    buf = io.BytesIO()
    doc = SimpleDocTemplate(buf, pagesize=letter, topMargin=0.5 * inch, bottomMargin=0.5 * inch)
    styles = getSampleStyleSheet()
    story = []

    # Custom styles
    title_style = ParagraphStyle("CustomTitle", parent=styles["Title"], fontSize=18, spaceAfter=6)
    heading_style = ParagraphStyle("CustomHeading", parent=styles["Heading2"], fontSize=12, spaceAfter=6, spaceBefore=12, textColor=colors.HexColor("#6d28d9"))
    body_style = ParagraphStyle("CustomBody", parent=styles["Normal"], fontSize=10, leading=14, spaceAfter=6)
    small_style = ParagraphStyle("Small", parent=styles["Normal"], fontSize=9, textColor=colors.grey, spaceAfter=4)

    # Header
    story.append(Paragraph(meeting.title, title_style))
    story.append(Paragraph(f"Created: {meeting.created_at.strftime('%B %d, %Y')} | Sentiment: {meeting.sentiment or 'N/A'}", small_style))
    story.append(Spacer(1, 12))

    # Summary
    if meeting.summary:
        story.append(Paragraph("Summary", heading_style))
        story.append(Paragraph(meeting.summary, body_style))

    # Action Items
    if meeting.action_items:
        story.append(Paragraph("Action Items", heading_style))
        table_data = [["Person", "Task", "Deadline"]]
        for item in meeting.action_items:
            table_data.append([item.person, item.task, item.deadline or "-"])
        table = Table(table_data, colWidths=[1.5 * inch, 3.5 * inch, 1.5 * inch])
        table.setStyle(TableStyle([
            ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#6d28d9")),
            ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
            ("FONTSIZE", (0, 0), (-1, -1), 9),
            ("GRID", (0, 0), (-1, -1), 0.5, colors.lightgrey),
            ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, colors.HexColor("#f5f3ff")]),
            ("VALIGN", (0, 0), (-1, -1), "TOP"),
            ("TOPPADDING", (0, 0), (-1, -1), 4),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
        ]))
        story.append(table)
        story.append(Spacer(1, 6))

    # Decisions
    if meeting.decisions:
        story.append(Paragraph("Decisions", heading_style))
        for i, d in enumerate(meeting.decisions, 1):
            story.append(Paragraph(f"{i}. {_strip_html(d)}", body_style))

    # Keywords
    if meeting.keywords:
        story.append(Paragraph("Keywords", heading_style))
        story.append(Paragraph(", ".join(meeting.keywords), body_style))

    # Transcript
    if meeting.cleaned_transcript:
        story.append(Paragraph("Cleaned Transcript", heading_style))
        # Limit transcript length for PDF
        transcript = meeting.cleaned_transcript[:10000]
        if len(meeting.cleaned_transcript) > 10000:
            transcript += "\n... (truncated)"
        story.append(Paragraph(_strip_html(transcript).replace("\n", "<br/>"), body_style))

    doc.build(story)
    return buf.getvalue()


def _strip_html(text: str) -> str:
    """Removes HTML tags from a string."""
    return re.sub(r"<[^>]+>", "", text)
