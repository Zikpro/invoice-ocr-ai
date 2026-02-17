def calculate_confidence(state: dict) -> int:

    score = 0

    header = state.get("header") or {}
    items = state.get("items") or []
    taxes = state.get("taxes") or []

    if header.get("invoice_number"):
        score += 20
    if header.get("invoice_date"):
        score += 20
    if header.get("currency"):
        score += 10

    if items:
        score += 30

    if taxes:
        score += 20

    return min(score, 100)