# =========================================================
# FINANCIAL VALIDATOR (Enterprise Safe Version)
# Path:
# apps/invoice_ocr/invoice_ocr/intelligence/financial_validator.py
# =========================================================


# ---------------------------------------------------------
# SAFE FLOAT (Local Utility – self contained)
# ---------------------------------------------------------

def safe_float(value):
    try:
        return float(value or 0)
    except (TypeError, ValueError):
        return 0.0


# ---------------------------------------------------------
# MAIN VALIDATOR
# ---------------------------------------------------------

def validate_financials(state: dict):

    items = state.get("items", [])
    taxes = state.get("taxes", [])
    header = state.get("header", {})

    detected_total = safe_float(state.get("detected_grand_total"))

    # =====================================================
    # 1️⃣ RECALCULATE SUBTOTAL (VALID ITEMS ONLY)
    # =====================================================

    calculated_subtotal = 0.0

    for item in items:

        # Ignore non-financial lines
        if item.get("classification") != "VALID_ITEM":
            continue

        qty = safe_float(item.get("qty"))
        rate = safe_float(item.get("rate"))
        amount = safe_float(item.get("amount"))

        if qty > 0 and rate > 0:
            calculated_subtotal += qty * rate
        else:
            calculated_subtotal += amount

    # =====================================================
    # 2️⃣ RECALCULATE TAX
    # =====================================================

    calculated_tax = 0.0

    for tax in taxes:
        calculated_tax += safe_float(tax.get("amount"))

    # =====================================================
    # 3️⃣ CALCULATE GRAND TOTAL
    # =====================================================

    calculated_grand_total = calculated_subtotal + calculated_tax

    # =====================================================
    # 4️⃣ MISMATCH CALCULATION
    # =====================================================

    mismatch_amount = abs(calculated_grand_total - detected_total)

    # =====================================================
    # 5️⃣ RISK EVALUATION (Smart Tolerance)
    # =====================================================

    tolerance_percent = 0.02  # 2%

    if detected_total > 0:
        allowed_difference = detected_total * tolerance_percent
    else:
        # If no detected total, allow small rounding diff
        allowed_difference = 1.0

    if mismatch_amount <= allowed_difference:
        is_valid = True
        risk_level = "LOW"
        confidence_adjustment = +5
    else:
        is_valid = False
        risk_level = "HIGH"
        confidence_adjustment = -20

    # =====================================================
    # 6️⃣ RETURN SAFE REPORT
    # =====================================================

    return {
        "is_valid": is_valid,
        "calculated_subtotal": round(calculated_subtotal, 2),
        "calculated_tax": round(calculated_tax, 2),
        "calculated_grand_total": round(calculated_grand_total, 2),
        "detected_grand_total": round(detected_total, 2),
        "mismatch_amount": round(mismatch_amount, 2),
        "risk_level": risk_level,
        "confidence_adjustment": confidence_adjustment
    }