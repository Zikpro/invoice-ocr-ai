import re
import frappe
from zikpro_invoice_ocr.ai.prompts import ITEMS_PROMPT_TEMPLATE
from zikpro_invoice_ocr.ai.ocr_nodes import call_deepinfra

def extract_items_agent(state: dict):

    context = state.get("context", {})
    ocr_text = state.get("ocr_text", "").strip()

    # =====================================================
    # DEBUG: Log OCR text received
    # =====================================================
    frappe.logger().info(f"[ITEMS_AGENT] OCR_TEXT LENGTH: {len(ocr_text) if ocr_text else 0} chars")
    frappe.logger().info(f"[ITEMS_AGENT] OCR_TEXT PREVIEW: {ocr_text[:200] if ocr_text else '(EMPTY)'}")

    # =====================================================
    # VALIDATION: If OCR text is too weak, return empty
    # =====================================================
    if not ocr_text or len(ocr_text) < 50:
        frappe.logger().warning("[ITEMS_AGENT] OCR text too weak, returning empty items")
        state["items"] = []
        return state

    table_structure = context.get("table_structure", "SIMPLE")

    prompt = ITEMS_PROMPT_TEMPLATE
    prompt = prompt.replace("{table_structure}", str(table_structure))

    prompt += "\n\nOCR_TEXT:\n" + ocr_text

    frappe.logger().info("[ITEMS_AGENT] Calling DeepSeek LLM...")
    result = call_deepinfra(prompt)
    
    # =====================================================
    # DEBUG: Log raw LLM response
    # =====================================================
    frappe.logger().info(f"[ITEMS_AGENT] LLM RESPONSE TYPE: {type(result)}")
    frappe.logger().info(f"[ITEMS_AGENT] LLM RESPONSE: {str(result)[:500]}")

    # =====================================================
    # VALIDATION: Reject hallucinated items
    # =====================================================
    if not isinstance(result, list):
        frappe.logger().warning(f"[ITEMS_AGENT] Result is not list, converting to []")
        result = []

    def safe_float(value):
        if value is None:
            return None
        if isinstance(value, (int, float)):
            return float(value)
        text_value = str(value).strip()
        if not text_value:
            return None
        text_value = text_value.replace(",", "").replace("£", "").replace("$", "").replace("€", "").replace("₹", "").replace("₨", "")
        try:
            return float(text_value)
        except (TypeError, ValueError):
            return None

    def _extract_last_monetary(item, exclude=None):
        numbers = []
        for value in item.values():
            if value is None:
                continue
            for match in re.findall(r"[-+]?[0-9][0-9,]*\.?[0-9]*", str(value)):
                cleaned = match.replace(",", "")
                try:
                    numbers.append(float(cleaned))
                except (ValueError, TypeError):
                    continue
        if not numbers:
            return None
        if exclude is not None and numbers[-1] == exclude and len(numbers) > 1:
            return numbers[-2]
        return numbers[-1]

    def _choose_quantity(item, explicit_qty):
        candidates = [
            item.get("accepted_qty"),
            item.get("accepted_quantity"),
            item.get("ordered_qty"),
            item.get("ordered_quantity"),
            item.get("invoice_qty"),
            item.get("invoice_quantity"),
            explicit_qty
        ]
        for value in candidates:
            qty = safe_float(value)
            if qty is not None and qty > 0:
                return qty
        return None

    hallucinated_keywords = [
        "widget",
        "sample",
        "example",
        "test item",
        "generic"
    ]

    cleaned_items = []
    for idx, item in enumerate(result):
        if not isinstance(item, dict):
            frappe.logger().warning(f"[ITEMS_AGENT] Item {idx} is not dict, skipping")
            continue

        item_name = (item.get("item_name") or item.get("description") or "").strip()
        item_name_lower = item_name.lower()

        # Skip obvious hallucinations
        if not item_name or any(kw in item_name_lower for kw in hallucinated_keywords):
            frappe.logger().warning(f"[ITEMS_AGENT] Item {idx} '{item.get('item_name')}' is hallucinated or invalid, skipping")
            continue

        qty = _choose_quantity(item, item.get("qty"))
        rate = safe_float(item.get("rate"))
        amount = safe_float(item.get("amount"))

        # Infer missing values when possible
        if amount is not None and qty is None and rate is None:
            qty = 1.0
            rate = amount

        if amount is not None and qty is not None and rate is None and qty != 0:
            rate = amount / qty

        if rate is None:
            inferred_rate = _extract_last_monetary(item, exclude=amount)
            if inferred_rate is not None and inferred_rate > 0:
                rate = inferred_rate

        if amount is not None and rate is not None and qty is None and rate != 0:
            qty = amount / rate

        if qty is not None and rate is not None and amount is None:
            amount = qty * rate

        tolerance = max(0.02, abs(amount or 0) * 0.01)
        if item_name == "" or qty is None or qty <= 0 or rate is None or rate <= 0 or amount is None or amount <= 0:
            frappe.logger().warning(
                f"[ITEMS_AGENT] Item {idx} '{item_name}' invalid numeric values (qty={qty} rate={rate} amount={amount}), skipping"
            )
            continue

        if abs((qty * rate) - amount) > tolerance:
            frappe.logger().warning(
                f"[ITEMS_AGENT] Item {idx} '{item_name}' amount mismatch qty*rate ({qty}*{rate}={qty*rate}) vs amount={amount}, skipping"
            )
            continue

        item["qty"] = qty
        item["rate"] = rate
        item["amount"] = amount
        item.setdefault("classification", "VALID_ITEM")

        cleaned_items.append(item)
        frappe.logger().info(
            f"[ITEMS_AGENT] Item {idx} ACCEPTED: {item_name} | qty={qty} rate={rate} amount={amount}"
        )

    frappe.logger().info(f"[ITEMS_AGENT] FINAL ITEMS COUNT: {len(cleaned_items)} (from {len(result)} LLM responses)")
    frappe.logger().info(f"[ITEMS_AGENT] CLEANED_ITEMS: {str(cleaned_items)[:500]}")

    state["items"] = cleaned_items
    return state
