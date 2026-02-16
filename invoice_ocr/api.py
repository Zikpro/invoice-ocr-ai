import re
import os
import tempfile
import frappe

from pdf2image import convert_from_path
from invoice_ocr.vision.ocr_engine import run_vision_ocr


# ============================================================
# PDF → IMAGE CONVERTER
# ============================================================

def convert_pdf_to_image(file_path):
    """
    Convert first page of PDF to PNG
    Returns temporary image file path
    """
    images = convert_from_path(file_path, dpi=300)

    if not images:
        return None

    temp_dir = tempfile.gettempdir()
    output_path = os.path.join(temp_dir, "converted_invoice.png")

    images[0].save(output_path, "PNG")

    return output_path


# ============================================================
# UTILITIES
# ============================================================

def detect_currency(text):
    t = text.upper()
    if "£" in t or "GBP" in t:
        return "GBP"
    if "$" in t or "USD" in t:
        return "USD"
    if "€" in t or "EUR" in t:
        return "EUR"
    if "₨" in t or "PKR" in t:
        return "PKR"
    return frappe.defaults.get_global_default("currency")


def extract_grand_total(text):
    match = re.search(
        r"Grand Total[:\s]*[£$€₹₨]?\s?([\d,]+\.\d{2})",
        text,
        re.IGNORECASE
    )
    if match:
        return float(match.group(1).replace(",", ""))
    return None


def extract_any_date(text):
    patterns = [
        r"\b\d{2}-\d{2}-\d{4}\b",
        r"\b\d{2}/\d{2}/\d{4}\b",
        r"\b\d{4}-\d{2}-\d{2}\b"
    ]

    for pattern in patterns:
        match = re.search(pattern, text)
        if match:
            return match.group(0)

    return None


# ============================================================
# RUN OCR PIPELINE (FULL STABLE VERSION)
# ============================================================

@frappe.whitelist()
def run_ocr(docname):

    from frappe.utils import getdate
    from invoice_ocr.ai.ocr_nodes import (
        extract_header,
        extract_items,
        extract_taxes,
        score_confidence
    )
    from invoice_ocr.intelligence.supplier_matcher import intelligent_supplier_match
    from invoice_ocr.intelligence.line_classifier import classify_lines
    from invoice_ocr.intelligence.financial_validator import validate_financials

    doc = frappe.get_doc("Invoice OCR", docname)
    # ========================================================
    # 1️⃣ FILE VALIDATION (FRAPPE SAFE METHOD)
    # ========================================================

    if not doc.invoice_file:
        frappe.throw("Please upload invoice file before running OCR")

    # Fetch File Doc properly
    file_doc = frappe.get_doc("File", {"file_url": doc.invoice_file})

    if not file_doc:
        frappe.throw("File record not found in system")

    # Get real path safely
    file_path = file_doc.get_full_path()

    if not os.path.exists(file_path):
        frappe.log_error(file_path, "Invoice File Not Found")
        frappe.throw("Invoice file not found on server")


    # ========================================================
    # 2️⃣ VISION OCR (PDF + IMAGE SAFE)
    # ========================================================

    try:

        if file_path.lower().endswith(".pdf"):
            image_path = convert_pdf_to_image(file_path)

            if not image_path or not os.path.exists(image_path):
                frappe.throw("PDF conversion failed")

            raw = run_vision_ocr(image_path)

        else:
            raw = run_vision_ocr(file_path)

    except Exception as e:
        frappe.log_error(str(e), "OCR Processing Failed")
        frappe.throw("OCR processing failed. Please check error logs.")

    doc.raw_ocr_text = raw

    # ========================================================
    # 3️⃣ AI EXTRACTION PIPELINE
    # ========================================================

    state = {
        "ocr_text": raw,
        "header": {},
        "items": [],
        "taxes": [],
        "confidence": 0
    }

    state = extract_header(state)
    state = extract_items(state)
    state = extract_taxes(state)
    state = score_confidence(state)

    # ========================================================
    # 4️⃣ LINE CLASSIFICATION
    # ========================================================

    state = classify_lines(state)

    header = state.get("header") or {}
    confidence = state.get("confidence", 60)

    # ========================================================
    # 5️⃣ SUPPLIER MATCHING
    # ========================================================

    supplier_meta = {}
    detected_supplier = None
    supplier_name = header.get("supplier_name")

    if supplier_name:
        result = intelligent_supplier_match(supplier_name)

        if isinstance(result, dict):
            detected_supplier = result.get("supplier")
            supplier_meta = result
        else:
            detected_supplier = result

    if detected_supplier:
        doc.supplier = detected_supplier

    state["supplier_match_meta"] = supplier_meta

    # ========================================================
    # 6️⃣ SAFE HEADER SAVE (DATE FALLBACK)
    # ========================================================

    doc.invoice_number = header.get("invoice_number")

    raw_date = header.get("invoice_date")

    if not raw_date:
        raw_date = extract_any_date(raw)

    try:
        doc.invoice_date = getdate(raw_date) if raw_date else None
    except Exception:
        doc.invoice_date = None

    if not doc.currency:
        doc.currency = header.get("currency") or detect_currency(raw)

    # ========================================================
    # 7️⃣ BUILD ITEMS (ROBUST VERSION)
    # ========================================================

    doc.items = []
    net_total = 0

    for it in state.get("items", []):

    # ✅ Accept both VALID_ITEM and HEADER_ROW
        if it.get("classification") not in ["VALID_ITEM", "HEADER_ROW"]:
            continue

        item_name = it.get("item_name")
        if not item_name:
            continue

        qty = float(it.get("qty") or 1)
        rate = float(it.get("rate") or 0)
        amount = float(it.get("amount") or (qty * rate))

        # Skip zero-value junk rows
        if amount == 0 and rate == 0:
            continue

        net_total += amount

        doc.append("items", {
            "item_name": item_name,
            "qty": qty,
            "rate": rate,
            "uom": "Nos"
        })

    # ========================================================
    # 9️⃣ GRAND TOTAL DETECTION
    # ========================================================

    detected_grand_total = extract_grand_total(raw)

    # ========================================================
    # 🔟 PREPARE FINANCIAL STATE
    # ========================================================

    state["net_total"] = net_total
    state["detected_grand_total"] = detected_grand_total

    # 🔥 Fallback VAT calculation BEFORE building tax table
    if (
        (not state.get("taxes"))
        and detected_grand_total
        and net_total
    ):
        calculated_tax = round(detected_grand_total - net_total, 2)

        if calculated_tax > 0:
            state["taxes"] = [{
                "charge_type": "Actual",
                "account_head": None,
                "label": "Auto VAT",
                "rate": 0,
                "amount": calculated_tax
            }]

    # ========================================================
    # 8️⃣ BUILD TAXES (NOW AFTER FALLBACK)
    # ========================================================

    doc.set("taxes", [])
    tax_total = 0

    company = frappe.defaults.get_user_default("Company")

    if not company:
        company = frappe.db.get_single_value("Global Defaults", "default_company")

    valid_tax_account = frappe.db.get_value(
        "Account",
        {
            "company": company,
            "account_type": "Tax",
            "is_group": 0
        },
        "name"
    )

    for tx in state.get("taxes", []):

        amount = float(tx.get("amount") or 0)

        if amount <= 0:
            continue

        tax_total += amount

        doc.append("taxes", {
            "charge_type": tx.get("charge_type") or "Actual",
            "account_head": valid_tax_account,
            "description": tx.get("label") or "VAT",
            "rate": float(tx.get("rate") or 0),
            "tax_amount": amount
        })

    state["tax_total"] = tax_total
    doc.tax_total = tax_total

    # ========================================================
    # 🔟 FINANCIAL VALIDATION
    # ========================================================

    financial_report = validate_financials(state)

    confidence += financial_report.get("confidence_adjustment", 0)
    confidence = max(0, min(100, confidence))

    doc.financial_risk = financial_report.get("risk_level")
    doc.calculated_grand_total = financial_report.get("calculated_grand_total")
    doc.financial_mismatch = financial_report.get("mismatch_amount")
    doc.is_financial_valid = financial_report.get("is_valid")


    # ========================================================
    # 1️⃣1️⃣ FINAL TOTALS
    # ========================================================

    doc.net_total = net_total
    doc.tax_total = tax_total

    doc.grand_total = (
        detected_grand_total
        or doc.calculated_grand_total
        or (net_total + tax_total)
    )

    # ========================================================
    # 1️⃣2️⃣ SAVE FINAL
    # ========================================================

    state["financial_validation"] = financial_report

    doc.semantic_invoice_json = frappe.as_json(state, indent=2)

    doc.confidence = confidence
    doc.status = "Ready"

    doc.flags.ignore_mandatory = True
    doc.save(ignore_permissions=True)
    frappe.db.commit()

    return {
        "confidence": confidence,
        "net_total": doc.net_total,
        "tax_total": doc.tax_total,
        "grand_total": doc.grand_total,
        "risk_level": doc.financial_risk,
        "is_valid": doc.is_financial_valid
    }


    # ============================================================
    # 2️⃣ CREATE PURCHASE INVOICE
    # ============================================================

    pi = frappe.new_doc("Purchase Invoice")

    pi.company = company
    pi.supplier = doc.supplier
    pi.bill_no = doc.invoice_number
    pi.bill_date = doc.invoice_date
    pi.posting_date = doc.invoice_date
    pi.currency = doc.currency
    pi.update_stock = 0

    # ============================================================
    # 3️⃣ LOAD SUPPLIER MEMORY (If Exists)
    # ============================================================

    profile = frappe.db.exists(
        "Supplier AI Profile",
        {"supplier": doc.supplier}
    )

    memory = None

    if profile:
        memory = frappe.get_doc("Supplier AI Profile", profile)

    # ============================================================
    # 4️⃣ ITEMS SECTION
    # ============================================================

    for row in doc.items:

        # Priority:
        # 1. Supplier Memory
        # 2. First Expense Account
        # 3. Throw error

        expense_account = None

        if memory and memory.default_expense_account:
            expense_account = memory.default_expense_account
        else:
            expense_account = frappe.db.get_value(
                "Account",
                {
                    "company": company,
                    "root_type": "Expense",
                    "is_group": 0
                },
                "name"
            )

        if not expense_account:
            frappe.throw("No Expense Account found for this company")

        pi.append("items", {
            "item_name": row.item_name,
            "description": row.item_name,
            "qty": row.qty or 1,
            "rate": row.rate or 0,
            "expense_account": expense_account
        })

    # ============================================================
    # 5️⃣ TAX SECTION (Company Safe Mapping)
    # ============================================================

    if doc.taxes:

        company_tax_accounts = frappe.get_all(
            "Account",
            filters={
                "company": company,
                "account_type": "Tax",
                "is_group": 0
            },
            fields=["name"]
        )

        valid_tax_accounts = [a.name for a in company_tax_accounts]

        for tax in doc.taxes:

            account_head = None

            # Priority:
            # 1. Valid detected tax account
            # 2. Supplier memory tax account
            # 3. First company tax account

            if tax.account_head in valid_tax_accounts:
                account_head = tax.account_head

            elif memory and memory.default_tax_account in valid_tax_accounts:
                account_head = memory.default_tax_account

            elif valid_tax_accounts:
                account_head = valid_tax_accounts[0]

            if not account_head:
                continue

            pi.append("taxes", {
                "charge_type": tax.charge_type or "On Net Total",
                "account_head": account_head,
                "description": tax.description or account_head,
                "rate": tax.rate or 0,
                "tax_amount": tax.tax_amount or 0
            })

    # ============================================================
    # 6️⃣ INSERT & SUBMIT
    # ============================================================

    pi.insert(ignore_permissions=True)

    if pi.docstatus == 0:
        pi.submit()

    # ============================================================
    # 7️⃣ UPDATE SUPPLIER MEMORY
    # ============================================================

    try:
        from invoice_ocr.intelligence.supplier_memory import update_supplier_memory
        update_supplier_memory(pi)
    except Exception as e:
        frappe.log_error(str(e), "Supplier Memory Update Failed")

    # ============================================================
    # 8️⃣ LINK BACK
    # ============================================================

    doc.purchase_invoice = pi.name
    doc.status = "Posted"
    doc.save(ignore_permissions=True)

    frappe.db.commit()

    return {
        "purchase_invoice": pi.name,
        "status": "Submitted"
    }
