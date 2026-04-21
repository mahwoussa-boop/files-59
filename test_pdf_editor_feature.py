from io import BytesIO
from pathlib import Path

import fitz
import pytesseract
from PIL import Image, ImageDraw, ImageFont

from pdf_editor import PDFEditor


def build_text_pdf(path: str):
    doc = fitz.open()
    page = doc.new_page()
    page.insert_text((72, 100), "Hello world from PDF", fontname="helv", fontsize=28)
    page.insert_text((72, 150), "Hello invoice", fontname="helv", fontsize=24)
    doc.save(path)
    doc.close()


def build_scanned_pdf(path: str):
    png_path = str(Path(path).with_suffix(".png"))
    img = Image.new("RGB", (2200, 900), "white")
    draw = ImageDraw.Draw(img)
    try:
        font = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf", 220)
    except Exception:
        font = ImageFont.load_default()
    draw.text((180, 260), "SCANNED HELLO", fill="black", font=font)
    img.save(png_path, "PNG")

    doc = fitz.open()
    page = doc.new_page(width=img.width, height=img.height)
    page.insert_image(page.rect, filename=png_path)
    doc.save(path)
    doc.close()


def _normalized(text: str) -> str:
    return "".join((text or "").lower().split())


def main():
    base = Path("/home/ubuntu/repo_import")
    base.mkdir(parents=True, exist_ok=True)

    text_pdf = str(base / "sample_text_test.pdf")
    scanned_pdf = str(base / "sample_scanned_test.pdf")

    build_text_pdf(text_pdf)
    build_scanned_pdf(scanned_pdf)

    editor = PDFEditor()
    editor.load(Path(text_pdf).read_bytes(), "sample_text_test.pdf")

    native_words = editor.extract_text_elements(0, mode="word", use_ocr_fallback=False)
    assert any(e.text == "Hello" for e in native_words), "Native word extraction failed"
    invoice_word = next(e for e in native_words if e.text == "invoice")

    native_lines = editor.extract_text_elements(0, mode="line", use_ocr_fallback=False)
    invoice_line = next(e for e in native_lines if "Hello invoice" in e.text)

    selected_by_point = editor.select_element_by_point(
        0,
        x=(invoice_word.x0 + invoice_word.x1) / 2.0,
        y=(invoice_word.y0 + invoice_word.y1) / 2.0,
        mode="word",
        use_ocr_fallback=False,
    )
    assert selected_by_point is not None, "Point-based selection failed"
    assert selected_by_point.text == "invoice", f"Unexpected point-selected text: {selected_by_point.text}"

    selected_by_region = editor.select_element_by_region(
        0,
        x0=invoice_line.x0 - 2,
        y0=invoice_line.y0 - 2,
        x1=invoice_line.x1 + 2,
        y1=invoice_line.y1 + 2,
        mode="line",
        use_ocr_fallback=False,
    )
    assert selected_by_region is not None, "Region-based selection failed"
    assert "Hello invoice" in selected_by_region.text, "Unexpected region-selected line"

    matches = editor.find_text_matches(0, "invoice", mode="word", use_ocr_fallback=False)
    assert matches, "Smart search did not find expected native text"

    result = editor.smart_replace(
        page_num=0,
        search_text="invoice",
        replacement_text="gypsy",
        mode="word",
        use_ocr_fallback=False,
        use_ai=False,
    )
    assert result["success"], f"Smart replacement failed: {result}"

    refreshed = editor.extract_text_elements(0, mode="word", use_ocr_fallback=False)
    refreshed_texts = [e.text for e in refreshed]
    assert any(e.text == "gypsy" for e in refreshed), "Replaced word not found after native replacement"
    assert "invoice" not in refreshed_texts, "Old native word still exists after replacement"

    ocr_status = editor.get_ocr_status(force_check=True)
    if ocr_status["available"]:
        rendered = Image.open(BytesIO(editor.render_page(0, zoom=4.0))).convert("RGB")
        ocr_text = pytesseract.image_to_string(rendered, config="--oem 3 --psm 6")
        assert "gypsy" in _normalized(ocr_text), f"Rendered replacement may be visually clipped or unreadable: {ocr_text!r}"

    scanned_editor = PDFEditor()
    scanned_editor.load(Path(scanned_pdf).read_bytes(), "sample_scanned_test.pdf")
    ocr_elements = scanned_editor.extract_text_elements(0, mode="word", use_ocr_fallback=True)
    assert ocr_elements, "OCR fallback did not extract any text from scanned PDF"

    scanned_selected = scanned_editor.select_element_by_point(
        0,
        x=(ocr_elements[0].x0 + ocr_elements[0].x1) / 2.0,
        y=(ocr_elements[0].y0 + ocr_elements[0].y1) / 2.0,
        mode="word",
        use_ocr_fallback=True,
    )
    assert scanned_selected is not None, "Point selection on OCR-derived elements failed"

    ocr_lines = scanned_editor.extract_text_elements(0, mode="line", use_ocr_fallback=True)
    assert ocr_lines, "OCR line extraction did not return any lines"

    ocr_result = scanned_editor.smart_replace(
        page_num=0,
        search_text="scanned",
        replacement_text="DIGITAL",
        mode="word",
        use_ocr_fallback=True,
        use_ai=False,
    )
    assert ocr_result["success"], f"OCR-based smart replacement failed: {ocr_result}"

    exported = scanned_editor.export_bytes()
    assert exported.startswith(b"%PDF"), "Exported OCR-edited PDF is invalid"

    print("PASS: click-based selection helpers and precise native/OCR replacement work")


if __name__ == "__main__":
    main()
