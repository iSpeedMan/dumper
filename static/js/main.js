/**
 * Dumper — Main JavaScript
 * Minimal vanilla JS: no framework dependencies.
 */

"use strict";

// ── Auto-dismiss flash messages ──────────────────────────────────────────────
document.addEventListener("DOMContentLoaded", () => {
  const flashes = document.querySelectorAll(".flash-message");
  flashes.forEach((el) => {
    setTimeout(() => {
      el.style.opacity = "0";
      el.style.transition = "opacity 0.5s";
      setTimeout(() => el.remove(), 500);
    }, 4000);
  });
});

// ── Confirm delete buttons (fallback if onsubmit attr not present) ────────────
document.addEventListener("submit", (e) => {
  const form = e.target;
  const msg = form.dataset.confirm;
  if (msg && !confirm(msg)) {
    e.preventDefault();
  }
});

// ── Table filter (used on inventory page) ─────────────────────────────────────
window.filterTable = function (inputId = "search-input", tableId = "devices-table") {
  const q = document.getElementById(inputId)?.value?.toLowerCase() ?? "";
  const rows = document.querySelectorAll(`#${tableId} tbody tr`);
  rows.forEach((row) => {
    row.style.display = row.textContent.toLowerCase().includes(q) ? "" : "none";
  });
};

// ── Stats refresh (used on dashboard) ─────────────────────────────────────────
window.refreshStats = async function () {
  try {
    const r = await fetch("/api/stats");
    if (!r.ok) return;
    const d = await r.json();
    const map = {
      "stat-total":    d.total,
      "stat-online":   d.online,
      "stat-offline":  d.offline,
      "stat-unknown":  d.unknown,
      "stat-success24": d.success_24h,
      "stat-failed24":  d.failed_24h,
    };
    Object.entries(map).forEach(([id, val]) => {
      const el = document.getElementById(id);
      if (el) el.textContent = val;
    });
  } catch (e) {
    console.warn("Stats refresh failed:", e);
  }
};

// ── Tooltip on truncated elements ─────────────────────────────────────────────
document.addEventListener("DOMContentLoaded", () => {
  document.querySelectorAll("[title]").forEach((el) => {
    if (!el.title) return;
    el.style.cursor = "help";
  });
});
