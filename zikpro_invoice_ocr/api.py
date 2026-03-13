import os
import frappe
from frappe.utils import getdate, today
from zikpro_invoice_ocr.vision.ocr_engine import run_vision_ocr


# ============================================================
# SAFE FILE RESOLUTION (MOBILE + UPLOAD SAFE)
# ============================================================

def _get_file_path(file_url):

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
        frappe.throw("Invoice file missing on server")

    return file_path


def _ensure_invoice_file(doc):

    if doc.invoice_file:
        return doc.invoice_file

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
    doc.save(ignore_permissions=True)
    frappe.db.commit()

    return doc.invoice_file


# ============================================================
# ENQUEUE OCR
# ============================================================

@frappe.whitelist()
def enqueue_ocr(docname):

    doc = frappe.get_doc("Invoice OCR", docname)
    doc.reload()

    _ensure_invoice_file(doc)

    if doc.status == "Processing":
        return {"status": "Already Processing"}

    doc.status = "Processing"
    doc.save(ignore_permissions=True)
    frappe.db.commit()

    frappe.enqueue(
        method="zikpro_invoice_ocr.api.run_ocr",
        queue="long",
        timeout=600,
        job_name=f"OCR-{doc.name}",
        docname=docname
    )

    return {"status": "Queued"}


# ============================================================
# RUN OCR (FULL PRODUCTION SAFE)
# ============================================================

@frappe.whitelist()
def run_ocr(docname):

    from zikpro_invoice_ocr.ai.agents.layout_agent import detect_layout
    from zikpro_invoice_ocr.ai.agents.context_builder import build_context
    from zikpro_invoice_ocr.ai.agents.header_agent import extract_header_agent
    from zikpro_invoice_ocr.ai.agents.items_agent import extract_items_agent
    from zikpro_invoice_ocr.ai.agents.tax_agent import extract_tax_agent
    from zikpro_invoice_ocr.intelligence.line_classifier import classify_lines
    from zikpro_invoice_ocr.intelligence.supplier_matcher import intelligent_supplier_match
    from zikpro_invoice_ocr.intelligence.financial_validator import validate_financials

    doc = frappe.get_doc("Invoice OCR", docname)
    file_url = _ensure_invoice_file(doc)
    file_path = _get_file_path(file_url)

    size = os.path.getsize(file_path)
    if file_path.lower().endswith(".pdf") and size > 10 * 1024 * 1024:
        frappe.throw("PDF too large. Max 10MB.")
    if not file_path.lower().endswith(".pdf") and size > 5 * 1024 * 1024:
        frappe.throw("Image too large. Max 5MB.")

    try:
        raw = run_vision_ocr(file_path)
    except Exception as e:
        frappe.log_error(str(e), "OCR Failed")
        doc.status = "Failed"
        doc.save(ignore_permissions=True)
        frappe.db.commit()
        frappe.throw("OCR processing failed.")

    doc.raw_ocr_text = raw

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
            "rate": rate,
            "amount": amount,
            "uom": "Nos"
        })

    doc.set("taxes", [])
    tax_total = 0

    company = frappe.defaults.get_user_default("Company")

    tax_account = frappe.db.get_value(
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
            "account_head": tax_account,
            "description": tx.get("label") or "Tax",
            "rate": float(tx.get("rate") or 0),
            "tax_amount": amount
        })

    header = state.get("header") or {}

    doc.invoice_number = header.get("invoice_number")

    try:
        doc.invoice_date = getdate(header.get("invoice_date"))
    except Exception:
        doc.invoice_date = None

    if not doc.currency:
        doc.currency = header.get("currency") or frappe.defaults.get_global_default("currency")

    supplier_name = header.get("supplier_name")

    if supplier_name:
        try:
            result = intelligent_supplier_match(supplier_name)

            if isinstance(result, dict):
                matched_supplier = result.get("supplier")
            else:
                matched_supplier = result

            if matched_supplier:
                doc.supplier = matched_supplier
            else:
                exact = frappe.db.get_value(
                    "Supplier",
                    {"supplier_name": supplier_name},
                    "name"
                )
                if exact:
                    doc.supplier = exact

        except Exception as e:
            frappe.log_error(str(e), "Supplier Matching Error")

    state["net_total"] = net_total
    state["tax_total"] = tax_total

    report = validate_financials(state)

    doc.net_total = net_total
    doc.tax_total = tax_total
    doc.grand_total = net_total + tax_total

    doc.financial_risk = report.get("risk_level")
    doc.financial_mismatch = report.get("mismatch_amount")
    doc.is_financial_valid = report.get("is_valid")
    doc.calculated_grand_total = report.get("calculated_grand_total")

    state["financial_validation"] = report
    doc.db_set("semantic_invoice_json", frappe.as_json(state, indent=2))
    doc.db_set("confidence", state.get("confidence", 60))
    doc.db_set("status", "Ready")

    doc.flags.ignore_mandatory = True
    doc.save(ignore_permissions=True, ignore_version=True)
    frappe.db.commit()

    return {"status": "Completed"}


@frappe.whitelist()
def create_purchase_invoice(docname):

    doc = frappe.get_doc("Invoice OCR", docname)

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
        frappe.throw("Default Company not set.")

    existing = frappe.db.exists(
        "Purchase Invoice",
        {
            "bill_no": doc.invoice_number,
            "supplier": doc.supplier
        }
    )

    if existing:
        frappe.throw(f"Purchase Invoice already exists: {existing}")

    pi = frappe.new_doc("Purchase Invoice")

    pi.company = company
    pi.supplier = doc.supplier
    pi.bill_no = doc.invoice_number
    pi.currency = doc.currency
    pi.bill_date = doc.invoice_date or frappe.utils.today()
    pi.posting_date = doc.invoice_date or frappe.utils.today()
    pi.update_stock = 0

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
        frappe.throw("No Expense Account found.")

    for row in doc.items:
        pi.append("items", {
            "item_name": row.item_name,
            "description": row.item_name,
            "qty": row.qty,
            "uom": row.uom or "Nos",
            "stock_uom": row.uom or "Nos",
            "conversion_factor": 1,
            "rate": row.rate,
            "expense_account": expense_account
        })

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
            if tax.tax_amount:
                pi.append("taxes", {
                    "charge_type": tax.charge_type or "Actual",
                    "account_head": tax_account,
                    "description": tax.description or "Tax",
                    "rate": tax.rate or 0,
                    "tax_amount": tax.tax_amount
                })

    try:
        pi.insert(ignore_permissions=True)
        pi.submit()
    except Exception as e:
        frappe.log_error(str(e), "Purchase Invoice Creation Failed")
        frappe.throw(str(e))

    doc.purchase_invoice = pi.name
    doc.status = "Posted"
    doc.save(ignore_permissions=True)
    frappe.db.commit()

    return {
        "purchase_invoice": pi.name,
        "status": "Submitted"
    }



@frappe.whitelist()
def test_deepinfra_connection():

    from zikpro_invoice_ocr.ai.ocr_nodes import call_deepinfra

    # Simple test prompt
    response = call_deepinfra('Respond with JSON: {"status":"ok"}')

    return response
