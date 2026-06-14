from __future__ import annotations

import os
import warnings
from pathlib import Path
from typing import Any

import moku.env_loader  # noqa: F401 — load .env before other moku imports

# Gradio + pandas on Python 3.14 emit noisy third-party deprecation warnings each tick.
warnings.filterwarnings("ignore", category=DeprecationWarning, module=r"gradio.*")
warnings.filterwarnings("ignore", message=r".*no_silent_downcasting.*")
warnings.filterwarnings("ignore", message=r".*copy keyword is deprecated.*")
try:
    from pandas.errors import Pandas4Warning

    warnings.filterwarnings("ignore", category=Pandas4Warning)
except ImportError:
    pass

import gradio as gr

from moku.llm_client import provider_label, warmup_local_backend
from moku.memory import get_memory_store
from moku.render_home import render_homepage
from moku.visual_layers import VisualLayers, layers_from_toggles
from moku.render_world import (
    render_guide_panel,
    render_side_panel,
    render_sim_shell,
    render_story_section,
    render_world_scene,
)
from moku.sim_engine import (
    create_for_watch_mode,
    export_trace_json,
    render_creature_cards,
    render_deception,
    render_dictionary,
    render_field_notes,
    render_glyph_drift_panel,
    render_language_evolution,
    render_social_graph,
    render_traces,
    render_traces_panel,
    render_transcript,
    render_trust,
    step_world,
    generate_run_summary,
)

APP_ROOT = Path(__file__).parent
CSS_PATH = APP_ROOT / "moku" / "web" / "style.css"
JS_PATH = APP_ROOT / "moku" / "web" / "sim.js"
TRACE_DIR = APP_ROOT / "data" / "traces"


def _llm_timer_interval() -> float:
    return float(os.environ.get("MOKU_TICK_SECONDS", "2.5"))


def _play_btn_update(playing: bool) -> dict:
    return gr.update(
        value="⏹ Stop" if playing else "▶ Play",
        variant="primary" if playing else "secondary",
    )


def _panel_html(state: Any) -> str:
    return render_side_panel(
        transcript=render_transcript(state),
        dictionary=render_dictionary(state),
        trust=render_trust(state),
        deception=render_deception(state),
        creatures_html=render_creature_cards(state),
        traces=render_traces(state),
        evolution=render_language_evolution(state),
        field_notes=render_field_notes(state),
        glyph_drift=render_glyph_drift_panel(state),
        social_graph=render_social_graph(state),
    )


def _build_layers(
    trust: bool,
    signals: bool,
    speech: bool,
    actions: bool,
    mood: bool,
    events: bool,
) -> VisualLayers:
    return layers_from_toggles(
        trust=trust,
        signals=signals,
        speech=speech,
        actions=actions,
        mood=mood,
        events=events,
    )


def _effective_playing(state: Any, playing: bool) -> bool:
    """Prefer WorldState.playing — timer may read stale gr.State during slow handlers."""
    if hasattr(state, "playing"):
        return bool(state.playing)
    return playing


def _world_html(state: Any, playing: bool, layers: VisualLayers) -> str:
    active = _effective_playing(state, playing)
    return render_sim_shell(render_world_scene(state, layers), state.watch_mode, active)


def _live_views(
    state: Any,
    playing: bool,
    layers: VisualLayers,
) -> tuple[str, str, str]:
    """World + story + traces — updated every tick. Excludes side panel shell."""
    last_trace = state.trace_log[-1] if state.trace_log else None
    active = _effective_playing(state, playing)
    return (
        _world_html(state, playing, layers),
        render_story_section(state, last_trace, playing=active),
        render_traces_panel(state),
    )


def _views(
    state: Any,
    playing: bool,
    layers: VisualLayers,
) -> tuple[str, str, str, str]:
    last_trace = state.trace_log[-1] if state.trace_log else None
    active = _effective_playing(state, playing)
    return (
        _world_html(state, playing, layers),
        render_story_section(state, last_trace, playing=active),
        _panel_html(state),
        render_traces_panel(state),
    )


def _reset(
    watch_mode: str,
    trust: bool,
    signals: bool,
    speech: bool,
    actions: bool,
    mood: bool,
    events: bool,
) -> tuple[Any, bool, str, str, str, str, int, dict]:
    state = create_for_watch_mode(watch_mode)
    state.playing = True
    layers = _build_layers(trust, signals, speech, actions, mood, events)
    world, story, panel, traces = _views(state, True, layers)
    _write_trace_file(state)
    return state, True, world, story, panel, traces, 0, _play_btn_update(True)


def _switch_mode(
    watch_mode: str,
    trust: bool,
    signals: bool,
    speech: bool,
    actions: bool,
    mood: bool,
    events: bool,
) -> tuple[Any, bool, str, str, str, str, int, dict]:
    return _reset(watch_mode, trust, signals, speech, actions, mood, events)


def _control_hint(mode: str) -> str:
    if mode == "sandbox":
        return (
            '<p class="moku-control-hint moku-hint-sandbox">'
            "<strong>Sandbox</strong> — curated beats for demos. "
            "Forest Chronicle updates each turn; Mind Traces hold exact reasoning."
            "</p>"
        )
    return (
        '<p class="moku-control-hint moku-hint-emergence">'
        "<strong>Wild run</strong> — random world, no scheduled beats. "
        "Watch glyphs, chronicle, and traces diverge."
        "</p>"
    )


def _sandbox_controls_visible(mode: str) -> tuple[dict, str]:
    return (
        gr.update(visible=mode == "sandbox"),
        _control_hint(mode),
    )


def _write_trace_file(state: Any) -> str | None:
    if not state.trace_log:
        return None
    payload = export_trace_json(state)
    TRACE_DIR.mkdir(parents=True, exist_ok=True)
    path = TRACE_DIR / f"{state.world_id}-t{state.turn}.json"
    path.write_text(payload, encoding="utf-8")
    return str(path)


def _page_layout(page: str) -> tuple[dict, dict]:
    on_home = page == "home"
    return gr.update(visible=on_home), gr.update(visible=not on_home)


def build_app() -> gr.Blocks:
    initial_mode = "sandbox"
    initial_page = "home"
    initial_state = create_for_watch_mode(initial_mode)
    memory_label = get_memory_store().backend_label
    model_label = provider_label()
    initial_layers = layers_from_toggles(
        trust=True,
        signals=True,
        speech=True,
        actions=True,
        mood=True,
        events=True,
    )
    world0, story0, panel0, traces0 = _views(initial_state, True, initial_layers)
    home0 = render_homepage(model_label, memory_label)
    js_inline = JS_PATH.read_text(encoding="utf-8") if JS_PATH.exists() else ""
    css = CSS_PATH.read_text(encoding="utf-8") if CSS_PATH.exists() else ""

    with gr.Blocks(
        title="Moku: The First Word",
        fill_height=True,
        elem_classes=["moku-root"],
        css=css,
        theme=gr.themes.Base(
            font=gr.themes.GoogleFont("Source Serif 4"),
            font_mono=gr.themes.GoogleFont("IBM Plex Mono"),
        ),
    ) as demo:
        gr.HTML(f"<script>{js_inline}</script>", container=False)
        gr.HTML(render_guide_panel(), elem_id="moku-guide-host", container=False)

        with gr.Column(elem_classes=["moku-layout"]):
            gr.HTML(
                f"""
                <header class="moku-topbar">
                  <div class="moku-brand">Moku: The First Word</div>
                  <div class="moku-subbrand">{model_label} · memory: {memory_label}</div>
                </header>
                """,
                container=False,
            )

            with gr.Row(elem_classes=["moku-nav-row"]):
                page = gr.Radio(
                    choices=[("Home", "home"), ("Watch Forest", "sim")],
                    value=initial_page,
                    label="",
                    elem_id="moku-page-nav",
                )

            with gr.Column(visible=True, elem_classes=["moku-home-col"]) as home_col:
                home_view = gr.HTML(value=home0, elem_classes=["moku-home-wrap"], container=False)
                enter_btn = gr.Button("Enter the forest →", elem_classes=["home-enter-btn"])

            with gr.Column(visible=False, elem_classes=["moku-sim-col"]) as sim_col:
                with gr.Row(elem_classes=["moku-mode-row"]):
                    watch_mode = gr.Radio(
                        choices=[("Sandbox", "sandbox"), ("Wild run", "emergence")],
                        value=initial_mode,
                        label="",
                        elem_id="moku-watch-mode",
                    )

                with gr.Row(elem_classes=["moku-overlay-row"]):
                    ov_speech = gr.Checkbox(label="Speech", value=True, elem_id="ov-speech")
                    ov_signals = gr.Checkbox(label="Signals", value=True, elem_id="ov-signals")
                    ov_trust = gr.Checkbox(label="Trust", value=True, elem_id="ov-trust")
                    ov_actions = gr.Checkbox(label="Actions", value=True, elem_id="ov-actions")
                    ov_mood = gr.Checkbox(label="Mood", value=True, elem_id="ov-mood")
                    ov_events = gr.Checkbox(label="Events", value=True, elem_id="ov-events")

                overlay_inputs = [
                    ov_trust,
                    ov_signals,
                    ov_speech,
                    ov_actions,
                    ov_mood,
                    ov_events,
                ]

                with gr.Row(elem_classes=["moku-controls-row"]):
                    play_btn = gr.Button("⏹ Stop", variant="primary", size="sm")
                    guide_btn = gr.Button("? Guide", size="sm", elem_id="moku-guide-btn")
                    obs_btn = gr.Button("☰ Details", size="sm", elem_id="moku-notes-btn")
                    trace_btn = gr.Button("⬇ JSON", size="sm")
                control_hint = gr.HTML(_control_hint(initial_mode), container=False)

                sim_view = gr.HTML(value=world0, elem_classes=["moku-sim-viewport"], container=False)
                story_view = gr.HTML(value=story0, elem_classes=["moku-story-wrap"], container=False)
                traces_view = gr.HTML(value=traces0, elem_classes=["moku-traces-wrap"], container=False)

        panel_view = gr.HTML(value=panel0, elem_id="moku-panel-host", container=False)
        trace_download = gr.DownloadButton("⬇ traces.json", visible=False, size="sm")

        state = gr.State(initial_state)
        playing = gr.State(True)
        tick_count = gr.State(0)

        timer = gr.Timer(value=_llm_timer_interval(), active=True)

        sim_outputs = [sim_view, story_view, panel_view, traces_view]
        sim_live_outputs = [sim_view, story_view, traces_view]
        tick_outputs = [
            state,
            *sim_live_outputs,
            tick_count,
            playing,
            play_btn,
        ]
        def refresh_sim_views(
            s: Any,
            p: bool,
            trust: bool,
            signals: bool,
            speech: bool,
            actions: bool,
            mood: bool,
            events: bool,
        ) -> tuple[str, str, str, str]:
            layers = _build_layers(trust, signals, speech, actions, mood, events)
            return _views(s, p, layers)

        def on_page_change(
            pg: str,
            s: Any,
            p: bool,
            trust: bool,
            signals: bool,
            speech: bool,
            actions: bool,
            mood: bool,
            events: bool,
        ) -> tuple[dict, dict, str, str, str, str, str]:
            home_up, sim_up = _page_layout(pg)
            layers = _build_layers(trust, signals, speech, actions, mood, events)
            w, st, pn, tr = _views(s, p if pg == "sim" else False, layers)
            return home_up, sim_up, pg, w, st, pn, tr

        def go_to_sim(
            s: Any,
            p: bool,
            trust: bool,
            signals: bool,
            speech: bool,
            actions: bool,
            mood: bool,
            events: bool,
        ) -> tuple[dict, dict, str, str, str, str, str]:
            home_up, sim_up = _page_layout("sim")
            layers = _build_layers(trust, signals, speech, actions, mood, events)
            w, st, pn, tr = _views(s, p, layers)
            return home_up, sim_up, "sim", w, st, pn, tr

        def on_timer_tick(
            s: Any,
            p: bool,
            mode: str,
            tc: int,
            pg: str,
            trust: bool,
            signals: bool,
            speech: bool,
            actions: bool,
            mood: bool,
            events: bool,
        ) -> tuple[Any, str, str, str, int, bool, dict]:
            p = _effective_playing(s, p)
            layers = _build_layers(trust, signals, speech, actions, mood, events)
            btn = _play_btn_update(p)
            world, story, traces = _live_views(s, p, layers)
            if pg != "sim" or not p:
                _write_trace_file(s)
                return s, world, story, traces, tc, p, btn
            tc += 1
            if mode == "emergence" and tc % 2 != 0:
                _write_trace_file(s)
                return s, world, story, traces, tc, p, btn
            s = step_world(s)
            world, story, traces = _live_views(s, p, layers)
            _write_trace_file(s)
            return s, world, story, traces, tc, p, btn

        def toggle_play_pause(
            p: bool,
            s: Any,
            trust: bool,
            signals: bool,
            speech: bool,
            actions: bool,
            mood: bool,
            events: bool,
        ) -> tuple[bool, dict, Any, str, str, str, str]:
            new_playing = not _effective_playing(s, p)
            s.playing = new_playing
            if new_playing:
                s.run_summary = None
            layers = _build_layers(trust, signals, speech, actions, mood, events)
            w, st, pn, tr = _views(s, new_playing, layers)
            return new_playing, _play_btn_update(new_playing), s, w, st, pn, tr

        def toggle_play_epilogue(
            s: Any,
            trust: bool,
            signals: bool,
            speech: bool,
            actions: bool,
            mood: bool,
            events: bool,
        ) -> tuple[Any, str, str, str, str]:
            if not s.playing and s.run_summary is None and s.turn >= 1:
                s = generate_run_summary(s)
            layers = _build_layers(trust, signals, speech, actions, mood, events)
            w, st, pn, tr = _views(s, s.playing, layers)
            return s, w, st, pn, tr

        def refresh_panel_view(
            s: Any,
            trust: bool,
            signals: bool,
            speech: bool,
            actions: bool,
            mood: bool,
            events: bool,
        ) -> str:
            layers = _build_layers(trust, signals, speech, actions, mood, events)
            return _panel_html(s)

        def export_traces(s: Any) -> dict:
            path = _write_trace_file(s)
            if not path:
                return gr.update(visible=False)
            return gr.update(value=path, visible=True)

        timer.tick(
            on_timer_tick,
            inputs=[state, playing, watch_mode, tick_count, page, *overlay_inputs],
            outputs=tick_outputs,
        )

        page.change(
            on_page_change,
            inputs=[page, state, playing, *overlay_inputs],
            outputs=[home_col, sim_col, page, *sim_outputs],
        )

        enter_btn.click(
            go_to_sim,
            inputs=[state, playing, *overlay_inputs],
            outputs=[home_col, sim_col, page, *sim_outputs],
        )

        for ov in overlay_inputs:
            ov.change(
                refresh_sim_views,
                inputs=[state, playing, *overlay_inputs],
                outputs=sim_outputs,
            )

        watch_mode.change(
            _switch_mode,
            inputs=[watch_mode, *overlay_inputs],
            outputs=[
                state,
                playing,
                *sim_outputs,
                tick_count,
                play_btn,
            ],
        ).then(
            _sandbox_controls_visible,
            inputs=[watch_mode],
            outputs=[obs_btn, control_hint],
        ).then(
            fn=None,
            js="() => { document.getElementById('moku-side-panel')?.classList.remove('open'); sessionStorage.setItem('moku-panel-open', '0'); }",
        )
        trace_btn.click(
            export_traces,
            inputs=[state],
            outputs=[trace_download],
        )

        play_btn.click(
            toggle_play_pause,
            inputs=[playing, state, *overlay_inputs],
            outputs=[playing, play_btn, state, *sim_outputs],
        ).then(
            toggle_play_epilogue,
            inputs=[state, *overlay_inputs],
            outputs=[state, *sim_outputs],
        )
        obs_btn.click(
            refresh_panel_view,
            inputs=[state, *overlay_inputs],
            outputs=[panel_view],
        ).then(
            fn=None,
            js="""() => {
              const panel = document.getElementById('moku-side-panel');
              if (!panel) return;
              const open = !panel.classList.contains('open');
              panel.classList.toggle('open', open);
              sessionStorage.setItem('moku-panel-open', open ? '1' : '0');
            }""",
        )
        guide_btn.click(
            fn=None,
            js="() => { const g = document.getElementById('moku-guide-panel'); if (g) { g.classList.toggle('open'); sessionStorage.setItem('moku-guide-open', g.classList.contains('open') ? '1' : '0'); } }",
        )

    return demo


if __name__ == "__main__":
    warmup_local_backend()
    app = build_app()
    port_env = os.environ.get("GRADIO_SERVER_PORT")
    host_env = os.environ.get("GRADIO_SERVER_NAME", "127.0.0.1")
    launch_kwargs: dict[str, Any] = {
        "server_name": host_env,
        "show_error": True,
        # HF Spaces enable Gradio SSR by default; it 404s on Consolas/system font woff2 paths.
        "ssr_mode": False,
    }
    if port_env:
        launch_kwargs["server_port"] = int(port_env)
    app.launch(**launch_kwargs)
