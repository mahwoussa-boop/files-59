"""
ai_helper.py
Optional AI-assisted helpers for smart text matching.
"""

import json
from typing import Optional


def choose_best_candidate_with_ai(query: str, candidates: list[str]) -> Optional[dict]:
    """Use an AI model to select the closest candidate for a search query.

    Returns a dict with keys: index, reason, confidence.
    Returns None on any failure so the application can continue safely.
    """
    if not query or not candidates:
        return None

    try:
        from openai import OpenAI
    except Exception:
        return None

    try:
        client = OpenAI()
        payload = {
            "query": query,
            "candidates": [{"index": i, "text": text} for i, text in enumerate(candidates[:200])],
        }
        prompt = (
            "أنت مساعد دقيق لاختيار أقرب عنصر نصي من قائمة عناصر PDF. "
            "اختر أفضل عنصر يطابق طلب المستخدم حتى لو كان هناك اختلاف بسيط في التهجئة أو المسافات أو علامات الترقيم. "
            "أعد النتيجة فقط بصيغة JSON صحيحة تحتوي المفاتيح: index, reason, confidence. "
            "confidence يجب أن تكون رقمًا بين 0 و 1. "
            f"\n\nالمدخلات:\n{json.dumps(payload, ensure_ascii=False)}"
        )
        response = client.responses.create(
            model="gemini-2.5-flash",
            input=prompt,
            temperature=0,
        )
        text = getattr(response, "output_text", "") or ""
        if not text.strip():
            return None

        start = text.find("{")
        end = text.rfind("}")
        if start == -1 or end == -1 or end <= start:
            return None

        data = json.loads(text[start : end + 1])
        index = int(data.get("index", -1))
        if index < 0 or index >= len(candidates[:200]):
            return None
        confidence = float(data.get("confidence", 0))
        return {
            "index": index,
            "reason": str(data.get("reason", "AI-selected candidate")),
            "confidence": max(0.0, min(confidence, 1.0)),
        }
    except Exception:
        return None
