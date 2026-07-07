def detect_layout(state: dict):
    """
    Detect invoice layout and country pattern
    """

    text = (state.get("ocr_text") or "").lower()

    layout = {}

    # -------------------------------
    # INDIA GST (Tally Style)
    # -------------------------------
    if "cgst" in text and "sgst" in text:
        layout["country_pattern"] = "INDIA_GST"
        layout["tax_pattern"] = "SPLIT_GST"
        layout["invoice_type"] = "Goods"

    # -------------------------------
    # UK VAT
    # -------------------------------
    elif "vat" in text and "gbp" in text:
        layout["country_pattern"] = "UK_VAT"
        layout["tax_pattern"] = "SINGLE_VAT"
        layout["invoice_type"] = "Goods"

    # -------------------------------
    # Pakistan FBR
    # -------------------------------
    elif "fbr" in text or "ntn" in text:
        layout["country_pattern"] = "PAK_FBR"
        layout["tax_pattern"] = "SALES_TAX"
        layout["invoice_type"] = "Goods"

    # -------------------------------
    # US Tax
    # -------------------------------
    elif "tax (" in text and "net" in text:
        layout["country_pattern"] = "US_TAX"
        layout["tax_pattern"] = "PERCENT_TAX"
        layout["invoice_type"] = "Goods"

    # -------------------------------
    # Service Invoice
    # -------------------------------
    elif "labour" in text or "professional" in text:
        layout["country_pattern"] = "GENERIC"
        layout["invoice_type"] = "SERVICE"

    else:
        layout["country_pattern"] = "GENERIC"
        layout["invoice_type"] = "Goods"

    state["layout"] = layout
    return state
