const API_BASE = "http://localhost:8000";

function getToken() {
  return localStorage.getItem("dpdp_token");
}

function setToken(token) {
  localStorage.setItem("dpdp_token", token);
}

function clearToken() {
  localStorage.removeItem("dpdp_token");
}

function setLoggedInEmail(email) {
  localStorage.setItem("dpdp_email", email);
}

function getLoggedInEmail() {
  return localStorage.getItem("dpdp_email");
}

function authHeaders() {
  return { Authorization: `Bearer ${getToken()}` };
}

function showError(el, message) {
  el.textContent = message;
  el.hidden = false;
}

function hide(el) {
  el.hidden = true;
}

function show(el) {
  el.hidden = false;
}

function renderTopnavUser() {
  const email = getLoggedInEmail();
  const userBlock = document.getElementById("topnav-user");
  if (!userBlock) return;
  if (!email) {
    userBlock.hidden = true;
    return;
  }
  document.getElementById("topnav-user-email").textContent = email;
  document.getElementById("topnav-user-initial").textContent = email.charAt(0).toUpperCase();
  userBlock.hidden = false;
}

// If a token 401s (expired, or referencing a user that no longer exists —
// e.g. after a dev DB reset), drop it and send the viewer back to the
// login page instead of leaving the UI stuck.
function redirectToLoginOnAuthFailure() {
  clearToken();
  window.location.href = "index.html";
}
