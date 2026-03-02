app_name = "invoice_ocr"
app_title = "Invoice OCR"
app_publisher = "Zikpro Ltd"
app_description = "AI-powered Invoice OCR to Purchase Invoice automation using DeepInfra"
app_email = "info@zikpro.com"
app_license = "MIT"

# -------------------------------------------------
# DocType JS (Cloud-safe)
# -------------------------------------------------

doctype_js = {
    "Invoice OCR": "public/js/invoice_ocr.js"
}

# -------------------------------------------------
# Optional: App visibility in Desk (disabled)
# -------------------------------------------------
# add_to_apps_screen = [
#     {
#         "name": "invoice_ocr",
#         "logo": "/assets/invoice_ocr/logo.png",
#         "title": "OCR-AI",
#         "route": "/invoice_ocr",
#         "has_permission": "invoice_ocr.api.permission.has_app_permission"
#     }
# ]

# -------------------------------------------------
# Notes
# -------------------------------------------------
# - No global JS/CSS injected (cloud safe)
# - No core DocType overrides
# - Only Invoice OCR DocType uses custom JS
