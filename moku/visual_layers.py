"""Forest overlay toggles — each layer is independent."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class VisualLayers:
    show_trust: bool = False
    signal_mode: str = "none"  # none | turn
    badge_mode: str = "none"  # none | last
    speech_mode: str = "none"  # none | last
    show_speech_meaning: bool = False
    show_status_rings: bool = False
    show_spotlight: bool = True
    show_toast: bool = False
    show_turn_beat: bool = True


def layers_from_toggles(
    *,
    trust: bool = False,
    signals: bool = False,
    speech: bool = True,
    actions: bool = True,
    mood: bool = False,
    events: bool = False,
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
