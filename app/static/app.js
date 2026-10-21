const TOKEN_KEY = "tickets_token";
const REFRESH_TOKEN_KEY = "tickets_refresh_token";
const SESSION_KEY = "tickets_session";

const NO_REFRESH_PATHS = [
  "/api/auth/login",
  "/api/auth/register",
  "/api/auth/refresh",
  "/api/auth/logout",
  "/api/auth/logout-all",
];

const STATUS_LABELS = { open: "Abierto", in_progress: "En progreso", closed: "Cerrado" };
const PRIORITY_LABELS = { low: "Baja", medium: "Media", high: "Alta" };

const state = {
  token: localStorage.getItem(TOKEN_KEY) || null,
  refreshToken: localStorage.getItem(REFRESH_TOKEN_KEY) || null,
  user: null,
  tickets: [],
  total: 0,
  skip: 0,
  limit: 10,
  filters: { status: "", priority: "", search: "" },
  detail: null,
};

const $ = (sel) => document.querySelector(sel);

function esc(value) {
  return String(value ?? "")
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;")
    .replaceAll("'", "&#39;");
}

function fmtDate(value) {
  if (!value) return "";
  const d = new Date(value);
  if (Number.isNaN(d.getTime())) return value;
  return d.toLocaleString();
}

let toastTimer = null;
function toast(message, isError = false) {
  const el = $("#toast");
  el.textContent = message;
  el.classList.toggle("error", isError);
  el.classList.remove("hidden");
  clearTimeout(toastTimer);
  toastTimer = setTimeout(() => el.classList.add("hidden"), 3200);
}

function decodeJwtPayload(token) {
  try {
    const raw = token.split(".")[1].replace(/-/g, "+").replace(/_/g, "/");
    const padded = raw.padEnd(raw.length + ((4 - (raw.length % 4)) % 4), "=");
    return JSON.parse(atob(padded));
  } catch (_) {
    return null;
  }
}

function tokenExpiresIn() {
  if (!state.token) return null;
  const payload = decodeJwtPayload(state.token);
  if (!payload || !payload.exp) return null;
  return payload.exp - Math.floor(Date.now() / 1000);
}

let refreshPromise = null;

async function refreshSession() {
  if (!refreshPromise) {
    refreshPromise = fetch("/api/auth/refresh", {
      method: "POST",
      credentials: "include",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(state.refreshToken ? { refresh_token: state.refreshToken } : {}),
    })
      .then(async (res) => {
        if (!res.ok) throw new Error("No se pudo refrescar la sesión");
        const data = await res.json();
        state.token = data.access_token;
        state.refreshToken = data.refresh_token || state.refreshToken;
        localStorage.setItem(TOKEN_KEY, state.token);
        localStorage.setItem(SESSION_KEY, "1");
        if (state.refreshToken) localStorage.setItem(REFRESH_TOKEN_KEY, state.refreshToken);
        return data;
      })
      .finally(() => {
        refreshPromise = null;
      });
  }
  return refreshPromise;
}

async function api(path, { method = "GET", body, form = false, auth = true, retry = true } = {}) {
  if (auth && state.token) {
    const expiresIn = tokenExpiresIn();
    if (expiresIn !== null && expiresIn <= 30) {
      try {
        await refreshSession();
      } catch (_) {}
    }
  }

  const headers = {};
  if (auth && state.token) headers["Authorization"] = "Bearer " + state.token;

  let payload;
  if (body !== undefined) {
    if (form) {
      headers["Content-Type"] = "application/x-www-form-urlencoded";
      payload = new URLSearchParams(body).toString();
    } else {
      headers["Content-Type"] = "application/json";
      payload = JSON.stringify(body);
    }
  }

  const res = await fetch(path, { method, headers, body: payload, credentials: "include" });

  if (res.status === 401 && auth && retry && !NO_REFRESH_PATHS.includes(path)) {
    try {
      await refreshSession();
    } catch (_) {
      logout(true);
      throw new Error("Sesión expirada, inicia sesión de nuevo");
    }
    return api(path, { method, body, form, auth, retry: false });
  }

  if (res.status === 401) {
    logout(true);
    throw new Error("Sesión expirada, inicia sesión de nuevo");
  }

  if (!res.ok) {
    let detail = "Error " + res.status;
    try {
      const data = await res.json();
      if (data.detail) {
        detail = typeof data.detail === "string" ? data.detail : JSON.stringify(data.detail);
      }
    } catch (_) {}
    throw new Error(detail);
  }

  if (res.status === 204) return null;
  return res.json();
}

function showAuth() {
  $("#auth-view").classList.remove("hidden");
  $("#app-view").classList.add("hidden");
}

function showApp() {
  $("#auth-view").classList.add("hidden");
  $("#app-view").classList.remove("hidden");
  $("#current-user").textContent = state.user ? state.user.username : "";
}

function clearSession() {
  state.token = null;
  state.refreshToken = null;
  state.user = null;
  localStorage.removeItem(TOKEN_KEY);
  localStorage.removeItem(REFRESH_TOKEN_KEY);
  localStorage.removeItem(SESSION_KEY);
}

function logout(silent = false) {
  clearSession();
  showAuth();
  fetch("/api/auth/logout", { method: "POST", credentials: "include" }).catch(() => {});
  if (!silent) toast("Sesión finalizada");
}

async function handleLogin(event) {
  event.preventDefault();
  try {
    const data = await api("/api/auth/login", {
      method: "POST",
      auth: false,
      form: true,
      body: {
        username: $("#login-username").value.trim(),
        password: $("#login-password").value,
      },
    });
    state.token = data.access_token;
    state.refreshToken = data.refresh_token || null;
    localStorage.setItem(TOKEN_KEY, state.token);
    localStorage.setItem(SESSION_KEY, "1");
    if (state.refreshToken) localStorage.setItem(REFRESH_TOKEN_KEY, state.refreshToken);
    state.user = await api("/api/auth/me");
    $("#login-form").reset();
    showApp();
    state.skip = 0;
    await loadTickets();
  } catch (err) {
    toast(err.message, true);
  }
}

async function handleRegister(event) {
  event.preventDefault();
  try {
    await api("/api/auth/register", {
      method: "POST",
      auth: false,
      body: {
        username: $("#register-username").value.trim(),
        email: $("#register-email").value.trim(),
        password: $("#register-password").value,
      },
    });
    $("#register-form").reset();
    toggleAuthMode();
    toast("Cuenta creada, ahora inicia sesión");
  } catch (err) {
    toast(err.message, true);
  }
}

function toggleAuthMode() {
  const showRegister = $("#register-form").classList.contains("hidden");
  $("#login-form").classList.toggle("hidden", showRegister);
  $("#register-form").classList.toggle("hidden", !showRegister);
  $("#auth-subtitle").textContent = showRegister
    ? "Crea una cuenta nueva"
    : "Inicia sesión para continuar";
  $("#toggle-text").textContent = showRegister ? "¿Ya tienes cuenta?" : "¿No tienes cuenta?";
  $("#toggle-auth").textContent = showRegister ? "Inicia sesión" : "Regístrate";
}

async function loadTickets() {
  const params = new URLSearchParams();
  if (state.filters.status) params.set("status", state.filters.status);
  if (state.filters.priority) params.set("priority", state.filters.priority);
  if (state.filters.search) params.set("search", state.filters.search);
  params.set("skip", state.skip);
  params.set("limit", state.limit);

  try {
    const data = await api("/api/tickets?" + params.toString());
    state.tickets = data.items;
    state.total = data.total;
    renderTickets();
    renderPagination();
  } catch (err) {
    toast(err.message, true);
  }
}

function renderTickets() {
  const container = $("#tickets");
  if (!state.tickets.length) {
    container.innerHTML = '<div class="empty">No hay tickets que mostrar.</div>';
    return;
  }
  container.innerHTML = state.tickets
    .map(
      (t) => `
      <article class="ticket" data-id="${t.id}">
        <div>
          <h3 class="ticket-title">${esc(t.title)}</h3>
          ${t.description ? `<p class="ticket-desc">${esc(t.description)}</p>` : ""}
          <div class="ticket-meta">#${t.id} · Creado ${esc(fmtDate(t.created_at))}</div>
        </div>
        <div class="ticket-right">
          <span class="badge status-${esc(t.status)}">${esc(STATUS_LABELS[t.status] || t.status)}</span>
          <span class="badge priority-${esc(t.priority)}">${esc(PRIORITY_LABELS[t.priority] || t.priority)}</span>
        </div>
      </article>`
    )
    .join("");

  container.querySelectorAll(".ticket").forEach((node) => {
    node.addEventListener("click", () => openTicket(Number(node.dataset.id)));
  });
}

function renderPagination() {
  const from = state.total === 0 ? 0 : state.skip + 1;
  const to = Math.min(state.skip + state.limit, state.total);
  $("#page-info").textContent = `${from}–${to} de ${state.total}`;
  $("#prev-page").disabled = state.skip <= 0;
  $("#next-page").disabled = state.skip + state.limit >= state.total;
}

function openModal(html) {
  $("#modal-content").innerHTML = html;
  $("#modal").classList.remove("hidden");
}

function closeModal() {
  $("#modal").classList.add("hidden");
  $("#modal-content").innerHTML = "";
  state.detail = null;
}

async function openTicket(id) {
  try {
    const ticket = await api(`/api/tickets/${id}`);
    state.detail = ticket;
    openModal(ticketDetailHtml(ticket));
    bindDetailEvents(ticket);
  } catch (err) {
    toast(err.message, true);
  }
}

function ticketDetailHtml(t) {
  return `
    <div class="detail-head">
      <span class="badge status-${esc(t.status)}">${esc(STATUS_LABELS[t.status] || t.status)}</span>
      <span class="badge priority-${esc(t.priority)}">${esc(PRIORITY_LABELS[t.priority] || t.priority)}</span>
      <span class="muted">#${t.id}</span>
    </div>
    <h2>${esc(t.title)}</h2>
    <p class="muted">Creado ${esc(fmtDate(t.created_at))} · Actualizado ${esc(fmtDate(t.updated_at))}</p>
    <p class="comment-body">${t.description ? esc(t.description) : '<span class="muted">Sin descripción</span>'}</p>

    <div class="detail-priority">
      <label class="muted">Estado:</label>
      <select id="detail-status">
        ${Object.entries(STATUS_LABELS)
          .map(([v, l]) => `<option value="${v}" ${v === t.status ? "selected" : ""}>${l}</option>`)
          .join("")}
      </select>
    </div>

    <div class="detail-actions">
      <button type="button" class="btn btn-danger" id="delete-ticket">Eliminar ticket</button>
    </div>

    <section class="comments">
      <h3>Comentarios (${t.comments.length})</h3>
      <div id="comment-list">${commentsHtml(t.comments)}</div>
      <form class="comment-form" id="comment-form">
        <textarea id="comment-body" rows="3" placeholder="Escribe un comentario..." required></textarea>
        <button type="submit" class="btn btn-primary">Añadir comentario</button>
      </form>
    </section>
  `;
}

function commentsHtml(comments) {
  if (!comments.length) return '<p class="muted">Todavía no hay comentarios.</p>';
  return comments
    .map(
      (c) => `
      <div class="comment">
        <div class="comment-head">
          <strong>${esc(c.author)}</strong>
          <span>${esc(fmtDate(c.created_at))}
            <button type="button" class="link" data-delete-comment="${c.id}">Eliminar</button>
          </span>
        </div>
        <p class="comment-body">${esc(c.body)}</p>
      </div>`
    )
    .join("");
}

function bindDetailEvents(ticket) {
  $("#detail-status").addEventListener("change", async (e) => {
    try {
      await api(`/api/tickets/${ticket.id}`, {
        method: "PATCH",
        body: { status: e.target.value },
      });
      toast("Estado actualizado");
      await loadTickets();
    } catch (err) {
      toast(err.message, true);
    }
  });

  $("#delete-ticket").addEventListener("click", async () => {
    if (!confirm(`¿Eliminar el ticket #${ticket.id}?`)) return;
    try {
      await api(`/api/tickets/${ticket.id}`, { method: "DELETE" });
      closeModal();
      toast("Ticket eliminado");
      if (state.tickets.length === 1 && state.skip > 0) state.skip -= state.limit;
      await loadTickets();
    } catch (err) {
      toast(err.message, true);
    }
  });

  $("#comment-form").addEventListener("submit", async (e) => {
    e.preventDefault();
    const body = $("#comment-body").value.trim();
    if (!body) return;
    try {
      await api(`/api/tickets/${ticket.id}/comments`, {
        method: "POST",
        body: { author: state.user.username, body },
      });
      await openTicket(ticket.id);
      await loadTickets();
    } catch (err) {
      toast(err.message, true);
    }
  });

  $("#modal-content").querySelectorAll("[data-delete-comment]").forEach((btn) => {
    btn.addEventListener("click", async () => {
      try {
        await api(`/api/comments/${btn.dataset.deleteComment}`, { method: "DELETE" });
        await openTicket(ticket.id);
      } catch (err) {
        toast(err.message, true);
      }
    });
  });
}

function openCreateModal() {
  openModal(`
    <h2>Nuevo ticket</h2>
    <form id="create-form">
      <div class="field">
        <label for="create-title">Título</label>
        <input type="text" id="create-title" maxlength="200" required />
      </div>
      <div class="field">
        <label for="create-description">Descripción</label>
        <textarea id="create-description" rows="4"></textarea>
      </div>
      <div class="row">
        <div class="field">
          <label for="create-priority">Prioridad</label>
          <select id="create-priority">
            ${Object.entries(PRIORITY_LABELS)
              .map(([v, l]) => `<option value="${v}" ${v === "medium" ? "selected" : ""}>${l}</option>`)
              .join("")}
          </select>
        </div>
        <div class="field">
          <label for="create-status">Estado</label>
          <select id="create-status">
            ${Object.entries(STATUS_LABELS)
              .map(([v, l]) => `<option value="${v}" ${v === "open" ? "selected" : ""}>${l}</option>`)
              .join("")}
          </select>
        </div>
      </div>
      <button type="submit" class="btn btn-primary">Crear ticket</button>
    </form>
  `);

  $("#create-form").addEventListener("submit", async (e) => {
    e.preventDefault();
    try {
      await api("/api/tickets", {
        method: "POST",
        body: {
          title: $("#create-title").value.trim(),
          description: $("#create-description").value.trim() || null,
          priority: $("#create-priority").value,
          status: $("#create-status").value,
        },
      });
      closeModal();
      toast("Ticket creado");
      state.skip = 0;
      await loadTickets();
    } catch (err) {
      toast(err.message, true);
    }
  });
}

let searchTimer = null;
function bindEvents() {
  $("#login-form").addEventListener("submit", handleLogin);
  $("#register-form").addEventListener("submit", handleRegister);
  $("#toggle-auth").addEventListener("click", toggleAuthMode);
  $("#logout-btn").addEventListener("click", () => logout());
  $("#new-ticket-btn").addEventListener("click", openCreateModal);

  $("#filter-status").addEventListener("change", (e) => {
    state.filters.status = e.target.value;
    state.skip = 0;
    loadTickets();
  });
  $("#filter-priority").addEventListener("change", (e) => {
    state.filters.priority = e.target.value;
    state.skip = 0;
    loadTickets();
  });
  $("#search").addEventListener("input", (e) => {
    clearTimeout(searchTimer);
    const value = e.target.value.trim();
    searchTimer = setTimeout(() => {
      state.filters.search = value;
      state.skip = 0;
      loadTickets();
    }, 300);
  });

  $("#prev-page").addEventListener("click", () => {
    state.skip = Math.max(0, state.skip - state.limit);
    loadTickets();
  });
  $("#next-page").addEventListener("click", () => {
    state.skip += state.limit;
    loadTickets();
  });

  document.querySelectorAll("[data-close='modal']").forEach((el) => {
    el.addEventListener("click", closeModal);
  });
  document.addEventListener("keydown", (e) => {
    if (e.key === "Escape") closeModal();
  });
}

async function init() {
  bindEvents();
  state.token = localStorage.getItem(TOKEN_KEY);
  state.refreshToken = localStorage.getItem(REFRESH_TOKEN_KEY);
  const hasSession = localStorage.getItem(SESSION_KEY) === "1";

  if (state.token || hasSession) {
    try {
      if (!state.token && hasSession) {
        // El access token caducó: la cookie httpOnly mantiene la sesión viva.
        await refreshSession();
      }
      state.user = await api("/api/auth/me");
      showApp();
      await loadTickets();
      return;
    } catch (_) {
      clearSession();
    }
  }
  showAuth();
}

init();
