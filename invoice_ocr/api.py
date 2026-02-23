import re
import os
import base64   # ✅ ADD THIS
import frappe
from frappe.utils import getdate
from invoice_ocr.vision.ocr_engine import run_vision_ocr


# ============================================================
# CAMERA / FILE UPLOAD (FRAPPE 15 SAFE)
# ============================================================

@frappe.whitelist()
def upload_camera_image(docname, filedata, filename):

    if not docname:
        frappe.throw("Document name missing")

    if not filedata:
        frappe.throw("No file data received")

    if "," not in filedata:
        frappe.throw("Invalid file format")

    try:
        header, encoded = filedata.split(",", 1)
        file_bytes = base64.b64decode(encoded)
    except Exception:
        frappe.throw("Invalid base64 image data")

    file_doc = frappe.get_doc({
        "doctype": "File",
        "file_name": filename or "invoice_image.jpg",
        "attached_to_doctype": "Invoice OCR",
        "attached_to_name": docname,
        "is_private": 1,
        "content": file_bytes
    })

    file_doc.save(ignore_permissions=True)

    return file_doc.file_url
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
            r"(grand total|total due|total including).*?([\d,]+\.\d{2})",
            text,
            re.IGNORECASE
        )

        if match:
            return float(match.group(2).replace(",", ""))

        # fallback → last number
        amounts = re.findall(r"[\d,]+\.\d{2}", text)

        if amounts:
            return float(amounts[-1].replace(",", ""))

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
# RUN OCR
# ============================================================
@frappe.whitelist()
def run_ocr(docname):

    from invoice_ocr.intelligence.supplier_matcher import intelligent_supplier_match
    from invoice_ocr.intelligence.line_classifier import classify_lines
    from invoice_ocr.intelligence.financial_validator import validate_financials

    from invoice_ocr.ai.agents.layout_agent import detect_layout
    from invoice_ocr.ai.agents.context_builder import build_context
    from invoice_ocr.ai.agents.header_agent import extract_header_agent
    from invoice_ocr.ai.agents.items_agent import extract_items_agent
    from invoice_ocr.ai.agents.tax_agent import extract_tax_agent
    from invoice_ocr.ai.agents.reflection_agent import reflect_and_correct

    doc = frappe.get_doc("Invoice OCR", docname)

    # ========================================================
    # FILE FETCH (SAFE VERSION)
    # ========================================================

    file_url = doc.invoice_file

    if not file_url:
        frappe.throw("Please upload or capture invoice before running OCR")

    # Fetch File document safely
    file_doc = frappe.get_all(
        "File",
        filters={"file_url": file_url},
        fields=["name", "file_url"]
    )

    if not file_doc:
        frappe.throw(f"File not found in File doctype: {file_url}")

    file_doc = frappe.get_doc("File", file_doc[0].name)

    file_path = file_doc.get_full_path()

    if not os.path.exists(file_path):
        frappe.throw(f"Invoice file not found on server path: {file_path}")
    

    # ========================================================
    # OCR
    # ========================================================

    try:
        raw = run_vision_ocr(file_path)
    except Exception as e:
        frappe.log_error(str(e), "OCR Processing Failed")
        frappe.throw("OCR processing failed. Please check error logs.")

    doc.raw_ocr_text = raw

    # ========================================================
    # INITIAL STATE
    # ========================================================

    state = {
        "ocr_text": raw,
        "header": {},
        "items": [],
        "taxes": [],
        "confidence": 60
    }

    # ========================================================
    # MULTI AGENT PIPELINE
    # ========================================================

    state = detect_layout(state)
    state = build_context(state)
    state = extract_header_agent(state)
    state = extract_items_agent(state)
    state = extract_tax_agent(state)
    state = classify_lines(state)

    detected_grand_total = extract_grand_total(raw)
    state["detected_grand_total"] = detected_grand_total

    # ========================================================
    # BUILD ITEMS (ONLY VALID ITEMS)
    # ========================================================

    doc.set("items", [])
    net_total = 0
    clean_items = []

    for it in state.get("items", []):

        if it.get("classification") != "VALID_ITEM":
            continue

        item_name = it.get("item_name")
        if not item_name:
            continue

        qty = float(it.get("qty") or 1)
        rate = float(it.get("rate") or 0)
        amount = float(it.get("amount") or (qty * rate))

        if amount <= 0:
            continue

        net_total += amount
        clean_items.append(it)

        doc.append("items", {
            "item_name": item_name,
            "qty": qty,
            "stock_qty": qty,
            "rate": rate,
            "amount": amount,
            "base_rate": rate,
            "base_amount": amount,
            "uom": "Nos"
        })

    state["items"] = clean_items
    state["net_total"] = net_total

    # ========================================================
    # CLEAN TAX VALIDATION
    # ========================================================

    clean_taxes = []
    tax_total = 0

    for tx in state.get("taxes", []):

        amount = float(tx.get("amount") or 0)

        if amount <= 0:
            continue

        # ❌ Ignore tax equal to subtotal
        if amount == net_total:
            continue

        # ❌ Ignore unrealistic tax (>40%)
        if net_total and amount > (net_total * 0.4):
            continue

        clean_taxes.append(tx)
        tax_total += amount

    state["taxes"] = clean_taxes
    state["tax_total"] = tax_total

    # ========================================================
    # SMART TAX FALLBACK
    # ========================================================

    if detected_grand_total and net_total:
        difference = round(detected_grand_total - net_total, 2)
    else:
        difference = 0

    if not state["taxes"] and difference > 0:

        if difference >= 1 and difference <= (net_total * 0.4):

            state["taxes"] = [{
                "charge_type": "Actual",
                "label": "Auto Detected Tax",
                "rate": None,
                "amount": difference
            }]

            state["tax_total"] = difference
            tax_total = difference

    # ========================================================
    # BUILD TAX TABLE IN ERP
    # ========================================================

    doc.set("taxes", [])

    company = frappe.defaults.get_user_default("Company") \
        or frappe.db.get_single_value("Global Defaults", "default_company")

    tax_account = frappe.db.get_value(
        "Account",
        {"company": company, "account_type": "Tax", "is_group": 0},
        "name"
    )

    for tx in state.get("taxes", []):

        amount = float(tx.get("amount") or 0)
        if amount <= 0:
            continue

        doc.append("taxes", {
            "charge_type": tx.get("charge_type") or "Actual",
            "account_head": tax_account,
            "description": tx.get("label") or "Tax",
            "rate": float(tx.get("rate") or 0),
            "tax_amount": amount,
            "base_tax_amount": amount
        })

    # ========================================================
    # FINANCIAL VALIDATION
    # ========================================================

    financial_report = validate_financials(state)

    confidence = state.get("confidence", 60)
    confidence += financial_report.get("confidence_adjustment", 0)
    confidence = max(0, min(100, confidence))

    doc.financial_risk = financial_report.get("risk_level")
    doc.calculated_grand_total = financial_report.get("calculated_grand_total")
    doc.financial_mismatch = financial_report.get("mismatch_amount")
    doc.is_financial_valid = financial_report.get("is_valid")

    # ========================================================
    # FINAL TOTALS
    # ========================================================

    doc.net_total = net_total
    doc.tax_total = tax_total

    doc.grand_total = (
        detected_grand_total
        or financial_report.get("calculated_grand_total")
        or (net_total + tax_total)
    )

    # ========================================================
    # SUPPLIER MATCHING
    # ========================================================

    header = state.get("header") or {}
    supplier_name = header.get("supplier_name")

    if supplier_name:
        result = intelligent_supplier_match(supplier_name)
        if isinstance(result, dict):
            doc.supplier = result.get("supplier")

    doc.invoice_number = header.get("invoice_number")

    raw_date = header.get("invoice_date") or extract_any_date(raw)

    try:
        doc.invoice_date = getdate(raw_date) if raw_date else None
    except Exception:
        doc.invoice_date = None

    if not doc.currency:
        doc.currency = header.get("currency") or detect_currency(raw)

    # ========================================================
    # SAVE
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
# CREATE PURCHASE INVOICE (FINAL PRODUCTION VERSION)
# ============================================================

@frappe.whitelist()
def create_purchase_invoice(docname):

    from frappe.utils import today, getdate

    doc = frappe.get_doc("Invoice OCR", docname)

    # ============================================================
    # 1️⃣ BASIC VALIDATIONS
    # ============================================================

    if not doc.supplier:
        frappe.throw("Please select Supplier before creating Purchase Invoice")

    if not doc.invoice_number:
        frappe.throw("Invoice Number missing")

    if not doc.items:
        frappe.throw("No items found")

    company = frappe.defaults.get_user_default("Company")

    if not company:
        frappe.throw("Default Company not found")

    # Prevent duplicate Purchase Invoice
    existing = frappe.db.exists(
        "Purchase Invoice",
        {"bill_no": doc.invoice_number, "supplier": doc.supplier}
    )

    if existing:
        frappe.throw(f"Purchase Invoice already exists: {existing}")

    # ============================================================
    # 2️⃣ CREATE PURCHASE INVOICE DOCUMENT
    # ============================================================

    pi = frappe.new_doc("Purchase Invoice")

    pi.company = company
    pi.supplier = doc.supplier
    pi.bill_no = doc.invoice_number
    pi.currency = doc.currency or frappe.defaults.get_global_default("currency")

    # -----------------------
    # Safe Date Handling
    # -----------------------

    invoice_date = doc.invoice_date or getdate(today())

    pi.bill_date = invoice_date

    if invoice_date > getdate(today()):
        pi.posting_date = getdate(today())
    else:
        pi.posting_date = invoice_date

    pi.update_stock = 0

    # ============================================================
    # 3️⃣ LOAD SUPPLIER MEMORY (OPTIONAL AI PROFILE)
    # ============================================================

    memory = None

    profile = frappe.db.exists(
        "Supplier AI Profile",
        {"supplier": doc.supplier}
    )

    if profile:
        memory = frappe.get_doc("Supplier AI Profile", profile)

    # ============================================================
    # 4️⃣ EXPENSE ACCOUNT RESOLUTION (INTELLIGENT)
    # ============================================================

    default_expense_account = None

    # Priority 1 → Supplier Memory
    if memory and memory.default_expense_account:
        default_expense_account = memory.default_expense_account

    # Priority 2 → Company Expense Account
    if not default_expense_account:
        default_expense_account = frappe.db.get_value(
            "Account",
            {
                "company": company,
                "root_type": "Expense",
                "is_group": 0
            },
            "name"
        )

    if not default_expense_account:
        frappe.throw("No Expense Account found for this company")

    # ============================================================
    # 5️⃣ ITEMS SECTION (ERP SAFE)
    # ============================================================

    for row in doc.items:

        qty = row.qty or 1
        rate = row.rate or 0
        amount = qty * rate

        pi.append("items", {
            "item_name": row.item_name,
            "description": row.item_name,
            "qty": qty,
            "uom": row.uom or "Nos",
            "stock_uom": row.uom or "Nos",
            "conversion_factor": 1,
            "rate": rate,
            "amount": amount,
            "base_rate": rate,
            "base_amount": amount,
            "expense_account": default_expense_account
        })

    # ============================================================
    # 6️⃣ TAX SECTION (SAFE + VALIDATED)
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

            # Priority 1 → If tax account already valid
            if tax.account_head in valid_tax_accounts:
                account_head = tax.account_head

            # Priority 2 → Supplier Memory Default Tax
            elif memory and memory.default_tax_account in valid_tax_accounts:
                account_head = memory.default_tax_account

            # Priority 3 → First Company Tax Account
            elif valid_tax_accounts:
                account_head = valid_tax_accounts[0]

            if not account_head:
                continue

            pi.append("taxes", {
                "charge_type": tax.charge_type or "Actual",
                "account_head": account_head,
                "description": tax.description or account_head,
                "rate": tax.rate or 0,
                "tax_amount": tax.tax_amount or 0,
                "base_tax_amount": tax.tax_amount or 0
            })

    # ============================================================
    # 7️⃣ INSERT + SUBMIT
    # ============================================================

    pi.insert(ignore_permissions=True)

    try:
        pi.submit()
    except Exception as e:
        frappe.log_error(str(e), "Purchase Invoice Submission Failed")
        frappe.throw(
            f"Purchase Invoice created but submission failed.\nError: {str(e)}"
        )

    # ============================================================
    # 8️⃣ UPDATE SUPPLIER MEMORY (OPTIONAL)
    # ============================================================

    try:
        from invoice_ocr.intelligence.supplier_memory import update_supplier_memory
        update_supplier_memory(pi)
    except Exception:
        pass

    # ============================================================
    # 9️⃣ LINK BACK TO OCR DOCUMENT
    # ============================================================

    doc.purchase_invoice = pi.name
    doc.status = "Posted"
    doc.save(ignore_permissions=True)

    frappe.db.commit()

    return {
        "purchase_invoice": pi.name,
        "status": "Submitted"
    }