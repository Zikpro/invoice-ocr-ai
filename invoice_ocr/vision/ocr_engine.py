import os
import base64
import mimetypes
import requests
import frappe
from frappe import _
from pypdf import PdfReader

DEEPINFRA_API_URL = "https://api.deepinfra.com/v1/openai/chat/completions"
VISION_MODEL = "deepseek-ai/DeepSeek-OCR"
TEXT_MODEL = "deepseek-ai/DeepSeek-V3"


# ============================================================
# FILE ENCODING (IMAGE ONLY)
# ============================================================

def _encode_file_to_base64(file_path):
    if not os.path.exists(file_path):
        frappe.throw(_("File not found"))

    with open(file_path, "rb") as f:
        return base64.b64encode(f.read()).decode("utf-8")


def _detect_mime_type(file_path):
    mime, _ = mimetypes.guess_type(file_path)
    return mime or "image/png"


# ============================================================
# PDF TEXT EXTRACTION (Cloud Safe)
# ============================================================

def extract_pdf_text(file_path):
    reader = PdfReader(file_path)
    text = ""

    for page in reader.pages:
        extracted = page.extract_text()
        if extracted:
            text += extracted + "\n"

    return text.strip()


# ============================================================
# IMAGE OCR (VISION MODEL)
# ============================================================

def run_image_ocr(file_path):

    api_key = frappe.conf.get("deepinfra_api_key")
    if not api_key:
        frappe.throw(_("DeepInfra API key not configured"))

    base64_file = _encode_file_to_base64(file_path)
    mime_type = _detect_mime_type(file_path)

    payload = {
        "model": VISION_MODEL,
        "messages": [
            {
                "role": "user",
                "content": [
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
        timeout=120
    )

    response.raise_for_status()

    data = response.json()
    content = data["choices"][0]["message"]["content"]

    if isinstance(content, list):
        return " ".join(c.get("text", "") for c in content)

    return content.strip()


# ============================================================
# UNIVERSAL OCR ENTRY POINT
# ============================================================

def run_vision_ocr(file_path):
    """
    Smart handler:
    - If PDF → extract text
    - If Image → Vision OCR
    """

    if file_path.lower().endswith(".pdf"):
        return extract_pdf_text(file_path)

    return run_image_ocr(file_path)
