const API_BASE = "http://localhost:8000";
const SEVERITY_ORDER = { CRITICAL: 4, HIGH: 3, MEDIUM: 2, LOW: 1 };

function getToken() {
  return localStorage.getItem("dpdp_token");
}

function authHeaders() {
  return { Authorization: `Bearer ${getToken()}` };
}

function getScanIdFromUrl() {
  const params = new URLSearchParams(window.location.search);
  return params.get("scan_id");
}

function setScanIdInUrl(scanId) {
  const url = new URL(window.location.href);
  url.searchParams.set("scan_id", scanId);
  window.history.pushState({}, "", url);
}

function redirectToLoginOnAuthFailure() {
  localStorage.removeItem("dpdp_token");
  window.location.href = "index.html";
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
let riskBreakdownChart = null;

async function loadPiiSummary(scanId) {
  const data = await fetchJson(`/datasets/${scanId}/pii/summary`);
  const canvas = document.getElementById("pii-summary-chart");
  const emptyEl = document.getElementById("pii-summary-empty");

  if (!data || data.length === 0) {
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
      labels: data.map((d) => d.category),
      datasets: [{ label: "Fields", data: data.map((d) => d.field_count), backgroundColor: "#2454ff" }],
    },
    options: {
      responsive: true,
      plugins: { legend: { display: false } },
      scales: { y: { beginAtZero: true, ticks: { stepSize: 1 } } },
    },
  });
}

async function loadRisk(scanId) {
  const data = await fetchJson(`/datasets/${scanId}/risk`);
  const scoreEl = document.getElementById("risk-score");
  const bandEl = document.getElementById("risk-band");
  const canvas = document.getElementById("risk-breakdown-chart");
  const emptyEl = document.getElementById("risk-empty");

  if (!data) {
    scoreEl.textContent = "—";
    bandEl.textContent = "";
    bandEl.className = "badge";
    canvas.hidden = true;
    emptyEl.hidden = false;
    return null;
  }
  canvas.hidden = false;
  emptyEl.hidden = true;

  scoreEl.textContent = data.score;
  bandEl.textContent = data.band;
  bandEl.className = `badge ${data.band}`;

  if (riskBreakdownChart) riskBreakdownChart.destroy();
  riskBreakdownChart = new Chart(canvas, {
    type: "bar",
    data: {
      labels: data.breakdown.map((b) => b.factor),
      datasets: [{ label: "Points", data: data.breakdown.map((b) => b.points_added), backgroundColor: "#8a6d00" }],
    },
    options: {
      indexAxis: "y",
      responsive: true,
      plugins: { legend: { display: false } },
    },
  });

  return data;
}

async function loadRules(scanId) {
  const data = await fetchJson(`/datasets/${scanId}/rules`);
  const counts = { PASS: 0, FAIL: 0, UNKNOWN: 0 };
  (data || []).forEach((r) => {
    if (counts[r.outcome] !== undefined) counts[r.outcome]++;
  });
  document.getElementById("rules-pass-count").textContent = counts.PASS;
  document.getElementById("rules-fail-count").textContent = counts.FAIL;
  document.getElementById("rules-unknown-count").textContent = counts.UNKNOWN;
}

let currentFindings = [];
let findingsSortAsc = false;

function renderFindings() {
  const tbody = document.getElementById("findings-tbody");
  tbody.innerHTML = "";

  const sorted = [...currentFindings].sort((a, b) => {
    const diff = (SEVERITY_ORDER[a.severity] || 0) - (SEVERITY_ORDER[b.severity] || 0);
    return findingsSortAsc ? diff : -diff;
  });

  sorted.forEach((finding, idx) => {
    const row = document.createElement("tr");
    row.className = "finding-row";
    row.innerHTML = `
      <td><span class="severity-badge ${finding.severity}">${finding.severity}</span></td>
      <td>${finding.category}</td>
      <td>${finding.rule_id}</td>
    `;
    const detailRow = document.createElement("tr");
    detailRow.className = "finding-detail";
    detailRow.innerHTML = `
      <td colspan="3">
        <strong>Rule:</strong> ${finding.rule_id}<br/>
        <strong>Evidence field:</strong> ${finding.evidence}<br/>
        <strong>Affected fields:</strong> ${finding.affected_fields.join(", ") || "—"}<br/>
        <strong>Explanation:</strong> ${finding.explanation}
      </td>
    `;
    row.addEventListener("click", () => detailRow.classList.toggle("open"));
    tbody.appendChild(row);
    tbody.appendChild(detailRow);
  });
}

async function loadFindings(scanId) {
  const data = await fetchJson(`/datasets/${scanId}/findings`);
  currentFindings = data || [];
  const table = document.getElementById("findings-table");
  const emptyEl = document.getElementById("findings-empty");

  if (currentFindings.length === 0) {
    table.hidden = true;
    emptyEl.hidden = false;
    return;
  }
  table.hidden = false;
  emptyEl.hidden = true;
  renderFindings();
  return currentFindings;
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
    row.innerHTML = `
      <td>${item.filename}</td>
      <td>${new Date(item.uploaded_at).toLocaleString()}</td>
      <td>${item.status}</td>
      <td><span class="scan-link" data-scan-id="${item.scan_id}">View</span></td>
    `;
    tbody.appendChild(row);
  });

  tbody.querySelectorAll(".scan-link").forEach((el) => {
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

async function loadAuditLog(scanId) {
  const data = await fetchJson(`/audit-log?scan_id=${scanId}&page_size=20`);
  const tbody = document.getElementById("audit-tbody");
  const emptyEl = document.getElementById("audit-empty");
  tbody.innerHTML = "";

  if (!data || data.items.length === 0) {
    emptyEl.hidden = false;
    return;
  }
  emptyEl.hidden = true;

  data.items.forEach((entry) => {
    const row = document.createElement("tr");
    row.innerHTML = `
      <td>${entry.action}</td>
      <td>${entry.scan_id ? entry.scan_id.slice(0, 8) + "…" : "—"}</td>
      <td>${new Date(entry.occurred_at).toLocaleString()}</td>
    `;
    tbody.appendChild(row);
  });
}

async function loadDashboard(scanId) {
  document.getElementById("no-scan-message").hidden = !!scanId;
  if (!scanId) return;

  document.getElementById("topbar-scan-id").textContent = scanId;

  await loadPiiSummary(scanId);
  const riskData = await loadRisk(scanId);
  await loadRules(scanId);
  const findings = await loadFindings(scanId);
  updateAlertBanner(riskData, findings);
  await loadAuditLog(scanId);

  document.getElementById("download-report-button").onclick = () => downloadReport(scanId);
}

document.addEventListener("DOMContentLoaded", () => {
  document.querySelectorAll('th[data-sort="severity"]').forEach((th) => {
    th.addEventListener("click", () => {
      findingsSortAsc = !findingsSortAsc;
      th.textContent = `Severity ${findingsSortAsc ? "▴" : "▾"}`;
      renderFindings();
    });
  });

  const scanId = getScanIdFromUrl();
  loadDashboard(scanId);
  loadScanHistory(1);
});
