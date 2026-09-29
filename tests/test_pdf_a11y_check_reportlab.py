"""The same checks on PDFs made by ReportLab (skipped when ReportLab is not installed)."""
import io

import pytest

pytest.importorskip("reportlab")

from reportlab.lib.pagesizes import letter  # noqa: E402
from reportlab.pdfbase import pdfmetrics  # noqa: E402
from reportlab.pdfbase.ttfonts import TTFont  # noqa: E402
from reportlab.pdfgen import canvas  # noqa: E402

from pdf_a11y_check import check_pdf  # noqa: E402


def _pdf(draw, **kw) -> bytes:
    buf = io.BytesIO()
    c = canvas.Canvas(buf, pagesize=letter, **kw)
    draw(c)
    c.showPage()
    c.save()
    return buf.getvalue()


def test_plain_reportlab_page_is_untagged_with_standard_font():
    def draw(c):
        c.setTitle("Lunch menu - Example Diner")
        c.setFont("Helvetica", 14)
        c.drawString(72, 700, "Soup of the day with bread, 7.50")
    r = check_pdf(_pdf(draw))
    assert r.finding("tagged").severity == "error"
    assert r.finding("lang").severity == "error"
    assert "Helvetica (standard 14)" in r.finding("fonts-embedded").details
    assert "text" in r.passed
    assert r.stats["title"] == "Lunch menu - Example Diner"


def test_reportlab_truetype_font_is_embedded():
    pdfmetrics.registerFont(TTFont("Vera", "Vera.ttf"))  # ships with ReportLab

    def draw(c):
        c.setFont("Vera", 14)
        c.drawString(72, 700, "Brochure: spring classes at the example.ca studio")
    r = check_pdf(_pdf(draw, pageCompression=1))
    assert "fonts-embedded" in r.passed
    assert "text" in r.passed


def test_reportlab_form_fields_tooltips():
    def draw(c):
        c.setFont("Helvetica", 12)
        c.drawString(72, 720, "Catering request form for Example Diner")
        c.acroForm.textfield(name="guest_name", tooltip="Your full name", x=72, y=650, width=200, height=20)
        c.acroForm.textfield(name="guest_phone", x=72, y=600, width=200, height=20)
    r = check_pdf(_pdf(draw))
    f = r.finding("form-tooltips")
    assert f is not None and f.details == ["guest_phone"]
    assert r.stats["form_fields"] == 2


def test_reportlab_link_without_contents():
    def draw(c):
        c.setFont("Helvetica", 12)
        c.drawString(72, 720, "Order online at example.ca or call 506-555-0199")
        c.linkURL("https://example.ca/order", (72, 715, 300, 735))
    r = check_pdf(_pdf(draw))
    assert "link-target" in r.passed
    assert r.finding("link-contents").details == ["page 1: https://example.ca/order"]
