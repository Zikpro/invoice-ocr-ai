import os
import base64
import mimetypes
import requests
import frappe
from frappe import _

DEEPINFRA_API_URL = "https://api.deepinfra.com/v1/openai/chat/completions"
DEEPSEEK_MODEL = "deepseek-ai/DeepSeek-OCR"


# ============================================================
# FILE ENCODING (FULL PATH + FILE_URL SAFE)
# ============================================================

def _encode_file_to_base64(file_input):
    """
    Accepts:
    - Full absolute file path
    - OR Frappe file_url
    """

    # Case 1: Already full system path
    if os.path.exists(file_input):
        file_path = file_input

    else:
        # Case 2: file_url → convert to system path
        file_url = file_input.lstrip("/")
        file_path = frappe.get_site_path(file_url)

    if not os.path.exists(file_path):
        frappe.throw(_("File not found"))

    with open(file_path, "rb") as f:
        return base64.b64encode(f.read()).decode("utf-8")


# ============================================================
# MIME DETECTION (FULL PATH SAFE)
# ============================================================

def _detect_mime_type(file_input):

    # If full path → use directly
    if os.path.exists(file_input):
        mime, _ = mimetypes.guess_type(file_input)
    else:
        mime, _ = mimetypes.guess_type(file_input)

    return mime or "image/png"


# ============================================================
# MAIN OCR FUNCTION
# ============================================================

def run_vision_ocr(file_input):

    api_key = frappe.conf.get("deepinfra_api_key")

    if not api_key:
        frappe.throw(_("DEEPINFRA API key not configured"))

    base64_file = _encode_file_to_base64(file_input)
    mime_type = _detect_mime_type(file_input)

    payload = {
        "model": DEEPSEEK_MODEL,
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
