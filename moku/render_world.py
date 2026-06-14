"""Immersive world scene renderer — organic forest, not a board grid."""

from __future__ import annotations

import html
import hashlib
import re
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from moku.sim_engine import Creature, WorldState

from moku.visual_layers import VisualLayers, layers_from_toggles, overlay_css_classes

# Keep grid edge cells visible — sprites anchor at center and extend past the point.
_MAP_INSET_PCT = 7.0

# Per-creature visual identity: body hue, accent, silhouette type (bright, glossy palette)
CREATURE_LOOKS: dict[str, dict[str, str]] = {
    "Lumo": {"body": "#6ef0e4", "accent": "#1ea898", "glow": "#c8fff8", "shape": "round"},
    "Nia": {"body": "#dcc4ff", "accent": "#8b62e8", "glow": "#f5ecff", "shape": "wisp"},
    "Oro": {"body": "#ffc878", "accent": "#e08828", "glow": "#fff0c0", "shape": "stout"},
    "Pika": {"body": "#ffb8cc", "accent": "#e06890", "glow": "#ffe0ea", "shape": "bouncy"},
    "Vey": {"body": "#98eeb0", "accent": "#38b068", "glow": "#d8ffe4", "shape": "leafy"},
    "Sora": {"body": "#b8d8ff", "accent": "#4890e8", "glow": "#e8f4ff", "shape": "drift"},
    "Miri": {"body": "#ffe888", "accent": "#d8a820", "glow": "#fff8c8", "shape": "round"},
    "Tiko": {"body": "#e8b8ff", "accent": "#a848e8", "glow": "#f8e8ff", "shape": "spiky"},
    "Brum": {"body": "#b8d0e8", "accent": "#5888a8", "glow": "#e8f4ff", "shape": "stout"},
    "Eli": {"body": "#ffd8b0", "accent": "#e09848", "glow": "#fff0d8", "shape": "wisp"},
}


def _creature_svg_defs(uid: str, body: str, accent: str, glow: str) -> str:
    return (
        f"<defs>"
        f'<linearGradient id="{uid}-body" x1="16%" y1="6%" x2="84%" y2="94%">'
        f'<stop offset="0%" stop-color="{glow}" stop-opacity="1"/>'
        f'<stop offset="42%" stop-color="{body}"/>'
        f'<stop offset="100%" stop-color="{accent}"/>'
        f"</linearGradient>"
        f'<radialGradient id="{uid}-shine" cx="34%" cy="26%" r="52%">'
        f'<stop offset="0%" stop-color="#ffffff" stop-opacity="0.78"/>'
        f'<stop offset="50%" stop-color="#ffffff" stop-opacity="0.22"/>'
        f'<stop offset="100%" stop-color="#ffffff" stop-opacity="0"/>'
        f"</radialGradient>"
        f'<radialGradient id="{uid}-aura" cx="50%" cy="58%" r="54%">'
        f'<stop offset="0%" stop-color="{glow}" stop-opacity="0.72"/>'
        f'<stop offset="100%" stop-color="{glow}" stop-opacity="0"/>'
        f"</radialGradient>"
        f"</defs>"
    )


def _creature_shine(uid: str, cx: int = 20, cy: int = 19, rx: int = 11, ry: int = 9) -> str:
    return (
        f'<ellipse cx="{cx}" cy="{cy}" rx="{rx}" ry="{ry}" '
        f'fill="url(#{uid}-shine)" pointer-events="none" class="creature-shine"/>'
    )


def _look(name: str) -> dict[str, str]:
    if name in CREATURE_LOOKS:
        return CREATURE_LOOKS[name]
    h = int(hashlib.md5(name.encode()).hexdigest()[:6], 16)
    hues = ["#6ef0e4", "#dcc4ff", "#ffc878", "#98eeb0", "#ffb8cc", "#b8d8ff"]
    body = hues[h % len(hues)]
    glow = body
    return {"body": body, "accent": body, "glow": glow, "shape": "round"}


def _terrain_variant(x: int, y: int) -> str:
    v = (x * 17 + y * 31) % 5
    variants = ["moss", "fern", "dark", "moss", "peat"]
    return variants[v]


def _creature_svg(creature: "Creature", size: int = 44, svg_id: str | None = None) -> str:
    look = _look(creature.name)
    body, accent, glow, shape = look["body"], look["accent"], look["glow"], look["shape"]
    fear_pulse = min(creature.fear / 100, 1.0)
    hunger_dim = max(0.9, 1.0 - min(creature.hunger / 200, 0.1))
    uid = "".join(ch if ch.isalnum() or ch in "-_" else "-" for ch in str(svg_id or creature.cid))
    body_fill = f"url(#{uid}-body)"
    rim = f' stroke="{glow}" stroke-opacity="0.35" stroke-width="0.6"'

    if shape == "round":
        body_path = (
            f'<ellipse cx="22" cy="26" rx="14" ry="13" fill="{body_fill}" stroke="{accent}" stroke-width="1.5"{rim}/>'
        )
        eyes = (
            f'<circle cx="17" cy="22" r="3.5" fill="#1a1a2e"/>'
            f'<circle cx="27" cy="22" r="3.5" fill="#1a1a2e"/>'
            f'<circle cx="18" cy="20.5" r="1.6" fill="white" opacity="0.95"/>'
            f'<circle cx="28" cy="20.5" r="1.6" fill="white" opacity="0.95"/>'
        )
        feet = f'<ellipse cx="16" cy="36" rx="4" ry="2" fill="{accent}" opacity="0.75"/>'
        feet += f'<ellipse cx="28" cy="36" rx="4" ry="2" fill="{accent}" opacity="0.75"/>'
        shine = _creature_shine(uid, 19, 18, 12, 10)
    elif shape == "wisp":
        body_path = (
            f'<path d="M22 8 Q30 18 28 28 Q26 38 22 40 Q18 38 16 28 Q14 18 22 8" '
            f'fill="{body_fill}" stroke="{accent}" stroke-width="1.2"{rim}/>'
        )
        eyes = (
            f'<ellipse cx="19" cy="22" rx="2.5" ry="4" fill="#1a1a2e"/>'
            f'<ellipse cx="25" cy="22" rx="2.5" ry="4" fill="#1a1a2e"/>'
            f'<circle cx="19.5" cy="19.5" r="1.2" fill="white" opacity="0.95"/>'
            f'<circle cx="25.5" cy="19.5" r="1.2" fill="white" opacity="0.95"/>'
        )
        feet = f'<path d="M18 38 Q22 42 26 38" stroke="{accent}" stroke-width="2" fill="none"/>'
        shine = _creature_shine(uid, 20, 16, 10, 12)
    elif shape == "stout":
        body_path = (
            f'<rect x="12" y="18" width="20" height="18" rx="8" fill="{body_fill}" stroke="{accent}" stroke-width="1.5"{rim}/>'
            f'<path d="M14 16 L18 10 L22 16" fill="{accent}"/>'
            f'<path d="M22 16 L26 10 L30 16" fill="{accent}"/>'
        )
        eyes = (
            f'<circle cx="17" cy="26" r="3" fill="#1a1a2e"/>'
            f'<circle cx="27" cy="26" r="3" fill="#1a1a2e"/>'
            f'<circle cx="18" cy="24.5" r="1.3" fill="white" opacity="0.95"/>'
            f'<circle cx="28" cy="24.5" r="1.3" fill="white" opacity="0.95"/>'
        )
        feet = f'<rect x="14" y="34" width="6" height="4" rx="2" fill="{accent}"/>'
        feet += f'<rect x="24" y="34" width="6" height="4" rx="2" fill="{accent}"/>'
        shine = _creature_shine(uid, 20, 22, 11, 8)
    elif shape == "leafy":
        body_path = (
            f'<ellipse cx="22" cy="26" rx="12" ry="14" fill="{body_fill}" stroke="{accent}" stroke-width="1.2"{rim}/>'
            f'<path d="M10 24 Q6 18 12 14" stroke="{accent}" stroke-width="2" fill="none"/>'
            f'<path d="M34 24 Q38 18 32 14" stroke="{accent}" stroke-width="2" fill="none"/>'
        )
        eyes = (
            f'<circle cx="18" cy="24" r="2.8" fill="#1a1a2e"/>'
            f'<circle cx="26" cy="24" r="2.8" fill="#1a1a2e"/>'
            f'<circle cx="18.8" cy="22.8" r="1.1" fill="white" opacity="0.9"/>'
            f'<circle cx="26.8" cy="22.8" r="1.1" fill="white" opacity="0.9"/>'
        )
        feet = f'<ellipse cx="18" cy="37" rx="3" ry="2" fill="{accent}"/>'
        feet += f'<ellipse cx="26" cy="37" rx="3" ry="2" fill="{accent}"/>'
        shine = _creature_shine(uid, 19, 19, 10, 9)
    elif shape == "spiky":
        body_path = (
            f'<circle cx="22" cy="26" r="13" fill="{body_fill}" stroke="{accent}" stroke-width="1.2"{rim}/>'
            f'<path d="M22 10 L24 16 L22 14 L20 16 Z" fill="{accent}"/>'
            f'<path d="M10 22 L16 24 L14 22 L16 20 Z" fill="{accent}"/>'
            f'<path d="M34 22 L28 24 L30 22 L28 20 Z" fill="{accent}"/>'
        )
        eyes = (
            f'<circle cx="17" cy="25" r="3" fill="#1a1a2e"/>'
            f'<circle cx="27" cy="25" r="3" fill="#1a1a2e"/>'
            f'<circle cx="18" cy="23.5" r="1.2" fill="white" opacity="0.95"/>'
            f'<circle cx="28" cy="23.5" r="1.2" fill="white" opacity="0.95"/>'
        )
        feet = f'<ellipse cx="17" cy="36" rx="3.5" ry="2" fill="{accent}"/>'
        feet += f'<ellipse cx="27" cy="36" rx="3.5" ry="2" fill="{accent}"/>'
        shine = _creature_shine(uid, 19, 18, 11, 9)
    elif shape == "bouncy":
        body_path = (
            f'<ellipse cx="22" cy="24" rx="15" ry="12" fill="{body_fill}" stroke="{accent}" stroke-width="1.5"{rim}/>'
        )
        eyes = (
            f'<circle cx="16" cy="21" r="4" fill="#1a1a2e"/>'
            f'<circle cx="28" cy="21" r="4" fill="#1a1a2e"/>'
            f'<circle cx="17" cy="19" r="1.8" fill="white" opacity="0.95"/>'
            f'<circle cx="29" cy="19" r="1.8" fill="white" opacity="0.95"/>'
        )
        feet = f'<ellipse cx="15" cy="35" rx="5" ry="3" fill="{accent}" opacity="0.85"/>'
        feet += f'<ellipse cx="29" cy="35" rx="5" ry="3" fill="{accent}" opacity="0.85"/>'
        shine = _creature_shine(uid, 20, 17, 13, 10)
    else:  # drift
        body_path = (
            f'<ellipse cx="22" cy="26" rx="11" ry="15" fill="{body_fill}" stroke="{accent}" stroke-width="1.2"{rim}/>'
            f'<ellipse cx="22" cy="20" rx="8" ry="6" fill="{glow}" opacity="0.55"/>'
        )
        eyes = (
            f'<circle cx="18" cy="24" r="2.5" fill="#1a1a2e"/>'
            f'<circle cx="26" cy="24" r="2.5" fill="#1a1a2e"/>'
            f'<circle cx="18.6" cy="22.8" r="1" fill="white" opacity="0.9"/>'
            f'<circle cx="26.6" cy="22.8" r="1" fill="white" opacity="0.9"/>'
        )
        feet = ""
        shine = _creature_shine(uid, 20, 18, 9, 11)

    opacity = hunger_dim
    fear_ring = ""
    if fear_pulse > 0.5:
        fear_ring = f'<circle cx="22" cy="26" r="18" fill="none" stroke="#e87878" stroke-width="1.5" opacity="{fear_pulse * 0.5}" class="fear-pulse"/>'

    return (
        f'<svg class="creature-svg" width="{size}" height="{size}" viewBox="0 0 44 44" '
        f'data-creature="{html.escape(creature.name)}" aria-label="{html.escape(creature.name)}" '
        f'style="opacity:{opacity:.2f};--crt-body:{body};--crt-glow:{glow}">'
        f"{_creature_svg_defs(uid, body, accent, glow)}"
        f'<circle cx="22" cy="28" r="17" fill="url(#{uid}-aura)"/>'
        f"{fear_ring}"
        f"<g class=\"creature-body\">{body_path}{shine}{eyes}{feet}</g>"
        f"</svg>"
    )


ACTION_ICONS: dict[str, str] = {
    "gather": "🌿",
    "hide": "🫥",
    "share_food": "🤝",
    "follow": "👣",
    "signal": "🔔",
    "stay": "•",
    "move_north": "↑",
    "move_south": "↓",
    "move_east": "→",
    "move_west": "←",
}


def _interpretation_tone(trace: dict[str, Any] | None) -> str:
    if not trace:
        return "tone-neutral"
    interp = trace.get("interpretation") if isinstance(trace.get("interpretation"), dict) else {}
    blob = " ".join(str(v).lower() for v in interp.values())
    if any(w in blob for w in ("danger", "fear", "suspicious", "lie", "trap")):
        return "tone-danger"
    if any(w in blob for w in ("food", "useful", "gather", "share", "promise")):
        return "tone-food"
    if any(w in blob for w in ("signal", "alert", "follow", "concern")):
        return "tone-social"
    return "tone-neutral"


def _status_class(creature: "Creature") -> str:
    if creature.fear >= 58:
        return " status-afraid"
    if creature.hunger >= 58:
        return " status-hungry"
    if creature.mood in {"scheming", "uneasy"}:
        return " status-wary"
    return " status-calm"


def _hud_verb_line(last_trace: dict[str, Any] | None) -> str:
    if not last_trace:
        return ""
    who = html.escape(str(last_trace.get("creature") or "?"))
    action = str(last_trace.get("action") or "acted").replace("_", " ")
    tgt = last_trace.get("target")
    glyphs = " ".join(html.escape(str(g)) for g in (last_trace.get("glyphs") or [])[:3])
    line = f"{who} · {html.escape(action)}"
    if tgt:
        line += f" → {html.escape(str(tgt))}"
    if glyphs:
        line += f' · <span class="hud-glyphs">{glyphs}</span>'
    return line


def _map_span(w: int, h: int) -> tuple[float, float, float, float]:
    span_x = 100.0 - 2 * _MAP_INSET_PCT
    span_y = 100.0 - 2 * _MAP_INSET_PCT
    cell_w = span_x / w
    cell_h = span_y / h
    return span_x, span_y, cell_w, cell_h


def _cell_center_pct(x: int, y: int, w: int, h: int) -> tuple[float, float]:
    _, _, cell_w, cell_h = _map_span(w, h)
    cx = _MAP_INSET_PCT + (x + 0.5) * cell_w
    cy = _MAP_INSET_PCT + (y + 0.5) * cell_h
    return cx, cy


def _clamp_map_pct(x: float, y: float) -> tuple[float, float]:
    lo = _MAP_INSET_PCT + 2.0
    hi = 100.0 - _MAP_INSET_PCT - 2.0
    return max(lo, min(hi, x)), max(lo, min(hi, y))


def _map_legend() -> str:
    return (
        '<div class="map-legend" aria-label="Map legend">'
        '<span class="legend-item"><i class="legend-dot legend-food"></i>food</span>'
        '<span class="legend-item"><i class="legend-dot legend-danger"></i>danger</span>'
        '<span class="legend-item"><i class="legend-dot legend-shelter"></i>shelter</span>'
        "</div>"
    )


def _social_bond_pairs(state: "WorldState") -> set[tuple[str, str]]:
    """Pairs with real social actions in the trace — not move intent or random trust."""
    pairs: set[tuple[str, str]] = set()
    for t in state.trace_log:
        action = str(t.get("action") or "")
        if action not in {"signal", "follow", "share_food"}:
            continue
        src, tgt = t.get("creature"), t.get("target")
        if not src or not tgt:
            continue
        pairs.add(tuple(sorted([str(src), str(tgt)])))
    for line in state.transcript:
        if "shares food with" not in line:
            continue
        m = re.search(r"Turn \d+ - (\S+) shares food with (\S+)\.", line)
        if m:
            pairs.add(tuple(sorted([m.group(1), m.group(2)])))
    return pairs


def _trust_threads(state: "WorldState", positions: dict[str, tuple[float, float]]) -> str:
    bonds = _social_bond_pairs(state)
    if not bonds:
        return ""
    drawn: set[tuple[str, str]] = set()
    segments: list[str] = []
    for pair in bonds:
        if pair in drawn:
            continue
        if pair[0] not in positions or pair[1] not in positions:
            continue
        drawn.add(pair)
        x1, y1 = positions[pair[0]]
        x2, y2 = positions[pair[1]]
        mx, my = (x1 + x2) / 2, (y1 + y2) / 2 + 4
        path = f"M{x1},{y1} Q{mx},{my} {x2},{y2}"
        segments.append(f'<path class="trust-thread trust-thread-glow" d="{path}" />')
        segments.append(f'<path class="trust-thread" d="{path}" />')
    if not segments:
        return ""
    return (
        '<svg class="world-trust" viewBox="0 0 100 100" preserveAspectRatio="none" aria-hidden="true">'
        f'{"".join(segments)}'
        "</svg>"
    )


def render_transcript_strip(state: "WorldState") -> str:
    lines = state.transcript[-5:]
    if not lines:
        return (
            '<div class="transcript-strip transcript-empty">'
            "<em>Public language will appear here when creatures speak.</em></div>"
        )
    items: list[str] = []
    for line in reversed(lines):
        if ":" not in line:
            continue
        head, glyphs = line.split(":", 1)
        speaker = head.split("-")[-1].strip() if "-" in head else head.strip()
        glyph_text = glyphs.strip()
        items.append(
            f'<span class="transcript-chip">'
            f'<strong>{html.escape(speaker)}</strong> '
            f'<span class="transcript-glyphs">{html.escape(glyph_text)}</span>'
            f"</span>"
        )
    body = "".join(items) if items else "<em>Quiet forest.</em>"
    return (
        '<div class="transcript-strip">'
        '<span class="transcript-label">Public speech</span>'
        f'<div class="transcript-chips">{body}</div>'
        "</div>"
    )


def render_story_section(
    state: "WorldState",
    last_trace: dict[str, Any] | None = None,
    *,
    playing: bool = True,
) -> str:
    if last_trace is None:
        last_trace = state.trace_log[-1] if state.trace_log else None
    parts: list[str] = [
        render_turn_beat_banner(last_trace),
        '<section class="moku-story-section moku-instrument">',
    ]

    if not playing and state.run_summary:
        rs = state.run_summary
        turns = rs.get("turns", state.turn)
        parts.append(
            '<div class="instrument-head">'
            '<span class="instrument-title">Forest Epilogue</span>'
            f'<span class="instrument-tag">turns 1–{turns}</span>'
            "</div>"
        )
        parts.append('<div class="instrument-body story-body">')
        parts.append(
            '<div class="story-subhead">'
            "Woven when you stopped · cross-check Mind Traces for proof"
            "</div>"
        )
        meta = f"{turns} turns"
        if rs.get("latency_ms"):
            meta += f" · {rs['latency_ms']}ms"
        if not rs.get("llm_ok"):
            meta += " · woven from traces"
        parts.append(f'<article class="chronicle-entry chronicle-finale">')
        parts.append(f'<div class="chronicle-meta">{html.escape(meta)}</div>')
        parts.append(f'<p class="chronicle-text chronicle-epilogue">{html.escape(str(rs.get("text", "")))}</p>')
        parts.append("</article>")
    else:
        parts.append(
            '<div class="instrument-head">'
            '<span class="instrument-title">Forest Chronicle</span>'
            '<span class="instrument-tag">narrative layer</span>'
            "</div>"
        )
        parts.append('<div class="instrument-body story-body">')
        parts.append(
            '<div class="story-subhead">'
            "Latest turn headline · press Stop for a full epilogue of the run"
            "</div>"
        )
        if not state.chronicle_log:
            parts.append('<p class="story-empty">Finish a full turn to weave the first line.</p>')
        else:
            entry = state.chronicle_log[-1]
            meta = f"Turn {entry.get('turn', '?')}"
            if entry.get("latency_ms"):
                meta += f" · {entry['latency_ms']}ms"
            if not entry.get("llm_ok"):
                meta += " · woven from traces"
            parts.append('<article class="chronicle-entry chronicle-latest">')
            parts.append(f'<div class="chronicle-meta">{html.escape(meta)}</div>')
            parts.append(f'<p class="chronicle-text">{html.escape(str(entry.get("text", "")))}</p>')
            parts.append("</article>")

    parts.append(render_transcript_strip(state))
    parts.append("</div></section>")
    return "".join(parts)


def _speech_bubble(glyphs: list[str], meaning: str = "", tone: str = "tone-neutral") -> str:
    if not glyphs:
        return ""
    text = " ".join(html.escape(g) for g in glyphs[:3])
    meaning_line = ""
    if meaning:
        meaning_line = f'<span class="glyph-meaning">{html.escape(meaning[:56])}</span>'
    return (
        f'<div class="speech-bubble speech-bubble-live {tone}">'
        f'<span class="speech-ripple"></span>'
        f'<span class="glyph-ring"></span>'
        f'<span class="glyph-text">{text}</span>'
        f"{meaning_line}"
        f"</div>"
    )


def _latest_trace_by_creature(trace_log: list[dict[str, Any]]) -> dict[str, dict[str, Any]]:
    latest: dict[str, dict[str, Any]] = {}
    for entry in trace_log:
        name = entry.get("creature")
        if name:
            latest[str(name)] = entry
    return latest


def _trace_glyph_caption(trace: dict[str, Any] | None) -> str:
    if not trace:
        return ""
    glyphs = trace.get("glyphs") or []
    if not glyphs:
        return ""
    interp = trace.get("interpretation") if isinstance(trace.get("interpretation"), dict) else {}
    bits: list[str] = []
    for g in glyphs[:3]:
        meaning = interp.get(g) if isinstance(interp, dict) else None
        if meaning:
            bits.append(f"{g}={meaning}")
        else:
            bits.append(str(g))
    return " · ".join(bits)


def _trace_action_class(trace: dict[str, Any] | None) -> str:
    if not trace or trace.get("fallback"):
        return ""
    action = trace.get("action")
    mapping = {
        "signal": " creature-signaling",
        "hide": " creature-hiding",
        "gather": " creature-gathering",
        "share_food": " creature-sharing",
        "follow": " creature-following",
    }
    return mapping.get(action, "")


def _signal_overlays(
    positions: dict[str, tuple[float, float]],
    trace_log: list[dict[str, Any]],
    *,
    signal_mode: str,
    focus_turn: int,
) -> str:
    if signal_mode == "none":
        return ""
    max_arcs = 4
    arcs: list[str] = []
    seen: set[tuple[str, str, str]] = set()
    for trace in reversed(trace_log):
        turn = int(trace.get("turn") or 0)
        if signal_mode == "turn" and turn != focus_turn:
            continue
        if trace.get("action") != "signal":
            continue
        src = trace.get("creature")
        tgt = trace.get("target")
        if not src or not tgt or src not in positions or tgt not in positions:
            continue
        glyphs = trace.get("glyphs") or []
        glyph_key = " ".join(str(g) for g in glyphs[:2])
        key = (str(src), str(tgt), glyph_key)
        if key in seen:
            continue
        seen.add(key)
        x1, y1 = positions[str(src)]
        x2, y2 = positions[str(tgt)]
        mx, my = (x1 + x2) / 2, min(y1, y2) - 10
        label = html.escape(glyph_key or "·")
        arcs.append(
            f'<g class="signal-group signal-strong" data-turn="{turn}">'
            f'<path class="signal-arc signal-arc-glow" d="M{x1},{y1} Q{mx},{my} {x2},{y2}" />'
            f'<path class="signal-arc" d="M{x1},{y1} Q{mx},{my} {x2},{y2}" />'
            f'<circle class="signal-pulse" cx="{x1}" cy="{y1}" r="1.4" />'
            f'<circle class="signal-pulse signal-pulse-delay signal-target-flash" cx="{x2}" cy="{y2}" r="1.1" />'
            f'<text class="signal-glyph" x="{mx}" y="{my - 2}">{label}</text>'
            f"</g>"
        )
        if len(arcs) >= max_arcs:
            break
    if not arcs:
        return ""
    return (
        '<svg class="world-signals" viewBox="0 0 100 100" preserveAspectRatio="none" aria-hidden="true">'
        f'{"".join(arcs)}'
        "</svg>"
    )


def _action_badges(
    positions: dict[str, tuple[float, float]],
    last_trace: dict[str, Any] | None,
    *,
    badge_mode: str,
    focus_turn: int,
) -> str:
    if badge_mode == "none" or not last_trace or last_trace.get("fallback"):
        return ""
    turn = int(last_trace.get("turn") or 0)
    if turn != focus_turn:
        return ""
    who = last_trace.get("creature")
    if not who or who not in positions:
        return ""
    cx, cy = positions[str(who)]
    action = str(last_trace.get("action") or "")
    icon = ACTION_ICONS.get(action, "•")
    return (
        f'<div class="action-badge action-{html.escape(action)}" '
        f'style="left:{cx:.1f}%;top:{cy:.1f}%" '
        f'data-creature="{html.escape(str(who))}" data-action="{html.escape(action)}" '
        f'title="{html.escape(action.replace("_", " "))}">'
        f'<span class="action-badge-icon">{icon}</span>'
        f"</div>"
    )


def _ambient_layer(seed: int) -> str:
    """Fireflies and dust — cheap life without a game engine."""
    parts: list[str] = ['<div class="world-ambient" aria-hidden="true">']
    for i in range(16):
        h = int(hashlib.md5(f"fly-{seed}-{i}".encode()).hexdigest()[:6], 16)
        left = 8 + (h % 840) / 10.0
        top = 12 + ((h >> 8) % 720) / 10.0
        delay = (h % 50) / 10.0
        dur = 3.5 + (h % 30) / 10.0
        parts.append(
            f'<span class="firefly" style="left:{left:.1f}%;top:{top:.1f}%;'
            f'animation-delay:{delay:.1f}s;animation-duration:{dur:.1f}s"></span>'
        )
    parts.append('<div class="canopy-light shaft-a"></div><div class="canopy-light shaft-b"></div>')
    parts.append("</div>")
    return "".join(parts)


def _event_toast(events: list[str]) -> str:
    if not events:
        return ""
    text = html.escape(events[-1][:120])
    return f'<div class="world-event-toast"><span class="toast-spark"></span>{text}</div>'


def _glyph_sparks(glyphs: list[str], glow: str) -> str:
    if not glyphs:
        return ""
    parts: list[str] = []
    for i, glyph in enumerate(glyphs[:3]):
        dx = (i - 1) * 14
        delay = i * 0.15
        parts.append(
            f'<span class="glyph-spark" style="--dx:{dx}px;--delay:{delay:.2f}s;--spark:{glow}">'
            f"{html.escape(glyph)}</span>"
        )
    return f'<div class="glyph-sparks" aria-hidden="true">{"".join(parts)}</div>'


def render_turn_beat_banner(last_trace: dict[str, Any] | None) -> str:
    line = _hud_verb_line(last_trace)
    if not line:
        return (
            '<div class="turn-beat-banner moku-instrument turn-beat-empty-wrap">'
            '<div class="instrument-head instrument-head-compact">'
            '<span class="instrument-title">Live beat</span>'
            '<span class="instrument-tag">idle</span>'
            "</div>"
            '<div class="instrument-body turn-beat-body">'
            "<em>Waiting for the first mind…</em></div></div>"
        )
    turn = int(last_trace.get("turn") or 0) if last_trace else 0
    return (
        f'<div class="turn-beat-banner moku-instrument">'
        f'<div class="instrument-head instrument-head-compact">'
        f'<span class="instrument-title">Live beat</span>'
        f'<span class="instrument-tag">turn {turn}</span>'
        f"</div>"
        f'<div class="instrument-body turn-beat-body">'
        f'<span class="turn-beat-action">{line}</span>'
        f"</div></div>"
    )


def render_world_scene(state: "WorldState", layers: VisualLayers | None = None) -> str:
    if layers is None:
        layers = layers_from_toggles()
    ov_cls = overlay_css_classes(layers)
    w, h = state.width, state.height
    span_x, span_y, cell_w, cell_h = _map_span(w, h)

    terrain_parts: list[str] = []
    for y in range(h):
        for x in range(w):
            variant = _terrain_variant(x, y)
            left = _MAP_INSET_PCT + x * cell_w
            top = _MAP_INSET_PCT + y * cell_h
            jitter_x = ((x * 7 + y * 13) % 5 - 2) * 0.3
            jitter_y = ((x * 11 + y * 3) % 5 - 2) * 0.3
            terrain_parts.append(
                f'<div class="terrain-tile {variant}" style="left:{left + jitter_x:.1f}%;top:{top + jitter_y:.1f}%;'
                f'width:{cell_w + 1.2}%;height:{cell_h + 1.2}%"></div>'
            )

    feature_parts: list[str] = []
    for x, y in state.food:
        fx, fy = _cell_center_pct(x, y, w, h)
        feature_parts.append(
            f'<div class="world-feature food-berry" style="left:{fx:.1f}%;top:{fy:.1f}%">'
            f'<div class="berry-glow"></div><div class="berry"></div></div>'
        )
    for x, y in state.danger:
        fx, fy = _cell_center_pct(x, y, w, h)
        feature_parts.append(
            f'<div class="world-feature danger-thorn" style="left:{fx:.1f}%;top:{fy:.1f}%">'
            f'<div class="thorn-pulse"></div></div>'
        )
    for x, y in state.shelter:
        fx, fy = _cell_center_pct(x, y, w, h)
        feature_parts.append(
            f'<div class="world-feature shelter-log" style="left:{fx:.1f}%;top:{fy:.1f}%">'
            f'<div class="log-mouth"></div></div>'
        )

    by_cell: dict[tuple[int, int], list["Creature"]] = {}
    for c in state.creatures:
        by_cell.setdefault((c.x, c.y), []).append(c)

    latest_traces = _latest_trace_by_creature(state.trace_log)
    last_trace = state.trace_log[-1] if state.trace_log else None
    last_actor = last_trace.get("creature") if last_trace else None
    positions: dict[str, tuple[float, float]] = {}

    creature_parts: list[str] = []
    for c in state.creatures:
        cell_mates = by_cell.get((c.x, c.y), [c])
        idx = cell_mates.index(c)
        n = len(cell_mates)
        # Fan overlapping creatures so every sprite stays visible.
        if n > 1:
            spread = min(6.0, cell_w * 0.28)
            offset_x = (idx - (n - 1) / 2) * spread
            offset_y = (idx % 2) * 2.0 - 1.0
        else:
            offset_x = 0.0
            offset_y = 0.0

        cx, cy = _cell_center_pct(c.x, c.y, w, h)
        cx += offset_x
        cy += offset_y
        cx, cy = _clamp_map_pct(cx, cy)
        positions[c.name] = (cx, cy)
        look = _look(c.name)
        creature_trace = latest_traces.get(c.name)
        is_last_actor = c.name == last_actor and last_trace and int(last_trace.get("turn") or 0) == state.turn

        bubble = ""
        if layers.speech_mode == "last" and is_last_actor and c.last_glyphs:
            tone = _interpretation_tone(creature_trace) if layers.show_speech_meaning else "tone-neutral"
            meaning = ""
            if layers.show_speech_meaning:
                meaning = _trace_glyph_caption(creature_trace) if creature_trace else ""
            bubble = _speech_bubble(c.last_glyphs, meaning=meaning, tone=tone)

        depth = c.y * 10 + idx
        svg_id = f"{c.cid}-t{state.turn}"

        mood_slug = "".join(ch if ch.isalnum() else "-" for ch in (c.mood or "calm")).strip("-") or "calm"
        action_slug = c.last_action or "stay"
        extra_cls = ""
        if is_last_actor:
            extra_cls += _trace_action_class(creature_trace)
            extra_cls += " creature-just-acted"
        if layers.show_status_rings:
            extra_cls += _status_class(c)
        if c.name.startswith("Stray"):
            extra_cls += " creature-stranger"

        status_ring = '<div class="creature-status-ring"></div>' if layers.show_status_rings else ""

        creature_parts.append(
            f'<div class="world-creature mood-{html.escape(mood_slug)} action-{html.escape(action_slug)}{extra_cls}" '
            f'style="left:{cx:.1f}%;top:{cy:.1f}%;--depth:{depth};'
            f'--glow:{look["glow"]}" '
            f'data-name="{html.escape(c.name)}" title="{html.escape(c.name)}">'
            f'<div class="creature-halo" style="background: radial-gradient(circle, {look["glow"]}ee 0%, {look["body"]}66 38%, transparent 72%)"></div>'
            f"{status_ring}"
            f'<div class="creature-action-ring"></div>'
            f"{_creature_svg(c, svg_id=svg_id)}"
            f'<span class="creature-label">{html.escape(c.name)}</span>'
            f"{bubble}"
            f"</div>"
        )

    weather_cls = f"weather-{state.weather}"
    scarcity_cls = f" scarcity-{min(state.scarcity_level, 5)}"
    event_text = " · ".join(state.last_events) if state.last_events else "The forest is quiet."
    thinker = None
    if state.creatures:
        idx = state.action_cursor - 1
        if idx < 0:
            idx = len(state.creatures) - 1
        thinker = state.creatures[idx].name
    thinker_line = f" · mind: {thinker}" if thinker else ""
    verb_line = _hud_verb_line(last_trace) if layers.show_turn_beat else ""
    toast = _event_toast(state.last_events) if layers.show_toast else ""
    trust = _trust_threads(state, positions) if layers.show_trust else ""

    return (
        f'<div class="world-scene {ov_cls}{weather_cls}{scarcity_cls}" data-turn="{state.turn}">'
        f'<div class="world-sky"></div>'
        f'<div class="world-dim"></div>'
        f"{_ambient_layer(state.turn)}"
        f"{_map_legend()}"
        f'<div class="world-ground">'
        f"{''.join(terrain_parts)}"
        f"{''.join(feature_parts)}"
        f"{trust}"
        f"{_signal_overlays(positions, state.trace_log, signal_mode=layers.signal_mode, focus_turn=state.turn)}"
        f"{''.join(creature_parts)}"
        f"{_action_badges(positions, last_trace, badge_mode=layers.badge_mode, focus_turn=state.turn)}"
        f"{toast}"
        f"</div>"
        f'<div class="world-hud">'
        f'<span class="hud-turn">Turn {state.turn}{thinker_line}</span>'
        f'<span class="hud-weather">{html.escape(state.weather)} · scarcity {state.scarcity_level}</span>'
        f'<span class="hud-verb">{verb_line}</span>'
        f'<span class="hud-event">{html.escape(event_text)}</span>'
        f"</div>"
        f'<div class="world-vignette"></div>'
        f"</div>"
    )


def render_guide_panel() -> str:
    """Static explainer — mounted once, toggled by Guide button; not tied to sim ticks."""
    return (
        '<aside class="moku-guide-panel" id="moku-guide-panel" aria-label="Simulator guide">'
        '<div class="guide-header">'
        '<div class="guide-title">Forest Guide</div>'
        '<button type="button" class="guide-close" id="moku-guide-close" aria-label="Close guide">×</button>'
        "</div>"
        '<p class="guide-lead">Glyphs are invented each run — no fixed dictionary. Meanings drift through play, memory, and trust.</p>'
        '<div class="guide-section">'
        '<div class="guide-section-title">Language</div>'
        '<ul class="guide-list">'
        "<li>Creatures coin short nonsense words (2–8 letters), not English.</li>"
        "<li><strong>Reuse</strong> words already in the public transcript when context repeats.</li>"
        "<li><strong>Private meaning</strong> lives in mind traces; the same word can mean different things to different creatures.</li>"
        "</ul></div>"
        '<div class="guide-section">'
        '<div class="guide-section-title">Map symbols</div>'
        '<ul class="guide-list">'
        '<li><span class="guide-swatch guide-swatch-food"></span><strong>Glimmer-fruit</strong> — food tile. Creatures can gather here.</li>'
        '<li><span class="guide-swatch guide-swatch-danger"></span><strong>Thorn</strong> — danger. Standing here raises fear and drains energy.</li>'
        '<li><span class="guide-swatch guide-swatch-shelter"></span><strong>Shelter log</strong> — safe cover. Hide actions work best nearby.</li>'
        "</ul></div>"
        '<div class="guide-section">'
        '<div class="guide-section-title">Creatures</div>'
        '<ul class="guide-list">'
        "<li>Each sprite is a mind controlled by a small LLM — hunger, fear, trust, and memory shape choices.</li>"
        "<li><strong>Speech bubble</strong> — public glyphs they last spoke (invented words, not English).</li>"
        "<li><strong>Subtitle under glyphs</strong> — that creature's latest private reading from traces (changes as language drifts).</li>"
        "<li><strong>Overlay toggles</strong> — turn layers on one at a time: Speech, Signals, Trust, Actions, Mood, Events.</li>"
        "</ul></div>"
        '<div class="guide-section">'
        '<div class="guide-section-title">Overlay layers</div>'
        '<ul class="guide-list">'
        "<li><strong>Speech</strong> — last speaker's public glyphs (+ private reading subtitle).</li>"
        "<li><strong>Signals</strong> — curved arcs for who signaled whom this turn.</li>"
        "<li><strong>Trust</strong> — faint bonds between allied minds.</li>"
        "<li><strong>Actions</strong> — icon on whoever acted last (gather, hide, signal…).</li>"
        "<li><strong>Mood</strong> — hunger / fear / calm rings on every creature.</li>"
        "<li><strong>Events</strong> — toast when sandbox beats fire (food, rain, stranger).</li>"
        "</ul></div>"
        '<div class="guide-section">'
        '<div class="guide-section-title">Always on</div>'
        '<ul class="guide-list">'
        "<li><strong>Spotlight</strong> — last actor gets a soft glow; everyone else stays sharp.</li>"
        "<li><strong>Turn beat</strong> — bold line under the map before the chronicle.</li>"
        "</ul></div>"
        '<div class="guide-section">'
        '<div class="guide-section-title">HUD bar</div>'
        '<ul class="guide-list">'
        "<li><strong>Turn</strong> — round number; <em>mind:</em> who thought last.</li>"
        "<li><strong>Weather / scarcity</strong> — world pressure (rain slows energy; scarcity raises hunger).</li>"
        "<li><strong>Italic line</strong> — latest world event.</li>"
        "</ul></div>"
        '<div class="guide-section">'
        '<div class="guide-section-title">Panels</div>'
        '<ul class="guide-list">'
        "<li><strong>Forest Chronicle</strong> — one short line for the latest turn while playing.</li>"
        "<li><strong>Forest Epilogue</strong> — full run summary when you press Stop.</li>"
        "<li><strong>Public speech strip</strong> — last glyphs spoken in the open.</li>"
        "<li><strong>Mind Traces</strong> — exact LLM reasoning each tick.</li>"
        "<li><strong>☰ Details</strong> — transcript, language evolution, dictionary, trust, deception.</li>"
        "<li><strong>⬇ JSON</strong> — export all traces for analysis.</li>"
        "</ul></div>"
        '<div class="guide-section">'
        '<div class="guide-section-title">Actions creatures may choose</div>'
        '<p class="guide-actions">move · gather · hide · signal · share_food · follow · stay</p>'
        "</div>"
        "</aside>"
    )


def render_side_panel(
    transcript: str,
    dictionary: str,
    trust: str,
    deception: str,
    creatures_html: str,
    traces: str = "",
    evolution: str = "",
    field_notes: str = "",
    report: str = "",
    glyph_drift: str = "",
    social_graph: str = "",
) -> str:
    def section(title: str, body: str, open_default: bool = False) -> str:
        open_attr = " open" if open_default else ""
        return (
            f'<details class="panel-section"{open_attr}>'
            f"<summary>{html.escape(title)}</summary>"
            f'<div class="panel-body">{body}</div>'
            f"</details>"
        )

    transcript_html = transcript.replace("\n", "<br>") if transcript else "<em>No one has spoken yet.</em>"
    dict_html = dictionary.replace("\n", "<br>") if dictionary else "<em>No glyphs yet.</em>"
    trust_html = trust.replace("\n", "<br>") if trust else "<em>No bonds formed.</em>"
    deception_html = deception.replace("\n", "<br>") if deception else "<em>No lies detected.</em>"
    traces_html = traces.replace("\n", "<br>") if traces else "<em>Waiting for minds…</em>"
    evolution_html = evolution.replace("\n", "<br>") if evolution else "<em>No words born yet.</em>"
    field_notes_html = field_notes.replace("\n", "<br>") if field_notes else "<em>Watching…</em>"
    drift_html = glyph_drift.replace("\n", "<br>") if glyph_drift else "<em>No drift yet.</em>"
    social_html = social_graph.replace("\n", "<br>") if social_graph else "<em>No signals yet.</em>"
    report_html = report.replace("\n", "<br>") if report else ""

    return (
        '<aside class="moku-side-panel" id="moku-side-panel">'
        '<div class="panel-header">Field Observatory</div>'
        '<div class="panel-subhead">Glyphs emerge in public. Minds and memories stay in the traces.</div>'
        f'{section("Glyph Transcript", transcript_html, open_default=True)}'
        f"{section('Language Evolution', evolution_html, open_default=True)}"
        f"{section('Glyph Drift', drift_html)}"
        f"{section('Social Graph', social_html)}"
        f"{section('Field Notes', field_notes_html)}"
        f"{section('Emergent Dictionary', dict_html)}"
        f"{section('Mind Traces', traces_html)}"
        f"{section('Trust Web', trust_html)}"
        f"{section('Deception Board', deception_html)}"
        f"{section('Creatures', creatures_html)}"
        + (section("Field Report", report_html) if report else "")
        + "</aside>"
    )


def render_sim_shell(world_html: str, watch_mode: str, playing: bool) -> str:
    mode_label = "Sandbox" if watch_mode == "sandbox" else "Wild run"
    play_label = "▶ LIVE" if playing else "⏸ PAUSED"
    return (
        '<div class="moku-sim-root">'
        '<span class="sim-corner sim-corner-tl" aria-hidden="true"></span>'
        '<span class="sim-corner sim-corner-tr" aria-hidden="true"></span>'
        '<span class="sim-corner sim-corner-bl" aria-hidden="true"></span>'
        '<span class="sim-corner sim-corner-br" aria-hidden="true"></span>'
        '<div class="sim-scanline" aria-hidden="true"></div>'
        '<div class="sim-hud-rail" aria-hidden="true">'
        '<span class="sim-rail-label">field observatory</span>'
        '<span class="sim-rail-track"><i></i><i></i><i></i></span>'
        "</div>"
        f'<div class="sim-mode-badge">{html.escape(mode_label)}</div>'
        f'<div class="sim-status sim-status-{"live" if playing else "paused"}">{html.escape(play_label)}</div>'
        f'<div class="sim-world-wrap">{world_html}</div>'
        "</div>"
    )
