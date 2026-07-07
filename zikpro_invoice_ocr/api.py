import os
import re
import frappe
from frappe.utils import getdate, today
from zikpro_invoice_ocr.vision.ocr_engine import run_vision_ocr
from zikpro_invoice_ocr.ai.ocr_nodes import score_confidence


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

    return doc.invoice_file


def _trim_page_bleeding(text: str) -> str:
    if not text:
        return text

    match = re.search(r"(?i)page\s*\d+\s*of\s*\d+", text)
    if not match:
        return text

    return text[: match.start()].rstrip()


def _has_header_content(header: dict) -> bool:
    if not isinstance(header, dict):
        return False

    return any([
        header.get("invoice_number"),
        header.get("supplier_name"),
        header.get("grand_total") is not None and header.get("grand_total") > 0,
        header.get("net_total") is not None and header.get("net_total") > 0,
        header.get("tax_total") is not None and header.get("tax_total") > 0,
        header.get("currency")
    ])


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
    from zikpro_invoice_ocr.intelligence.item_matcher import intelligent_item_match
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

        frappe.throw("OCR processing failed.")

    # =====================================================
    # VALIDATE RAW OCR TEXT
    # =====================================================
    if not raw or len(raw.strip()) < 50:
        frappe.log_error(f"Weak OCR output: {len(raw) if raw else 0} chars", "OCR Validation Error")
        
        doc.status = "Failed"
        doc.save(ignore_permissions=True)
        
        frappe.throw("Could not extract text from invoice. Please ensure image is clear and readable.")

    doc.raw_ocr_text = raw
    cleaned_text = _trim_page_bleeding(raw)

    state = {
        "ocr_text": cleaned_text,
        "header": {},
        "items": [],
        "taxes": [],
        "confidence": 60
    }

    try:
        frappe.logger().info("[RUN_OCR] Detecting layout")
        state = detect_layout(state)
        frappe.logger().info(f"[RUN_OCR] Layout: {state.get('layout')}")

        frappe.logger().info("[RUN_OCR] Building context")
        state = build_context(state)
        frappe.logger().info(f"[RUN_OCR] Context: {state.get('context')}")

        frappe.logger().info("[RUN_OCR] Extracting header")
        state = extract_header_agent(state)
        frappe.logger().info(f"[RUN_OCR] Header: {state.get('header')}")

        if not _has_header_content(state.get('header', {})):
            frappe.log_error("Header extraction returned no meaningful values", "OCR Stage Failure")
            doc.status = "Failed"
            doc.save(ignore_permissions=True)
            frappe.throw("Invoice header extraction failed. Please verify the invoice content.")

        frappe.logger().info("[RUN_OCR] Extracting items")
        state = extract_items_agent(state)
        frappe.logger().info(f"[RUN_OCR] Items extracted: {len(state.get('items') or [])}")

        if not isinstance(state.get('items'), list) or len(state.get('items') or []) == 0:
            frappe.log_error("Item extraction returned no rows", "OCR Stage Failure")
            doc.status = "Failed"
            doc.save(ignore_permissions=True)
            frappe.throw("Invoice item extraction failed. Please check the invoice layout.")

        frappe.logger().info("[RUN_OCR] Extracting taxes")
        state = extract_tax_agent(state)
        state["taxes"] = state.get("taxes") or []
        frappe.logger().info(f"[RUN_OCR] Taxes extracted: {len(state.get('taxes') or [])}")

        frappe.logger().info("[RUN_OCR] Classifying extracted lines")
        state = classify_lines(state)
        frappe.logger().info(f"[RUN_OCR] Classified items: {state.get('items')}")

    except Exception as e:
        frappe.log_error(str(e), "AI Pipeline Error")
        doc.status = "Failed"
        doc.save(ignore_permissions=True)
        frappe.throw("AI pipeline failed during invoice extraction.")

    # =====================================================
    # ITEMS
    # =====================================================

    doc.set("items", [])

    net_total = 0
    charge_total = 0

    for it in state.get("items", []):

        classification = it.get("classification")

        qty = float(it.get("qty") or 1)
        rate = float(it.get("rate") or 0)
        amount = float(it.get("amount") or qty * rate)

        if amount <= 0:
            continue

        if classification == "VALID_ITEM":
            net_total += amount

        elif classification == "CHARGE_ROW":
            charge_total += amount

        else:
            continue

        match = intelligent_item_match(it.get("item_name"))
        matched_item = match.get("item")
        match_confidence = match.get("confidence", 0)
        multiple_matches = match.get("multiple_matches", False)

        if matched_item:
            status = "Matched"
        elif multiple_matches:
            status = "Multiple Matches"
        else:
            status = "Pending"

        doc.append("items", {
            "ocr_item_name": it.get("item_name"),
            "qty": qty,
            "rate": rate,
            "amount": amount,
            "matched_item": matched_item,
            "match_confidence": match_confidence,
            "status": status
        })

    # =====================================================
    # TAXES
    # =====================================================

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

    # =====================================================
    # HEADER
    # =====================================================

    header = state.get("header") or {}

    doc.invoice_number = header.get("invoice_number")

    try:
        doc.invoice_date = getdate(header.get("invoice_date"))

    except Exception:
        doc.invoice_date = None

    doc.currency = (
        header.get("currency")
        or doc.currency
        or frappe.defaults.get_global_default("currency")
    )

    supplier_name = header.get("supplier_name")
    doc.supplier_name = supplier_name

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

    # =====================================================
    # FINANCIALS
    # =====================================================

    state["net_total"] = net_total
    state["tax_total"] = tax_total
    state["charge_total"] = charge_total

    state["detected_grand_total"] = float(
        header.get("grand_total") or 0
    )

    report = validate_financials(state)

    doc.net_total = net_total
    doc.tax_total = tax_total

    doc.grand_total = (
        net_total
        + tax_total
        + charge_total
    )

    doc.financial_risk = report.get("risk_level")
    doc.financial_mismatch = report.get("mismatch_amount")
    doc.is_financial_valid = report.get("is_valid")
    doc.calculated_grand_total = report.get("calculated_grand_total")

    state["financial_validation"] = report
    state = score_confidence(state)

    doc.db_set(
        "semantic_invoice_json",
        frappe.as_json(state, indent=2)
    )

    doc.db_set(
        "confidence",
        state.get("confidence", 60)
    )

    doc.db_set("status", "Ready")

    doc.flags.ignore_mandatory = True

    doc.save(
        ignore_permissions=True,
        ignore_version=True
    )

    return {
        "status": "Completed"
    }


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

    # ==================================================
    # ITEMS
    # ==================================================

    for row in doc.items:

        item_code = getattr(row, "matched_item", None)

        if item_code:

            pi.append("items", {
                "item_code": item_code,
                "qty": row.qty,
                "uom": "Nos",
                "stock_uom": "Nos",
                "conversion_factor": 1,
                "rate": row.rate,
                "expense_account": expense_account
            })

        else:

            # Fallback when no ERP Item match exists

            pi.append("items", {
                "item_name": row.ocr_item_name,
                "description": row.ocr_item_name,
                "qty": row.qty,
                "uom": "Nos",
                "stock_uom": "Nos",
                "conversion_factor": 1,
                "rate": row.rate,
                "expense_account": expense_account
            })

    # ==================================================
    # TAXES
    # ==================================================

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
                "tax_amount": tax.tax_amount
            })

    # ==================================================
    # SAVE & SUBMIT
    # ==================================================

    try:
        pi.insert(ignore_permissions=True)
        pi.submit()

    except Exception:
        frappe.log_error(
            frappe.get_traceback(),
            "Purchase Invoice Creation Failed"
        )
        raise

    doc.purchase_invoice = pi.name
    doc.status = "Posted"

    doc.save(
        ignore_permissions=True,
        ignore_version=True
    )

    return {
        "purchase_invoice": pi.name,
        "status": "Submitted"
    }