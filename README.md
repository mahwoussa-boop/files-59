# 📄 محرر PDF الاحترافي — Professional PDF Text Editor

تطبيق **Streamlit** لتعديل النصوص مباشرةً داخل ملفات PDF مع محاولة الحفاظ على نفس الخط والحجم واللون والموضع قدر الإمكان.

> A **Streamlit** app for in-place PDF text editing, preserving font, size, color, and position as closely as possible.

---

## 🚀 التثبيت والتشغيل السريع / Quick Setup

```bash
# 1. Clone or copy the project
cd pdf_editor_app

# 2. Create a virtual environment (recommended)
python -m venv venv
source venv/bin/activate        # Linux / macOS
# venv\Scripts\activate         # Windows

# 3. Install dependencies
pip install -r requirements.txt

# 4. Run the app
streamlit run app.py
```

The app will open automatically at **http://localhost:8501**

---

## 📁 هيكل المشروع / Project Structure

```
pdf_editor_app/
├── app.py            ← Streamlit UI (main entry point)
├── pdf_editor.py     ← Core PDF editing engine (PyMuPDF)
├── utils.py          ← Helpers: RTL detection, color conversion, diff, etc.
├── requirements.txt  ← Python dependencies
└── README.md         ← This file
```

---

## ✨ الميزات / Features

| الميزة | Feature |
|--------|---------|
| رفع PDF من الواجهة | Upload PDF via browser |
| معاينة كل صفحة | Per-page visual preview |
| استخراج النصوص مع الإحداثيات | Text extraction with coordinates |
| تعديل أي عنصر نصي في مكانه | In-place text replacement |
| مطابقة الخط والحجم واللون | Font/size/color matching |
| دعم العربية والاتجاه RTL | Arabic & RTL support |
| تصغير تلقائي للنصوص الطويلة | Auto-shrink for longer replacement text |
| تراجع (Undo) عن آخر تعديل | Undo last edit |
| عدة تعديلات قبل التصدير | Multiple edits before export |
| تحميل ملف PDF المعدّل | Download edited PDF |
| عرض الفرق بين النصين | Before/after diff preview |

---

## ⚠️ حدود التقنية / Technical Limitations

### 1. مطابقة الخط / Font Matching
ملفات PDF لا تُصدّر الخطوط دائمًا بشكل كامل، لذا:
- إذا كان الخط الأصلي **مضمّنًا** داخل الملف، لا يمكن إعادة استخدامه مباشرةً لإدراج نص جديد عبر PyMuPDF بدون تعقيدات إضافية.
- يعتمد التطبيق على **خريطة بدائل ذكية** تُعيّن الخطوط الشائعة (Arial، Times، Helvetica، ...) إلى أقرب خط قياسي مدعوم.
- النتيجة البصرية ستكون **قريبة جداً** لكن ليست مطابقة 100% لكل الخطوط.

PDF fonts are not always fully exportable, so the app uses a smart fallback mapping to the nearest standard font. Visual results are very close but may not be pixel-perfect.

### 2. الملفات الممسوحة ضوئيًا / Scanned PDFs
- إذا كانت الصفحة **صورة فقط** (ممسوحة ضوئيًا) بدون نص قابل للاستخراج، سيظهر تحذير في الواجهة.
- دعم OCR مخطط كميزة مستقبلية (Tesseract / PaddleOCR).

If the page is a scanned image with no extractable text, the app shows a warning. OCR support is planned as a future feature.

### 3. تغطية النص القديم / Covering Old Text
- يُرسم مستطيل بلون الخلفية (يُكتشف تلقائيًا) فوق النص القديم قبل كتابة النص الجديد.
- في حالات الخلفيات المعقدة (تدرجات، صور) قد تظهر حواف بسيطة.

A background-colored rectangle covers the old text before inserting the new one. Complex backgrounds (gradients, images) may show slight artifacts.

---

## 🔧 التوسع المستقبلي / Future Enhancements

- [ ] دعم OCR للملفات الممسوحة ضوئيًا (Tesseract)
- [ ] تضمين الخطوط العربية (Cairo، Amiri) مباشرةً
- [ ] تعديل النصوص عبر النقر على الصورة (canvas)
- [ ] دعم إدراج نص في صناديق النماذج (AcroForms)
- [ ] معالجة دفعية لعدة ملفات

---

## 📦 المكتبات المستخدمة / Libraries Used

| Library | Purpose |
|---------|---------|
| `PyMuPDF (fitz)` | Core PDF read/write/render engine |
| `Streamlit` | Web UI framework |
| `Pillow` | Image processing helpers |
| `pandas` | Text elements table display |

---

## 📝 ملاحظات للمطورين / Developer Notes

- كل تعديل يُحفظ **snapshot** من الملف للتراجع لاحقًا — مناسب لعدة تعديلات متتالية.
- كلاس `PDFEditor` مستقل تمامًا عن Streamlit ويمكن استخدامه في أي سياق آخر.
- `utils.py` يحتوي على منطق RTL/LTR مبسّط يعتمد على Unicode Bidirectional Algorithm.

Each edit saves a document snapshot for undo. `PDFEditor` is decoupled from Streamlit for reusability. RTL/LTR detection uses Unicode Bidirectional character properties.
