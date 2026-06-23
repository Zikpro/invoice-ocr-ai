import frappe
import difflib


def intelligent_item_match(item_name: str):
    """
    Enterprise-safe Item Matching

    Returns:
    {
        "item": item_code or None,
        "confidence": int,
        "multiple_matches": bool
    }
    """

    if not item_name:
        return {
            "item": None,
            "confidence": 0,
            "multiple_matches": False
        }

    item_name = item_name.strip().lower()

    items = frappe.get_all(
        "Item",
        fields=["name", "item_name"]
    )

    # --------------------------------
    # 1. Exact Match
    # --------------------------------

    for item in items:

        if not item.item_name:
            continue

        if item.item_name.lower() == item_name:
            return {
                "item": item.name,
                "confidence": 100,
                "multiple_matches": False
            }

    # --------------------------------
    # 2. Fuzzy Match
    # --------------------------------

    scores = []

    for item in items:

        if not item.item_name:
            continue

        score = difflib.SequenceMatcher(
            None,
            item_name,
            item.item_name.lower()
        ).ratio()

        scores.append((score, item.name))

    if not scores:
        return {
            "item": None,
            "confidence": 0,
            "multiple_matches": False
        }

    scores.sort(reverse=True)

    best_score, best_item = scores[0]

    confidence = int(best_score * 100)

    # --------------------------------
    # 3. Multiple Similar Matches
    # --------------------------------

    close_matches = [
        s for s in scores
        if s[0] > 0.75
    ]

    if len(close_matches) > 1:
        return {
            "item": None,
            "confidence": confidence,
            "multiple_matches": True
        }

    # --------------------------------
    # 4. Threshold
    # --------------------------------

    if confidence >= 80:
        return {
            "item": best_item,
            "confidence": confidence,
            "multiple_matches": False
        }

    return {
        "item": None,
        "confidence": confidence,
        "multiple_matches": False
    }