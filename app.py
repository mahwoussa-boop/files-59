"""
app.py
Professional Streamlit PDF Text Editor
Supports Arabic & English, RTL/LTR, in-place text replacement with font matching.
"""

import io
import streamlit as st
from PIL import Image

from pdf_editor import PDFEditor, TextElement
from utils import (
    elements_to_dataframe,
    validate_pdf_bytes,
    estimate_is_scanned,
    simple_diff,
    decode_font_flags,
    rgb_to_hex,
    hex_to_rgb,
    contains_arabic,
)

# ─────────────────────────────────────────────
#  Page config
# ─────────────────────────────────────────────
st.set_page_config(
    page_title="محرر PDF الاحترافي | PDF Editor",
    page_icon="📄",
    layout="wide",
    initial_sidebar_state="expanded",
)

# ─────────────────────────────────────────────
#  Custom CSS
# ─────────────────────────────────────────────
st.markdown(
    """
    <style>
    /* RTL support for Arabic text inputs */
    .rtl-input textarea, .rtl-input input { direction: rtl; text-align: right; }
    /* Card-like containers */
    .info-card {
        background: #f8f9fa;
        border-radius: 8px;
        padding: 12px 16px;
        margin-bottom: 8px;
        border-left: 4px solid #4a86e8;
    }
    .success-card {
        background: #e8f5e9;
        border-radius: 8px;
        padding: 12px 16px;
        border-left: 4px solid #43a047;
    }
    .warning-card {
        background: #fff8e1;
        border-radius: 8px;
        padding: 12px 16px;
        border-left: 4px solid #ffa000;
    }
    </style>
    """,
    unsafe_allow_html=True,
)

# ─────────────────────────────────────────────
#  Session state initialisation
# ─────────────────────────────────────────────
def _init_state():
    defaults = {
        "editor":           PDFEditor(),
        "elements":         [],
        "selected_idx":     None,
        "page_num":         0,
        "edit_results":     [],   # list of result dicts
        "filename":         "",
    }
    for k, v in defaults.items():
        if k not in st.session_state:
            st.session_state[k] = v

_init_state()

editor: PDFEditor = st.session_state["editor"]

# ─────────────────────────────────────────────
#  Sidebar
# ─────────────────────────────────────────────
with st.sidebar:
    st.title("📄 محرر PDF الاحترافي")
    st.caption("Professional PDF Text Editor")
    st.divider()

    # --- Upload ---
    uploaded = st.file_uploader(
        "ارفع ملف PDF / Upload PDF",
        type=["pdf"],
        help="يدعم ملفات PDF النصية. الملفات الممسوحة ضوئيًا غير مدعومة بالكامل.",
    )

    if uploaded is not None:
        raw_bytes = uploaded.read()
        ok, msg = validate_pdf_bytes(raw_bytes)
        if not ok:
            st.error(msg)
        elif uploaded.name != st.session_state["filename"]:
            editor.load(raw_bytes, uploaded.name)
            st.session_state["filename"]     = uploaded.name
            st.session_state["page_num"]     = 0
            st.session_state["selected_idx"] = None
            st.session_state["elements"]     = editor.extract_text_elements(0)
            st.session_state["edit_results"] = []
            st.success(f"✅ تم رفع الملف: {uploaded.name}")

    st.divider()

    if editor.is_loaded():
        # --- Page selector ---
        page_num = st.selectbox(
            "اختر الصفحة / Select Page",
            options=list(range(editor.page_count)),
            format_func=lambda p: f"صفحة {p + 1} / Page {p + 1}",
            index=st.session_state["page_num"],
        )
        if page_num != st.session_state["page_num"]:
            st.session_state["page_num"]     = page_num
            st.session_state["elements"]     = editor.extract_text_elements(page_num)
            st.session_state["selected_idx"] = None

        st.divider()

        # --- Edit history ---
        if editor.history:
            st.subheader("📝 سجل التعديلات / Edit History")
            for i, h in enumerate(reversed(editor.history), 1):
                st.caption(f"{i}. {h}")

            if st.button("↩️ تراجع / Undo Last Edit", use_container_width=True):
                if editor.undo():
                    pg = st.session_state["page_num"]
                    st.session_state["elements"] = editor.extract_text_elements(pg)
                    st.session_state["selected_idx"] = None
                    st.success("تم التراجع عن آخر تعديل.")
                    st.rerun()
                else:
                    st.warning("لا يوجد تعديل للتراجع عنه.")

        st.divider()

        # --- Download ---
        st.subheader("⬇️ تحميل الملف / Download")
        pdf_bytes = editor.export_bytes()
        base_name = st.session_state["filename"].replace(".pdf", "")
        st.download_button(
            label="💾 تحميل PDF المعدّل / Download Edited PDF",
            data=pdf_bytes,
            file_name=f"{base_name}_edited.pdf",
            mime="application/pdf",
            use_container_width=True,
        )

# ─────────────────────────────────────────────
#  Main area
# ─────────────────────────────────────────────
if not editor.is_loaded():
    st.markdown(
        """
        <div style="text-align:center; padding: 80px 20px; color: #888;">
            <h2>📄 محرر PDF الاحترافي</h2>
            <p style="font-size:1.1em;">ارفع ملف PDF من الشريط الجانبي للبدء<br>
            <em>Upload a PDF from the sidebar to get started</em></p>
        </div>
        """,
        unsafe_allow_html=True,
    )
    st.stop()

# ─── Layout: preview | editor ───────────────
col_preview, col_editor = st.columns([1.1, 0.9], gap="large")

elements: list[TextElement] = st.session_state["elements"]
page_num: int               = st.session_state["page_num"]

# ─── Left column: page preview + text table ─
with col_preview:
    st.subheader(f"📋 معاينة الصفحة {page_num + 1} / Page Preview")

    # Scanned PDF warning
    if estimate_is_scanned(elements):
        st.markdown(
            """
            <div class="warning-card">
            ⚠️ <strong>تحذير / Warning:</strong> لا يحتوي هذا الصفحة على نصوص قابلة للاستخراج.
            قد تكون الصفحة ممسوحة ضوئيًا (صورة فقط).<br>
            <em>This page contains no extractable text — it may be a scanned image.
            Direct text editing is not possible. OCR support may be added in a future version.</em>
            </div>
            """,
            unsafe_allow_html=True,
        )

    # Render page image
    png_bytes = editor.render_page(page_num, zoom=1.8)
    if png_bytes:
        st.image(png_bytes, use_container_width=True)

    # Text elements table
    if elements:
        st.subheader("📃 عناصر النص / Text Elements")
        df = elements_to_dataframe(elements)
        st.dataframe(
            df,
            use_container_width=True,
            height=280,
            hide_index=True,
            column_config={
                "#": st.column_config.NumberColumn(width="small"),
                "النص / Text": st.column_config.TextColumn(width="large"),
                "اللون / Color": st.column_config.TextColumn(width="small"),
            },
        )

        # Element selector
        idx_options = [e.index for e in elements]
        sel = st.selectbox(
            "اختر عنصر نصي للتعديل / Select a text element to edit",
            options=idx_options,
            format_func=lambda i: f"[{i}] {elements[i].text[:60]}{'…' if len(elements[i].text) > 60 else ''}",
            index=st.session_state.get("selected_idx") or 0,
        )
        st.session_state["selected_idx"] = sel

# ─── Right column: edit form ─────────────────
with col_editor:
    st.subheader("✏️ نموذج التعديل / Edit Form")

    if not elements:
        st.info("لا توجد عناصر نصية في هذه الصفحة. / No text elements on this page.")
    else:
        selected_idx = st.session_state.get("selected_idx", 0)
        elem: TextElement = elements[selected_idx]

        # ── Element info card ──
        flags = decode_font_flags(elem.flags)
        is_arabic = contains_arabic(elem.text)

        st.markdown(
            f"""
            <div class="info-card">
            <strong>العنصر #{elem.index}</strong> &nbsp;|&nbsp;
            الخط: <code>{elem.font_name}</code> &nbsp;|&nbsp;
            الحجم: <code>{elem.font_size}pt</code> &nbsp;|&nbsp;
            اللون: <code>{rgb_to_hex(*elem.color)}</code><br>
            الموضع: ({elem.x0:.1f}, {elem.y0:.1f}) → ({elem.x1:.1f}, {elem.y1:.1f}) &nbsp;|&nbsp;
            الاتجاه: {'RTL ←' if is_arabic else 'LTR →'}
            {'&nbsp;| <strong>Bold</strong>' if flags['bold'] else ''}
            {'&nbsp;| <em>Italic</em>' if flags['italic'] else ''}
            </div>
            """,
            unsafe_allow_html=True,
        )

        # ── Original text (read-only) ──
        st.text_area(
            "النص الأصلي / Original Text",
            value=elem.text,
            height=80,
            disabled=True,
            key=f"orig_{selected_idx}",
        )

        # ── New text input ──
        new_text = st.text_area(
            "النص الجديد / New Text",
            value=elem.text,
            height=80,
            key=f"new_{selected_idx}",
            help="أدخل النص البديل. سيحاول التطبيق الحفاظ على نفس الخط والحجم والموضع.",
        )

        # ── Advanced options (collapsible) ──
        with st.expander("⚙️ خيارات متقدمة / Advanced Options"):
            col_a, col_b = st.columns(2)
            with col_a:
                custom_size = st.number_input(
                    "حجم الخط / Font Size (pt)",
                    min_value=4.0,
                    max_value=200.0,
                    value=float(elem.font_size),
                    step=0.5,
                    key=f"size_{selected_idx}",
                )
                auto_fit = st.checkbox(
                    "تصغير تلقائي / Auto-fit size",
                    value=True,
                    key=f"autofit_{selected_idx}",
                    help="تقليل حجم الخط تلقائيًا إذا كان النص الجديد أطول من المساحة الأصلية.",
                )
            with col_b:
                color_hex = st.color_picker(
                    "اللون / Color",
                    value=rgb_to_hex(*elem.color),
                    key=f"color_{selected_idx}",
                )

        # ── Diff preview ──
        if new_text != elem.text:
            diff_str = simple_diff(elem.text, new_text)
            st.markdown(
                f'<div class="info-card">🔍 الفرق / Diff: {diff_str}</div>',
                unsafe_allow_html=True,
            )

        st.divider()

        # ── Apply button ──
        apply_col, _ = st.columns([1, 1])
        with apply_col:
            apply = st.button(
                "✅ تطبيق التعديل / Apply Edit",
                type="primary",
                use_container_width=True,
                disabled=(new_text.strip() == ""),
            )

        if apply:
            if new_text.strip() == elem.text.strip():
                st.warning("النص الجديد مطابق للنص الأصلي. / New text is identical to original.")
            else:
                # Override color from picker
                override_color = hex_to_rgb(color_hex)
                # Temporarily patch element color
                elem.color = override_color

                size_override = None if auto_fit else custom_size

                result = editor.replace_text(
                    page_num=page_num,
                    element=elem,
                    new_text=new_text,
                    font_size_override=size_override,
                    auto_fit=auto_fit,
                )

                if result["success"]:
                    # Refresh elements from updated doc
                    st.session_state["elements"] = editor.extract_text_elements(page_num)
                    st.session_state["selected_idx"] = None
                    st.session_state["edit_results"].append(result)

                    st.markdown(
                        f"""
                        <div class="success-card">
                        ✅ <strong>تم التعديل بنجاح! / Edit applied successfully!</strong><br>
                        الخط المستخدم: <code>{result['font_used']}</code>
                        ({result['font_source']}) &nbsp;|&nbsp;
                        الحجم: <code>{result['font_size_used']:.1f}pt</code>
                        </div>
                        """,
                        unsafe_allow_html=True,
                    )
                    st.rerun()
                else:
                    st.error(f"❌ فشل التعديل / Edit failed: {result['message']}")

        # ── Recent results ──
        recent = st.session_state.get("edit_results", [])
        if recent:
            with st.expander(f"📊 نتائج التعديلات ({len(recent)}) / Edit Results"):
                for i, r in enumerate(reversed(recent[-5:]), 1):
                    status = "✅" if r["success"] else "❌"
                    st.caption(
                        f"{status} [{i}] خط: {r.get('font_used','—')} | "
                        f"حجم: {r.get('font_size_used','—')} | {r.get('message','')}"
                    )

# ─────────────────────────────────────────────
#  Footer
# ─────────────────────────────────────────────
st.divider()
st.caption(
    "⚡ محرر PDF الاحترافي — مبني بـ PyMuPDF + Streamlit | "
    "يعمل على PDF النصية. ملفات الصور/OCR قيد التطوير. | "
    "Professional PDF Editor — works on text-based PDFs. Scanned/OCR PDFs not yet supported."
)
