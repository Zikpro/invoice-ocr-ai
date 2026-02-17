import frappe
import difflib


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

    detected_name = detected_name.strip().lower()

    suppliers = frappe.get_all(
        "Supplier",
        fields=["name", "supplier_name"]
    )

    # ----------------------------
    # 1️⃣ Exact Match (Strongest)
    # ----------------------------
    for s in suppliers:
        if s.supplier_name and s.supplier_name.lower() == detected_name:
            return {
                "supplier": s.name,
                "confidence": 100,
                "multiple_matches": False
            }

    # ----------------------------
    # 2️⃣ Fuzzy Similarity
    # ----------------------------
    scores = []

    for s in suppliers:
        if not s.supplier_name:
            continue

        score = difflib.SequenceMatcher(
            None,
            detected_name,
            s.supplier_name.lower()
        ).ratio()

        scores.append((score, s.name))

    if not scores:
        return {"supplier": None, "confidence": 0, "multiple_matches": False}

    scores.sort(reverse=True)

    best_score, best_supplier = scores[0]

    # Convert to %
    confidence = int(best_score * 100)

    # ----------------------------
    # 3️⃣ If too many similar matches
    # ----------------------------
    close_matches = [s for s in scores if s[0] > 0.75]

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