from pathlib import Path

import fitz
from PIL import Image, ImageDraw, ImageFont

from pdf_editor import PDFEditor


def build_text_pdf(path: str):
    doc = fitz.open()
    page = doc.new_page()
    page.insert_text((72, 100), "Hello world from PDF", fontname="helv", fontsize=18)
    page.insert_text((72, 140), "Hello invoice", fontname="helv", fontsize=16)
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

    native_lines = editor.extract_text_elements(0, mode="line", use_ocr_fallback=False)
    assert any("Hello invoice" in e.text for e in native_lines), "Native line extraction failed"

    matches = editor.find_text_matches(0, "invoice", mode="word", use_ocr_fallback=False)
    assert matches, "Smart search did not find expected native text"

    result = editor.smart_replace(
        page_num=0,
        search_text="invoice",
        replacement_text="receipt",
        mode="word",
        use_ocr_fallback=False,
        use_ai=False,
    )
    assert result["success"], f"Smart replacement failed: {result}"

    refreshed = editor.extract_text_elements(0, mode="word", use_ocr_fallback=False)
    refreshed_texts = [e.text for e in refreshed]
    assert any(e.text == "receipt" for e in refreshed), "Replaced word not found after native replacement"
    assert "invoice" not in refreshed_texts, "Old native word still exists after replacement"

    scanned_editor = PDFEditor()
    scanned_editor.load(Path(scanned_pdf).read_bytes(), "sample_scanned_test.pdf")
    ocr_elements = scanned_editor.extract_text_elements(0, mode="word", use_ocr_fallback=True)
    assert ocr_elements, "OCR fallback did not extract any text from scanned PDF"

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

    print("PASS: native and OCR smart replacement work")


if __name__ == "__main__":
    main()
