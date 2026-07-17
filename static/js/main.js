"use strict";

// ── Apply saved theme immediately ─────────────────────────────────────────────
(function () {
  const theme = getCookie("theme") || "dark";
  if (theme === "light") document.body.classList.add("theme-light");
})();

function getCookie(name) {
  const m = document.cookie.match(new RegExp("(?:^|; )" + name + "=([^;]*)"));
  return m ? decodeURIComponent(m[1]) : null;
}

// ── Theme toggle ─────────────────────────────────────────────────────────────
window.toggleTheme = function () {
  const isLight = document.body.classList.toggle("theme-light");
  const theme = isLight ? "light" : "dark";
  // Post to server to set cookie
  const form = document.createElement("form");
  form.method = "POST";
  form.action = "/set-theme";
  const f = document.createElement("input");
  f.name = "theme"; f.value = theme;
  form.appendChild(f);
  document.body.appendChild(form);
  form.submit();
};

// ── Language switch ──────────────────────────────────────────────────────────
window.switchLang = function (lang) {
  const form = document.createElement("form");
  form.method = "POST";
  form.action = "/set-lang";
  const f = document.createElement("input");
  f.name = "lang"; f.value = lang;
  form.appendChild(f);
  document.body.appendChild(form);
  form.submit();
};

// ── Table filter ─────────────────────────────────────────────────────────────
window.filterTable = function (inputId, tableId) {
  const q = (document.getElementById(inputId)?.value || "").toLowerCase();
  document.querySelectorAll(`#${tableId} tbody tr`).forEach(row => {
    row.style.display = row.textContent.toLowerCase().includes(q) ? "" : "none";
  });
};

// ── Dashboard stats refresh ──────────────────────────────────────────────────
window.refreshStats = async function () {
  try {
    const r = await fetch("/api/stats");
    if (!r.ok) return;
    const d = await r.json();
    const map = {
      "stat-total": d.total, "stat-online": d.online,
      "stat-offline": d.offline, "stat-unknown": d.unknown,
      "stat-success24": d.success_24h, "stat-failed24": d.failed_24h,
    };
    Object.entries(map).forEach(([id, v]) => {
      const el = document.getElementById(id);
      if (el) el.textContent = v;
    });
  } catch (e) { console.warn("Stats refresh failed:", e); }
};

// ── LDAP test connection ──────────────────────────────────────────────────────
window.testLdap = async function () {
  const btn = document.getElementById("ldap-test-btn");
  const res = document.getElementById("ldap-result");
  if (!btn || !res) return;
  btn.disabled = true;
  btn.textContent = "testing…";
  try {
    const r = await fetch("/settings/ldap/test", { method: "POST" });
    const d = await r.json();
    res.style.display = "block";
    res.className = "ldap-result " + (d.ok ? "ok" : "err");
    res.textContent = d.message;
  } catch (e) {
    res.style.display = "block";
    res.className = "ldap-result err";
    res.textContent = "Connection error";
  } finally {
    btn.disabled = false;
    btn.textContent = "test connection";
  }
};

// ── Mobile sidebar toggle ─────────────────────────────────────────────────────
window.toggleSidebar = function () {
  const sidebar = document.querySelector(".sidebar");
  const overlay = document.querySelector(".sidebar-overlay");
  if (!sidebar) return;
  sidebar.classList.toggle("open");
  if (overlay) overlay.classList.toggle("visible");
};

window.closeSidebar = function () {
  document.querySelector(".sidebar")?.classList.remove("open");
  document.querySelector(".sidebar-overlay")?.classList.remove("visible");
};

// Close sidebar on nav link click (mobile)
document.querySelectorAll(".nav-link").forEach(link => {
  link.addEventListener("click", closeSidebar);
});

// ── Confirm helper ────────────────────────────────────────────────────────────
document.addEventListener("submit", e => {
  const msg = e.target.dataset.confirm;
  if (msg && !confirm(msg)) e.preventDefault();
});

// ── Auto-refresh dashboard every 30s ─────────────────────────────────────────
if (document.getElementById("stat-total")) {
  setInterval(refreshStats, 30000);
}
