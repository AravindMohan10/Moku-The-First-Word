"""Project homepage — orientation before entering the simulation."""

from __future__ import annotations

import html


def render_homepage(model_label: str, memory_label: str) -> str:
    model_label = html.escape(model_label)
    memory_label = html.escape(memory_label)
    return f"""
<section class="moku-home" id="moku-home">
  <div class="home-hero">
    <p class="home-eyebrow">Build Small Hackathon · Thousand Token Wood</p>
    <h1 class="home-title">Moku: The First Word</h1>
    <p class="home-deck">
      A live forest toy where six tiny creatures invent their own words, lie to each other,
      and sometimes become friends. You watch. The AI plays every mind. Every choice is logged.
    </p>
    <p class="home-hook">
      They cannot speak English. They only shout <strong>glyphs</strong>: short made-up sounds
      like <strong>brlu</strong> or <strong>lin</strong>. Each creature decides privately what
      those words mean.
    </p>
    <p class="home-meta">{model_label} · memory: {memory_label}</p>
  </div>

  <div class="home-glyph-explainer">
    <h2 class="home-section-title">What is a glyph?</h2>
    <p class="home-glyph-lead">
      A glyph is an invented word. Not English. It is the only public language in the forest.
    </p>
    <p class="home-glyph-lead">
      There is no official dictionary. When Lumo shouts <strong>brlu</strong>, Pika might think
      "food" while Oro thinks "run." That mismatch is the fun.
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
        <p class="home-glyph-caption">Open <strong>Details → Mind Traces</strong> to see private readings</p>
      </div>
    </div>
  </div>

  <div class="home-watch-box">
    <h2 class="home-section-title">Three things to watch for</h2>
    <ol class="home-watch-list">
      <li>
        <strong>Which glyph wins.</strong>
        One sound gets copied until the whole forest is saying it. That is language spreading.
      </li>
      <li>
        <strong>Deception.</strong>
        When food is scarce, creatures may use a friendly glyph in a scary moment.
        Check the Deception board in Details.
      </li>
      <li>
        <strong>Trust lines (sometimes).</strong>
        Turn on the <strong>Trust</strong> overlay. Faint lines appear when creatures
        signal, follow, or share food with someone by name. Bonds are not scripted;
        the model chooses them.
      </li>
    </ol>
  </div>

  <div class="home-honest-box">
    <h2 class="home-section-title">What we set up vs what the AI decides</h2>
    <div class="home-split">
      <div class="home-split-col">
        <p class="home-split-label">We set up (same in Sandbox every time)</p>
        <ul>
          <li>Forest map, six creatures, seed 42</li>
          <li>Timed events: food, scarcity, a stranger, danger, rain</li>
          <li>Rules: hunger, fear, movement, memory</li>
        </ul>
      </div>
      <div class="home-split-col home-split-em">
        <p class="home-split-label">The AI decides (different every run)</p>
        <ul>
          <li>Which glyphs get invented and copied</li>
          <li>Private meanings and drift over time</li>
          <li>Lies and mistrust under pressure</li>
          <li>Social bonds: who signals, follows, or shares food with whom</li>
        </ul>
      </div>
    </div>
    <p class="home-honest-foot">
      Same stage every Sandbox run. New story every time.
    </p>
  </div>

  <div class="home-start-box">
    <h2 class="home-section-title">How to start</h2>
    <ol class="home-path-steps">
      <li>
        <span class="home-step-num">1</span>
        <div>
          Tap <strong>Enter the forest</strong>, pick <strong>Sandbox</strong>, press
          <strong>▶ Play</strong>. Turn on <strong>Speech</strong> and <strong>Trust</strong>.
        </div>
      </li>
      <li>
        <span class="home-step-num">2</span>
        <div>
          Watch 10–15 turns. Look for a dominant glyph, a deception flag, and maybe a trust line.
        </div>
      </li>
      <li>
        <span class="home-step-num">3</span>
        <div>
          Press <strong>⏹ Stop</strong> for the epilogue. Press <strong>⬇ JSON</strong> to export proof.
        </div>
      </li>
    </ol>
  </div>

  <details class="home-screen-guide">
    <summary>Screen guide</summary>
    <ul class="home-look-list">
      <li><strong>Forest</strong>: the map. The glowing creature just acted.</li>
      <li><strong>Glyphs</strong>: invented words in speech bubbles.</li>
      <li><strong>Trust overlay</strong>: lines between creatures who signaled, followed, or shared food.</li>
      <li><strong>Details panel</strong>: mind traces, dictionary guesses, deception, trust scores.</li>
      <li><strong>JSON export</strong>: every model choice with latency and reasoning.</li>
    </ul>
  </details>
</section>
"""
