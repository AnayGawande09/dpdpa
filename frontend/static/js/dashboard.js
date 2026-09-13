// Requires static/js/shared.js to be loaded first.

const SEVERITY_ORDER = { CRITICAL: 4, HIGH: 3, MEDIUM: 2, LOW: 1 };
const BAND_COLOR = { Low: "#10b981", Medium: "#eab308", High: "#f59e0b", Critical: "#ef4444" };
const LOW_RISK_THRESHOLD = 30; // matches risk_engine.py's Low band upper bound

function getScanIdFromUrl() {
  const params = new URLSearchParams(window.location.search);
  return params.get("scan_id");
}

function setScanIdInUrl(scanId) {
  const url = new URL(window.location.href);
  url.searchParams.set("scan_id", scanId);
  window.history.pushState({}, "", url);
}

async function fetchJson(path) {
  const res = await fetch(`${API_BASE}${path}`, { headers: authHeaders() });
  if (res.status === 401) {
    redirectToLoginOnAuthFailure();
    return null;
  }
  if (!res.ok) return null;
  return res.json();
}

let piiSummaryChart = null;
let piiSummaryData = [];

async function loadPiiSummary(scanId) {
  const data = await fetchJson(`/datasets/${scanId}/pii/summary`);
  piiSummaryData = data || [];
  const canvas = document.getElementById("pii-summary-chart");
  const emptyEl = document.getElementById("pii-summary-empty");

  const totalFields = piiSummaryData.reduce((sum, d) => sum + d.field_count, 0);
  document.getElementById("pii-total").textContent = totalFields;
  document.getElementById("pii-category-count").textContent = `across ${piiSummaryData.length} categories`;

  if (piiSummaryData.length === 0) {
    canvas.hidden = true;
    emptyEl.hidden = false;
    return;
  }
  canvas.hidden = false;
  emptyEl.hidden = true;

  if (piiSummaryChart) piiSummaryChart.destroy();
  piiSummaryChart = new Chart(canvas, {
    type: "bar",
    data: {
      labels: piiSummaryData.map((d) => d.category),
      datasets: [{ label: "Fields", data: piiSummaryData.map((d) => d.field_count), backgroundColor: "#2563eb", borderRadius: 3 }],
    },
    options: {
      responsive: true,
      plugins: { legend: { display: false } },
      scales: { y: { beginAtZero: true, ticks: { stepSize: 1 } } },
    },
  });
}

function renderGauge(score, band) {
  const gauge = document.getElementById("risk-gauge");
  const color = BAND_COLOR[band] || "#64748b";
  const pct = Math.max(0, Math.min(100, score));
  gauge.style.background = `conic-gradient(${color} ${pct * 3.6}deg, #e2e8f0 0deg)`;
  gauge.innerHTML = `<div style="background:#fff; width:46px; height:46px; border-radius:50%; display:flex; align-items:center; justify-content:center; font-size:15px; font-weight:700; color:${color};">${score}</div>`;
}

async function loadRisk(scanId) {
  const data = await fetchJson(`/datasets/${scanId}/risk`);
  const bandEl = document.getElementById("risk-band");
  const deltaEl = document.getElementById("risk-delta");
  const listEl = document.getElementById("risk-breakdown-list");
  const emptyEl = document.getElementById("risk-empty");

  if (!data) {
    document.getElementById("risk-gauge").textContent = "—";
    bandEl.textContent = "—";
    bandEl.className = "chip neutral";
    deltaEl.textContent = "";
    listEl.innerHTML = "";
    emptyEl.hidden = false;
    return null;
  }
  emptyEl.hidden = true;

  renderGauge(data.score, data.band);
  bandEl.textContent = data.band;
  bandEl.className = `chip ${data.band}`;
  const delta = data.score - LOW_RISK_THRESHOLD;
  deltaEl.textContent =
    delta > 0
      ? `+${delta} above the Low-risk threshold (≤${LOW_RISK_THRESHOLD})`
      : `${Math.abs(delta)} below the Low-risk threshold (≤${LOW_RISK_THRESHOLD})`;

  const maxAbs = Math.max(1, ...data.breakdown.map((b) => Math.abs(b.points_added)));
  listEl.innerHTML =
    `<div style="display:flex; justify-content:space-between; font-size:13px; font-weight:600; padding: 6px 0; border-bottom: 1px solid var(--border);">
      <span>Net score</span><span>${data.score} / 100</span>
    </div>` +
    data.breakdown
      .map((item) => {
        const positive = item.points_added >= 0;
        const widthPct = (Math.abs(item.points_added) / maxAbs) * 100;
        const barColor = positive ? "#2563eb" : "#78716c";
        return `
          <div style="padding: 8px 0; border-bottom: 1px solid var(--border-light);">
            <div style="display:flex; justify-content:space-between; font-size:12.5px; font-weight:600;">
              <span>${item.factor}</span><span>${item.points_added > 0 ? "+" : ""}${item.points_added} pts</span>
            </div>
            <div style="background:var(--border-light); border-radius:3px; height:6px; margin:4px 0;">
              <div style="background:${barColor}; width:${widthPct}%; height:100%; border-radius:3px;"></div>
            </div>
            <div style="font-size:11.5px; color:var(--on-surface-variant);">${item.reason}</div>
          </div>`;
      })
      .join("");

  return data;
}

let allRuleEvaluations = [];
let findingsByRuleId = {};
let currentFilter = "ALL";
let findingsSortAsc = false;

function renderFindingsTable() {
  const tbody = document.getElementById("findings-tbody");
  tbody.innerHTML = "";

  let rows = allRuleEvaluations;
  if (currentFilter !== "ALL") {
    rows = rows.filter((r) => r.outcome === currentFilter);
  }
  rows = [...rows].sort((a, b) => {
    const diff = (SEVERITY_ORDER[a.severity] || 0) - (SEVERITY_ORDER[b.severity] || 0);
    return findingsSortAsc ? diff : -diff;
  });

  rows.forEach((rule) => {
    const finding = findingsByRuleId[rule.rule_id];
    const outcomeChipClass = rule.outcome === "PASS" ? "PASS" : rule.outcome === "FAIL" ? "FAIL" : "UNKNOWN";
    const gapText =
      rule.outcome === "FAIL" && finding
        ? `${rule.requirement} <div style="margin-top:4px; color:var(--critical-text); font-size:12px;">Gap: ${finding.explanation}</div>`
        : rule.outcome === "PASS"
        ? `${rule.requirement} <div style="margin-top:4px; color:var(--pass-text); font-size:12px;">Satisfied by the declared processing context.</div>`
        : rule.requirement;

    const row = document.createElement("tr");
    row.innerHTML = `
      <td><span class="chip ${rule.severity}">${rule.severity}</span> <span class="chip ${outcomeChipClass}" style="margin-left:4px;">${rule.outcome}</span></td>
      <td class="mono">${rule.rule_id}</td>
      <td>${rule.category}</td>
      <td style="max-width: 320px;">${gapText}</td>
      <td style="max-width: 220px;">${rule.remediation}</td>
    `;
    tbody.appendChild(row);
  });
}

async function loadRulesAndFindings(scanId) {
  const [rules, findings] = await Promise.all([
    fetchJson(`/datasets/${scanId}/rules`),
    fetchJson(`/datasets/${scanId}/findings`),
  ]);
  allRuleEvaluations = rules || [];
  findingsByRuleId = {};
  (findings || []).forEach((f) => {
    findingsByRuleId[f.rule_id] = f;
  });

  const counts = { PASS: 0, FAIL: 0, UNKNOWN: 0 };
  allRuleEvaluations.forEach((r) => {
    if (counts[r.outcome] !== undefined) counts[r.outcome]++;
  });
  const total = allRuleEvaluations.length;
  document.getElementById("rules-total").textContent = total;
  document.getElementById("rules-pass-rate").textContent = total ? `${Math.round((counts.PASS / total) * 100)}% pass rate` : "—";
  document.getElementById("rules-pass-count").textContent = counts.PASS;
  document.getElementById("rules-fail-count").textContent = counts.FAIL;
  document.getElementById("rules-unknown-count").textContent = counts.UNKNOWN;

  const urgentCount = (findings || []).filter((f) => f.severity === "CRITICAL" || f.severity === "HIGH").length;
  document.getElementById("urgent-count").textContent = urgentCount;

  renderFindingsTable();
  return findings || [];
}

function updateAlertBanner(riskData, findings) {
  const banner = document.getElementById("alert-banner");
  const titleEl = document.getElementById("alert-title");
  const bodyEl = document.getElementById("alert-body");

  const riskIsHighOrCritical = riskData && (riskData.band === "High" || riskData.band === "Critical");
  const criticalFindings = (findings || []).filter((f) => f.severity === "CRITICAL");

  if (!riskIsHighOrCritical && criticalFindings.length === 0) {
    banner.hidden = true;
    return;
  }

  const topFinding =
    criticalFindings[0] ||
    [...(findings || [])].sort((a, b) => (SEVERITY_ORDER[b.severity] || 0) - (SEVERITY_ORDER[a.severity] || 0))[0];

  titleEl.textContent = riskIsHighOrCritical
    ? `Risk band: ${riskData.band} (score ${riskData.score}/100) — potential compliance gaps detected.`
    : "Critical finding detected — potential compliance gap.";
  bodyEl.textContent = topFinding
    ? `Top recommended action: ${topFinding.explanation}`
    : "Review the findings panel for details.";
  banner.hidden = false;

  // NOTE: this banner is display-only. Wiring it to a real email/Slack
  // webhook is a future integration point, not built in this phase.
}

async function loadScanHistory(page) {
  const data = await fetchJson(`/datasets?page=${page}&page_size=5`);
  const tbody = document.getElementById("history-tbody");
  tbody.innerHTML = "";
  if (!data) return;

  data.items.forEach((item) => {
    const row = document.createElement("tr");
    row.className = "clickable";
    row.innerHTML = `
      <td>${item.filename}</td>
      <td>${new Date(item.uploaded_at).toLocaleString()}</td>
      <td><span class="chip ${item.status === "scanned" ? "PASS" : "neutral"}">${item.status}</span></td>
      <td><span class="link-text" data-scan-id="${item.scan_id}">View →</span></td>
    `;
    tbody.appendChild(row);
  });

  tbody.querySelectorAll("[data-scan-id]").forEach((el) => {
    el.addEventListener("click", () => {
      const scanId = el.getAttribute("data-scan-id");
      setScanIdInUrl(scanId);
      loadDashboard(scanId);
    });
  });

  const totalPages = Math.max(1, Math.ceil(data.total / data.page_size));
  document.getElementById("history-page-label").textContent = `Page ${data.page} of ${totalPages}`;
  document.getElementById("history-prev").disabled = data.page <= 1;
  document.getElementById("history-next").disabled = data.page >= totalPages;

  document.getElementById("history-prev").onclick = () => loadScanHistory(data.page - 1);
  document.getElementById("history-next").onclick = () => loadScanHistory(data.page + 1);
}

async function downloadReport(scanId) {
  const statusEl = document.getElementById("report-status");
  const errorEl = document.getElementById("report-error");
  statusEl.hidden = true;
  errorEl.hidden = true;

  try {
    const genRes = await fetch(`${API_BASE}/datasets/${scanId}/report`, {
      method: "POST",
      headers: authHeaders(),
    });
    if (genRes.status === 401) return redirectToLoginOnAuthFailure();
    if (!genRes.ok) {
      errorEl.textContent = "Could not generate report.";
      errorEl.hidden = false;
      return;
    }

    const downloadRes = await fetch(`${API_BASE}/datasets/${scanId}/report`, { headers: authHeaders() });
    if (downloadRes.status === 401) return redirectToLoginOnAuthFailure();
    if (!downloadRes.ok) {
      errorEl.textContent = "Could not download report.";
      errorEl.hidden = false;
      return;
    }

    const blob = await downloadRes.blob();
    const url = URL.createObjectURL(blob);
    const a = document.createElement("a");
    a.href = url;
    a.download = `${scanId}.pdf`;
    document.body.appendChild(a);
    a.click();
    a.remove();
    URL.revokeObjectURL(url);

    statusEl.textContent = "Report downloaded.";
    statusEl.hidden = false;
  } catch (err) {
    errorEl.textContent = "Could not reach the server.";
    errorEl.hidden = false;
  }
}

const AUDIT_ACTION_LABEL = {
  login: "Login",
  upload: "Dataset uploaded",
  context_submitted: "Processing context submitted",
  scan_run: "Compliance scan run",
  report_exported: "Report exported",
};

async function loadAuditLog(scanId) {
  const data = await fetchJson(`/audit-log?scan_id=${scanId}&page_size=20`);
  const list = document.getElementById("audit-timeline");
  const emptyEl = document.getElementById("audit-empty");
  list.innerHTML = "";

  if (!data || data.items.length === 0) {
    emptyEl.hidden = false;
    return;
  }
  emptyEl.hidden = true;

  const items = [...data.items].sort((a, b) => new Date(a.occurred_at) - new Date(b.occurred_at));
  items.forEach((entry) => {
    const detailParts = Object.entries(entry.details || {}).map(([k, v]) => `${k}: ${v}`);
    const li = document.createElement("li");
    li.innerHTML = `
      <span class="t-time">${new Date(entry.occurred_at).toLocaleString()}</span>
      <div class="t-action">${AUDIT_ACTION_LABEL[entry.action] || entry.action}</div>
      ${detailParts.length ? `<div class="t-detail">${detailParts.join(" · ")}</div>` : ""}
    `;
    list.appendChild(li);
  });
}

async function loadDatasetHeader(scanId) {
  const dataset = await fetchJson(`/datasets/${scanId}`);
  if (!dataset) return;
  document.getElementById("dataset-title").textContent = `Scan Summary — ${dataset.filename}`;
  document.getElementById("scan-meta-line").innerHTML =
    `<span class="mono">${scanId}</span> &middot; ${dataset.row_count} rows &middot; ` +
    `${dataset.column_names.length} columns &middot; status: <span class="chip ${dataset.status === "scanned" ? "PASS" : "neutral"}">${dataset.status}</span>`;
}

let currentScanId = null;

async function runRescan() {
  if (!currentScanId) return;
  const btn = document.getElementById("rescan-button");
  btn.disabled = true;
  const originalText = btn.textContent;
  btn.textContent = "Scanning...";
  try {
    const res = await fetch(`${API_BASE}/datasets/${currentScanId}/scan`, { method: "POST", headers: authHeaders() });
    if (res.status === 401) return redirectToLoginOnAuthFailure();
    if (res.status !== 202) return;
    for (let attempt = 0; attempt < 60; attempt++) {
      await new Promise((r) => setTimeout(r, 1000));
      const dataset = await fetchJson(`/datasets/${currentScanId}`);
      if (dataset && dataset.status === "scanned") break;
    }
    await loadDashboard(currentScanId);
  } finally {
    btn.disabled = false;
    btn.textContent = originalText;
  }
}

async function loadDashboard(scanId) {
  document.getElementById("no-scan-message").hidden = !!scanId;
  document.getElementById("scan-header").hidden = !scanId;
  if (!scanId) return;
  currentScanId = scanId;

  document.getElementById("topbar-scan-id").textContent = scanId;
  await loadDatasetHeader(scanId);

  await loadPiiSummary(scanId);
  const riskData = await loadRisk(scanId);
  const findings = await loadRulesAndFindings(scanId);
  updateAlertBanner(riskData, findings);
  await loadAuditLog(scanId);

  document.getElementById("download-report-button").onclick = () => downloadReport(scanId);
  document.getElementById("rescan-button").onclick = () => runRescan();
}

document.addEventListener("DOMContentLoaded", () => {
  renderTopnavUser();

  document.querySelectorAll(".tab-btn").forEach((btn) => {
    btn.addEventListener("click", () => {
      document.querySelectorAll(".tab-btn").forEach((b) => b.classList.remove("active"));
      btn.classList.add("active");
      currentFilter = btn.getAttribute("data-filter");
      renderFindingsTable();
    });
  });

  document.querySelector('th[data-sort="severity"]').addEventListener("click", (e) => {
    findingsSortAsc = !findingsSortAsc;
    e.target.textContent = `Severity ${findingsSortAsc ? "▴" : "▾"}`;
    renderFindingsTable();
  });

  const scanId = getScanIdFromUrl();
  loadDashboard(scanId);
  loadScanHistory(1);
});
