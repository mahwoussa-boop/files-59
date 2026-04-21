from pathlib import Path
from io import BytesIO

import fitz
from PIL import Image, ImageOps
import pytesseract

pdf_path = Path('/home/ubuntu/repo_import/sample_scanned_test.pdf')
out_path = Path('/home/ubuntu/repo_import/debug_scanned_page.png')

if not pdf_path.exists():
    raise SystemExit('sample_scanned_test.pdf not found')

doc = fitz.open(str(pdf_path))
page = doc[0]
pix = page.get_pixmap(matrix=fitz.Matrix(3, 3), alpha=False)
img = Image.open(BytesIO(pix.tobytes('png'))).convert('RGB')
img.save(out_path)

gray = ImageOps.grayscale(img)
processed = gray.point(lambda p: 255 if p > 180 else 0)
processed.save('/home/ubuntu/repo_import/debug_scanned_processed.png')

print('IMAGE_SIZE', img.size)
print('OCR_STRING_RAW')
print(pytesseract.image_to_string(img, lang='eng', config='--oem 3 --psm 6'))
print('OCR_STRING_PROCESSED')
print(pytesseract.image_to_string(processed, lang='eng', config='--oem 3 --psm 6'))
print('OCR_DATA_TEXTS')
data = pytesseract.image_to_data(processed, lang='eng', output_type=pytesseract.Output.DICT, config='--oem 3 --psm 6')
print(data.get('text', []))
