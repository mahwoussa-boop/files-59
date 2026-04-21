"""
pdf_editor.py
Core PDF editing logic using PyMuPDF (fitz).
Handles text extraction, property detection, and in-place replacement.
"""

import fitz  # PyMuPDF
import io
from dataclasses import dataclass, field
from typing import Optional


@dataclass
class TextElement:
    """Represents a single text element extracted from a PDF page."""
    index: int
    text: str
    page_num: int
    x0: float
    y0: float
    x1: float
    y1: float
    font_name: str
    font_size: float
    color: tuple          # (r, g, b) in 0-1 range
    block_no: int
    line_no: int
    span_no: int
    flags: int = 0        # bold / italic flags
    origin: tuple = field(default_factory=lambda: (0.0, 0.0))

    @property
    def bbox(self):
        return (self.x0, self.y0, self.x1, self.y1)

    @property
    def width(self):
        return self.x1 - self.x0

    @property
    def height(self):
        return self.y1 - self.y0

    @property
    def color_hex(self):
        r, g, b = [int(c * 255) for c in self.color]
        return f"#{r:02x}{g:02x}{b:02x}"


class PDFEditor:
    """
    Handles PDF loading, text extraction, and in-place text replacement.

    Strategy for replacement:
      1. Draw a white (or background-colored) rectangle over the old text bbox.
      2. Insert new text at the same position with matched font properties.
      3. If the embedded font is available in the document, reuse it;
         otherwise fall back to the closest standard font.
    """

    # Fallback font mapping: partial font-name fragments → standard PDF font
    FONT_FALLBACKS = {
        "arial":       "Helvetica",
        "helvetica":   "Helvetica",
        "times":       "Times-Roman",
        "courier":     "Courier",
        "verdana":     "Helvetica",
        "calibri":     "Helvetica",
        "georgia":     "Times-Roman",
        "tahoma":      "Helvetica",
        "trebuchet":   "Helvetica",
        "impact":      "Helvetica-Bold",
    }

    def __init__(self):
        self.doc: Optional[fitz.Document] = None
        self.original_bytes: bytes = b""
        self.filename: str = ""
        # Stack of (page_num, edit_description) for undo support
        self._history: list = []
        # Snapshot of doc bytes before each edit (for undo)
        self._snapshots: list = []

    # ------------------------------------------------------------------ #
    #  Loading
    # ------------------------------------------------------------------ #

    def load(self, pdf_bytes: bytes, filename: str = "document.pdf"):
        """Load a PDF from bytes."""
        self.original_bytes = pdf_bytes
        self.filename = filename
        self.doc = fitz.open(stream=pdf_bytes, filetype="pdf")
        self._history.clear()
        self._snapshots.clear()

    def is_loaded(self) -> bool:
        return self.doc is not None

    @property
    def page_count(self) -> int:
        return len(self.doc) if self.doc else 0

    # ------------------------------------------------------------------ #
    #  Text extraction
    # ------------------------------------------------------------------ #

    def extract_text_elements(self, page_num: int) -> list[TextElement]:
        """
        Extract all text spans from a page with full property metadata.
        Returns a flat list of TextElement objects sorted top-to-bottom.
        """
        if not self.doc or page_num >= len(self.doc):
            return []

        page = self.doc[page_num]
        elements = []
        idx = 0

        # dict mode gives us per-span font details
        blocks = page.get_text("dict", flags=fitz.TEXT_PRESERVE_WHITESPACE)["blocks"]

        for block in blocks:
            if block.get("type") != 0:   # 0 = text block
                continue
            b_no = block.get("number", 0)
            for l_no, line in enumerate(block.get("lines", [])):
                for s_no, span in enumerate(line.get("spans", [])):
                    raw_text = span.get("text", "").strip()
                    if not raw_text:
                        continue

                    bbox = span["bbox"]          # (x0, y0, x1, y1)
                    origin = span.get("origin", (bbox[0], bbox[3]))

                    # Color is stored as packed int in PyMuPDF
                    color_int = span.get("color", 0)
                    color_rgb = _int_to_rgb(color_int)

                    elem = TextElement(
                        index=idx,
                        text=raw_text,
                        page_num=page_num,
                        x0=bbox[0], y0=bbox[1],
                        x1=bbox[2], y1=bbox[3],
                        font_name=span.get("font", "Helvetica"),
                        font_size=round(span.get("size", 12), 2),
                        color=color_rgb,
                        block_no=b_no,
                        line_no=l_no,
                        span_no=s_no,
                        flags=span.get("flags", 0),
                        origin=origin,
                    )
                    elements.append(elem)
                    idx += 1

        # Sort top-to-bottom, left-to-right
        elements.sort(key=lambda e: (round(e.y0, 1), e.x0))
        # Re-index after sort
        for i, e in enumerate(elements):
            e.index = i

        return elements

    # ------------------------------------------------------------------ #
    #  Page rendering (for preview)
    # ------------------------------------------------------------------ #

    def render_page(self, page_num: int, zoom: float = 1.5) -> bytes:
        """Render a page to PNG bytes at the given zoom level."""
        if not self.doc or page_num >= len(self.doc):
            return b""
        page = self.doc[page_num]
        mat = fitz.Matrix(zoom, zoom)
        pix = page.get_pixmap(matrix=mat, alpha=False)
        return pix.tobytes("png")

    # ------------------------------------------------------------------ #
    #  Text replacement
    # ------------------------------------------------------------------ #

    def replace_text(
        self,
        page_num: int,
        element: TextElement,
        new_text: str,
        font_size_override: Optional[float] = None,
        auto_fit: bool = True,
    ) -> dict:
        """
        Replace the text of `element` on the given page.

        Approach:
          1. Snapshot current state for undo.
          2. Cover old text with a white (filled) rectangle.
          3. Insert new text at the same origin with matched properties.

        Returns a result dict with keys: success, message, font_used, font_size_used.
        """
        if not self.doc:
            return {"success": False, "message": "No document loaded."}

        # -- Snapshot for undo --
        self._snapshots.append(self.doc.tobytes())
        self._history.append(f"Page {page_num + 1}: '{element.text}' → '{new_text}'")

        page = self.doc[page_num]
        rect = fitz.Rect(element.x0, element.y0, element.x1, element.y1)

        # 1. Cover old text
        # Try to detect background color; default white
        bg_color = _detect_background(page, rect)
        page.draw_rect(rect, color=None, fill=bg_color)

        # 2. Determine font to use
        font_name, font_source = self._resolve_font(element.font_name)

        # 3. Determine font size
        font_size = font_size_override or element.font_size
        if auto_fit and font_size_override is None:
            font_size = self._fit_font_size(
                new_text, font_name, element.font_size, element.width, element.height
            )

        # 4. Insert new text
        color = element.color  # (r, g, b) in 0-1 range

        try:
            # Use insert_text for precise placement
            rc = page.insert_text(
                fitz.Point(element.x0, element.origin[1]),
                new_text,
                fontname=font_name,
                fontsize=font_size,
                color=color,
                render_mode=0,
            )
            if rc < 0:
                # insert_text returns chars written; negative means failure
                raise RuntimeError("insert_text returned error code")

            return {
                "success": True,
                "message": f"Text replaced successfully.",
                "font_used": font_name,
                "font_source": font_source,
                "font_size_used": font_size,
            }

        except Exception as e:
            # Roll back snapshot on failure
            self._undo_internal()
            return {"success": False, "message": f"Replacement failed: {e}"}

    # ------------------------------------------------------------------ #
    #  Undo
    # ------------------------------------------------------------------ #

    def undo(self) -> bool:
        """Restore the document to the state before the last edit."""
        if not self._snapshots:
            return False
        self._undo_internal()
        return True

    def _undo_internal(self):
        snapshot = self._snapshots.pop()
        self.doc = fitz.open(stream=snapshot, filetype="pdf")
        if self._history:
            self._history.pop()

    @property
    def history(self) -> list[str]:
        return list(self._history)

    # ------------------------------------------------------------------ #
    #  Export
    # ------------------------------------------------------------------ #

    def export_bytes(self) -> bytes:
        """Return the current document as PDF bytes (deflated)."""
        if not self.doc:
            return b""
        return self.doc.tobytes(deflate=True)

    # ------------------------------------------------------------------ #
    #  Internal helpers
    # ------------------------------------------------------------------ #

    def _resolve_font(self, original_font_name: str) -> tuple[str, str]:
        """
        Try to find an appropriate font name for insertion.
        Returns (font_name_for_fitz, source_description).
        """
        lower = original_font_name.lower()

        # Check if bold/italic flags can be inferred from font name
        is_bold   = "bold"   in lower or "heavy" in lower or "black" in lower
        is_italic = "italic" in lower or "oblique" in lower

        # Walk fallback table
        for fragment, base in self.FONT_FALLBACKS.items():
            if fragment in lower:
                if is_bold and is_italic:
                    mapped = base + "-BoldOblique" if "Times" in base else base + "-BoldOblique"
                elif is_bold:
                    mapped = base.replace("Roman", "Bold") if "Roman" in base else base + "-Bold"
                elif is_italic:
                    mapped = base.replace("Roman", "Italic") if "Roman" in base else base + "-Oblique"
                else:
                    mapped = base
                return mapped, f"fallback (matched '{fragment}')"

        # Default: Helvetica family
        if is_bold and is_italic:
            return "Helvetica-BoldOblique", "default fallback"
        if is_bold:
            return "Helvetica-Bold", "default fallback"
        if is_italic:
            return "Helvetica-Oblique", "default fallback"
        return "Helvetica", "default fallback"

    def _fit_font_size(
        self,
        text: str,
        font_name: str,
        original_size: float,
        max_width: float,
        max_height: float,
    ) -> float:
        """
        Reduce font size iteratively until `text` fits within the bounding box.
        Minimum font size is 4pt.
        """
        size = original_size
        try:
            temp_doc = fitz.open()
            temp_page = temp_doc.new_page(width=max_width * 10, height=max_height * 10)
            while size >= 4:
                # Measure text width at current size
                tw = fitz.get_text_length(text, fontname=font_name, fontsize=size)
                if tw <= max_width:
                    break
                size -= 0.5
            temp_doc.close()
        except Exception:
            pass
        return max(size, 4.0)


# ------------------------------------------------------------------ #
#  Module-level helpers
# ------------------------------------------------------------------ #

def _int_to_rgb(color_int: int) -> tuple:
    """Convert PyMuPDF packed integer color to (r, g, b) floats in [0, 1]."""
    r = ((color_int >> 16) & 0xFF) / 255.0
    g = ((color_int >> 8)  & 0xFF) / 255.0
    b = (color_int         & 0xFF) / 255.0
    return (r, g, b)


def _detect_background(page: fitz.Page, rect: fitz.Rect) -> tuple:
    """
    Sample a small area around the text bbox to guess background color.
    Falls back to white (1, 1, 1) if detection fails.
    """
    try:
        # Render a tiny portion of the page around the rect
        clip = fitz.Rect(rect.x0 - 2, rect.y0 - 2, rect.x1 + 2, rect.y1 + 2)
        pix = page.get_pixmap(clip=clip, alpha=False)
        # Sample top-left corner pixel
        sample = pix.pixel(0, 0)  # returns (r, g, b)
        return tuple(c / 255.0 for c in sample[:3])
    except Exception:
        return (1.0, 1.0, 1.0)
