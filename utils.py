"""
utils.py
Helper utilities for PDF text editing, matching, and UI display.
"""

import re
import unicodedata
import pandas as pd


# ------------------------------------------------------------------ #
# RTL / Arabic helpers
# ------------------------------------------------------------------ #

def contains_arabic(text: str) -> bool:
    """Return True if the text contains Arabic / RTL characters."""
    for char in text:
        if unicodedata.bidirectional(char) in ("R", "AL", "AN"):
            return True
    return False


def detect_text_direction(text: str) -> str:
    """Return 'rtl' if the text is predominantly RTL, else 'ltr'."""
    rtl_count = sum(1 for c in text if unicodedata.bidirectional(c) in ("R", "AL", "AN"))
    ltr_count = sum(1 for c in text if unicodedata.bidirectional(c) in ("L",))
    return "rtl" if rtl_count >= ltr_count else "ltr"


def normalize_text(text: str) -> str:
    """Normalize Arabic and English text for tolerant matching."""
    if not text:
        return ""

    text = unicodedata.normalize("NFKC", text)
    text = text.strip().lower()

    arabic_diacritics = re.compile(
        r"[\u0610-\u061A\u064B-\u065F\u0670\u06D6-\u06ED]"
    )
    text = arabic_diacritics.sub("", text)
    text = text.replace("ـ", "")
    text = text.replace("أ", "ا").replace("إ", "ا").replace("آ", "ا")
    text = text.replace("ة", "ه")
    text = text.replace("ى", "ي")
    text = text.replace("ؤ", "و").replace("ئ", "ي")

    text = re.sub(r"[^\w\s\u0600-\u06FF]", " ", text)
    text = re.sub(r"\s+", " ", text).strip()
    return text


# ------------------------------------------------------------------ #
# Color helpers
# ------------------------------------------------------------------ #

def rgb_to_hex(r: float, g: float, b: float) -> str:
    """Convert (r, g, b) floats in [0, 1] to CSS hex string."""
    return "#{:02x}{:02x}{:02x}".format(int(r * 255), int(g * 255), int(b * 255))


def hex_to_rgb(hex_color: str) -> tuple:
    """Convert CSS hex string to (r, g, b) floats in [0, 1]."""
    hex_color = hex_color.lstrip("#")
    if len(hex_color) == 3:
        hex_color = "".join(c * 2 for c in hex_color)
    r = int(hex_color[0:2], 16) / 255.0
    g = int(hex_color[2:4], 16) / 255.0
    b = int(hex_color[4:6], 16) / 255.0
    return (r, g, b)


# ------------------------------------------------------------------ #
# DataFrame builder
# ------------------------------------------------------------------ #

def elements_to_dataframe(elements: list) -> pd.DataFrame:
    """Convert editable text elements to a display-ready DataFrame."""
    if not elements:
        return pd.DataFrame()

    rows = []
    for element in elements:
        direction = detect_text_direction(element.text)
        kind_value = getattr(element, "kind", "span")
        source_value = getattr(element, "source", "native")
        rows.append(
            {
                "#": element.index,
                "النص / Text": element.text,
                "النوع / Type": kind_value,
                "المصدر / Source": source_value,
                "الخط / Font": element.font_name,
                "الحجم / Size": round(float(element.font_size), 2),
                "اللون / Color": rgb_to_hex(*element.color),
                "X0": round(element.x0, 1),
                "Y0": round(element.y0, 1),
                "X1": round(element.x1, 1),
                "Y1": round(element.y1, 1),
                "الاتجاه / Dir": direction.upper(),
            }
        )

    return pd.DataFrame(rows)


# ------------------------------------------------------------------ #
# Font flags decoder
# ------------------------------------------------------------------ #

def decode_font_flags(flags: int) -> dict:
    """Decode PyMuPDF span flags into human-readable properties."""
    return {
        "superscript": bool(flags & 1),
        "italic": bool(flags & 2),
        "serif": bool(flags & 4),
        "monospace": bool(flags & 8),
        "bold": bool(flags & 16),
    }


# ------------------------------------------------------------------ #
# Text diff helper
# ------------------------------------------------------------------ #

def simple_diff(old: str, new: str) -> str:
    """Return a simple inline diff string showing what changed."""
    old_words = old.split()
    new_words = new.split()

    removed = set(old_words) - set(new_words)
    added = set(new_words) - set(old_words)

    parts = []
    if removed:
        parts.append("🔴 حُذف / Removed: " + ", ".join(f'\"{w}\"' for w in removed))
    if added:
        parts.append("🟢 أُضيف / Added: " + ", ".join(f'\"{w}\"' for w in added))
    if not removed and not added:
        parts.append("🔵 تغيير في التنسيق فقط / Formatting change only")

    return " | ".join(parts) if parts else "لا يوجد فرق / No difference"


# ------------------------------------------------------------------ #
# PDF validation
# ------------------------------------------------------------------ #

def validate_pdf_bytes(data: bytes) -> tuple[bool, str]:
    """Quick validation of uploaded bytes."""
    if len(data) < 10:
        return False, "الملف فارغ أو تالف / File is empty or corrupt."
    if data[:4] != b"%PDF":
        return False, "ليس ملف PDF صالح / Not a valid PDF file."
    return True, "OK"


def estimate_is_scanned(elements: list) -> bool:
    """Heuristic: if no text elements are extracted, the page is likely scanned."""
    return len(elements) == 0
