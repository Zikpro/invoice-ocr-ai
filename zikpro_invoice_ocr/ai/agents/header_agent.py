import re
import frappe
from dateutil.parser import parse as parse_date
from zikpro_invoice_ocr.ai.prompts import HEADER_PROMPT_TEMPLATE
from zikpro_invoice_ocr.ai.ocr_nodes import call_deepinfra


def _normalize_currency(value):
    if not value:
        return None
    value = str(value).strip().upper()
    value = re.sub(r"[^A-Z]", "", value)
    if not value:
        return None
    return value


def _parse_date(value):
    if not value:
        return None

    try:
        parsed = parse_date(str(value), fuzzy=True, dayfirst=False, yearfirst=False)
        return parsed.date().isoformat()
    except Exception:
        return None


def _to_number(value):
    if value is None:
        return None
    if isinstance(value, (int, float)):
        return float(value)
    value = str(value).strip()
    if not value:
        return None
    value = value.replace(",", "").replace("£", "").replace("$", "").replace("€", "").replace("₹", "").replace("₨", "")
    try:
        return float(value)
    except Exception:
        return None


def extract_header_agent(state: dict):

    context = state.get("context", {})
    ocr_text = state.get("ocr_text", "").strip()

    # =====================================================
    # DEBUG: Log OCR text received
    # =====================================================
    frappe.logger().info(f"[HEADER_AGENT] OCR_TEXT LENGTH: {len(ocr_text) if ocr_text else 0} chars")
    frappe.logger().info(f"[HEADER_AGENT] OCR_TEXT PREVIEW: {ocr_text[:200] if ocr_text else '(EMPTY)'}")

    # =====================================================
    # VALIDATION: If OCR text is too weak, return defaults
    # =====================================================
    if not ocr_text or len(ocr_text) < 50:
        frappe.logger().warning("[HEADER_AGENT] OCR text too weak, returning defaults")
        state["header"] = {
            "invoice_number": None,
            "invoice_date": None,
            "due_date": None,
            "supplier_name": None,
            "supplier_address": None,
            "currency": None,
            "grand_total": None,
            "net_total": None,
            "tax_total": None,
            "payment_terms": None,
            "purchase_order_number": None,
            "reference_number": None,
            "vendor_tax_id": None,
            "buyer_tax_id": None,
            "country": None
        }
        return state

    country = context.get("country", "UNKNOWN")
    invoice_type = context.get("invoice_type", "Invoice")

    prompt = HEADER_PROMPT_TEMPLATE
    prompt = prompt.replace("{country}", country)
    prompt = prompt.replace("{invoice_type}", invoice_type)
    prompt += "\n\nOCR_TEXT:\n" + ocr_text

    frappe.logger().info("[HEADER_AGENT] Calling DeepSeek LLM...")
    result = call_deepinfra(prompt)

    # =====================================================
    # DEBUG: Log raw LLM response
    # =====================================================
    frappe.logger().info(f"[HEADER_AGENT] LLM RESPONSE TYPE: {type(result)}")
    frappe.logger().info(f"[HEADER_AGENT] LLM RESPONSE: {str(result)[:500]}")

    if not isinstance(result, dict):
        frappe.logger().warning(f"[HEADER_AGENT] Result is not dict, converting")
        result = {}

    defaults = {
        "invoice_number": None,
        "invoice_date": None,
        "due_date": None,
        "supplier_name": None,
        "supplier_address": None,
        "currency": None,
        "grand_total": None,
        "net_total": None,
        "tax_total": None,
        "payment_terms": None,
        "purchase_order_number": None,
        "reference_number": None,
        "vendor_tax_id": None,
        "buyer_tax_id": None,
        "country": None
    }
    for k, v in defaults.items():
        if k not in result:
            result[k] = v

    header = {
        "invoice_number": result.get("invoice_number") or None,
        "invoice_date": _parse_date(result.get("invoice_date")) or _parse_date(result.get("due_date")),
        "due_date": _parse_date(result.get("due_date")),
        "supplier_name": result.get("supplier_name") or None,
        "supplier_address": result.get("supplier_address") or None,
        "currency": _normalize_currency(result.get("currency")),
        "grand_total": _to_number(result.get("grand_total")),
        "net_total": _to_number(result.get("net_total")),
        "tax_total": _to_number(result.get("tax_total")),
        "payment_terms": result.get("payment_terms") or None,
        "purchase_order_number": result.get("purchase_order_number") or None,
        "reference_number": result.get("reference_number") or None,
        "vendor_tax_id": result.get("vendor_tax_id") or None,
        "buyer_tax_id": result.get("buyer_tax_id") or None,
        "country": result.get("country") or None
    }

    has_content = any([
        header["invoice_number"],
        header["supplier_name"],
        header["grand_total"],
        header["net_total"],
        header["tax_total"],
        header["currency"]
    ])

    frappe.logger().info(f"[HEADER_AGENT] Has content: {has_content}")
    frappe.logger().info(
        f"[HEADER_AGENT] Extracted: invoice_number={header.get('invoice_number')}, supplier={header.get('supplier_name')}, total={header.get('grand_total')}, currency={header.get('currency')}"
    )

    if not has_content:
        frappe.logger().warning("[HEADER_AGENT] No meaningful content extracted, returning defaults")
        header = defaults

    state["header"] = header
    return state
