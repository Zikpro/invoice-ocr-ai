import re
import frappe
from rapidfuzz import fuzz


def intelligent_supplier_match(detected_name: str):
    """
    Enterprise-safe supplier detection
    Returns:
        {
            "supplier": supplier_name or None,
            "confidence": int,
            "multiple_matches": bool
        }
    """

    if not detected_name:
        return {"supplier": None, "confidence": 0, "multiple_matches": False}

    def _normalize_text(value):
        if not value:
            return ""
        text = str(value).strip().lower()
        text = re.sub(r"[^a-z0-9\s]", " ", text)
        return " ".join(text.split())

    detected_norm = _normalize_text(detected_name)

    try:
        suppliers = frappe.get_all(
            "Supplier",
            fields=["name", "supplier_name", "supplier_code", "tax_id"]
        )
    except Exception:
        suppliers = frappe.get_all(
            "Supplier",
            fields=["name", "supplier_name"]
        )

    # ----------------------------
    # 1️⃣ Exact Match (Strongest)
    # ----------------------------
    for supplier in suppliers:
        supplier_name = supplier.get("supplier_name") or ""
        supplier_code = supplier.get("supplier_code") or supplier.get("name") or ""
        tax_id = supplier.get("tax_id") or ""

        if _normalize_text(supplier_name) == detected_norm:
            return {"supplier": supplier["name"], "confidence": 100, "multiple_matches": False}

        if _normalize_text(supplier_code) == detected_norm:
            return {"supplier": supplier["name"], "confidence": 100, "multiple_matches": False}

        if _normalize_text(tax_id) == detected_norm:
            return {"supplier": supplier["name"], "confidence": 100, "multiple_matches": False}

    # ----------------------------
    # 2️⃣ Fuzzy Similarity
    # ----------------------------
    scores = []

    for supplier in suppliers:
        supplier_name = supplier.get("supplier_name") or ""
        supplier_code = supplier.get("supplier_code") or supplier.get("name") or ""
        tax_id = supplier.get("tax_id") or ""

        for candidate in {supplier_name, supplier_code, tax_id}:
            candidate_norm = _normalize_text(candidate)
            if not candidate_norm:
                continue

            score = max(
                fuzz.token_sort_ratio(detected_norm, candidate_norm),
                fuzz.partial_ratio(detected_norm, candidate_norm),
                fuzz.ratio(detected_norm, candidate_norm)
            )
            scores.append((score, supplier["name"]))

    if not scores:
        return {"supplier": None, "confidence": 0, "multiple_matches": False}

    scores.sort(reverse=True)

    best_score, best_supplier = scores[0]

    # Already on 0-100 scale
    confidence = int(best_score)

    # ----------------------------
    # 3️⃣ If too many similar matches
    # ----------------------------
    close_matches = [s for s in scores if s[0] >= 80]

    if len(close_matches) > 1:
        return {
            "supplier": None,
            "confidence": confidence,
            "multiple_matches": True
        }

    # ----------------------------
    # 4️⃣ Threshold rule
    # ----------------------------
    if confidence >= 80:
        return {
            "supplier": best_supplier,
            "confidence": confidence,
            "multiple_matches": False
        }

    return {"supplier": None, "confidence": confidence, "multiple_matches": False}