# -*- coding: utf-8 -*-
"""RapidOCR 封装：从 PIL 图里定位文字与其包围盒，供键鼠自动化使用。"""

_engine = None


def engine():
    global _engine
    if _engine is None:
        from rapidocr_onnxruntime import RapidOCR
        _engine = RapidOCR()
    return _engine


def ocr(img):
    """img: PIL.Image -> [{text, box, cx, cy, w, h, score}]"""
    import numpy as np
    arr = np.array(img.convert("RGB"))
    res, _ = engine()(arr)
    out = []
    for item in (res or []):
        box, text, score = item[0], item[1], item[2]
        xs = [float(p[0]) for p in box]
        ys = [float(p[1]) for p in box]
        x1, y1, x2, y2 = int(min(xs)), int(min(ys)), int(max(xs)), int(max(ys))
        out.append({"text": str(text).strip(), "box": [x1, y1, x2, y2],
                    "cx": (x1 + x2) // 2, "cy": (y1 + y2) // 2,
                    "w": x2 - x1, "h": y2 - y1, "score": float(score)})
    return out


def find(items, *keywords, exact=False, ymin=0, ymax=10 ** 9, xmin=0, xmax=10 ** 9):
    """按关键字找第一段匹配文字。exact=True 时要求完全相等。"""
    for it in items:
        if not (ymin <= it["cy"] <= ymax and xmin <= it["cx"] <= xmax):
            continue
        for k in keywords:
            if it["text"] == k if exact else k in it["text"]:
                return it
    return None


def find_all(items, *keywords, exact=False):
    out = []
    for it in items:
        for k in keywords:
            if it["text"] == k if exact else k in it["text"]:
                out.append(it)
                break
    return out


def dump(items, tag=""):
    lines = ["-- %s (%d 段文字) --" % (tag, len(items))]
    for it in items:
        lines.append("   y=%-5d x=%-5d w=%-4d h=%-3d | %s" % (
            it["cy"], it["cx"], it["w"], it["h"], it["text"][:50]))
    return "\n".join(lines)
