# ============================================================
# HEADER PROMPT
# ============================================================
HEADER_PROMPT_TEMPLATE = """
Extract invoice header information.

Return ONLY valid JSON.

{
    "invoice_number": "",
    "invoice_date": "",
    "supplier_name": "",
    "currency": "",
    "grand_total": 0
}
"""


ITEMS_PROMPT_TEMPLATE = """
You are extracting line items from a {table_structure} invoice.

Rules:
- If item name contains "Charges", "Freight", "Carriage", classify separately
- Do NOT mix tax rows with goods
- Validate qty * rate = amount


Return JSON array:
 [
    {{
      "item_name": null,
      "qty": 1,
      "rate": 0,
      "amount": 0
    }}
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