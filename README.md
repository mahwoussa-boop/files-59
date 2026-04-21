# 📄 محرر PDF الاحترافي — Professional PDF Text Editor

تطبيق **Streamlit** لتعديل النصوص مباشرةً داخل ملفات PDF مع محاولة الحفاظ على نفس الخط والحجم واللون والموضع قدر الإمكان، ويدعم الآن **تحرير أي كلمة مفردة أو أي عنصر نصي كامل** داخل ملفات PDF النصية.

> A **Streamlit** app for in-place PDF text editing, preserving font, size, color, and position as closely as possible, with support for editing **single words** or **full text elements**.

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

```text
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
|---|---|
| رفع PDF من الواجهة | Upload PDF via browser |
| معاينة كل صفحة | Per-page visual preview |
| استخراج النصوص مع الإحداثيات | Text extraction with coordinates |
| تعديل عنصر نصي كامل في مكانه | In-place full text element editing |
| تعديل أي كلمة منفردة داخل الصفحة | Edit any single word on the page |
| التبديل بين وضع الكلمة ووضع العنصر النصي | Switch between word mode and text-element mode |
| مطابقة الخط والحجم واللون | Font/size/color matching |
| دعم العربية والاتجاه RTL | Arabic & RTL support |
| تصغير تلقائي للنصوص الطويلة | Auto-shrink for longer replacement text |
| تراجع (Undo) عن آخر تعديل | Undo last edit |
| عدة تعديلات قبل التصدير | Multiple edits before export |
| تحميل ملف PDF المعدّل | Download edited PDF |
| عرض الفرق بين النصين | Before/after diff preview |

---

## 🧭 طريقة الاستخدام / How to Use

بعد رفع ملف PDF، اختر الصفحة المطلوبة من الشريط الجانبي، ثم حدّد **وضع التحرير**:

| الوضع | الاستخدام |
|---|---|
| **عنصر نصي كامل** | مناسب لتعديل عبارة كاملة أو سطر أو جزء مستخرج كعنصر واحد |
| **كلمة واحدة** | مناسب عندما تريد تعديل كلمة منفردة داخل السطر بدون استبدال بقية النص |

بعد ذلك اختر النص من القائمة، عدّل المحتوى في نموذج التحرير، ثم اضغط **تطبيق التعديل**. عند الانتهاء يمكنك تنزيل الملف المعدّل مباشرة.

---

## ⚠️ حدود التقنية / Technical Limitations

### 1. مطابقة الخط / Font Matching
ملفات PDF لا تُصدّر الخطوط دائمًا بشكل كامل، لذا:

- إذا كان الخط الأصلي **مضمّنًا** داخل الملف، لا يمكن إعادة استخدامه مباشرةً لإدراج نص جديد عبر PyMuPDF بدون تعقيدات إضافية.
- يعتمد التطبيق على **خريطة بدائل ذكية** تُعيّن الخطوط الشائعة مثل Arial وTimes وHelvetica إلى أقرب خط قياسي مدعوم.
- النتيجة البصرية تكون **قريبة جدًا** غالبًا، لكنها ليست مطابقة 100% في كل الملفات.

### 2. الملفات الممسوحة ضوئيًا / Scanned PDFs

- إذا كانت الصفحة **صورة فقط** بدون نص قابل للاستخراج، سيظهر تحذير في الواجهة.
- دعم OCR غير مفعّل حاليًا، لذلك لا يمكن تعديل النصوص داخل الصور الممسوحة ضوئيًا مباشرةً.

### 3. تغطية النص القديم / Covering Old Text

- يُرسم مستطيل بلون الخلفية فوق النص القديم قبل كتابة النص الجديد.
- في الخلفيات المعقدة أو المتدرجة قد تظهر آثار بسيطة حول موضع التعديل.

### 4. تحرير الكلمات الطويلة / Longer Word Replacement

- عند تعديل كلمة قصيرة بكلمة أطول، قد يحتاج التطبيق إلى تصغير الحجم تلقائيًا حتى يبقى النص داخل نفس المساحة.
- إذا كانت المساحة الأصلية صغيرة جدًا، قد تختلف النتيجة البصرية عن النص الأصلي.

---

## 🔧 التوسع المستقبلي / Future Enhancements

- [ ] دعم OCR للملفات الممسوحة ضوئيًا
- [ ] تضمين خطوط عربية مخصصة مثل Cairo وAmiri
- [ ] تعديل النصوص عبر النقر المباشر على المعاينة (canvas)
- [ ] دعم إدراج وتحرير حقول النماذج (AcroForms)
- [ ] معالجة دفعية لعدة ملفات

---

## 📦 المكتبات المستخدمة / Libraries Used

| Library | Purpose |
|---|---|
| `PyMuPDF (fitz)` | Core PDF read/write/render engine |
| `Streamlit` | Web UI framework |
| `Pillow` | Image processing helpers |
| `pandas` | Text elements table display |

---

## 📝 ملاحظات للمطورين / Developer Notes

يعتمد التطبيق الآن على مستويين للاستخراج: استخراج **العناصر النصية الكاملة** واستخراج **الكلمات المفردة**. كما أن `PDFEditor` ما يزال منفصلًا عن الواجهة، مما يجعل إعادة استخدامه في أدوات أخرى أمرًا سهلاً. كل تعديل يُخزّن نسخة سابقة من المستند حتى يمكن التراجع عنه لاحقًا.
