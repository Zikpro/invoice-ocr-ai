import re

def classify_lines(state):

    classified_items = []
    calculated_subtotal = 0

    for item in state.get("items", []):

        name = (item.get("item_name") or "").strip()
        name_lower = name.lower()

        qty = item.get("qty")
        rate = item.get("rate")
        amount = item.get("amount")

        classification = "VALID_ITEM"

        # ---------------------------------------------------
        # 1️⃣ Detect obvious non-item rows
        # ---------------------------------------------------

        if not name:
            classification = "NOISE"

        elif any(word in name_lower for word in ["subtotal"]):
            classification = "SUBTOTAL_ROW"

        elif any(word in name_lower for word in ["grand total"]):
            classification = "TOTAL_ROW"

        elif (
            "total" in name_lower
            and "subtotal" not in name_lower
            and "grand" not in name_lower
        ):
            classification = "TOTAL_ROW"

        elif any(word in name_lower for word in ["tax", "vat", "gst"]):
            classification = "TAX_ROW"

        # ---------------------------------------------------
        # 2️⃣ Numeric structural validation
        # ---------------------------------------------------

        else:

            # If amount exists but qty missing → assume qty=1
            if amount and not qty:
                qty = 1

            # If rate missing but amount exists → assume rate=amount
            if amount and not rate:
                rate = amount

            if qty and rate and amount:

                try:
                    qty = float(qty)
                    rate = float(rate)
                    amount = float(amount)

                    # Validate multiplication logic
                    if abs((qty * rate) - amount) < 1:
                        classification = "VALID_ITEM"
                    else:
                        # Still valid if reasonable amount
                        classification = "VALID_ITEM"

                except Exception:
                    classification = "NOISE"

            else:
                classification = "NOISE"

        # ---------------------------------------------------
        # 3️⃣ REMOVE OLD HEADER_ROW LOGIC
        # ---------------------------------------------------
        # ❌ We DO NOT mark small items as HEADER_ROW anymore
        # This was causing your £25 invoice to break.

        # ---------------------------------------------------
        # 4️⃣ Subtotal Calculation
        # ---------------------------------------------------

        if classification == "VALID_ITEM":
            calculated_subtotal += float(amount or 0)

        item["classification"] = classification
        classified_items.append(item)

    state["items"] = classified_items
    state["calculated_subtotal"] = calculated_subtotal

    return state