"""Keep hidden mind-trace fields in English (MiniCPM often leaks Chinese)."""

from __future__ import annotations

import re

_CJK_RE = re.compile(r"[\u4e00-\u9fff\u3400-\u4dbf\uf900-\ufaff]+")

_CJK_GLOSS: dict[str, str] = {
    "探索": "explore",
    "谨慎": "cautious",
    "警惕": "alert",
    "危险": "danger",
    "食物": "food",
    "饥饿": "hungry",
    "跟随": "follow",
    "分享": "share",
    "信号": "signal",
    "移动": "move",
    "停留": "stay",
    "隐藏": "hide",
    "信任": "trust",
    "欺骗": "deceive",
    "平静": "calm",
    "焦虑": "anxious",
    "高兴": "joyful",
}


def contains_cjk(text: str) -> bool:
    return bool(text and _CJK_RE.search(text))


def strip_cjk(text: str) -> str:
    if not text:
        return ""
    return re.sub(r"\s+", " ", _CJK_RE.sub("", text)).strip()


def _gloss_cjk(text: str) -> str:
    if not text:
        return ""
    parts: list[str] = []
    for word, gloss in _CJK_GLOSS.items():
        if word in text:
            parts.append(gloss)
    if parts:
        return ", ".join(dict.fromkeys(parts))
    for chunk in _CJK_RE.findall(text):
        parts.append(_CJK_GLOSS.get(chunk, "unsure"))
    return ", ".join(parts)


def enforce_english_prose(text: str, *, fallback: str) -> str:
    if not text:
        return fallback[:240]
    if not contains_cjk(text):
        return text.strip()[:240]
    ascii_part = strip_cjk(text)
    if len(ascii_part) >= 12:
        return ascii_part[:240]
    gloss = _gloss_cjk(text)
    if gloss:
        return gloss[:240]
    return fallback[:240]


def enforce_english_interpretation(interp: dict[str, str]) -> dict[str, str]:
    out: dict[str, str] = {}
    for key, value in interp.items():
        if not key:
            continue
        raw = (value or "").strip()
        if not raw:
            out[str(key)] = "unsure meaning"
            continue
        if not contains_cjk(raw):
            out[str(key)] = raw[:80]
            continue
        ascii_part = strip_cjk(raw)
        if len(ascii_part) >= 3:
            out[str(key)] = ascii_part[:80]
            continue
        gloss = _gloss_cjk(raw)
        out[str(key)] = (gloss or "unsure meaning")[:80]
    return out
