"""Project homepage — orientation before entering the simulation."""

from __future__ import annotations

import html


def render_homepage(model_label: str, memory_label: str) -> str:
    model_label = html.escape(model_label)
    memory_label = html.escape(memory_label)
    return f"""
<section class="moku-home" id="moku-home">
  <div class="home-hero">
    <p class="home-eyebrow">Thousand Token Wood · Build Small Hackathon</p>
    <h1 class="home-title">Moku: The First Word</h1>
    <p class="home-deck">
      Partial emergence in a live forest sim — glyphs, trust, bonds, and betrayal.
      Scripted map. Unscripted language and social life. Every LLM choice logged.
    </p>
    <p class="home-hook">
      Six creatures cannot speak English — only <strong>glyphs</strong>, invented sounds
      they shout into the air. A real 3B LLM plus memory picks each word and each move.
    </p>
    <p class="home-hook">
      Who shares food, who follows a signal, who distrusts whom — none of that is written
      in advance. Mind Traces and JSON export are the proof; chronicle prose is garnish.
    </p>
    <p class="home-meta">{model_label} · memory: {memory_label}</p>
  </div>

  <div class="home-glyph-explainer">
    <h2 class="home-section-title">What is a glyph?</h2>
    <p class="home-glyph-lead">
      A glyph is a made-up word — like <strong>brlu</strong>. Not English.
      It is the only way creatures can talk.
    </p>
    <p class="home-glyph-lead">
      There is no fixed dictionary. Each creature privately decides what a glyph means.
      It learns from what happened when it last heard that sound.
    </p>
    <div class="home-glyph-demo">
      <div class="home-glyph-example">
        <p class="home-glyph-example-label">Everyone hears</p>
        <p class="home-glyph-word">brlu</p>
        <p class="home-glyph-caption">Speech bubble above the creature</p>
      </div>
      <div class="home-glyph-arrow" aria-hidden="true">→</div>
      <div class="home-glyph-example home-glyph-private">
        <p class="home-glyph-example-label">Each mind decides alone</p>
        <ul class="home-glyph-readings">
          <li>Lumo reads <strong>brlu</strong> as <em>food nearby</em></li>
          <li>Pika reads <strong>brlu</strong> as <em>come closer</em></li>
        </ul>
        <p class="home-glyph-caption">Shown in <strong>Mind Traces</strong> — the raw LLM reasoning log</p>
      </div>
    </div>
  </div>

  <div class="home-watch-box">
    <h2 class="home-section-title">Before you press Play — three things to watch for</h2>
    <ol class="home-watch-list">
      <li>
        <strong>Same glyph, different minds.</strong>
        Open Mind Traces. Pick any glyph — try <strong>niliso</strong>.
        Oro reads it as safety. Vey reads it as fear.
        That gap is the experiment.
      </li>
      <li>
        <strong>Which glyph wins.</strong>
        One sound will start appearing everywhere. Not scripted.
        The model reuses what it hears — like a meme in the forest.
      </li>
      <li>
        <strong>JSON export.</strong>
        Every LLM call is logged with latency, memory, and reasoning.
        The chronicle prose is garnish. The JSON is proof.
      </li>
    </ol>
  </div>

  <div class="home-honest-box">
    <h2 class="home-section-title">What&apos;s scripted vs what&apos;s not</h2>
    <div class="home-split">
      <div class="home-split-col">
        <p class="home-split-label">Scripted — same every sandbox run</p>
        <ul>
          <li>Forest layout, six creatures, seed 42</li>
          <li>World events: food T2 · scarcity T5 · stranger T8 · danger T11 · rain T14</li>
          <li>Mechanics: hunger, proximity, trust scores</li>
        </ul>
      </div>
      <div class="home-split-col home-split-em">
        <p class="home-split-label">Not scripted — emergence</p>
        <ul>
          <li>Which glyphs get invented, echoed, or overloaded</li>
          <li>Actions: signal, share food, gather, move — and toward whom</li>
          <li>Private translations: same glyph, diverging beliefs across minds</li>
          <li>Social bonds: who shares, who follows, who ignores a signal</li>
          <li>Trust shifts — the model raises or lowers trust each turn</li>
          <li>Deception flags when a glyph is used against its usual context</li>
        </ul>
      </div>
    </div>
    <p class="home-honest-foot">
      Same map every run. Different language every time.
    </p>
  </div>

  <div class="home-why-box">
    <h2 class="home-section-title">Why it&apos;s interesting — the emergence angle</h2>
    <p class="home-why-lead">
      We script the forest pressure. Language and social life grow on their own.
    </p>
    <ul class="home-why-list">
      <li>
        <strong>Language without a dictionary.</strong>
        No one assigns meanings. Sounds spread because the model reuses what it hears.
      </li>
      <li>
        <strong>Social bonds, unscripted.</strong>
        Who shares food, who signals whom, who follows — chosen each turn by the LLM.
        Turn on the <strong>Trust</strong> overlay to see scores shift.
      </li>
      <li>
        <strong>Miscommunication and mistrust.</strong>
        Same glyph, different private readings. Trust can fall as easily as it rises.
        The Deception board flags glyphs used in the wrong place.
      </li>
      <li>
        <strong>Same stage, new story every run.</strong>
        Seed 42 gives the same map and beats. Alliances and dialects do not repeat.
      </li>
      <li>
        <strong>Auditable, not magic.</strong>
        Every move has a Mind Trace. Export JSON to verify any claim.
      </li>
    </ul>
  </div>

  <div class="home-start-box">
    <h2 class="home-section-title">How to start</h2>
    <ol class="home-path-steps">
      <li>
        <span class="home-step-num">1</span>
        <div>
          <strong>Watch Forest</strong> → <strong>Sandbox</strong> → <strong>▶ Play</strong>.
          Turn on <strong>Speech</strong> so glyphs appear above creatures.
        </div>
      </li>
      <li>
        <span class="home-step-num">2</span>
        <div>
          Let 10–14 turns unfold. Watch which glyph starts winning.
        </div>
      </li>
      <li>
        <span class="home-step-num">3</span>
        <div>
          Press <strong>⏹ Stop</strong> for the epilogue.
          Press <strong>⬇ JSON</strong> for the full trace.
        </div>
      </li>
    </ol>
  </div>

  <details class="home-screen-guide">
    <summary>Screen guide</summary>
    <ul class="home-look-list">
      <li><strong>Forest</strong> — the map. The glowing creature just thought.</li>
      <li><strong>Glyphs</strong> — invented words in speech bubbles.</li>
      <li><strong>Turn beat</strong> — one-line summary of the last action.</li>
      <li><strong>Chronicle</strong> — AI headline while the run is playing.</li>
      <li><strong>Epilogue</strong> — short run summary when you press Stop.</li>
      <li><strong>Mind Traces</strong> — raw LLM reasoning. Primary evidence.</li>
    </ul>
  </details>
</section>
"""
