import os
import base64
import mimetypes
import requests
import frappe
from frappe import _
from pypdf import PdfReader

DEEPINFRA_API_URL = "https://api.deepinfra.com/v1/openai/chat/completions"
VISION_MODEL = "meta-llama/Llama-3.2-11B-Vision-Instruct"
TEXT_MODEL = "deepseek-ai/DeepSeek-V3"


# ============================================================
# 🔒 FILE PATH VALIDATION (FIXED + MARKETPLACE SAFE)
# ============================================================

def _validate_file_path(file_path):
    """
    Marketplace safe + supports Frappe file URLs
    """

    if not file_path:
        frappe.throw(_("Invalid file path"))

    # Handle Frappe file URLs
    if file_path.startswith("/private") or file_path.startswith("/files"):
        file_path = frappe.get_site_path(file_path.lstrip("/"))

    abs_path = os.path.abspath(file_path)

    if not os.path.exists(abs_path):
        frappe.throw(_("File not found"))

    return abs_path


# ============================================================
# GET API KEY FROM SETTINGS
# ============================================================

def get_deepinfra_api_key():

    settings = frappe.get_single("DeepInfra Settings")
    api_key = settings.get_password("deepinfra_api_key")

    if not api_key:
        frappe.log_error("DeepInfra API key missing", "OCR Config Error")
        return None

    return api_key


# ============================================================
# FILE ENCODING
# ============================================================

def _encode_file_to_base64(file_path):

    file_path = _validate_file_path(file_path)

    with open(file_path, "rb") as f:
        return base64.b64encode(f.read()).decode("utf-8")


def _detect_mime_type(file_path):
    mime, _ = mimetypes.guess_type(file_path)
    return mime or "image/png"


# ============================================================
# PDF TEXT EXTRACTION
# ============================================================

def extract_pdf_text(file_path):

    file_path = _validate_file_path(file_path)

    try:
        reader = PdfReader(file_path)
        text = ""

        for page in reader.pages:
            extracted = page.extract_text()
            if extracted:
                text += extracted + "\n"

        return text.strip()

    except Exception as e:
        frappe.log_error(str(e), "PDF Extraction Failed")
        return ""


# ============================================================
# IMAGE OCR (VISION MODEL)
# ============================================================
def run_image_ocr(file_path):

    file_path = _validate_file_path(file_path)

    api_key = get_deepinfra_api_key()

    if not api_key:
        return ""

    try:

        frappe.log_error(f"Processing file: {file_path}", "OCR Debug")

        base64_file = _encode_file_to_base64(file_path)
        mime_type = _detect_mime_type(file_path)

        payload = {
            "model": VISION_MODEL,
            "messages": [
                {
                    "role": "user",
                    "content": [
                        {
                            "type": "text",
                            "text": """Extract ALL text from this invoice EXACTLY as written.

Rules:
- Do NOT summarize
- Do NOT explain
- Do NOT add extra words
- Preserve line breaks
- Keep original structure

Output:
Plain raw text only
"""
                        },
                        {
                            "type": "image_url",
                            "image_url": {
                                "url": f"data:{mime_type};base64,{base64_file}"
                            }
                        }
                    ]
                }
            ],
            "temperature": 0
        }

        headers = {
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json"
        }

        response = requests.post(
            DEEPINFRA_API_URL,
            json=payload,
            headers=headers,
            timeout=(10,120)
        )

        # 🔴 API error handling
        if response.status_code != 200:
            frappe.log_error(response.text, "DeepInfra API Error")
            return ""

        data = response.json()

        if "choices" not in data:
            frappe.log_error(str(data), "DeepInfra Invalid Response")
            return ""

        content = data["choices"][0]["message"]["content"]

        # 🟡 Handle list response (rare case)
        if isinstance(content, list):
            content = " ".join(c.get("text", "") for c in content)

        content = (content or "").strip()

        # 🔴 SAFETY CHECK (VERY IMPORTANT)
        if not content or len(content) < 20:
            frappe.log_error(content, "Weak OCR Output")
            return ""

        return content

    except requests.exceptions.Timeout:
        frappe.log_error("DeepInfra Timeout", "OCR Timeout")
        return ""

    except Exception as e:
        frappe.log_error(str(e), "OCR Vision Error")
        return ""

# ============================================================
# MAIN OCR HANDLER
# ============================================================

def run_vision_ocr(file_path):
    """
    Smart handler:
    - PDF → extract text
    - Image → Vision OCR
    """

    try:

        file_path = _validate_file_path(file_path)

        if not os.path.exists(file_path):
            return ""

        file_size = os.path.getsize(file_path)

        # Image limit
        if not file_path.lower().endswith(".pdf"):
            if file_size > 5 * 1024 * 1024:
                frappe.log_error(
                    f"Image too large: {file_size}",
                    "OCR Size Limit"
                )
                return ""

        # PDF limit
        if file_path.lower().endswith(".pdf"):
            if file_size > 10 * 1024 * 1024:
                frappe.log_error(
                    f"PDF too large: {file_size}",
                    "OCR Size Limit"
                )
                return ""

            return extract_pdf_text(file_path)

        return run_image_ocr(file_path)

    except Exception as e:
        frappe.log_error(str(e), "OCR Engine Fatal Error")
        return ""
