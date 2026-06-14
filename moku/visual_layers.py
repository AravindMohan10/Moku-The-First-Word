"""Forest overlay toggles — each layer is independent."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class VisualLayers:
    show_trust: bool = True
    signal_mode: str = "turn"  # none | turn
    badge_mode: str = "last"  # none | last
    speech_mode: str = "last"  # none | last
    show_speech_meaning: bool = True
    show_status_rings: bool = True
    show_spotlight: bool = True
    show_toast: bool = True
    show_turn_beat: bool = True


def layers_from_toggles(
    *,
    trust: bool = True,
    signals: bool = True,
    speech: bool = True,
    actions: bool = True,
    mood: bool = True,
    events: bool = True,
) -> VisualLayers:
    """Build overlay state from UI checkboxes."""
    return VisualLayers(
        show_trust=trust,
        signal_mode="turn" if signals else "none",
        badge_mode="last" if actions else "none",
        speech_mode="last" if speech else "none",
        show_speech_meaning=speech,
        show_status_rings=mood,
        show_spotlight=True,
        show_toast=events,
    )


def overlay_css_classes(layers: VisualLayers) -> str:
    parts: list[str] = []
    if layers.show_trust:
        parts.append("ov-trust")
    if layers.signal_mode != "none":
        parts.append("ov-signals")
    if layers.speech_mode != "none":
        parts.append("ov-speech")
    if layers.badge_mode != "none":
        parts.append("ov-actions")
    if layers.show_status_rings:
        parts.append("ov-mood")
    if layers.show_toast:
        parts.append("ov-events")
    return " ".join(parts)
