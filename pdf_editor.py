"""
pdf_editor.py
Core PDF editing logic using PyMuPDF (fitz).
Supports native text extraction, OCR fallback, smart matching, and in-place replacement.
"""

from dataclasses import dataclass, field
from difflib import SequenceMatcher
from io import BytesIO
from typing import Optional

import fitz  # PyMuPDF
from PIL import Image, ImageOps

from ai_helper import choose_best_candidate_with_ai
from utils import normalize_text

try:
    import pytesseract
except Exception:  # pragma: no cover - optional dependency at runtime
    pytesseract = None


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
    source: str = "native"

    @property
    def bbox(self):
        return (self.x0, self.y0, self.x1, self.y1)

    @property
    def width(self):
        return self.x1 - self.x0

    @property
    def height(self):
        return self.y1 - self.y0


class PDFEditor:
    """Handles PDF loading, extraction, search, smart replacement, and export."""

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
    # Extraction
    # ------------------------------------------------------------------ #

    def extract_text_elements(
        self,
        page_num: int,
        mode: str = "word",
        use_ocr_fallback: bool = False,
    ) -> list[TextElement]:
        if not self.doc or page_num >= len(self.doc):
            return []

        mode = mode or "word"
        if mode == "span":
            elements = self._extract_span_elements(page_num)
        else:
            elements = self._extract_word_elements(page_num)

        if not elements and use_ocr_fallback:
            elements = self._extract_ocr_elements(page_num)
        return elements

    def _extract_span_elements(self, page_num: int) -> list[TextElement]:
        page = self.doc[page_num]
        elements = []
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
                    elements.append(
                        TextElement(
                            index=len(elements),
                            text=raw_text.strip(),
                            page_num=page_num,
                            x0=bbox[0],
                            y0=bbox[1],
                            x1=bbox[2],
                            y1=bbox[3],
                            font_name=span.get("font", "Helvetica"),
                            font_size=round(float(span.get("size", 12)), 2),
                            color=_int_to_rgb(span.get("color", 0)),
                            block_no=b_no,
                            line_no=l_no,
                            span_no=s_no,
                            flags=span.get("flags", 0),
                            origin=origin,
                            kind="span",
                            word_no=-1,
                            source="native",
                        )
                    )

        elements.sort(key=lambda e: (round(e.y0, 1), e.x0))
        for idx, element in enumerate(elements):
            element.index = idx
        return elements

    def _extract_word_elements(self, page_num: int) -> list[TextElement]:
        page = self.doc[page_num]
        spans = self._extract_span_elements(page_num)
        words = page.get_text("words", flags=fitz.TEXT_PRESERVE_WHITESPACE)
        elements = []

        for word in words:
            x0, y0, x1, y1, raw_text, block_no, line_no, word_no = word
            clean_text = (raw_text or "").strip()
            if not clean_text:
                continue

            span = self._match_span_for_word(x0, y0, x1, y1, block_no, line_no, spans)
            if span:
                font_name = span.font_name
                font_size = span.font_size
                color = span.color
                flags = span.flags
                origin = (x0, span.origin[1])
                span_no = span.span_no
            else:
                font_name = "Helvetica"
                font_size = max((y1 - y0) * 0.9, 8.0)
                color = (0.0, 0.0, 0.0)
                flags = 0
                origin = (x0, y1)
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
                    font_size=round(float(font_size), 2),
                    color=color,
                    block_no=block_no,
                    line_no=line_no,
                    span_no=span_no,
                    flags=flags,
                    origin=origin,
                    kind="word",
                    word_no=word_no,
                    source="native",
                )
            )

        elements.sort(key=lambda e: (round(e.y0, 1), e.x0))
        for idx, element in enumerate(elements):
            element.index = idx
        return elements

    def _extract_ocr_elements(self, page_num: int, zoom: float = 3.0) -> list[TextElement]:
        if pytesseract is None or not self.doc:
            return []

        page = self.doc[page_num]
        image = self._page_image(page_num, zoom=zoom)
        gray = ImageOps.grayscale(image)
        processed = gray.point(lambda p: 255 if p > 180 else 0)
        data = pytesseract.image_to_data(
            processed,
            lang="ara+eng",
            output_type=pytesseract.Output.DICT,
            config="--oem 3 --psm 6",
        )

        elements = []
        width, height = image.size
        for i, text in enumerate(data.get("text", [])):
            clean_text = (text or "").strip()
            conf = str(data.get("conf", ["-1"])[i]).strip()
            if not clean_text:
                continue
            try:
                conf_value = float(conf)
            except Exception:
                conf_value = -1
            if conf_value < 20:
                continue

            left = int(data["left"][i])
            top = int(data["top"][i])
            box_w = int(data["width"][i])
            box_h = int(data["height"][i])
            if box_w <= 0 or box_h <= 0:
                continue

            x0 = left / zoom
            y0 = top / zoom
            x1 = (left + box_w) / zoom
            y1 = (top + box_h) / zoom
            color = _sample_text_color(image, left, top, box_w, box_h)
            font_size = max((box_h / zoom) * 0.85, 8.0)

            elements.append(
                TextElement(
                    index=len(elements),
                    text=clean_text,
                    page_num=page_num,
                    x0=x0,
                    y0=y0,
                    x1=x1,
                    y1=y1,
                    font_name="Helvetica",
                    font_size=round(float(font_size), 2),
                    color=color,
                    block_no=int(data.get("block_num", [0])[i]),
                    line_no=int(data.get("line_num", [0])[i]),
                    span_no=0,
                    flags=0,
                    origin=(x0, y1),
                    kind="ocr_word",
                    word_no=int(data.get("word_num", [0])[i]),
                    source="ocr",
                )
            )

        elements.sort(key=lambda e: (round(e.y0, 1), e.x0))
        for idx, element in enumerate(elements):
            element.index = idx
        return elements

    # ------------------------------------------------------------------ #
    # Rendering
    # ------------------------------------------------------------------ #

    def render_page(self, page_num: int, zoom: float = 1.8) -> bytes:
        if not self.doc or page_num >= len(self.doc):
            return b""
        page = self.doc[page_num]
        pix = page.get_pixmap(matrix=fitz.Matrix(zoom, zoom), alpha=False)
        return pix.tobytes("png")

    def _page_image(self, page_num: int, zoom: float = 2.0) -> Image.Image:
        page = self.doc[page_num]
        pix = page.get_pixmap(matrix=fitz.Matrix(zoom, zoom), alpha=False)
        return Image.open(BytesIO(pix.tobytes("png"))).convert("RGB")

    # ------------------------------------------------------------------ #
    # Search and smart replacement
    # ------------------------------------------------------------------ #

    def find_text_matches(
        self,
        page_num: int,
        query: str,
        mode: str = "word",
        use_ocr_fallback: bool = False,
        max_results: int = 25,
    ) -> list[dict]:
        query = (query or "").strip()
        if not query:
            return []

        query_norm = normalize_text(query)
        elements = self.extract_text_elements(page_num, mode=mode, use_ocr_fallback=use_ocr_fallback)
        matches = []

        for element in elements:
            text = (element.text or "").strip()
            if not text:
                continue
            text_norm = normalize_text(text)
            reason = None
            score = 0.0

            if text == query:
                score = 1.0
                reason = "exact"
            elif text_norm == query_norm and query_norm:
                score = 0.97
                reason = "normalized exact"
            elif query in text:
                score = 0.92
                reason = "substring"
            elif query_norm and query_norm in text_norm:
                score = 0.88
                reason = "normalized substring"
            else:
                similarity = SequenceMatcher(None, query_norm, text_norm).ratio() if query_norm and text_norm else 0.0
                if similarity >= 0.6:
                    score = round(similarity, 3)
                    reason = "similar"

            if reason:
                matches.append({"element": element, "score": score, "reason": reason})

        matches.sort(key=lambda item: (-item["score"], item["element"].page_num, item["element"].y0, item["element"].x0))
        return matches[:max_results]

    def smart_replace(
        self,
        page_num: int,
        search_text: str,
        replacement_text: str,
        mode: str = "word",
        use_ocr_fallback: bool = False,
        use_ai: bool = False,
        font_size_override: Optional[float] = None,
        auto_fit: bool = True,
    ) -> dict:
        search_text = (search_text or "").strip()
        replacement_text = (replacement_text or "").strip()
        if not search_text:
            return {"success": False, "message": "Search text is empty."}
        if not replacement_text:
            return {"success": False, "message": "Replacement text is empty."}

        matches = self.find_text_matches(
            page_num=page_num,
            query=search_text,
            mode=mode,
            use_ocr_fallback=use_ocr_fallback,
        )

        selected = matches[0]["element"] if matches else None
        selection_reason = matches[0]["reason"] if matches else ""

        if selected is None and use_ai:
            elements = self.extract_text_elements(page_num, mode=mode, use_ocr_fallback=use_ocr_fallback)
            ai_result = choose_best_candidate_with_ai(search_text, [e.text for e in elements])
            if ai_result is not None:
                idx = ai_result["index"]
                if 0 <= idx < len(elements):
                    selected = elements[idx]
                    selection_reason = f"ai: {ai_result.get('reason', 'best candidate')} ({ai_result.get('confidence', 0):.2f})"

        if selected is None:
            return {
                "success": False,
                "message": "No matching text was found on this page.",
                "matches_found": 0,
            }

        result = self.replace_text(
            page_num=page_num,
            element=selected,
            new_text=replacement_text,
            font_size_override=font_size_override,
            auto_fit=auto_fit,
        )
        result["matched_text"] = selected.text
        result["matched_kind"] = selected.kind
        result["matched_source"] = selected.source
        result["selection_reason"] = selection_reason
        result["matches_found"] = len(matches)
        return result

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
        if not self.doc:
            return {"success": False, "message": "No document loaded."}

        new_text = new_text.strip()
        if not new_text:
            return {"success": False, "message": "New text is empty."}

        self._snapshots.append(self.doc.tobytes())
        self._history.append(
            f"Page {page_num + 1} [{element.source}/{element.kind}]: '{element.text}' → '{new_text}'"
        )

        page = self.doc[page_num]
        rect = fitz.Rect(element.x0, element.y0, element.x1, element.y1)
        bg_color = _detect_background(page, rect)
        page.draw_rect(rect, color=None, fill=bg_color, overlay=True)

        font_name, font_source = self._resolve_font(element.font_name)
        font_size = font_size_override or element.font_size
        if auto_fit and font_size_override is None:
            font_size = self._fit_font_size(new_text, font_name, element.font_size, max(element.width, 5), max(element.height, 5))

        color = element.color
        baseline_y = element.origin[1] if element.origin and len(element.origin) > 1 else rect.y1
        insert_point = fitz.Point(rect.x0, baseline_y)

        try:
            rc = page.insert_text(
                insert_point,
                new_text,
                fontname=font_name,
                fontsize=font_size,
                color=color,
                render_mode=0,
                overlay=True,
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
                "element_source": element.source,
            }
        except Exception as exc:
            self._undo_internal()
            return {"success": False, "message": f"Replacement failed: {exc}"}

    # ------------------------------------------------------------------ #
    # Undo / Export
    # ------------------------------------------------------------------ #

    def undo(self) -> bool:
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

    def export_bytes(self) -> bytes:
        if not self.doc:
            return b""
        return self.doc.tobytes(deflate=True)

    # ------------------------------------------------------------------ #
    # Internal helpers
    # ------------------------------------------------------------------ #

    def _match_span_for_word(self, x0, y0, x1, y1, block_no, line_no, spans: list[TextElement]) -> Optional[TextElement]:
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
            score = inter.get_area() / max(word_rect.get_area(), 1.0)
            if score > best_score:
                best_score = score
                best_match = span

        return best_match

    def _resolve_font(self, original_font_name: str) -> tuple[str, str]:
        lower = (original_font_name or "Helvetica").lower()
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

    def _fit_font_size(self, text: str, font_name: str, original_size: float, max_width: float, max_height: float) -> float:
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
# Helper functions
# ------------------------------------------------------------------ #

def _int_to_rgb(color_int: int) -> tuple:
    r = ((color_int >> 16) & 0xFF) / 255.0
    g = ((color_int >> 8) & 0xFF) / 255.0
    b = (color_int & 0xFF) / 255.0
    return (r, g, b)


def _detect_background(page: fitz.Page, rect: fitz.Rect) -> tuple:
    try:
        clip = fitz.Rect(rect.x0 - 2, rect.y0 - 2, rect.x1 + 2, rect.y1 + 2)
        pix = page.get_pixmap(clip=clip, alpha=False)
        sample = pix.pixel(0, 0)
        return tuple(c / 255.0 for c in sample[:3])
    except Exception:
        return (1.0, 1.0, 1.0)


def _sample_text_color(image: Image.Image, left: int, top: int, width: int, height: int) -> tuple:
    try:
        crop = image.crop((left, top, left + width, top + height))
        pixels = list(crop.getdata())
        if not pixels:
            return (0.0, 0.0, 0.0)
        darkest = min(pixels, key=lambda p: sum(p[:3]))
        return tuple(channel / 255.0 for channel in darkest[:3])
    except Exception:
        return (0.0, 0.0, 0.0)
