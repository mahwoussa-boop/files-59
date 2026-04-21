import fitz

from pdf_editor import PDFEditor


def build_sample_pdf(path: str):
    doc = fitz.open()
    page = doc.new_page()
    page.insert_text((72, 100), "Hello world from PDF", fontname="helv", fontsize=14)
    page.insert_text((72, 140), "مرحبا بالعالم", fontname="helv", fontsize=14)
    doc.save(path)
    doc.close()


def main():
    sample_path = "/home/ubuntu/repo_import/sample_test.pdf"
    build_sample_pdf(sample_path)

    with open(sample_path, "rb") as f:
        data = f.read()

    editor = PDFEditor()
    editor.load(data, "sample_test.pdf")

    span_elements = editor.extract_text_elements(0, mode="span")
    word_elements = editor.extract_text_elements(0, mode="word")

    assert len(span_elements) >= 2, f"Expected at least 2 span elements, got {len(span_elements)}"
    assert len(word_elements) >= 5, f"Expected at least 5 word elements, got {len(word_elements)}"

    hello = next((e for e in word_elements if e.text == "Hello"), None)
    assert hello is not None, "Word-level extraction failed to find 'Hello'"

    result_word = editor.replace_text(0, hello, "Hi", auto_fit=True)
    assert result_word["success"], f"Word replacement failed: {result_word}"

    refreshed_words = editor.extract_text_elements(0, mode="word")
    assert any(e.text == "Hi" for e in refreshed_words), "Edited word 'Hi' was not found after replacement"

    phrase = next((e for e in editor.extract_text_elements(0, mode="span") if "world" in e.text), None)
    assert phrase is not None, "Span-level extraction failed to find expected phrase"

    result_span = editor.replace_text(0, phrase, "Greetings Earth", auto_fit=True)
    assert result_span["success"], f"Span replacement failed: {result_span}"

    exported = editor.export_bytes()
    assert exported.startswith(b"%PDF"), "Exported bytes are not a valid PDF"

    print("PASS: word-level and span-level editing work")


if __name__ == "__main__":
    main()
