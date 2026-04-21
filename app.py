"""
app.py
Professional Streamlit PDF Text Editor.
Supports Arabic & English, smart search-and-replace, OCR fallback, and manual editing.
"""

from io import BytesIO

import streamlit as st
from PIL import Image

try:
    from streamlit_image_coordinates import streamlit_image_coordinates
except Exception:  # pragma: no cover - optional at runtime until environment installs it
    streamlit_image_coordinates = None

from pdf_editor import PDFEditor, TextElement
from utils import (
    contains_arabic,
    decode_font_flags,
    elements_to_dataframe,
    estimate_is_scanned,
    hex_to_rgb,
    rgb_to_hex,
    simple_diff,
    validate_pdf_bytes,
)


st.set_page_config(
    page_title="محرر PDF الذكي | Smart PDF Editor",
    page_icon="📄",
    layout="wide",
    initial_sidebar_state="expanded",
)

st.markdown(
    """
    <style>
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
    .panel-card {
        background: #ffffff;
        border: 1px solid #e5e7eb;
        border-radius: 12px;
        padding: 14px 16px;
        box-shadow: 0 1px 2px rgba(0,0,0,.04);
    }
    </style>
    """,
    unsafe_allow_html=True,
)

SELECTION_MODES = {
    "كلمات / Words": "word",
    "أسطر / Lines": "line",
    "عناصر نصية كاملة / Full Text Elements": "span",
}


def _init_state():
    defaults = {
        "editor": PDFEditor(),
        "elements": [],
        "selected_idx": 0,
        "page_num": 0,
        "edit_results": [],
        "filename": "",
        "selection_mode": "word",
        "use_ocr_fallback": True,
        "use_ai_assist": False,
        "smart_matches": [],
        "last_preview_click_ts": 0,
        "preview_selection_info": None,
    }
    for key, value in defaults.items():
        if key not in st.session_state:
            st.session_state[key] = value


_init_state()
editor: PDFEditor = st.session_state["editor"]


def refresh_elements(reset_selection: bool = False):
    if not editor.is_loaded():
        st.session_state["elements"] = []
        st.session_state["selected_idx"] = 0
        return
    page_num = st.session_state["page_num"]
    mode = st.session_state["selection_mode"]
    use_ocr = st.session_state["use_ocr_fallback"]
    st.session_state["elements"] = editor.extract_text_elements(page_num, mode=mode, use_ocr_fallback=use_ocr)
    if reset_selection:
        st.session_state["selected_idx"] = 0
    elif st.session_state["selected_idx"] >= len(st.session_state["elements"]):
        st.session_state["selected_idx"] = 0


def _selected_rows_from_event(event) -> list[int]:
    if event is None:
        return []
    selection = getattr(event, "selection", None)
    if selection is None and isinstance(event, dict):
        selection = event.get("selection")
    if selection is None:
        return []
    if isinstance(selection, dict):
        return list(selection.get("rows", []) or [])
    rows = getattr(selection, "rows", None)
    return list(rows or [])


def _clamp(value: float, low: float, high: float) -> float:
    return max(low, min(value, high))


def _process_preview_selection(event_value, image_width: int, image_height: int):
    if not event_value or not isinstance(event_value, dict):
        return

    unix_time = int(event_value.get("unix_time") or 0)
    if unix_time and unix_time == st.session_state.get("last_preview_click_ts", 0):
        return
    if unix_time:
        st.session_state["last_preview_click_ts"] = unix_time

    page_num = st.session_state["page_num"]
    mode = st.session_state["selection_mode"]
    use_ocr = st.session_state["use_ocr_fallback"]
    page_width, page_height = editor.get_page_size(page_num)
    if page_width <= 0 or page_height <= 0:
        return

    display_width = max(float(event_value.get("width") or image_width), 1.0)
    display_height = max(float(event_value.get("height") or image_height), 1.0)
    scale_x = image_width / display_width
    scale_y = image_height / display_height
    pdf_scale_x = page_width / max(image_width, 1)
    pdf_scale_y = page_height / max(image_height, 1)

    if all(key in event_value for key in ("x1", "y1", "x2", "y2")):
        ix0 = _clamp(float(event_value["x1"]) * scale_x, 0.0, float(image_width))
        iy0 = _clamp(float(event_value["y1"]) * scale_y, 0.0, float(image_height))
        ix1 = _clamp(float(event_value["x2"]) * scale_x, 0.0, float(image_width))
        iy1 = _clamp(float(event_value["y2"]) * scale_y, 0.0, float(image_height))
        selected = editor.select_element_by_region(
            page_num=page_num,
            x0=ix0 * pdf_scale_x,
            y0=iy0 * pdf_scale_y,
            x1=ix1 * pdf_scale_x,
            y1=iy1 * pdf_scale_y,
            mode=mode,
            use_ocr_fallback=use_ocr,
        )
    elif all(key in event_value for key in ("x", "y")):
        ix = _clamp(float(event_value["x"]) * scale_x, 0.0, float(image_width))
        iy = _clamp(float(event_value["y"]) * scale_y, 0.0, float(image_height))
        selected = editor.select_element_by_point(
            page_num=page_num,
            x=ix * pdf_scale_x,
            y=iy * pdf_scale_y,
            mode=mode,
            use_ocr_fallback=use_ocr,
        )
    else:
        return

    if selected is None:
        st.session_state["preview_selection_info"] = {
            "status": "miss",
            "message": "لم يتم العثور على عنصر نصي قريب من هذا الموضع.",
        }
        return

    st.session_state["selected_idx"] = int(selected.index)
    st.session_state["preview_selection_info"] = {
        "status": "selected",
        "message": f"تم تحديد: {selected.text}",
        "kind": selected.kind,
        "source": selected.source,
    }
    st.rerun()


with st.sidebar:
    st.title("📄 محرر PDF الذكي")
    st.caption("Smart PDF Text Replacement")
    st.divider()

    uploaded = st.file_uploader(
        "ارفع ملف PDF / Upload PDF",
        type=["pdf"],
        help="يدعم ملفات PDF النصية ويمكنه التعامل مع الصفحات الصورية باستخدام OCR عند التفعيل.",
    )

    if uploaded is not None:
        raw_bytes = uploaded.read()
        ok, msg = validate_pdf_bytes(raw_bytes)
        if not ok:
            st.error(msg)
        elif uploaded.name != st.session_state["filename"]:
            editor.load(raw_bytes, uploaded.name)
            st.session_state["filename"] = uploaded.name
            st.session_state["page_num"] = 0
            st.session_state["selected_idx"] = 0
            st.session_state["edit_results"] = []
            st.session_state["smart_matches"] = []
            st.session_state["last_preview_click_ts"] = 0
            st.session_state["preview_selection_info"] = None
            refresh_elements(reset_selection=True)
            st.success(f"✅ تم رفع الملف: {uploaded.name}")

    st.divider()

    if editor.is_loaded():
        page_num = st.selectbox(
            "اختر الصفحة / Select Page",
            options=list(range(editor.page_count)),
            format_func=lambda p: f"صفحة {p + 1} / Page {p + 1}",
            index=st.session_state["page_num"],
        )
        if page_num != st.session_state["page_num"]:
            st.session_state["page_num"] = page_num
            st.session_state["smart_matches"] = []
            st.session_state["last_preview_click_ts"] = 0
            st.session_state["preview_selection_info"] = None
            refresh_elements(reset_selection=True)

        mode_label = st.radio(
            "طريقة الاختيار / Selection Mode",
            options=list(SELECTION_MODES.keys()),
            index=list(SELECTION_MODES.values()).index(st.session_state["selection_mode"]),
            help="اختر بين تحرير كلمة مفردة أو سطر كامل أو عنصر نصي كامل حسب الحاجة.",
        )
        mode_value = SELECTION_MODES[mode_label]
        if mode_value != st.session_state["selection_mode"]:
            st.session_state["selection_mode"] = mode_value
            st.session_state["smart_matches"] = []
            st.session_state["last_preview_click_ts"] = 0
            st.session_state["preview_selection_info"] = None
            refresh_elements(reset_selection=True)

        use_ocr = st.checkbox(
            "استخدام OCR عند غياب النص الأصلي",
            value=st.session_state["use_ocr_fallback"],
            help="مفيد للصفحات التي تكون عبارة عن صورة داخل ملف PDF.",
        )
        if use_ocr != st.session_state["use_ocr_fallback"]:
            st.session_state["use_ocr_fallback"] = use_ocr
            st.session_state["smart_matches"] = []
            st.session_state["last_preview_click_ts"] = 0
            st.session_state["preview_selection_info"] = None
            refresh_elements(reset_selection=True)

        if st.session_state["use_ocr_fallback"]:
            ocr_status = editor.get_ocr_status(force_check=True)
            if ocr_status["available"]:
                st.caption(f"OCR: {ocr_status['message']}")
            else:
                st.warning(f"OCR غير متاح حاليًا: {ocr_status['message']}")

        use_ai = st.checkbox(
            "مساعدة ذكية اختيارية للعثور على أقرب تطابق",
            value=st.session_state["use_ai_assist"],
            help="تُستخدم فقط عندما لا يجد التطبيق تطابقًا مباشرًا بشكل كافٍ.",
        )
        st.session_state["use_ai_assist"] = use_ai

        if editor.history:
            st.divider()
            st.subheader("📝 سجل التعديلات / Edit History")
            for i, item in enumerate(reversed(editor.history[-10:]), 1):
                st.caption(f"{i}. {item}")

            if st.button("↩️ تراجع / Undo Last Edit", use_container_width=True):
                if editor.undo():
                    refresh_elements(reset_selection=True)
                    st.success("تم التراجع عن آخر تعديل.")
                    st.rerun()
                else:
                    st.warning("لا يوجد تعديل للتراجع عنه.")

        st.divider()
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


if not editor.is_loaded():
    st.markdown(
        """
        <div style="text-align:center; padding: 80px 20px; color: #888;">
            <h2>📄 محرر PDF الذكي</h2>
            <p style="font-size:1.1em;">ارفع ملف PDF من الشريط الجانبي للبدء<br>
            <em>Upload a PDF from the sidebar to start smart text replacement</em></p>
        </div>
        """,
        unsafe_allow_html=True,
    )
    st.stop()


elements: list[TextElement] = st.session_state["elements"]
page_num: int = st.session_state["page_num"]
selection_mode: str = st.session_state["selection_mode"]
use_ocr_fallback: bool = st.session_state["use_ocr_fallback"]
use_ai_assist: bool = st.session_state["use_ai_assist"]

smart_col, preview_col, edit_col = st.columns([0.95, 1.15, 0.9], gap="large")

with smart_col:
    st.subheader("🧠 الاستبدال الذكي / Smart Replace")
    search_text = st.text_input(
        "الكلمة أو النص المراد استبداله",
        key="smart_search_text",
        placeholder="مثال: الاسم أو Hello",
    )
    replacement_text = st.text_input(
        "النص البديل",
        key="smart_replacement_text",
        placeholder="اكتب الكلمة الجديدة هنا",
    )

    search_clicked = st.button("🔎 بحث عن التطابقات", use_container_width=True)
    replace_clicked = st.button("⚡ استبدال أول تطابق ذكيًا", type="primary", use_container_width=True)

    if search_clicked:
        st.session_state["smart_matches"] = editor.find_text_matches(
            page_num=page_num,
            query=search_text,
            mode=selection_mode,
            use_ocr_fallback=use_ocr_fallback,
        )

    if replace_clicked:
        result = editor.smart_replace(
            page_num=page_num,
            search_text=search_text,
            replacement_text=replacement_text,
            mode=selection_mode,
            use_ocr_fallback=use_ocr_fallback,
            use_ai=use_ai_assist,
        )
        if result["success"]:
            refresh_elements(reset_selection=True)
            st.session_state["smart_matches"] = []
            st.session_state["edit_results"].append(result)
            st.markdown(
                f"""
                <div class="success-card">
                ✅ <strong>تم الاستبدال بنجاح</strong><br>
                النص المطابق: <code>{result.get('matched_text', '—')}</code><br>
                المصدر: <code>{result.get('matched_source', '—')}</code> &nbsp;|&nbsp;
                سبب الاختيار: <code>{result.get('selection_reason', '—')}</code>
                </div>
                """,
                unsafe_allow_html=True,
            )
            st.rerun()
        else:
            st.error(f"❌ {result['message']}")

    matches = st.session_state.get("smart_matches", [])
    if matches:
        st.markdown(f"**عدد النتائج:** {len(matches)}")
        for i, item in enumerate(matches[:8], 1):
            elem = item["element"]
            st.caption(
                f"{i}. [{item['reason']} | {item['score']:.2f}] {elem.text} "
                f"— {elem.source}/{elem.kind}"
            )
    else:
        st.caption("استخدم البحث الذكي لإيجاد أقرب كلمة أو عبارة داخل الصفحة الحالية.")

with preview_col:
    st.subheader(f"📋 معاينة الصفحة {page_num + 1} / Page Preview")

    if estimate_is_scanned(elements):
        st.markdown(
            """
            <div class="warning-card">
            ⚠️ <strong>تنبيه:</strong> لم يتم العثور على نصوص أصلية قابلة للتحرير في هذا الوضع.
            إذا كانت الصفحة صورة، فعّل OCR من الشريط الجانبي ليحاول التطبيق استخراج الكلمات أو الأسطر تلقائيًا.
            </div>
            """,
            unsafe_allow_html=True,
        )
        if use_ocr_fallback:
            ocr_status = editor.get_ocr_status()
            if not ocr_status["available"]:
                st.caption(f"حالة OCR الحالية: {ocr_status['message']}")

    preview_zoom = 2.1
    png_bytes = editor.render_page(page_num, zoom=preview_zoom)
    if png_bytes:
        preview_image = Image.open(BytesIO(png_bytes)).convert("RGB")
        image_width, image_height = preview_image.size
        if streamlit_image_coordinates is not None:
            st.caption("اضغط أو اسحب بالماوس فوق الكلمة أو السطر في المعاينة ليتم تحديده مباشرة في نافذة التحرير.")
            preview_event = streamlit_image_coordinates(
                preview_image,
                key=f"preview_click_{page_num}_{selection_mode}_{int(use_ocr_fallback)}",
                use_column_width="auto",
                click_and_drag=True,
                cursor="crosshair",
            )
            _process_preview_selection(preview_event, image_width=image_width, image_height=image_height)
        else:
            st.image(png_bytes, use_container_width=True)
            st.warning("مكوّن التحديد المباشر غير متاح في البيئة الحالية، لذلك تم عرض المعاينة العادية فقط.")

        preview_info = st.session_state.get("preview_selection_info")
        if preview_info:
            if preview_info.get("status") == "selected":
                st.caption(
                    f"{preview_info.get('message', '')} — {preview_info.get('source', '—')}/{preview_info.get('kind', '—')}"
                )
            else:
                st.caption(preview_info.get("message", ""))

    if elements:
        st.subheader("📃 العناصر القابلة للتحرير / Editable Items")
        st.caption("يمكنك الضغط على أي صف في الجدول لفتح العنصر نفسه في نافذة التحرير على اليمين.")
        df = elements_to_dataframe(elements)
        dataframe_kwargs = {
            "data": df,
            "use_container_width": True,
            "height": 320,
            "hide_index": True,
            "column_config": {
                "#": st.column_config.NumberColumn(width="small"),
                "النص / Text": st.column_config.TextColumn(width="large"),
                "النوع / Type": st.column_config.TextColumn(width="small"),
                "المصدر / Source": st.column_config.TextColumn(width="small"),
                "اللون / Color": st.column_config.TextColumn(width="small"),
            },
        }

        selected_rows = []
        try:
            event = st.dataframe(
                **dataframe_kwargs,
                on_select="rerun",
                selection_mode="single-row",
            )
            selected_rows = _selected_rows_from_event(event)
        except TypeError:
            st.dataframe(**dataframe_kwargs)

        if selected_rows:
            selected_from_table = int(df.iloc[selected_rows[0]]["#"])
            if selected_from_table != st.session_state["selected_idx"]:
                st.session_state["selected_idx"] = selected_from_table
                st.rerun()

with edit_col:
    st.subheader("✏️ نافذة تحرير العنصر المحدد / Edit Window")

    if not elements:
        st.info("لا توجد عناصر قابلة للتحرير حاليًا. جرّب تفعيل OCR أو استخدم الاستبدال الذكي بعد تغيير الإعدادات.")
    else:
        with st.container(border=True):
            nav_col1, nav_col2 = st.columns([1, 1])
            with nav_col1:
                idx_options = list(range(len(elements)))
                default_index = min(st.session_state.get("selected_idx", 0), len(idx_options) - 1)
                selected_idx = st.selectbox(
                    "اختر عنصرًا للتعديل اليدوي",
                    options=idx_options,
                    index=default_index,
                    format_func=lambda i: f"[{i}] {elements[i].text[:60]}{'…' if len(elements[i].text) > 60 else ''}",
                )
                st.session_state["selected_idx"] = selected_idx
            with nav_col2:
                st.caption("لتحرير أشمل وبنفس السطر، اختر وضع الأسطر من الشريط الجانبي عند الحاجة.")

            elem: TextElement = elements[selected_idx]
            flags = decode_font_flags(elem.flags)
            is_arabic = contains_arabic(elem.text)

            st.markdown(
                f"""
                <div class="info-card">
                <strong>العنصر #{elem.index}</strong> &nbsp;|&nbsp;
                المصدر: <code>{elem.source}</code> &nbsp;|&nbsp;
                النوع: <code>{elem.kind}</code> &nbsp;|&nbsp;
                الخط: <code>{elem.font_name}</code> &nbsp;|&nbsp;
                الحجم: <code>{elem.font_size}pt</code> &nbsp;|&nbsp;
                اللون: <code>{rgb_to_hex(*elem.color)}</code><br>
                الاتجاه: {'RTL ←' if is_arabic else 'LTR →'}
                {'&nbsp;| <strong>Bold</strong>' if flags['bold'] else ''}
                {'&nbsp;| <em>Italic</em>' if flags['italic'] else ''}
                </div>
                """,
                unsafe_allow_html=True,
            )

            st.text_area(
                "النص الأصلي / Original Text",
                value=elem.text,
                height=80,
                disabled=True,
            )
            new_text = st.text_area(
                "النص الجديد / New Text",
                value=elem.text,
                height=90,
                key=f"manual_new_{selected_idx}_{selection_mode}",
                help="سيتم مسح النص السابق واستبداله في الموضع نفسه قدر الإمكان مع الحفاظ على السطر واللون والحجم والخط القريب.",
            )

            with st.expander("⚙️ خيارات متقدمة / Advanced Options"):
                col_a, col_b = st.columns(2)
                with col_a:
                    custom_size = st.number_input(
                        "حجم الخط / Font Size (pt)",
                        min_value=4.0,
                        max_value=200.0,
                        value=float(elem.font_size),
                        step=0.5,
                        key=f"size_{selected_idx}_{selection_mode}",
                    )
                    auto_fit = st.checkbox(
                        "تصغير تلقائي / Auto-fit",
                        value=True,
                        key=f"autofit_{selected_idx}_{selection_mode}",
                        help="يحافظ على بقاء النص داخل نفس الصندوق والموضع عند زيادة طول النص الجديد.",
                    )
                with col_b:
                    color_hex = st.color_picker(
                        "اللون / Color",
                        value=rgb_to_hex(*elem.color),
                        key=f"color_{selected_idx}_{selection_mode}",
                    )

            if new_text != elem.text:
                st.markdown(
                    f'<div class="info-card">🔍 الفرق / Diff: {simple_diff(elem.text, new_text)}</div>',
                    unsafe_allow_html=True,
                )

            if st.button("✅ تطبيق التعديل اليدوي", use_container_width=True):
                elem.color = hex_to_rgb(color_hex)
                size_override = None if auto_fit else custom_size
                result = editor.replace_text(
                    page_num=page_num,
                    element=elem,
                    new_text=new_text,
                    font_size_override=size_override,
                    auto_fit=auto_fit,
                )
                if result["success"]:
                    refresh_elements(reset_selection=True)
                    st.session_state["edit_results"].append(result)
                    st.success("تم حفظ التعديل اليدوي بنجاح.")
                    st.rerun()
                else:
                    st.error(f"❌ فشل التعديل: {result['message']}")

            recent = st.session_state.get("edit_results", [])
            if recent:
                with st.expander(f"📊 آخر النتائج ({len(recent)})"):
                    for i, result in enumerate(reversed(recent[-5:]), 1):
                        st.caption(
                            f"{i}. {result.get('message', '')} | "
                            f"{result.get('matched_text', result.get('element_kind', '—'))}"
                        )

st.divider()
st.caption(
    "⚡ المحرر الذكي يدعم الآن اختيار الكلمات أو الأسطر، وOCR الاحتياطي الآمن، والاستبدال داخل نفس الموضع بأعلى دقة ممكنة دون إعادة بناء المشروع من الصفر."
)
