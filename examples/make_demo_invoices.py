"""Generate three demo invoices with invoice-pdf-canada, then check them.

    python examples/make_demo_invoices.py [path/to/invoice-pdf-canada]
    python -m pdf_a11y_check examples/demo-invoices

invoice-pdf-canada (https://github.com/dreadmoreeee/invoice-pdf-canada) must be
installed, or its source folder given as the first argument. All names, e-mails
and phone numbers below are invented.
"""
import json
import sys
from pathlib import Path

sys.dont_write_bytecode = True  # do not leave __pycache__ in the other project
if len(sys.argv) > 1:
    sys.path.insert(0, str(Path(sys.argv[1]).resolve()))

from invoice_pdf_canada import load_invoice, render_pdf  # noqa: E402

OUT = Path(__file__).resolve().parent / "demo-invoices"

SELLER = {
    "name": "Tidewater Web Co.",
    "address": ["200 Example Street", "Miramichi, NB  E1V 0A1"],
    "email": "billing@tidewater.example.ca",
    "phone": "506-555-0100",
    "gst_hst_number": "123456789 RT0001",
}

INVOICES = {
    "invoice-nb-en.json": {
        "number": "TW-2026-0101", "issue_date": "2026-09-15", "due_date": "2026-10-15",
        "language": "en", "province": "NB", "seller": SELLER,
        "buyer": {"name": "Harbourview Bakery", "address": ["12 Wharf Road", "Moncton, NB  E1C 0B2"],
                  "email": "orders@harbourview.example.ca"},
        "lines": [
            {"description": "Menu redesign (print and PDF)", "quantity": 1, "unit_price": "650.00"},
            {"description": "Online ordering page (hours)", "quantity": "4.5", "unit_price": "85.00"},
        ],
        "notes": "Payment by Interac e-Transfer to billing@tidewater.example.ca. Questions: 506-555-0100.",
    },
    "invoice-qc-fr.json": {
        "number": "TW-2026-0102", "issue_date": "2026-09-20", "due_date": "2026-10-20",
        "language": "fr", "province": "QC",
        "seller": dict(SELLER, qst_number="1234567890 TQ0001"),
        "buyer": {"name": "Cafe du Vieux-Port", "address": ["8 rue de l'Exemple", "Quebec, QC  G1K 0C3"],
                  "email": "compta@vieuxport.example.ca"},
        "lines": [
            {"description": "Site web bilingue (5 pages)", "quantity": 1, "unit_price": "1400.00"},
            {"description": "Hebergement, 12 mois", "quantity": 12, "unit_price": "12.00"},
        ],
        "notes": "Paiement par virement Interac. Merci!",
    },
    "invoice-on-en.json": {
        "number": "TW-2026-0103", "issue_date": "2026-09-25",
        "language": "en", "province": "ON", "seller": SELLER,
        "buyer": {"name": "Maple Lane Dental", "address": ["300 Sample Avenue", "Ottawa, ON  K1A 0B4"],
                  "email": "office@maplelane.example.ca"},
        "lines": [
            {"description": "Accessible appointment form", "quantity": 1, "unit_price": "480.00"},
            {"description": "Stripe payment link setup (hours)", "quantity": 2, "unit_price": "85.00"},
        ],
    },
}


def main() -> None:
    OUT.mkdir(exist_ok=True)
    for name, data in INVOICES.items():
        src = OUT / name
        src.write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")
        pdf = src.with_suffix(".pdf")
        size = len(render_pdf(load_invoice(src), pdf))
        print(f"wrote {pdf.relative_to(OUT.parent.parent)} ({size:,} bytes)")


if __name__ == "__main__":
    main()
