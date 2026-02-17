# ============================================================
# HEADER PROMPT
# ============================================================

HEADER_PROMPT = """
Extract invoice header from OCR text.

Return JSON:

{
  "supplier_name": null,
  "invoice_number": null,
  "invoice_date": null,
  "currency": null
}
"""


# ============================================================
# ITEMS PROMPT
# ============================================================

ITEMS_PROMPT = """
Extract invoice line items.

Return JSON array:

[
  {
    "item_name": null,
    "qty": 1,
    "rate": 0,
    "amount": 0
  }
]
"""


# ============================================================
# TAX PROMPT
# ============================================================

TAX_PROMPT = """
Extract all taxes from invoice.

Return JSON array:

[
  {
    "label": null,
    "amount": 0,
    "rate": null,
    "charge_type": "Actual",
    "account_head": null
  }
]
"""