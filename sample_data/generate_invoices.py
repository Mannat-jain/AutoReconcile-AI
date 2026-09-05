"""
generate_invoices.py
Generates 5 realistic vendor invoice PDFs into sample_data/invoices/.
Each invoice is deliberately designed to exercise a specific reconciliation
scenario when matched against razorpay_payouts_log.csv and bank_statement.csv:

  INV-1001  -> Perfect match (clean, auto-payout eligible)
  INV-1002  -> Price mismatch (invoice total != settlement amount)
  INV-1003  -> Missing TDS deduction (vendor invoice doesn't reflect 10% TDS
               that bank statement shows was withheld)
  INV-1004  -> Duplicate invoice (same invoice number/amount submitted twice
               historically -> should be flagged)
  INV-1005  -> Bank account mismatch (IFSC/account number on invoice differs
               from the payout beneficiary on record)

Run: python generate_invoices.py
"""
import os
from reportlab.lib.pagesizes import A4
from reportlab.lib.units import mm
from reportlab.lib import colors
from reportlab.pdfgen import canvas

OUT_DIR = os.path.join(os.path.dirname(__file__), "invoices")
os.makedirs(OUT_DIR, exist_ok=True)


def draw_invoice(filename, data):
    path = os.path.join(OUT_DIR, filename)
    c = canvas.Canvas(path, pagesize=A4)
    width, height = A4

    # Header
    c.setFillColor(colors.HexColor("#0f172a"))
    c.rect(0, height - 30 * mm, width, 30 * mm, fill=1, stroke=0)
    c.setFillColor(colors.white)
    c.setFont("Helvetica-Bold", 18)
    c.drawString(20 * mm, height - 15 * mm, data["vendor_name"])
    c.setFont("Helvetica", 9)
    c.drawString(20 * mm, height - 22 * mm, f"GSTIN: {data['gstin']}")

    c.setFillColor(colors.black)
    c.setFont("Helvetica-Bold", 14)
    c.drawRightString(width - 20 * mm, height - 15 * mm, "TAX INVOICE")
    c.setFont("Helvetica", 10)
    c.drawRightString(width - 20 * mm, height - 22 * mm, f"Invoice #: {data['invoice_no']}")

    y = height - 42 * mm
    c.setFont("Helvetica", 10)
    c.drawString(20 * mm, y, f"Invoice Date: {data['invoice_date']}")
    c.drawString(20 * mm, y - 6 * mm, f"Due Date: {data['due_date']}")
    c.drawString(20 * mm, y - 12 * mm, f"Bill To: {data['bill_to']}")

    c.drawString(120 * mm, y, f"Bank: {data['bank_name']}")
    c.drawString(120 * mm, y - 6 * mm, f"Account No: {data['account_no']}")
    c.drawString(120 * mm, y - 12 * mm, f"IFSC: {data['ifsc']}")

    # Line items table
    y -= 26 * mm
    c.setFont("Helvetica-Bold", 10)
    c.setFillColor(colors.HexColor("#f1f5f9"))
    c.rect(20 * mm, y - 2 * mm, width - 40 * mm, 8 * mm, fill=1, stroke=0)
    c.setFillColor(colors.black)
    c.drawString(22 * mm, y, "Description")
    c.drawString(110 * mm, y, "Qty")
    c.drawString(130 * mm, y, "Unit Price")
    c.drawString(160 * mm, y, "Amount")

    c.setFont("Helvetica", 9)
    y -= 10 * mm
    subtotal = 0
    for item in data["line_items"]:
        amount = item["qty"] * item["unit_price"]
        subtotal += amount
        c.drawString(22 * mm, y, item["desc"])
        c.drawString(110 * mm, y, str(item["qty"]))
        c.drawRightString(150 * mm, y, f"{item['unit_price']:,.2f}")
        c.drawRightString(180 * mm, y, f"{amount:,.2f}")
        y -= 7 * mm

    y -= 3 * mm
    c.line(20 * mm, y, width - 20 * mm, y)
    y -= 7 * mm

    gst_amount = subtotal * data.get("gst_rate", 0.18)
    total = subtotal + gst_amount

    c.setFont("Helvetica", 9)
    c.drawRightString(150 * mm, y, "Subtotal:")
    c.drawRightString(180 * mm, y, f"{subtotal:,.2f}")
    y -= 6 * mm
    c.drawRightString(150 * mm, y, f"GST ({int(data.get('gst_rate', 0.18)*100)}%):")
    c.drawRightString(180 * mm, y, f"{gst_amount:,.2f}")
    y -= 6 * mm

    if data.get("show_tds"):
        tds = total * data.get("tds_rate", 0.10)
        total_after_tds = total - tds
        c.drawRightString(150 * mm, y, f"TDS Deducted ({int(data.get('tds_rate',0.10)*100)}%):")
        c.drawRightString(180 * mm, y, f"-{tds:,.2f}")
        y -= 6 * mm
        c.setFont("Helvetica-Bold", 11)
        c.drawRightString(150 * mm, y, "Net Payable:")
        c.drawRightString(180 * mm, y, f"{total_after_tds:,.2f}")
    else:
        c.setFont("Helvetica-Bold", 11)
        c.drawRightString(150 * mm, y, "Total Payable:")
        c.drawRightString(180 * mm, y, f"{total:,.2f}")

    y -= 20 * mm
    c.setFont("Helvetica-Oblique", 8)
    c.setFillColor(colors.grey)
    c.drawString(20 * mm, y, "This is a computer-generated invoice for demo/reconciliation testing purposes only.")

    c.showPage()
    c.save()
    print(f"Generated {path}")


invoices = [
    # 1. Perfect match
    dict(
        filename="INV-1001_CloudNine_Hosting.pdf",
        vendor_name="CloudNine Hosting Pvt Ltd",
        gstin="29ABCDE1234F1Z5",
        invoice_no="INV-1001",
        invoice_date="2026-08-01",
        due_date="2026-08-15",
        bill_to="Zenith Labs Pvt Ltd",
        bank_name="HDFC Bank",
        account_no="50100234567890",
        ifsc="HDFC0001234",
        line_items=[
            {"desc": "Cloud Server Hosting - Aug 2026", "qty": 1, "unit_price": 45000.00},
            {"desc": "Managed Backup Service", "qty": 1, "unit_price": 5000.00},
        ],
        gst_rate=0.18,
        show_tds=False,
    ),
    # 2. Price mismatch (invoice says 88500 but settlement log will show 92500)
    dict(
        filename="INV-1002_Bright_Ads_Media.pdf",
        vendor_name="Bright Ads Media LLP",
        gstin="07PQRSX5678K1Z2",
        invoice_no="INV-1002",
        invoice_date="2026-08-03",
        due_date="2026-08-18",
        bill_to="Zenith Labs Pvt Ltd",
        bank_name="ICICI Bank",
        account_no="000701234567",
        ifsc="ICIC0000007",
        line_items=[
            {"desc": "Performance Marketing Campaign - Q3", "qty": 1, "unit_price": 75000.00},
        ],
        gst_rate=0.18,
        show_tds=False,
    ),
    # 3. Missing TDS on invoice, but bank statement will show net-of-TDS payout
    dict(
        filename="INV-1003_Sharma_Consulting.pdf",
        vendor_name="Sharma & Associates Consulting",
        gstin="27LMNOQ4321P1Z8",
        invoice_no="INV-1003",
        invoice_date="2026-08-05",
        due_date="2026-08-20",
        bill_to="Zenith Labs Pvt Ltd",
        bank_name="Axis Bank",
        account_no="912010012345678",
        ifsc="UTIB0001122",
        line_items=[
            {"desc": "Professional Fees - Financial Advisory (Aug)", "qty": 1, "unit_price": 100000.00},
        ],
        gst_rate=0.18,
        show_tds=False,  # Invoice does NOT show TDS -> anomaly vs bank statement
    ),
    # 4. Duplicate invoice number/amount (a second, near-identical copy)
    dict(
        filename="INV-1004_Metro_Office_Supplies.pdf",
        vendor_name="Metro Office Supplies Co.",
        gstin="19WXYZC8765D1Z3",
        invoice_no="INV-1004",
        invoice_date="2026-08-07",
        due_date="2026-08-21",
        bill_to="Zenith Labs Pvt Ltd",
        bank_name="Kotak Mahindra Bank",
        account_no="8802345671",
        ifsc="KKBK0000456",
        line_items=[
            {"desc": "Office Stationery & Supplies - Aug batch", "qty": 1, "unit_price": 18500.00},
        ],
        gst_rate=0.18,
        show_tds=False,
    ),
    # 5. Bank account mismatch (invoice bank details differ from Razorpay beneficiary)
    dict(
        filename="INV-1005_Velocity_Logistics.pdf",
        vendor_name="Velocity Logistics Pvt Ltd",
        gstin="33AACCV1122B1Z9",
        invoice_no="INV-1005",
        invoice_date="2026-08-09",
        due_date="2026-08-24",
        bill_to="Zenith Labs Pvt Ltd",
        bank_name="State Bank of India",
        account_no="30012345678",
        ifsc="SBIN0001234",
        line_items=[
            {"desc": "Freight & Warehousing Charges - Aug", "qty": 1, "unit_price": 60000.00},
        ],
        gst_rate=0.18,
        show_tds=False,
    ),
]

for inv in invoices:
    fname = inv.pop("filename")
    draw_invoice(fname, inv)

# Duplicate copy of INV-1004 filed again by mistake (same vendor/amount/number)
dup = dict(
    vendor_name="Metro Office Supplies Co.",
    gstin="19WXYZC8765D1Z3",
    invoice_no="INV-1004",
    invoice_date="2026-08-07",
    due_date="2026-08-21",
    bill_to="Zenith Labs Pvt Ltd",
    bank_name="Kotak Mahindra Bank",
    account_no="8802345671",
    ifsc="KKBK0000456",
    line_items=[
        {"desc": "Office Stationery & Supplies - Aug batch", "qty": 1, "unit_price": 18500.00},
    ],
    gst_rate=0.18,
    show_tds=False,
)
draw_invoice("INV-1004_Metro_Office_Supplies_DUPLICATE_SUBMISSION.pdf", dup)

print("\nAll sample invoices generated successfully.")
