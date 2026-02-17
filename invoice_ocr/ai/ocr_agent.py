from .ocr_nodes import (
    extract_header,
    extract_items,
    extract_taxes,
    score_confidence,
)
from .validation import validate_invoice


def run_ocr_agent(ocr_text: str) -> dict:
    """
    DeepInfra-powered OCR Agent
    Enterprise-safe
    """

    state = {
        "ocr_text": ocr_text,
        "header": {},
        "items": [],
        "charges": [],
        "confidence": 0
    }

    state = extract_header(state)
    state = extract_items(state)
    state = extract_taxes(state)
    state = score_confidence(state)

    validation = validate_invoice(state)

    return {
        "confidence": state["confidence"],
        "data": state,
        "validation": validation
    }