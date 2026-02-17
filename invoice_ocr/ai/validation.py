def validate_invoice(data: dict) -> dict:
    errors = []
    warnings = []

    items = data.get("items") or []
    totals = data.get("totals") or {}

    calculated_net = sum(
        (i.get("qty", 1) or 1) * (i.get("rate", 0) or 0)
        for i in items
    )

    declared_net = totals.get("net_total")

    if declared_net and abs(calculated_net - declared_net) > 1:
        warnings.append("Net total mismatch with line calculation")

    if not items:
        errors.append("No items extracted")

    return {
        "is_valid": len(errors) == 0,
        "warnings": warnings,
        "errors": errors
    }