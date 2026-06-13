function setPanelOpen(open) {
  const panel = document.getElementById("moku-side-panel");
  if (!panel) return;
  panel.classList.toggle("open", open);
  sessionStorage.setItem("moku-panel-open", open ? "1" : "0");
}

function setGuideOpen(open) {
  const guide = document.getElementById("moku-guide-panel");
  if (!guide) return;
  guide.classList.toggle("open", open);
  sessionStorage.setItem("moku-guide-open", open ? "1" : "0");
}

function restorePanelState() {
  if (sessionStorage.getItem("moku-panel-open") === "1") {
    document.getElementById("moku-side-panel")?.classList.add("open");
  }
}

function restoreGuideState() {
  if (sessionStorage.getItem("moku-guide-open") === "1") {
    document.getElementById("moku-guide-panel")?.classList.add("open");
  }
}

document.addEventListener("click", (e) => {
  if (e.target.closest("#moku-guide-btn") || e.target.closest("#moku-guide-close")) {
    e.preventDefault();
    const guide = document.getElementById("moku-guide-panel");
    setGuideOpen(!guide?.classList.contains("open"));
    return;
  }
  if (e.target.closest(".moku-panel-btn") || e.target.closest("#moku-notes-btn")) {
    e.preventDefault();
    const panel = document.getElementById("moku-side-panel");
    setPanelOpen(!panel?.classList.contains("open"));
    return;
  }
  const panel = document.getElementById("moku-side-panel");
  if (panel?.classList.contains("open") && !e.target.closest(".moku-side-panel")) {
    if (e.target.closest(".sim-world-wrap") || e.target.closest(".world-scene")) {
      setPanelOpen(false);
    }
  }
});

document.addEventListener("keydown", (e) => {
  if (e.key !== "Escape") return;
  const guide = document.getElementById("moku-guide-panel");
  if (guide?.classList.contains("open")) {
    setGuideOpen(false);
    return;
  }
  setPanelOpen(false);
});

const panelObserver = new MutationObserver(() => {
  restorePanelState();
  restoreGuideState();
});
document.addEventListener("DOMContentLoaded", () => {
  const host = document.getElementById("moku-panel-host");
  if (host) panelObserver.observe(host, { childList: true, subtree: true });
  restorePanelState();
  restoreGuideState();
});
setInterval(() => {
  restorePanelState();
  restoreGuideState();
}, 400);
