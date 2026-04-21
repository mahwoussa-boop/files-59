"""
pdf_editor.py
Core PDF editing logic using PyMuPDF (fitz).
Supports extraction and replacement at both span level and word level.
"""

import fitz  # PyMuPDF
from dataclasses import dataclass, field
from typing import Optional


@dataclass
class TextElement:
    """Represents a single editable text element extracted from a PDF page."""

    index: int
    text: str
    page_num: int
    x0: float
    y0: float
    x1: float
    y1: float
    font_name: str
    font_size: float
    color: tuple
    block_no: int
    line_no: int
    span_no: int
    flags: int = 0
    origin: tuple = field(default_factory=lambda: (0.0, 0.0))
    kind: str = "span"
    word_no: int = -1

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

    The editor supports two selection granularities:
      1. span: edit the full extracted text span.
      2. word: edit an individual word with inherited style metadata.
    """

    FONT_FALLBACKS = {
        "arial": "Helvetica",
        "helvetica": "Helvetica",
        "times": "Times-Roman",
        "courier": "Courier",
        "verdana": "Helvetica",
        "calibri": "Helvetica",
        "georgia": "Times-Roman",
        "tahoma": "Helvetica",
        "trebuchet": "Helvetica",
        "impact": "Helvetica-Bold",
    }

    def __init__(self):
        self.doc: Optional[fitz.Document] = None
        self.original_bytes: bytes = b""
        self.filename: str = ""
        self._history: list = []
        self._snapshots: list = []

    # ------------------------------------------------------------------ #
    # Loading
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
    # Text extraction
    # ------------------------------------------------------------------ #

    def extract_text_elements(self, page_num: int, mode: str = "span") -> list[TextElement]:
        """Return editable text elements for the selected page and mode."""
        if not self.doc or page_num >= len(self.doc):
            return []
        if mode == "word":
            return self._extract_word_elements(page_num)
        return self._extract_span_elements(page_num)

    def _extract_span_elements(self, page_num: int) -> list[TextElement]:
        """Extract text spans with styling metadata."""
        page = self.doc[page_num]
        elements = []
        idx = 0
        blocks = page.get_text("dict", flags=fitz.TEXT_PRESERVE_WHITESPACE).get("blocks", [])

        for block in blocks:
            if block.get("type") != 0:
                continue
            b_no = block.get("number", 0)
            for l_no, line in enumerate(block.get("lines", [])):
                for s_no, span in enumerate(line.get("spans", [])):
                    raw_text = span.get("text", "")
                    if not raw_text or not raw_text.strip():
                        continue

                    bbox = span["bbox"]
                    origin = span.get("origin", (bbox[0], bbox[3]))
                    color_int = span.get("color", 0)
                    color_rgb = _int_to_rgb(color_int)

                    elements.append(
                        TextElement(
                            index=idx,
                            text=raw_text.strip(),
                            page_num=page_num,
                            x0=bbox[0],
                            y0=bbox[1],
                            x1=bbox[2],
                            y1=bbox[3],
                            font_name=span.get("font", "Helvetica"),
                            font_size=round(span.get("size", 12), 2),
                            color=color_rgb,
                            block_no=b_no,
                            line_no=l_no,
                            span_no=s_no,
                            flags=span.get("flags", 0),
                            origin=origin,
                            kind="span",
                            word_no=-1,
                        )
                    )
                    idx += 1

        elements.sort(key=lambda e: (round(e.y0, 1), e.x0))
        for i, e in enumerate(elements):
            e.index = i
        return elements

    def _extract_word_elements(self, page_num: int) -> list[TextElement]:
        """Extract individual words and inherit style metadata from the nearest span."""
        page = self.doc[page_num]
        span_elements = self._extract_span_elements(page_num)
        words = page.get_text("words", flags=fitz.TEXT_PRESERVE_WHITESPACE)
        elements = []

        for idx, word in enumerate(words):
            x0, y0, x1, y1, raw_text, block_no, line_no, word_no = word
            clean_text = (raw_text or "").strip()
            if not clean_text:
                continue

            matched = self._match_span_for_word(
                x0=x0,
                y0=y0,
                x1=x1,
                y1=y1,
                block_no=block_no,
                line_no=line_no,
                spans=span_elements,
            )

            if matched:
                font_name = matched.font_name
                font_size = matched.font_size
                color = matched.color
                flags = matched.flags
                baseline_y = matched.origin[1]
                span_no = matched.span_no
            else:
                font_name = "Helvetica"
                font_size = max(round(y1 - y0, 2), 8.0)
                color = (0.0, 0.0, 0.0)
                flags = 0
                baseline_y = y1
                span_no = 0

            elements.append(
                TextElement(
                    index=len(elements),
                    text=clean_text,
                    page_num=page_num,
                    x0=x0,
                    y0=y0,
                    x1=x1,
                    y1=y1,
                    font_name=font_name,
                    font_size=font_size,
                    color=color,
                    block_no=block_no,
                    line_no=line_no,
                    span_no=span_no,
                    flags=flags,
                    origin=(x0, baseline_y),
                    kind="word",
                    word_no=word_no,
                )
            )

        elements.sort(key=lambda e: (round(e.y0, 1), e.x0))
        for i, e in enumerate(elements):
            e.index = i
        return elements

    # ------------------------------------------------------------------ #
    # Page rendering
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
    # Text replacement
    # ------------------------------------------------------------------ #

    def replace_text(
        self,
        page_num: int,
        element: TextElement,
        new_text: str,
        font_size_override: Optional[float] = None,
        auto_fit: bool = True,
    ) -> dict:
        """Replace the selected text element on the given page."""
        if not self.doc:
            return {"success": False, "message": "No document loaded."}

        new_text = new_text.strip()
        if not new_text:
            return {"success": False, "message": "New text is empty."}

        self._snapshots.append(self.doc.tobytes())
        self._history.append(
            f"Page {page_num + 1} [{element.kind}]: '{element.text}' → '{new_text}'"
        )

        page = self.doc[page_num]
        rect = fitz.Rect(element.x0, element.y0, element.x1, element.y1)

        bg_color = _detect_background(page, rect)
        page.draw_rect(rect, color=None, fill=bg_color)

        font_name, font_source = self._resolve_font(element.font_name)
        font_size = font_size_override or element.font_size
        if auto_fit and font_size_override is None:
            font_size = self._fit_font_size(
                text=new_text,
                font_name=font_name,
                original_size=element.font_size,
                max_width=max(element.width, 5),
                max_height=max(element.height, 5),
            )

        color = element.color
        insert_point = fitz.Point(element.x0, element.origin[1])

        try:
            rc = page.insert_text(
                insert_point,
                new_text,
                fontname=font_name,
                fontsize=font_size,
                color=color,
                render_mode=0,
            )
            if rc < 0:
                raise RuntimeError("insert_text returned error code")

            return {
                "success": True,
                "message": "Text replaced successfully.",
                "font_used": font_name,
                "font_source": font_source,
                "font_size_used": font_size,
                "element_kind": element.kind,
            }
        except Exception as exc:
            self._undo_internal()
            return {"success": False, "message": f"Replacement failed: {exc}"}

    # ------------------------------------------------------------------ #
    # Undo
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
    # Export
    # ------------------------------------------------------------------ #

    def export_bytes(self) -> bytes:
        """Return the current document as PDF bytes."""
        if not self.doc:
            return b""
        return self.doc.tobytes(deflate=True)

    # ------------------------------------------------------------------ #
    # Internal helpers
    # ------------------------------------------------------------------ #

    def _match_span_for_word(
        self,
        x0: float,
        y0: float,
        x1: float,
        y1: float,
        block_no: int,
        line_no: int,
        spans: list[TextElement],
    ) -> Optional[TextElement]:
        """Return the best matching span for a word based on overlap and locality."""
        word_rect = fitz.Rect(x0, y0, x1, y1)
        best_match = None
        best_score = -1.0

        for span in spans:
            if span.block_no != block_no or span.line_no != line_no:
                continue
            span_rect = fitz.Rect(span.x0, span.y0, span.x1, span.y1)
            inter = word_rect & span_rect
            if inter.is_empty:
                continue
            overlap_area = inter.get_area()
            word_area = max(word_rect.get_area(), 1.0)
            score = overlap_area / word_area
            if score > best_score:
                best_score = score
                best_match = span

        if best_match:
            return best_match

        for span in spans:
            span_rect = fitz.Rect(span.x0, span.y0, span.x1, span.y1)
            inter = word_rect & span_rect
            if inter.is_empty:
                continue
            overlap_area = inter.get_area()
            word_area = max(word_rect.get_area(), 1.0)
            score = overlap_area / word_area
            if score > best_score:
                best_score = score
                best_match = span

        return best_match

    def _resolve_font(self, original_font_name: str) -> tuple[str, str]:
        """Map the original font name to a supported insertion font."""
        lower = original_font_name.lower()
        is_bold = "bold" in lower or "heavy" in lower or "black" in lower
        is_italic = "italic" in lower or "oblique" in lower

        for fragment, base in self.FONT_FALLBACKS.items():
            if fragment in lower:
                if is_bold and is_italic:
                    mapped = base.replace("Roman", "BoldItalic") if "Roman" in base else base + "-BoldOblique"
                elif is_bold:
                    mapped = base.replace("Roman", "Bold") if "Roman" in base else base + "-Bold"
                elif is_italic:
                    mapped = base.replace("Roman", "Italic") if "Roman" in base else base + "-Oblique"
                else:
                    mapped = base
                return mapped, f"fallback (matched '{fragment}')"

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
        """Reduce font size iteratively until the text fits inside the target box."""
        size = min(original_size, max(max_height * 0.95, 4.0))
        try:
            while size >= 4.0:
                text_width = fitz.get_text_length(text, fontname=font_name, fontsize=size)
                if text_width <= max_width:
                    break
                size -= 0.5
        except Exception:
            pass
        return max(size, 4.0)


# ------------------------------------------------------------------ #
# Module-level helpers
# ------------------------------------------------------------------ #

def _int_to_rgb(color_int: int) -> tuple:
    """Convert PyMuPDF packed integer color to (r, g, b) floats in [0, 1]."""
    r = ((color_int >> 16) & 0xFF) / 255.0
    g = ((color_int >> 8) & 0xFF) / 255.0
    b = (color_int & 0xFF) / 255.0
    return (r, g, b)


def _detect_background(page: fitz.Page, rect: fitz.Rect) -> tuple:
    """Guess background color around a text rectangle; default to white."""
    try:
        clip = fitz.Rect(rect.x0 - 2, rect.y0 - 2, rect.x1 + 2, rect.y1 + 2)
        pix = page.get_pixmap(clip=clip, alpha=False)
        sample = pix.pixel(0, 0)
        return tuple(c / 255.0 for c in sample[:3])
    except Exception:
        return (1.0, 1.0, 1.0)
