const API_BASE = "http://localhost:8000";

function getToken() {
  return localStorage.getItem("dpdp_token");
}

function setToken(token) {
  localStorage.setItem("dpdp_token", token);
}

function showError(el, message) {
  el.textContent = message;
  el.classList.remove("hidden");
}

function hide(el) {
  el.classList.add("hidden");
}

function show(el) {
  el.classList.remove("hidden");
}

document.addEventListener("DOMContentLoaded", () => {
  const loginForm = document.getElementById("login-form");
  const loginError = document.getElementById("login-error");
  const loginSection = document.getElementById("login-section");
  const uploadSection = document.getElementById("upload-section");

  if (getToken()) {
    hide(loginSection);
    show(uploadSection);
  }

  loginForm.addEventListener("submit", async (e) => {
    e.preventDefault();
    hide(loginError);
    const email = document.getElementById("email").value;
    const password = document.getElementById("password").value;

    const body = new URLSearchParams();
    body.set("username", email);
    body.set("password", password);

    try {
      const res = await fetch(`${API_BASE}/auth/login`, {
        method: "POST",
        headers: { "Content-Type": "application/x-www-form-urlencoded" },
        body,
      });
      if (!res.ok) {
        showError(loginError, "Login failed — check your credentials.");
        return;
      }
      const data = await res.json();
      setToken(data.access_token);
      hide(loginSection);
      show(uploadSection);
    } catch (err) {
      showError(loginError, "Could not reach the server.");
    }
  });

  const uploadForm = document.getElementById("upload-form");
  const uploadError = document.getElementById("upload-error");
  const uploadResult = document.getElementById("upload-result");
  const contextSection = document.getElementById("context-section");
  const contextForm = document.getElementById("context-form");
  const contextError = document.getElementById("context-error");
  const contextSuccess = document.getElementById("context-success");
  const scanButton = document.getElementById("scan-button");
  const scanStatus = document.getElementById("scan-status");

  let currentScanId = null;

  function contextFieldsFromForm() {
    return {
      purpose: document.getElementById("purpose").value,
      consent_status: document.getElementById("consent-status").value,
      retention_value: parseInt(document.getElementById("retention-value").value, 10),
      retention_unit: document.getElementById("retention-unit").value,
      access_scope: document.getElementById("access-scope").value,
      encryption_enabled: document.getElementById("encryption-enabled").checked,
      access_control_enabled: document.getElementById("access-control-enabled").checked,
      notice_status: document.getElementById("notice-status").value,
    };
  }

  function fillContextForm(context) {
    document.getElementById("purpose").value = context.purpose;
    document.getElementById("consent-status").value = context.consent_status;
    document.getElementById("retention-value").value = context.retention_value;
    document.getElementById("retention-unit").value = context.retention_unit;
    document.getElementById("access-scope").value = context.access_scope;
    document.getElementById("encryption-enabled").checked = context.encryption_enabled;
    document.getElementById("access-control-enabled").checked = context.access_control_enabled;
    document.getElementById("notice-status").value = context.notice_status;
  }

  async function loadContextDefaults(scanId) {
    const res = await fetch(`${API_BASE}/datasets/${scanId}/context`, {
      headers: { Authorization: `Bearer ${getToken()}` },
    });
    if (res.ok) {
      const context = await res.json();
      fillContextForm(context);
      scanButton.disabled = !context.submitted;
    }
  }

  uploadForm.addEventListener("submit", async (e) => {
    e.preventDefault();
    hide(uploadError);
    hide(uploadResult);
    hide(contextSection);
    const fileInput = document.getElementById("file-input");
    if (!fileInput.files.length) return;

    const formData = new FormData();
    formData.append("file", fileInput.files[0]);

    try {
      const res = await fetch(`${API_BASE}/datasets/upload`, {
        method: "POST",
        headers: { Authorization: `Bearer ${getToken()}` },
        body: formData,
      });
      if (!res.ok) {
        const err = await res.json().catch(() => ({}));
        showError(uploadError, err.detail || "Upload failed.");
        return;
      }
      const data = await res.json();
      currentScanId = data.scan_id;

      document.getElementById("result-filename").textContent = data.filename;
      document.getElementById("result-rowcount").textContent = data.row_count;
      document.getElementById("result-columns").textContent = data.column_names.join(", ");
      show(uploadResult);

      show(contextSection);
      scanButton.disabled = true; // hard gate: scanning is blocked until context is saved
      await loadContextDefaults(currentScanId);
    } catch (err) {
      showError(uploadError, "Could not reach the server.");
    }
  });

  contextForm.addEventListener("submit", async (e) => {
    e.preventDefault();
    hide(contextError);
    hide(contextSuccess);
    if (!currentScanId) return;

    try {
      const res = await fetch(`${API_BASE}/datasets/${currentScanId}/context`, {
        method: "POST",
        headers: {
          Authorization: `Bearer ${getToken()}`,
          "Content-Type": "application/json",
        },
        body: JSON.stringify(contextFieldsFromForm()),
      });
      if (!res.ok) {
        const err = await res.json().catch(() => ({}));
        showError(contextError, err.detail || "Could not save context.");
        return;
      }
      contextSuccess.textContent = "Context saved.";
      show(contextSuccess);
      scanButton.disabled = false; // gate lifted now that context exists
    } catch (err) {
      showError(contextError, "Could not reach the server.");
    }
  });

  scanButton.addEventListener("click", async () => {
    if (!currentScanId) return;
    scanButton.disabled = true;
    scanStatus.textContent = "Starting scan...";
    show(scanStatus);
    try {
      const res = await fetch(`${API_BASE}/datasets/${currentScanId}/scan`, {
        method: "POST",
        headers: { Authorization: `Bearer ${getToken()}` },
      });
      if (res.status === 202) {
        const data = await res.json();
        scanStatus.textContent = `Scan status: ${data.status}`;
        const dashboardLink = document.getElementById("dashboard-link");
        const dashboardAnchor = document.getElementById("dashboard-link-anchor");
        dashboardAnchor.href = `dashboard.html?scan_id=${currentScanId}`;
        show(dashboardLink);
      } else {
        const err = await res.json().catch(() => ({}));
        scanStatus.textContent = `Scan failed: ${err.detail || res.status}`;
      }
    } catch (err) {
      scanStatus.textContent = "Could not reach the server.";
    } finally {
      scanButton.disabled = false;
    }
  });
});
