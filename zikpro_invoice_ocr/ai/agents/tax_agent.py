import re
import frappe
from zikpro_invoice_ocr.ai.prompts import TAX_PROMPT
from zikpro_invoice_ocr.ai.ocr_nodes import call_deepinfra


def extract_tax_agent(state: dict):

    text = state.get("ocr_text", "")
    header = state.get("header", {}) or {}
    detected_grand_total = header.get("grand_total") or 0
    net_total = header.get("net_total") or 0
    header_tax_total = header.get("tax_total") or 0

    # =====================================================
    # DEBUG: Log OCR text received
    # =====================================================
    frappe.logger().info(f"[TAX_AGENT] OCR_TEXT LENGTH: {len(text) if text else 0} chars")
    frappe.logger().info(f"[TAX_AGENT] OCR_TEXT PREVIEW: {text[:200] if text else '(EMPTY)'}")

    # =====================================================
    # VALIDATION: If OCR text is too weak, return empty
    # =====================================================
    if not text or len(text.strip()) < 50:
        frappe.logger().warning("[TAX_AGENT] OCR text too weak, returning empty taxes")
        state["taxes"] = []
        return state

    # =====================================================
    # 1️⃣ LLM EXTRACTION
    # =====================================================
    prompt = TAX_PROMPT + "\n\nOCR_TEXT:\n" + text
    
    frappe.logger().info("[TAX_AGENT] Calling DeepSeek LLM...")
    result = call_deepinfra(prompt)
    
    # =====================================================
    # DEBUG: Log raw LLM response
    # =====================================================
    frappe.logger().info(f"[TAX_AGENT] LLM RESPONSE TYPE: {type(result)}")
    frappe.logger().info(f"[TAX_AGENT] LLM RESPONSE: {str(result)[:500]}")

    # Ensure list
    if not isinstance(result, list):
        frappe.logger().warning(f"[TAX_AGENT] Result is not list, converting to []")
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
        except Exception:
            return None

    cleaned_taxes = []

    for idx, tax in enumerate(result):

        if not isinstance(tax, dict):
            frappe.logger().warning(f"[TAX_AGENT] Tax {idx} is not dict, skipping")
            continue

        amount = safe_float(tax.get("amount"))
        rate = safe_float(tax.get("rate"))
        label = (tax.get("label") or "").lower()

        # =====================================================
        # 2️⃣ SAFETY FILTERS
        # =====================================================

        # Skip zero
        if amount <= 0:
            frappe.logger().info(f"[TAX_AGENT] Tax {idx} '{tax.get('label')}' REJECTED: amount <= 0 ({amount})")
            continue

        # Skip if equals grand total
        if detected_grand_total and amount == detected_grand_total:
            frappe.logger().info(f"[TAX_AGENT] Tax {idx} '{tax.get('label')}' REJECTED: equals grand_total ({amount})")
            continue

        # Skip if equals net total (common hallucination)
        if net_total and amount == net_total:
            frappe.logger().info(f"[TAX_AGENT] Tax {idx} '{tax.get('label')}' REJECTED: equals net_total ({amount})")
            continue

        # Skip summary words
        if any(word in label for word in [
            "total",
            "net total",
            "grand",
            "including"
        ]):
            frappe.logger().info(f"[TAX_AGENT] Tax {idx} '{tax.get('label')}' REJECTED: contains summary word")
            continue

        # =====================================================
        # 3️⃣ Verify tax is visible in OCR text
        # =====================================================
        tax_label = (tax.get("label") or "").strip()
        
        # If we have a label, it should appear somewhere in the OCR text
        if tax_label:
            label_words = tax_label.lower().split()
            found = any(
                keyword in text.lower() 
                for keyword in label_words
            )
            
            if not found:
                frappe.logger().info(f"[TAX_AGENT] Tax {idx} '{tax.get('label')}' REJECTED: keywords not in OCR text")
                continue

        if (rate is None or rate <= 0) and net_total:
            rate = round((amount / net_total) * 100, 2)
            frappe.logger().info(f"[TAX_AGENT] Tax {idx} derived rate from net total: {rate}%")

        cleaned_taxes.append({
            "label": tax.get("label"),
            "rate": rate or 0,
            "amount": amount,
            "charge_type": "Actual"
        })
        
        frappe.logger().info(f"[TAX_AGENT] Tax {idx} ACCEPTED: '{tax.get('label')}' amount={amount} rate={rate}")

    if not cleaned_taxes:
        if header_tax_total and header_tax_total > 0:
            derived_rate = None
            if net_total:
                derived_rate = round((header_tax_total / net_total) * 100, 2)
            frappe.logger().info("[TAX_AGENT] No explicit taxes found, deriving from header tax_total")
            cleaned_taxes.append({
                "label": "Tax",
                "rate": derived_rate or 0,
                "amount": safe_float(header_tax_total) or 0,
                "charge_type": "Actual"
            })
        elif detected_grand_total and net_total and detected_grand_total > net_total:
            derived_amount = round(detected_grand_total - net_total, 2)
            if derived_amount > 0:
                derived_rate = None
                if net_total:
                    derived_rate = round((derived_amount / net_total) * 100, 2)
                frappe.logger().info("[TAX_AGENT] No explicit taxes found, deriving from grand_total - net_total")
                cleaned_taxes.append({
                    "label": "Tax",
                    "rate": derived_rate or 0,
                    "amount": derived_amount,
                    "charge_type": "Actual"
                })

    frappe.logger().info(f"[TAX_AGENT] FINAL TAXES COUNT: {len(cleaned_taxes)} (from {len(result)} LLM responses)")
    frappe.logger().info(f"[TAX_AGENT] CLEANED_TAXES: {str(cleaned_taxes)[:500]}")

    state["taxes"] = cleaned_taxes
    return state