# ============================================================
# HEADER PROMPT
# ============================================================
HEADER_PROMPT_TEMPLATE = """
You are extracting header information from an invoice (Country: {country}, Type: {invoice_type}).

RULES:
- Extract ONLY values that are VISIBLE in the document
- If a field is not visible, return null (not empty string, not 0)
- Do NOT hallucinate or guess values
- Currency: Use currency code (GBP, USD, EUR, PKR, INR, AED) if visible, else null
- Amounts: Return as numbers (no currency symbols)
- Dates: Return in ISO format (YYYY-MM-DD) or null if unparseable

Return ONLY valid JSON object:

{
    "invoice_number": null,
    "invoice_date": null,
    "due_date": null,
    "supplier_name": null,
    "supplier_address": null,
    "currency": null,
    "grand_total": null,
    "net_total": null,
    "tax_total": null,
    "payment_terms": null,
    "purchase_order_number": null,
    "reference_number": null,
    "vendor_tax_id": null,
    "buyer_tax_id": null,
    "country": null
}

Important:
- Return null for any field NOT visible in the OCR text
- Never fill fields with generic or example values
- Preserve exact supplier name as written
"""


ITEMS_PROMPT_TEMPLATE = """
You are extracting line items from a {table_structure} invoice.

RULES:
- Extract ONLY items visible in the document
- Do NOT hallucinate product names or quantities
- Each item should include: item_name, qty, rate, amount
- If qty or rate are missing but amount exists, infer the missing field(s)
  using visible invoice line values
- For ERPNext printed Purchase Invoice layout, prefer accepted_qty,
  ordered_qty, or invoice_qty as the invoice quantity
- Do NOT use received_qty or rejected_qty as invoice quantity
- When a row includes multiple monetary values, prefer the last monetary
  value in the row as the unit rate
- If only amount is visible, set qty=1 and rate=amount
- Currency amounts: return as numbers without symbols
- Return null for any field not visible
- UOM: Nos, kg, ltr, m, box, pcs, etc. (null if not specified)
- Include item_code when explicitly visible on the invoice
- classification should be VALID_ITEM, CHARGE_ROW, TAX_ROW, or NOISE
- Do NOT include tax rows, totals, or section headers in items

Return ONLY valid JSON array:

[
  {
    "item_code": null,
    "item_name": null,
    "description": null,
    "qty": null,
    "rate": null,
    "amount": null,
    "uom": null,
    "classification": "VALID_ITEM"
  }
]

Important:
- Each object must have at least item_name and amount
- Never include generic names like "Widget A", "Widget B"
- Never include tax descriptions in items array
- Do NOT fabricate items not present in the document
"""


# ============================================================
# TAX PROMPT
# ============================================================

TAX_PROMPT = """
Extract all tax rows from the invoice.

RULES:
- Extract ONLY taxes visible in the document
- Do NOT include line items in taxes
- Do NOT hallucinate tax names
- Return null for fields not visible
- Tax examples: VAT, GST, CGST, SGST, IGST, Sales Tax, Service Tax, etc.
- If tax is not explicitly labeled but tax amount can be derived from Grand Total and Net Total, return the derived tax amount

Return ONLY valid JSON array:

[
  {
    "label": null,
    "amount": null,
    "rate": null,
    "charge_type": "Actual",
    "account_head": null
  }
]

Important:
- Return empty array [] if no taxes are visible
- Never fabricate tax rows
- Amount must be a number
- Use the same label visible in the invoice when possible
"""