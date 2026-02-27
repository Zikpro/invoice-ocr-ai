import re
import os
import frappe
from frappe.utils import getdate, today
from invoice_ocr.vision.ocr_engine import run_vision_ocr


# ============================================================
# SAFE FILE RESOLUTION (CRITICAL FOR MOBILE)
# ============================================================

def _ensure_invoice_file(doc):

    # If already saved in field
    if doc.invoice_file:
        return doc.invoice_file

    # Try to auto-detect attachment
    attached = frappe.get_all(
        "File",
        filters={
            "attached_to_doctype": "Invoice OCR",
            "attached_to_name": doc.name
        },
        fields=["file_url"],
        limit=1
    )

    if not attached:
        frappe.throw("Please upload invoice first")

    doc.invoice_file = attached[0].file_url
    doc.flags.ignore_mandatory = True
    doc.save(ignore_permissions=True)
    frappe.db.commit()

    return doc.invoice_file


# ============================================================
# ENQUEUE OCR (BACKGROUND SAFE)
# ============================================================

@frappe.whitelist()
def enqueue_ocr(docname):

    doc = frappe.get_doc("Invoice OCR", docname)
    doc.reload()

    _ensure_invoice_file(doc)

    if doc.status == "Processing":
        return {"status": "Already Processing"}

    doc.status = "Processing"
    doc.flags.ignore_mandatory = True
    doc.save(ignore_permissions=True, ignore_version=True)
    frappe.db.commit()

    frappe.enqueue(
        method="invoice_ocr.api.run_ocr",
        queue="long",
        timeout=600,
        job_name=f"OCR-{doc.name}",
        docname=docname
    )

    return {"status": "Queued"}


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

    doc = frappe.get_doc("Invoice OCR", docname)
    file_url = _ensure_invoice_file(doc)

    # ========================================================
    # FILE PATH RESOLUTION (SAFER)
    # ========================================================

    file_list = frappe.get_all(
        "File",
        filters={"file_url": file_url},
        fields=["name"],
        limit=1
    )

    if not file_list:
        frappe.throw("File not found in File doctype")

    file_doc = frappe.get_doc("File", file_list[0].name)
    file_path = file_doc.get_full_path()

    if not os.path.exists(file_path):
        frappe.throw("Invoice file not found on server")

    # File size protection
    file_size = os.path.getsize(file_path)

    if file_path.lower().endswith(".pdf"):
        if file_size > 10 * 1024 * 1024:
            frappe.throw("PDF too large. Max 10MB allowed.")
    else:
        if file_size > 5 * 1024 * 1024:
            frappe.throw("Image too large. Max 5MB allowed.")

    # ========================================================
    # OCR ENGINE
    # ========================================================

    try:
        raw = run_vision_ocr(file_path)
    except Exception as e:
        frappe.log_error(str(e), "OCR Processing Failed")
        doc.status = "Failed"
        doc.save(ignore_permissions=True)
        frappe.db.commit()
        frappe.throw("OCR processing failed.")

    doc.raw_ocr_text = raw

    # ========================================================
    # AI PIPELINE
    # ========================================================

    state = {
        "ocr_text": raw,
        "header": {},
        "items": [],
        "taxes": [],
        "confidence": 60
    }

    try:
        state = detect_layout(state)
        state = build_context(state)
        state = extract_header_agent(state)
        state = extract_items_agent(state)
        state = extract_tax_agent(state)
        state = classify_lines(state)
    except Exception as e:
        frappe.log_error(str(e), "AI Pipeline Error")

    # ========================================================
    # BUILD ITEMS
    # ========================================================

    doc.set("items", [])
    net_total = 0

    for it in state.get("items", []):
        if it.get("classification") != "VALID_ITEM":
            continue

        qty = float(it.get("qty") or 1)
        rate = float(it.get("rate") or 0)
        amount = float(it.get("amount") or qty * rate)

        if amount <= 0:
            continue

        net_total += amount

        doc.append("items", {
            "item_name": it.get("item_name"),
            "qty": qty,
            "stock_qty": qty,
            "rate": rate,
            "amount": amount,
            "base_rate": rate,
            "base_amount": amount,
            "uom": "Nos"
        })

    # ========================================================
    # BUILD TAXES
    # ========================================================

    doc.set("taxes", [])
    tax_total = 0

    for tx in state.get("taxes", []):
        amount = float(tx.get("amount") or 0)
        if amount <= 0:
            continue

        tax_total += amount

        doc.append("taxes", {
            "charge_type": tx.get("charge_type") or "Actual",
            "account_head": None,
            "description": tx.get("label") or "Tax",
            "rate": tx.get("rate") or 0,
            "tax_amount": amount,
            "base_tax_amount": amount
        })

    # ========================================================
    # HEADER MAPPING
    # ========================================================

    header = state.get("header") or {}

    doc.supplier_name = header.get("supplier_name")

    if header.get("supplier_name"):
        try:
            result = intelligent_supplier_match(header.get("supplier_name"))
            doc.supplier = result.get("supplier")
        except Exception:
            pass

    doc.invoice_number = header.get("invoice_number")

    try:
        doc.invoice_date = getdate(header.get("invoice_date"))
    except Exception:
        doc.invoice_date = None

    if not doc.currency:
        doc.currency = header.get("currency") or frappe.defaults.get_global_default("currency")

    # ========================================================
    # FINANCIAL VALIDATION
    # ========================================================

    try:
        financial_report = validate_financials(state)
        doc.financial_risk = financial_report.get("risk_level")
        doc.financial_mismatch = financial_report.get("mismatch_amount")
        doc.is_financial_valid = financial_report.get("is_valid")
        doc.calculated_grand_total = financial_report.get("calculated_grand_total")
    except Exception:
        pass

    doc.net_total = net_total
    doc.tax_total = tax_total
    doc.grand_total = net_total + tax_total

    doc.confidence = state.get("confidence", 60)

    doc.status = "Ready"
    doc.flags.ignore_mandatory = True
    doc.save(ignore_permissions=True, ignore_version=True)
    frappe.db.commit()

    return {"status": "Completed"}



# ============================================================
# CREATE PURCHASE INVOICE (FULL PRODUCTION SAFE)
# ============================================================

@frappe.whitelist()
def create_purchase_invoice(docname):

    from frappe.utils import getdate, today

    doc = frappe.get_doc("Invoice OCR", docname)

    # ============================================================
    # 1️⃣ VALIDATIONS
    # ============================================================

    if doc.status != "Ready":
        frappe.throw("OCR not completed yet.")

    if not doc.supplier:
        frappe.throw("Supplier is required.")

    if not doc.invoice_number:
        frappe.throw("Invoice Number missing.")

    if not doc.items:
        frappe.throw("No items found.")

    company = frappe.defaults.get_user_default("Company")

    if not company:
        frappe.throw("Default Company not configured.")

    # Duplicate Protection
    existing = frappe.db.exists(
        "Purchase Invoice",
        {
            "bill_no": doc.invoice_number,
            "supplier": doc.supplier
        }
    )

    if existing:
        frappe.throw(f"Purchase Invoice already exists: {existing}")

    # ============================================================
    # 2️⃣ CREATE DOCUMENT
    # ============================================================

    pi = frappe.new_doc("Purchase Invoice")

    pi.company = company
    pi.supplier = doc.supplier
    pi.bill_no = doc.invoice_number
    pi.currency = doc.currency or frappe.defaults.get_global_default("currency")

    invoice_date = doc.invoice_date or getdate(today())

    pi.bill_date = invoice_date
    pi.posting_date = invoice_date
    pi.update_stock = 0

    # ============================================================
    # 3️⃣ EXPENSE ACCOUNT AUTO DETECT
    # ============================================================

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
        frappe.throw("No Expense Account found for this company.")

    # ============================================================
    # 4️⃣ ITEMS
    # ============================================================

    for row in doc.items:

        qty = row.qty or 1
        rate = row.rate or 0

        if qty <= 0:
            continue

        pi.append("items", {
            "item_name": row.item_name,
            "description": row.item_name,
            "qty": qty,
            "uom": row.uom or "Nos",
            "stock_uom": row.uom or "Nos",
            "conversion_factor": 1,
            "rate": rate,
            "expense_account": expense_account
        })

    if not pi.items:
        frappe.throw("No valid items to create Purchase Invoice.")

    # ============================================================
    # 5️⃣ TAXES (SAFE VERSION – NO ACCOUNT HEAD ERROR)
    # ============================================================

    if doc.taxes:

        tax_account = frappe.db.get_value(
            "Account",
            {
                "company": company,
                "account_type": "Tax",
                "is_group": 0
            },
            "name"
        )

        if tax_account:

            for tax in doc.taxes:

                if not tax.tax_amount:
                    continue

                pi.append("taxes", {
                    "charge_type": tax.charge_type or "Actual",
                    "account_head": tax_account,
                    "description": tax.description or "Tax",
                    "rate": tax.rate or 0,
                    "tax_amount": tax.tax_amount or 0
                })

        else:
            frappe.logger().warning(
                f"No Tax Account found for company {company}. Skipping tax rows."
            )

    # ============================================================
    # 6️⃣ INSERT + SUBMIT
    # ============================================================

    try:
        pi.insert(ignore_permissions=True)
        pi.submit()
    except Exception as e:
        frappe.log_error(str(e), "Purchase Invoice Submission Failed")
        frappe.throw(
            f"Purchase Invoice creation failed.\n\nError:\n{str(e)}"
        )

    # ============================================================
    # 7️⃣ LINK BACK TO OCR DOCUMENT
    # ============================================================

    doc.purchase_invoice = pi.name
    doc.status = "Posted"
    doc.flags.ignore_mandatory = True
    doc.save(ignore_permissions=True)
    frappe.db.commit()

    return {
        "purchase_invoice": pi.name,
        "status": "Submitted"
    }