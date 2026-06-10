const app = document.querySelector("#app");
const OWNER = {
  name: "Augustin Kayembe",
  phone: "+243 991 599 600",
  emailPrimary: "kayboxstore@gmail.com",
  emailSecondary: "kayboxstore@outlook.fr",
  company: "Kay Box Store",
};

const moduleLabels = {
  dashboard: "Tableau de bord",
  orders: "Commandes",
  cash: "Caisse",
  stock: "Stock",
  production: "Production",
  commissions: "Commissions",
  workers: "Travailleurs",
  reports: "Rapports",
  users: "Utilisateurs",
  history: "Historique",
  about: "À propos",
};

const orderRates = {
  "Dépositaire": 4100,
  "Maman": 6000,
  "Vente cash": 4350,
};

const state = {
  setupRequired: null,
  user: null,
  active: "dashboard",
  loading: false,
  error: "",
  notice: "",
  filters: {
    date: todayIso(),
    all: false,
    orderStatus: "all",
    start: `${todayIso().slice(0, 8)}01`,
    end: todayIso(),
  },
  historyIdentifiant: "",
  historyRole: "",
  historyPage: 1,
};

let heartbeatTimer = null;

function todayIso() {
  return new Date().toISOString().slice(0, 10);
}

function currentYear() {
  return new Date().getFullYear();
}

function escapeHtml(value) {
  return String(value ?? "")
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;")
    .replaceAll("'", "&#039;");
}

function money(value) {
  const parsed = Number(value || 0);
  const safeValue = Number.isFinite(parsed) ? parsed : 0;
  return `${safeValue.toLocaleString("fr-FR", { maximumFractionDigits: 0 })} FC`;
}

function number(value) {
  const parsed = Number(value || 0);
  return parsed.toLocaleString("fr-FR", { maximumFractionDigits: Number.isInteger(parsed) ? 0 : 2 });
}

function can(moduleName) {
  return (state.user?.modules || []).includes(moduleName);
}

function readOnly(moduleName) {
  return (state.user?.readOnlyModules || []).includes(moduleName);
}

function isDirectorGeneral() {
  return state.user?.role === "Directeur Général";
}

function setState(patch) {
  Object.assign(state, patch);
  syncHeartbeat();
  render();
}

async function api(path, options = {}) {
  const csrfToken = state.user?.csrfToken || "";
  const response = await fetch(path, {
    ...options,
    credentials: "same-origin",
    headers: {
      "Content-Type": "application/json",
      ...(csrfToken ? { "X-CSRF-Token": csrfToken } : {}),
      ...(options.headers || {}),
    },
  });
  const payload = await response.json().catch(() => ({ ok: false, error: "Réponse serveur illisible." }));
  if (!response.ok || !payload.ok) {
    const error = new Error(payload.error || `Erreur HTTP ${response.status}`);
    error.status = response.status;
    error.payload = payload;
    error.sessionConflict = Boolean(payload.sessionConflict);
    throw error;
  }
  return payload;
}

async function post(path, body) {
  return api(path, { method: "POST", body: JSON.stringify(body || {}) });
}

function delay(milliseconds) {
  return new Promise((resolve) => setTimeout(resolve, milliseconds));
}

function syncHeartbeat() {
  if (state.user && !heartbeatTimer) {
    heartbeatTimer = window.setInterval(sendHeartbeat, 30000);
  } else if (!state.user && heartbeatTimer) {
    window.clearInterval(heartbeatTimer);
    heartbeatTimer = null;
  }
}

async function sendHeartbeat() {
  if (!state.user) return;
  try {
    await api("/api/session/ping");
  } catch {
    if (!state.user) return;
    state.user = null;
    state.active = "dashboard";
    state.loading = false;
    state.notice = "";
    state.error = "Votre session a ete fermee. Reconnectez-vous pour continuer.";
    syncHeartbeat();
    render();
  }
}

async function boot() {
  localStorage.removeItem("lomoto.webpro.token");
  try {
    const setup = await api("/api/setup/status");
    state.setupRequired = Boolean(setup.required);
  } catch {
    state.setupRequired = false;
  }
  if (state.setupRequired) {
    state.user = null;
    render();
    return;
  }
  try {
    const payload = await api("/api/me");
    state.user = payload.user;
  } catch {
    state.user = null;
  }
  syncHeartbeat();
  render();
}

function setupView() {
  return `
    <main class="login-page">
      <section class="login-card">
        <div class="brand-mark">
          <img src="/brand-assets/logo-boulangerie-lomoto.png" alt="Logo" />
          <span>Première configuration</span>
        </div>
        <p class="eyebrow">Configuration initiale</p>
        <h1>CRÉER L'ADMINISTRATEUR</h1>
        <p class="lead">Ce compte administrera les utilisateurs, les accès, les sauvegardes et la configuration générale.</p>
        ${state.error ? `<div class="alert danger">${escapeHtml(state.error)}</div>` : ""}
        <form id="setupForm" class="form-grid" autocomplete="on">
          <label>Nom complet <input name="fullName" autocomplete="name" required /></label>
          <label>Adresse e-mail <input name="email" type="email" autocomplete="email" required /></label>
          <label>Identifiant <input name="identifiant" autocomplete="username" autocapitalize="none" spellcheck="false" required /></label>
          <label>Mot de passe <input name="password" type="password" autocomplete="new-password" minlength="14" required /></label>
          <label>Confirmer le mot de passe <input name="confirmPassword" type="password" autocomplete="new-password" minlength="14" required /></label>
          <button class="primary" type="submit">Terminer la configuration</button>
        </form>
      </section>
    </main>
  `;
}

function loginView() {
  return `
    <main class="login-page">
      <section class="login-card">
        <div class="brand-mark">
          <img src="/brand-assets/logo-boulangerie-lomoto.png" alt="Logo" />
          <span>Version web professionnelle 1.4.6</span>
        </div>
        <p class="eyebrow">Application connectée</p>
        <h1>BOULANGERIE LOMOTO</h1>
        ${state.error ? `<div class="alert danger">${escapeHtml(state.error)}</div>` : ""}
        ${state.notice ? `<div class="alert success">${escapeHtml(state.notice)}</div>` : ""}
        <form id="loginForm" class="form-grid" autocomplete="off">
          <input class="autofill-decoy" name="username" autocomplete="username" tabindex="-1" aria-hidden="true" />
          <input class="autofill-decoy" name="password" type="password" autocomplete="current-password" tabindex="-1" aria-hidden="true" />
          <label>Identifiant ou e-mail <input id="loginIdentifiant" name="lomotoLoginIdentifiant" autocomplete="off" autocapitalize="none" spellcheck="false" required /></label>
          <label>Mot de passe <input id="passwordInput" name="lomotoLoginPassword" type="password" autocomplete="new-password" required /></label>
          <label class="toggle-line"><input id="showPassword" type="checkbox" /><span>Afficher le mot de passe</span></label>
          ${state.loading ? `<div class="login-progress" aria-label="Connexion en cours"><span></span></div>` : ""}
          <button class="primary" type="submit" ${state.loading ? "disabled" : ""}>${state.loading ? "Connexion..." : "Se connecter"}</button>
        </form>
      </section>
    </main>
  `;
}

function shell(content) {
  const modules = state.user?.modules || ["dashboard"];
  return `
    <main class="shell">
      <aside class="sidebar">
        <div class="sidebar-header">
          <div class="side-brand">
            <img src="/brand-assets/logo-boulangerie-lomoto.png" alt="Logo" />
            <div>
              <strong>BOULANGERIE LOMOTO</strong>
              <span>Pain Lia o Tonda</span>
              <small>Données Windows v${escapeHtml(state.user?.appVersion || "1.4.6")}</small>
            </div>
          </div>
          <button class="mobile-menu-toggle" id="mobileMenuToggle" type="button" aria-expanded="false" aria-controls="sidebarMenu" title="Ouvrir le menu">☰</button>
        </div>
        <div class="sidebar-menu" id="sidebarMenu">
          <nav>
            ${modules.map((name) => `<button class="nav-button ${state.active === name ? "active" : ""}" data-module="${name}">${moduleLabels[name] || name}</button>`).join("")}
          </nav>
          <button class="nav-button logout" id="logoutButton">Déconnexion</button>
        </div>
      </aside>
      <section class="workspace">
        <header class="topbar">
          <div>
            <p class="eyebrow">Cockpit web</p>
            <h1>${escapeHtml(moduleLabels[state.active] || "Tableau de bord")}</h1>
          </div>
          <div class="status-cluster">
            <div class="status-pill online"><i></i><span>Serveur actif</span></div>
            <div class="user-card">
              <span>${escapeHtml(state.user?.fullName || "")}</span>
              <strong>${escapeHtml(state.user?.role || "")}</strong>
            </div>
            <div class="version-card">
              <span>Version</span>
              <strong>${escapeHtml(state.user?.appVersion || "1.4.6")}</strong>
            </div>
          </div>
        </header>
        ${state.error ? `<div class="alert danger">${escapeHtml(state.error)}</div>` : ""}
        ${state.notice ? `<div class="alert success">${escapeHtml(state.notice)}</div>` : ""}
        ${isDirectorGeneral() ? `<div class="alert warning">Mode lecture seule : consultation complète, génération des rapports et clôture journalière autorisées.</div>` : ""}
        ${content}
        ${legalFooter()}
      </section>
    </main>
  `;
}

function legalFooter() {
  return `
    <footer class="legal-footer">
      <strong>© ${currentYear()} ${escapeHtml(state.user?.appName || "Boulangerie Lomoto")} - ${OWNER.name} / ${OWNER.company}. Tous droits réservés.</strong>
      <span>Application de gestion commerciale développée pour Boulangerie Lomoto. Toute reproduction, distribution ou modification non autorisée est interdite.</span>
    </footer>
  `;
}

function toolbar(moduleName, extra = "") {
  return `
    <section class="panel toolbar">
      <div>
        <p class="eyebrow">Filtre</p>
        <strong>${state.filters.all ? "Toutes les dates" : `Date : ${state.filters.date}`}</strong>
      </div>
      <div class="toolbar-actions">
        <button title="Actualiser" data-refresh>↻ Actualiser</button>
        <input id="filterDate" type="date" value="${escapeHtml(state.filters.date)}" />
        <button data-filter="date">Afficher</button>
        <button data-filter="today">Aujourd'hui</button>
        <button data-filter="all">Tout afficher</button>
        ${extra}
      </div>
    </section>
  `;
}

function cards(items) {
  return `<section class="card-grid">${items.map((item) => `
    <article class="metric">
      <span>${escapeHtml(item.label)}</span>
      <strong>${item.money ? money(item.value) : escapeHtml(number(item.value))}</strong>
      <small>${escapeHtml(item.unit || "")}</small>
    </article>
  `).join("")}</section>`;
}

function table(rows, columns, headings, actions = []) {
  return `
    <section class="panel table-panel">
      <div class="table-wrap">
        <table>
          <thead><tr>${headings.map((heading) => `<th>${escapeHtml(heading)}</th>`).join("")}${actions.length ? "<th>Actions</th>" : ""}</tr></thead>
          <tbody>
            ${rows?.length ? rows.map((row) => `
              <tr>
                ${columns.map((key) => `<td>${formatCell(key, row[key])}</td>`).join("")}
                ${actions.length ? `<td class="row-actions">${rowActionButtons(row, actions)}</td>` : ""}
              </tr>
            `).join("") : `<tr><td colspan="${columns.length + (actions.length ? 1 : 0)}">Aucune donnée disponible.</td></tr>`}
          </tbody>
        </table>
      </div>
    </section>
  `;
}

function rowActionButtons(row, actions) {
  const visibleActions = actions.filter((action) => !action.visible || action.visible(row));
  if (!visibleActions.length) return `<span class="muted-cell">-</span>`;
  return visibleActions.map((action) => {
    const disabled = action.disabled && action.disabled(row);
    return `<button data-row-action="${action.name}" data-row="${encodeURIComponent(JSON.stringify(row))}" ${disabled ? "disabled" : ""}>${escapeHtml(action.label)}</button>`;
  }).join("");
}

function formatCell(key, value) {
  const lower = key.toLowerCase();
  if (key === "ConnexionStatut") {
    const online = String(value || "").toLowerCase().includes("en ligne");
    return `<span class="session-status ${online ? "online" : "offline"}">${escapeHtml(value || "Hors ligne")}</span>`;
  }
  if (lower.startsWith("date") || lower.endsWith("date") || lower.includes("date")) {
    return escapeHtml(formatDate(value));
  }
  if (lower.includes("anciennete")) {
    return escapeHtml(value ?? "");
  }
  if (lower.includes("montant") || lower.includes("dette") || lower.includes("solde") || lower.includes("commission") || lower.includes("salaire") || lower.includes("prime") || lower.includes("avance") || lower.includes("retenue") || lower.includes("net")) {
    return escapeHtml(money(value));
  }
  if (lower.includes("taux")) return `${escapeHtml(number(value))} %`;
  return escapeHtml(value ?? "");
}

function formatDate(value) {
  const text = String(value ?? "").trim();
  if (!text) return "";
  const match = text.match(/^(\d{4})-(\d{2})-(\d{2})(.*)$/);
  if (!match) return text;
  const time = (match[4] || "").replace(/^T/, " ");
  return `${match[3]}/${match[2]}/${match[1]}${time}`;
}

function formatFileSize(value) {
  const bytes = Number(value || 0);
  if (bytes < 1024) return `${bytes} o`;
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toLocaleString("fr-FR", { maximumFractionDigits: 1 })} Ko`;
  return `${(bytes / (1024 * 1024)).toLocaleString("fr-FR", { maximumFractionDigits: 1 })} Mo`;
}

function reportFilesList(files) {
  if (!files?.length) return `<div class="calc-note">Aucun rapport disponible.</div>`;
  return `
    <div class="report-file-list">
      ${files.map((file) => `
        <a href="${escapeHtml(file.url)}" target="_blank" rel="noopener" class="report-file">
          <span>
            <strong>${escapeHtml(file.name)}</strong>
            <small>${escapeHtml(formatDate(file.modifiedAt))} • ${escapeHtml(formatFileSize(file.size))}</small>
          </span>
          <b>${escapeHtml(file.format)}</b>
        </a>
      `).join("")}
    </div>
  `;
}

async function dashboardView() {
  const payload = await api("/api/dashboard");
  const data = payload.data;
  return shell(`
    <section class="hero">
      <div>
        <p class="eyebrow">Tableau de bord</p>
        <h2>${escapeHtml(state.user?.role || "")}</h2>
        <small>Indicateurs de ${escapeHtml(data.periodLabel || "")}</small>
      </div>
      <button title="Actualiser" data-refresh>↻ Actualiser</button>
      <img src="/brand-assets/icon-baguette.png" alt="Baguette" />
    </section>
    ${cards(data.cards || [])}
    ${(data.alerts || []).length || (data.recentActivity || []).length ? `
      <section class="split">
        ${(data.alerts || []).length ? `<article class="panel">
          <h3>Alertes</h3>
          <ul class="clean-list">${data.alerts.map((alert) => `<li><strong>${escapeHtml(alert.title)}</strong><span>${escapeHtml(alert.message)}</span></li>`).join("")}</ul>
        </article>` : ""}
        ${(data.recentActivity || []).length ? `<article class="panel">
          <h3>Activité récente</h3>
          ${table(data.recentActivity, ["DateAction", "NomComplet", "Module", "Action"], ["Date", "Utilisateur", "Module", "Action"])}
        </article>` : ""}
      </section>
    ` : ""}
  `);
}

async function ordersView() {
  const orderStatus = state.filters.orderStatus || "all";
  const payload = await api(`/api/orders?date=${state.filters.date}&all=${state.filters.all ? 1 : 0}&status=${encodeURIComponent(orderStatus)}`);
  const summary = payload.summary || {};
  const readonly = readOnly("orders");
  const directorView = isDirectorGeneral();
  return shell(`
    ${toolbar("orders", `
      <select id="orderStatusFilter" title="Filtrer les commandes">
        <option value="all" ${orderStatus === "all" ? "selected" : ""}>Toutes les commandes</option>
        <option value="Maman" ${orderStatus === "Maman" ? "selected" : ""}>Commandes des mamans</option>
        <option value="Dépositaire" ${orderStatus === "Dépositaire" ? "selected" : ""}>Commandes des dépositaires</option>
      </select>
    `)}
    ${cards([
      { label: "Bacs", value: summary.NombreTotalBacs || 0, unit: "bacs" },
      { label: "À percevoir", value: summary.MontantAttendu || 0, unit: "FC", money: true },
      { label: "Reçu", value: summary.MontantRecu || 0, unit: "FC", money: true },
      { label: "Dettes", value: summary.TotalDettes || 0, unit: "FC", money: true },
      { label: "Avances utilisées", value: summary.AvancesUtilisees || 0, unit: "FC", money: true },
      { label: "Nouvelles avances", value: summary.AvancesGenerees || 0, unit: "FC", money: true },
    ])}
    ${readonly && !directorView ? `<div class="alert warning">Lecture seule : vous pouvez consulter les commandes, pas les modifier.</div>` : orderForm()}
    ${table(payload.rows || [], ["DateCommande", "Client", "Statut", "NombreBacs", "MontantAPercevoir", "MontantRecu", "AvanceUtilisee", "AvanceGeneree", "SoldeAvance", "Dette"], ["Date", "Client", "Statut", "Bacs", "À percevoir", "Reçu en caisse", "Avance utilisée", "Nouvelle avance", "Solde avance", "Dette"], readonly && !directorView ? [] : [{ name: "edit-order", label: "Modifier" }, { name: "delete-order", label: "Supprimer" }])}
  `);
}

function orderForm() {
  return `
    <section class="panel">
      <h2>Nouvelle commande</h2>
      <form id="orderForm" class="form-grid cols-4" data-advance="0">
        <input name="id" type="hidden" />
        <label>Date <input name="date" type="date" value="${state.filters.date}" required /></label>
        <label>Client <input name="client" required /></label>
        <label>Statut <select name="status"><option>Dépositaire</option><option>Maman</option><option>Vente cash</option></select></label>
        <label>Bacs <input name="trays" type="number" min="0" step="1" required /></label>
        <label>Montant à percevoir <input name="amountDue" readonly /></label>
        <label>Montant reçu <input name="amountReceived" type="number" min="0" step="1" required /></label>
        <label>Avance disponible <input name="advanceAvailable" readonly /></label>
        <label>Avance utilisée <input name="advanceUsed" readonly /></label>
        <label>Nouvelle avance <input name="advanceGenerated" readonly /></label>
        <label>Dette <input name="debt" readonly /></label>
        <div id="orderCalc" class="calc-note wide">Le calcul se fait automatiquement.</div>
        <button class="primary wide" type="submit">Enregistrer la commande</button>
      </form>
    </section>
  `;
}

async function cashView() {
  const payload = await api(`/api/cash?date=${state.filters.date}&all=${state.filters.all ? 1 : 0}`);
  const summary = payload.summary || {};
  const orders = payload.orders || {};
  const entries = Number(orders.MontantRecu || 0) + Number(summary.DettesPayeesAujourdHui || 0);
  const balance = entries - Number(summary.MontantTotalDepenses || 0);
  return shell(`
    ${toolbar("cash")}
    ${cards([
      { label: "Montant reçu", value: orders.MontantRecu || 0, unit: "FC", money: true },
      { label: "Dettes payées", value: summary.DettesPayeesAujourdHui || 0, unit: "FC", money: true },
      { label: "Total entrées", value: entries, unit: "FC", money: true },
      { label: "Solde", value: balance, unit: "FC", money: true },
    ])}
    <section class="panel">
      <h2>Caisse du jour</h2>
      <form id="cashForm" class="form-grid cols-3" data-received="${Number(orders.MontantRecu || 0)}">
        <input name="id" type="hidden" />
        <label>Date <input name="date" type="date" value="${state.filters.date}" required /></label>
        <label>Dépenses <input name="expenses" type="number" min="0" step="1" value="${summary.MontantTotalDepenses || 0}" /></label>
        <label>Dettes payées aujourd'hui <input name="paidDebts" type="number" min="0" step="1" value="${summary.DettesPayeesAujourdHui || 0}" /></label>
        <label>Total entrées <input name="entries" readonly /></label>
        <label>Solde <input name="balance" readonly /></label>
        <label class="wide">Liste des dépenses <textarea name="expenseDetails">${escapeHtml(summary.DepensesEffectuees || "")}</textarea></label>
        <label class="wide">Ceux qui ont payé <textarea name="paidDetails">${escapeHtml(summary.DettesPayeesDetails || "")}</textarea></label>
        <div id="cashCalc" class="calc-note wide">Calcul automatique.</div>
        <button class="primary wide" type="submit">Enregistrer la caisse</button>
      </form>
    </section>
    ${table(payload.rows || [], ["DateCaisse", "TotalEntrees", "MontantTotalDepenses", "Solde", "DettesPayeesAujourdHui", "DettesPayeesDetails"], ["Date", "Entrées", "Dépenses", "Solde", "Dettes payées", "Détails"], [{ name: "edit-cash", label: "Modifier" }, { name: "delete-cash", label: "Supprimer" }])}
  `);
}

async function stockView() {
  const payload = await api(`/api/stock?date=${state.filters.date}&all=${state.filters.all ? 1 : 0}`);
  const configPayload = await api("/api/stock/config");
  const summary = payload.summary || {};
  const config = configPayload.config || {};
  const stockConfigEditable = Boolean(configPayload.editable);
  return shell(`
    ${toolbar("stock")}
    ${cards([
      { label: "Farine", value: summary.FarineRestante || 0, unit: "sacs" },
      { label: "Levure", value: summary.LevureRestante || 0, unit: "paquets" },
      { label: "Sel", value: summary.SelRestant || 0, unit: "kg" },
      { label: "Huile", value: summary.HuileRestante || 0, unit: "litres" },
    ])}
    <section class="split">
      ${stockForm("stockSupplyForm", "Approvisionnement", "stock/supply")}
      ${stockForm("stockExitForm", "Sortie de stock", "stock/exit")}
    </section>
    ${stockConfigPanel(config, stockConfigEditable)}
    <h2>Approvisionnements</h2>
    ${table(payload.supplies || [], ["DateApprovisionnement", "SacsAjoutes", "PaquetsAjoutes", "KgSelAjoutes", "LitresHuileAjoutes", "Observations"], ["Date", "Farine", "Levure", "Sel", "Huile", "Observations"], [{ name: "edit-stock-supply", label: "Modifier" }, { name: "delete-stock-supply", label: "Supprimer" }])}
    <h2>Sorties</h2>
    ${table(payload.exits || [], ["DateSortie", "SacsUtilises", "PaquetsUtilises", "KgSelUtilises", "LitresHuileUtilises"], ["Date", "Farine", "Levure", "Sel", "Huile"], [{ name: "edit-stock-exit", label: "Modifier" }, { name: "delete-stock-exit", label: "Supprimer" }])}
  `);
}

function stockConfigPanel(config, editable) {
  return `
    <section class="panel">
      <h2>Paramètres du stock</h2>
      <p class="muted-text">${editable ? "Modification réservée au profil Admin, comme sur la version distante Windows." : "Consultation uniquement : seul l'Admin peut modifier ces paramètres."}</p>
      <form id="stockConfigForm" class="form-grid cols-4">
        <label>Farine initiale <input name="flourInitial" type="number" min="0" step="0.01" value="${config.FarineInitial || 0}" ${editable ? "" : "disabled"} /></label>
        <label>Levure initiale <input name="yeastInitial" type="number" min="0" step="0.01" value="${config.LevureInitial || 0}" ${editable ? "" : "disabled"} /></label>
        <label>Sel initial <input name="saltInitial" type="number" min="0" step="0.01" value="${config.SelInitial || 0}" ${editable ? "" : "disabled"} /></label>
        <label>Huile initiale <input name="oilInitial" type="number" min="0" step="0.01" value="${config.HuileInitial || 0}" ${editable ? "" : "disabled"} /></label>
        <label>Alerte farine <input name="flourAlert" type="number" min="0" step="0.01" value="${config.FarineAlerteMin || 0}" ${editable ? "" : "disabled"} /></label>
        <label>Alerte levure <input name="yeastAlert" type="number" min="0" step="0.01" value="${config.LevureAlerteMin || 0}" ${editable ? "" : "disabled"} /></label>
        <label>Alerte sel <input name="saltAlert" type="number" min="0" step="0.01" value="${config.SelAlerteMin || 0}" ${editable ? "" : "disabled"} /></label>
        <label>Alerte huile <input name="oilAlert" type="number" min="0" step="0.01" value="${config.HuileAlerteMin || 0}" ${editable ? "" : "disabled"} /></label>
        ${editable ? `<button class="primary wide" type="submit">Sauvegarder les paramètres</button>` : ""}
      </form>
    </section>
  `;
}

function stockForm(id, title) {
  return `
    <article class="panel">
      <h2>${title}</h2>
      <form id="${id}" class="form-grid cols-2">
        <input name="id" type="hidden" />
        <label>Date <input name="date" type="date" value="${state.filters.date}" required /></label>
        <label>Farine <input name="flour" type="number" min="0" step="0.01" /></label>
        <label>Levure <input name="yeast" type="number" min="0" step="0.01" /></label>
        <label>Sel <input name="salt" type="number" min="0" step="0.01" /></label>
        <label>Huile <input name="oil" type="number" min="0" step="0.01" /></label>
        <label class="wide">Observations <textarea name="observations"></textarea></label>
        <button class="primary wide" type="submit">Enregistrer</button>
      </form>
    </article>
  `;
}

async function productionView() {
  const payload = await api(`/api/production?date=${state.filters.date}&all=${state.filters.all ? 1 : 0}`);
  const summary = payload.summary || {};
  const readonly = readOnly("production");
  const directorView = isDirectorGeneral();
  return shell(`
    ${toolbar("production")}
    ${cards([
      { label: "Bacs commandés", value: summary.NombreBacsCommandes || 0, unit: "bacs" },
      { label: "Bacs produits", value: summary.NombreBacsProduits || 0, unit: "bacs" },
      { label: "Sacs utilisés", value: summary.NombreSacsUtilises || 0, unit: "sacs" },
      { label: "Couverture", value: summary.TauxCouverture || 0, unit: "%" },
    ])}
    ${readonly && !directorView ? `<div class="alert warning">Lecture seule : vous pouvez consulter la production, pas la modifier.</div>` : productionForm()}
    ${table(payload.rows || [], ["DateProduction", "NombreBacsCommandes", "NombreBacsProduits", "NombreSacsUtilises", "EcartCommandes", "TauxCouverture", "Observations"], ["Date", "Commandés", "Produits", "Sacs", "Écart", "Couverture", "Observations"], readonly && !directorView ? [] : [{ name: "edit-production", label: "Modifier" }, { name: "delete-production", label: "Supprimer" }])}
  `);
}

function productionForm() {
  return `
    <section class="panel">
      <h2>Production journalière</h2>
      <form id="productionForm" class="form-grid cols-4">
        <input name="id" type="hidden" />
        <label>Date <input name="date" type="date" value="${state.filters.date}" required /></label>
        <label>Bacs commandés <input name="ordered" type="number" min="0" step="1" /></label>
        <label>Livrés dépositaires <input name="depositaries" type="number" min="0" step="1" /></label>
        <label>Livrés mamans <input name="mamas" type="number" min="0" step="1" /></label>
        <label>Bacs donnés <input name="given" type="number" min="0" step="1" /></label>
        <label>Échantillons <input name="samples" type="number" min="0" step="1" /></label>
        <label>Bacs restants <input name="remaining" type="number" min="0" step="1" /></label>
        <label>Bacs foutus <input name="wasted" type="number" min="0" step="1" /></label>
        <label>Sacs utilisés <input name="sacks" type="number" min="0" step="0.01" /></label>
        <label class="wide">Observations <textarea name="observations"></textarea></label>
        <div id="productionCalc" class="calc-note wide">Total automatique.</div>
        <button class="primary wide" type="submit">Enregistrer la production</button>
      </form>
    </section>
  `;
}

async function commissionsView() {
  const payload = await api(`/api/commissions?date=${state.filters.date}&all=${state.filters.all ? 1 : 0}`);
  return shell(`
    ${toolbar("commissions")}
    ${cards([{ label: "Total commissions", value: payload.total || 0, unit: "FC", money: true }])}
    ${table(payload.rows || [], ["DateCommission", "Nom", "Statut", "NombreBacs", "Commissions", "Dettes", "NetAPayer"], ["Date", "Nom", "Statut", "Bacs", "Commission", "Dette", "Net"])}
  `);
}

async function workersView() {
  const payload = await api(`/api/workers?start=${state.filters.start}&end=${state.filters.end}`);
  const workers = payload.workers || [];
  const activeWorkers = workers.filter((worker) => worker.Statut === "Actif");
  const options = activeWorkers.map((worker) => `<option value="${worker.Id}">${escapeHtml(worker.NomComplet)} - ${escapeHtml(worker.Fonction || "Travailleur")}</option>`).join("");
  return shell(`
    <section class="panel toolbar">
      <div><p class="eyebrow">Paies</p><strong>Du ${state.filters.start} au ${state.filters.end}</strong></div>
      <div class="toolbar-actions">
        <input id="filterStart" type="date" value="${state.filters.start}" />
        <input id="filterEnd" type="date" value="${state.filters.end}" />
        <button data-filter="period">Actualiser</button>
      </div>
    </section>
    ${cards([
      { label: "Travailleurs actifs", value: payload.summary?.TravailleursActifs || 0, unit: "personnes" },
      { label: "Masse salariale", value: payload.summary?.MasseSalarialeMensuelle || 0, unit: "FC", money: true },
      { label: "Net payé", value: payload.summary?.TotalNet || 0, unit: "FC", money: true },
      { label: "Paies", value: payload.summary?.NombrePaies || 0, unit: "opérations" },
    ])}
    <section class="split">
      <article class="panel">
        <h2>Travailleur</h2>
        <form id="workerForm" class="form-grid cols-2">
          <input name="id" type="hidden" />
          <label>Nom complet <input name="fullName" required /></label>
          <label>Fonction <input name="function" /></label>
          <label>Téléphone <input name="phone" /></label>
          <label>Adresse e-mail <input name="email" type="email" required /></label>
          <label>Date d'embauche <input name="hireDate" type="date" value="${todayIso()}" /></label>
          <label>Salaire <input name="salary" type="number" min="0" step="1" /></label>
          <label>Statut <select name="status"><option>Actif</option><option>Inactif</option></select></label>
          <label class="wide">Adresse <textarea name="address"></textarea></label>
          <label class="wide">Observations <textarea name="observations"></textarea></label>
          <button class="primary wide" type="submit">Enregistrer</button>
        </form>
      </article>
      <article class="panel">
        <h2>Paie</h2>
        <form id="payrollForm" class="form-grid cols-2">
          <input name="id" type="hidden" />
          <label>Travailleur <select name="workerId" required><option value="">Choisir...</option>${options}</select></label>
          <label>Date <input name="payDate" type="date" value="${todayIso()}" /></label>
          <label>Période <input name="period" value="${todayIso().slice(5, 7)}/${todayIso().slice(0, 4)}" /></label>
          <label>Brut <input name="gross" type="number" min="0" step="1" /></label>
          <label>Prime <input name="bonus" type="number" min="0" step="1" value="0" /></label>
          <label>Avance <input name="advance" type="number" min="0" step="1" value="0" /></label>
          <label>Retenue <input name="withholding" type="number" min="0" step="1" value="0" /></label>
          <label>Net <input name="net" readonly /></label>
          <label>Mode <select name="paymentMode"><option>Espèces</option><option>Mobile Money</option><option>Virement</option></select></label>
          <label>Statut <select name="status"><option>Préparée</option><option>Validée</option><option>Payée</option><option>En attente</option><option>Avance seulement</option></select></label>
          <label class="wide">Observations <textarea name="observations"></textarea></label>
          <div id="payrollCalc" class="calc-note wide">Net automatique.</div>
          <button class="primary wide" type="submit">Enregistrer la paie</button>
        </form>
      </article>
    </section>
    <h2>Travailleurs</h2>
    ${table(workers, ["NomComplet", "Fonction", "Telephone", "Email", "DateEmbauche", "Anciennete", "SalaireMensuel", "Statut", "TotalPaye", "DernierePaie"], ["Nom", "Fonction", "Téléphone", "E-mail", "Embauche", "Ancienneté", "Salaire", "Statut", "Total payé", "Dernière paie"], [{ name: "edit-worker", label: "Modifier" }, { name: "delete-worker", label: "Supprimer" }])}
    <h2>Paies</h2>
    ${table(payload.payrolls || [], ["DatePaie", "NomComplet", "Periode", "MontantBrut", "Prime", "Avance", "Retenue", "MontantNet", "ModePaiement", "Statut"], ["Date", "Travailleur", "Période", "Brut", "Prime", "Avance", "Retenue", "Net", "Mode", "Statut"], [{ name: "edit-payroll", label: "Modifier" }, { name: "delete-payroll", label: "Supprimer" }])}
  `);
}

async function reportView() {
  const payload = await api(`/api/report?date=${state.filters.date}&start=${state.filters.start}&end=${state.filters.end}`);
  const sections = payload.data.sections || {};
  const cash = sections.cash || {};
  const orders = sections.orders || {};
  const entries = Number(orders.MontantRecu || 0) + Number(cash.DettesPayeesAujourdHui || 0);
  return shell(`
    <section class="panel toolbar no-print">
      <div>
        <p class="eyebrow">Rapports PDF et Excel</p>
        <strong>Choisissez le type de rapport avant de générer un fichier.</strong>
        <p class="muted-text">Journalier utilise seulement la date de référence. Mensuel utilise le mois de cette date. Période utilise la date de début et la date de fin.</p>
      </div>
      <div class="toolbar-actions">
        <button title="Actualiser" data-refresh>↻ Actualiser</button>
        <button id="reportsFolderButton">Afficher le dossier des rapports</button>
      </div>
    </section>
    <section class="panel">
      <h2>Paramètres du rapport</h2>
      <form id="reportGenerateForm" class="form-grid cols-4">
        <label>Type
          <select name="type">
            <option value="daily">Journalier</option>
            <option value="monthly">Mensuel</option>
            <option value="period">Période</option>
          </select>
        </label>
        <label>Date de référence <input name="date" id="filterDate" type="date" value="${state.filters.date}" /></label>
        <label>Date de début <input name="start" id="filterStart" type="date" value="${state.filters.start}" /></label>
        <label>Date de fin <input name="end" id="filterEnd" type="date" value="${state.filters.end}" /></label>
        <button type="button" data-filter="report">Actualiser l'aperçu</button>
        <button class="primary" type="submit" data-report-format="pdf">Générer PDF</button>
        <button class="primary" type="submit" data-report-format="excel">Générer Excel</button>
      </form>
      <div id="reportResult" class="calc-note wide">Le chemin du fichier généré apparaîtra ici.</div>
      <div id="reportsFolderResult" class="calc-note wide">Cliquez sur « Afficher le dossier des rapports » pour consulter les fichiers.</div>
    </section>
    <section class="report-page">
      <img class="watermark" src="/brand-assets/logo-boulangerie-lomoto-watermark.png" alt="" />
      <header class="report-header">
        <img src="/brand-assets/logo-boulangerie-lomoto.png" alt="Logo" />
        <div>
          <h2>BOULANGERIE LOMOTO</h2>
          <p>Rapport du ${state.filters.date}</p>
          <small>Généré par ${escapeHtml(payload.data.generatedBy)} (${escapeHtml(payload.data.role)})</small>
        </div>
        <img src="/brand-assets/icon-baguette.png" alt="Baguette" />
      </header>
      <div class="report-grid">
        ${sections.orders ? `<article><h3>Commandes</h3><p>Bacs : <strong>${orders.NombreTotalBacs || 0}</strong></p><p>Reçu : <strong>${money(orders.MontantRecu || 0)}</strong></p><p>Dettes : <strong>${money(orders.TotalDettes || 0)}</strong></p></article>` : ""}
        ${sections.cash ? `<article><h3>Caisse</h3><p>Entrées : <strong>${money(entries)}</strong></p><p class="green">Dépenses : <strong>${money(cash.MontantTotalDepenses || 0)}</strong></p><p class="red">Solde : <strong>${money(entries - Number(cash.MontantTotalDepenses || 0))}</strong></p></article>` : ""}
        ${sections.stock ? `<article><h3>Stock</h3><p>Farine : <strong>${number(sections.stock.FarineRestante || 0)} sacs</strong></p><p>Levure : <strong>${number(sections.stock.LevureRestante || 0)} paquets</strong></p></article>` : ""}
        ${sections.production ? `<article><h3>Production</h3><p>Produits : <strong>${sections.production.NombreBacsProduits || 0} bacs</strong></p><p>Sacs : <strong>${number(sections.production.NombreSacsUtilises || 0)}</strong></p></article>` : ""}
        ${sections.commissions ? `<article><h3>Commissions</h3><p>Total : <strong>${money(sections.commissions.total || 0)}</strong></p></article>` : ""}
        ${sections.workers ? `<article><h3>Travailleurs</h3><p>Actifs : <strong>${sections.workers.TravailleursActifs || 0}</strong></p><p>Net payé : <strong>${money(sections.workers.TotalNet || 0)}</strong></p></article>` : ""}
      </div>
      <p class="nb"><strong>NB :</strong> ce rapport donne une lecture simple des entrées, sorties, dettes, stocks et charges pour comprendre la santé de l'activité.</p>
    </section>
  `);
}

async function usersView() {
  const payload = await api("/api/users");
  const emailPayload = state.user?.role === "Admin" ? await api("/api/email/status") : null;
  const emailData = emailPayload?.data || {};
  const emailSettings = emailData.settings || {};
  const emailCounts = emailData.counts || {};
  const userActions = [
    { name: "edit-user", label: "Modifier" },
    { name: "delete-user", label: "Supprimer" },
    {
      name: "disconnect-user",
      label: "Déconnecter",
      visible: (row) => state.user?.role === "Admin"
        && Number(row.SessionActive || 0) > 0
        && String(row.Identifiant || "").toLowerCase() !== String(state.user?.identifiant || "").toLowerCase(),
    },
  ];
  return shell(`
    <section class="panel toolbar">
      <div><p class="eyebrow">Sécurité du compte</p><strong>Gestion des utilisateurs et mots de passe</strong></div>
      <div class="toolbar-actions"><button title="Actualiser" data-refresh>↻ Actualiser</button></div>
    </section>
    <section class="panel">
      <h2>Compte utilisateur</h2>
      <form id="userForm" class="form-grid cols-4">
        <input name="originalIdentifiant" type="hidden" />
        <label>Nom complet <input name="fullName" required /></label>
        <label>Identifiant <input name="identifiant" autocomplete="off" required /></label>
        <label>Adresse e-mail <input name="email" type="email" autocomplete="off" placeholder="Automatique si vide" /></label>
        <label>Nouveau mot de passe <input name="password" type="password" autocomplete="new-password" minlength="12" /></label>
        <label>Rôle
          <select name="role" required>
            <option>Caissier</option>
            <option>Chargé de la production</option>
            <option>Gestionnaire des commandes</option>
            <option>Gestionnaire de stock</option>
            <option>Directeur Général</option>
            <option>Admin</option>
          </select>
        </label>
        <div class="calc-note wide" id="userFormNote">Mot de passe fort requis : 12 caractères minimum, 14 pour Admin/DG. Si l'e-mail est vide, une adresse @boulangerie-lomoto.com sera créée.</div>
        <button class="primary wide" type="submit">Enregistrer l'utilisateur</button>
      </form>
    </section>
    <section class="panel">
      <h2>Changer mon mot de passe</h2>
      <form id="passwordForm" class="form-grid cols-3">
        <label>Mot de passe actuel <input name="currentPassword" type="password" required /></label>
        <label>Nouveau mot de passe <input name="newPassword" type="password" minlength="12" required /></label>
        <label>Confirmer <input name="confirmPassword" type="password" minlength="12" required /></label>
        <button class="primary wide" type="submit">Sauvegarder le mot de passe</button>
      </form>
    </section>
    ${state.user?.role === "Admin" ? `
      <section class="panel">
        <div class="section-heading">
          <div>
            <p class="eyebrow">Notifications</p>
            <h2>Envoi des e-mails</h2>
          </div>
          <div class="toolbar-actions">
            <button id="emailTestButton" type="button">Tester l'envoi</button>
            <button id="emailRetryButton" type="button">Relancer les envois</button>
          </div>
        </div>
        ${emailSettings.configured
          ? `<div class="alert success">Service e-mail actif via ${escapeHtml(emailSettings.provider)}.</div>`
          : `<div class="alert warning">Service e-mail non configuré. Les messages restent conservés dans la file d'attente.</div>`}
        ${cards([
          { label: "En attente", value: emailData.pending || 0, unit: "messages" },
          { label: "Envoyés", value: (emailCounts["Envoyé"] || 0) + (emailCounts["Mis en file"] || 0), unit: "messages" },
          { label: "Échecs", value: emailCounts["Échec"] || 0, unit: "messages" },
        ])}
        <form id="emailSettingsForm" class="form-grid cols-4">
          <label>Service
            <select name="provider">
              <option value="cloudflare" ${emailSettings.provider === "cloudflare" ? "selected" : ""}>Cloudflare Email Sending</option>
              <option value="smtp" ${emailSettings.provider === "smtp" ? "selected" : ""}>Serveur SMTP</option>
              <option value="gateway" ${emailSettings.provider === "gateway" ? "selected" : ""}>Passerelle sécurisée</option>
            </select>
          </label>
          <label>Adresse d'envoi <input name="fromAddress" type="email" value="${escapeHtml(emailSettings.from_address || "notifications@boulangerie-lomoto.com")}" /></label>
          <label>Nom d'envoi <input name="fromName" value="Boulangerie Lomoto" /></label>
          <label>Répondre à <input name="replyTo" type="email" value="${escapeHtml(emailSettings.reply_to || "")}" /></label>
          <label>Compte Cloudflare <input name="accountId" value="${escapeHtml(emailSettings.account_id || "")}" /></label>
          <label>Jeton Cloudflare <input name="apiToken" type="password" autocomplete="new-password" placeholder="Conserver le jeton actuel si vide" /></label>
          <label>Serveur SMTP <input name="smtpHost" value="${escapeHtml(emailSettings.smtp_host || "")}" placeholder="smtp.office365.com" /></label>
          <label>Port SMTP <input name="smtpPort" type="number" value="${escapeHtml(emailSettings.smtp_port || 587)}" /></label>
          <label>Utilisateur SMTP <input name="smtpUsername" value="${escapeHtml(emailSettings.smtp_username || "")}" /></label>
          <label>Mot de passe SMTP <input name="smtpPassword" type="password" autocomplete="new-password" placeholder="Conserver le mot de passe actuel si vide" /></label>
          <label class="toggle-line"><input name="smtpUseTls" type="checkbox" ${emailSettings.provider !== "smtp" || !emailSettings.smtp_use_ssl ? "checked" : ""} /><span>STARTTLS</span></label>
          <label class="toggle-line"><input name="smtpUseSsl" type="checkbox" ${emailSettings.smtp_use_ssl ? "checked" : ""} /><span>SSL direct</span></label>
          <label class="wide">URL de passerelle <input name="gatewayUrl" type="url" value="${escapeHtml(emailSettings.gateway_url || "")}" /></label>
          <label class="wide">Jeton de passerelle <input name="gatewayToken" type="password" autocomplete="new-password" placeholder="Conserver le jeton actuel si vide" /></label>
          <button class="primary wide" type="submit">Sauvegarder et tester la file d'envoi</button>
        </form>
        <h3>Dernières notifications</h3>
        ${table(emailData.recent || [], ["DateCreation", "TypeNotification", "Destinataire", "Sujet", "Statut", "NombreTentatives", "DerniereErreur"], ["Création", "Type", "Destinataire", "Sujet", "Statut", "Tentatives", "Dernière erreur"])}
      </section>
    ` : ""}
    ${table(
      payload.rows || [],
      ["NomComplet", "Identifiant", "Email", "Role", "ConnexionStatut", "SessionPlateforme", "SessionAdresseIP", "DerniereActivite"],
      ["Nom complet", "Identifiant", "E-mail", "Rôle", "Connexion", "Plateforme", "Adresse IP", "Dernière activité"],
      userActions,
    )}
  `);
}

async function historyView() {
  const identifiant = state.historyIdentifiant || "";
  const role = state.historyRole || "";
  const pageSize = 10;
  const payload = await api(`/api/history?identifiant=${encodeURIComponent(identifiant)}&role=${encodeURIComponent(role)}&limit=50`);
  const closures = await api(`/api/closures?date=${state.filters.date}`);
  const backups = await api("/api/backups");
  const closure = closures.closure || {};
  const historyRows = payload.rows || [];
  const totalPages = Math.max(1, Math.ceil(historyRows.length / pageSize));
  const currentPage = Math.min(Math.max(Number(state.historyPage || 1), 1), totalPages);
  state.historyPage = currentPage;
  const firstIndex = (currentPage - 1) * pageSize;
  const visibleRows = historyRows.slice(firstIndex, firstIndex + pageSize);
  const firstVisible = historyRows.length ? firstIndex + 1 : 0;
  const lastVisible = Math.min(firstIndex + pageSize, historyRows.length);
  return shell(`
    <section class="panel toolbar">
      <div>
        <p class="eyebrow">Historique des actions</p>
        <strong>${historyRows.length} dernière(s) action(s) • ${firstVisible}-${lastVisible}</strong>
      </div>
      <div class="toolbar-actions">
        <button title="Actualiser" data-refresh>↻ Actualiser</button>
        <input id="historyIdentifiant" placeholder="Identifiant" value="${escapeHtml(identifiant)}" />
        <select id="historyRole">
          <option value="">Tous les rôles</option>
          ${["Admin", "Directeur Général", "Caissier", "Chargé de la production", "Gestionnaire des commandes", "Gestionnaire de stock"].map((item) => `<option ${role === item ? "selected" : ""}>${item}</option>`).join("")}
        </select>
        <button id="historyFilterButton">Filtrer</button>
      </div>
    </section>
    ${table(visibleRows, ["DateAction", "NomComplet", "Identifiant", "Role", "Module", "Action", "Details"], ["Date et heure", "Nom complet", "Identifiant", "Rôle", "Module", "Action", "Détails"])}
    <section class="pagination-bar">
      <button data-history-page="${currentPage - 1}" ${currentPage <= 1 ? "disabled" : ""}>Précédent</button>
      <strong>Page ${currentPage} sur ${totalPages}</strong>
      <button data-history-page="${currentPage + 1}" ${currentPage >= totalPages ? "disabled" : ""}>Suivant</button>
    </section>
    <section class="panel">
      <h2>Clôture journalière</h2>
      <form id="closureForm" class="form-grid cols-4">
        <label>Date à clôturer <input name="date" type="date" value="${state.filters.date}" /></label>
        <label class="wide">Motif de réouverture <input name="reason" placeholder="Obligatoire pour rouvrir une journée" /></label>
        <button class="primary" type="submit" data-closure-action="close">Clôturer la journée</button>
        <button type="submit" data-closure-action="reopen">Réouvrir la journée</button>
      </form>
      <div class="calc-note">
        Statut : <strong>${escapeHtml(closure.StatutAffichage || "Ouverte")}</strong><br />
        ${closure.DateCloture ? `Clôturée le ${escapeHtml(closure.DateCloture)} par ${escapeHtml(closure.NomComplet || closure.Identifiant || "")}<br />` : ""}
        ${closure.CheminRapport ? `Rapport : ${escapeHtml(closure.CheminRapport)}<br />` : ""}
        ${closure.CheminSauvegarde ? `Sauvegarde : ${escapeHtml(closure.CheminSauvegarde)}` : ""}
      </div>
      <h3>Historique des clôtures</h3>
      ${table(closures.rows || [], ["DateJour", "StatutAffichage", "DateCloture", "NomComplet", "Role", "DateReouverture", "ReouvertParNomComplet", "MotifReouverture", "CheminRapport", "CheminSauvegarde"], ["Jour", "Statut", "Date clôture", "Clôturée par", "Rôle", "Date réouverture", "Réouverte par", "Motif", "Rapport", "Sauvegarde"])}
    </section>
    <section class="panel">
      <h2>Sauvegarde</h2>
      <p class="muted-text">En mode connecté, les sauvegardes doivent être faites sur le PC serveur central pour protéger la base partagée.</p>
      <button class="primary" id="backupButton">Sauvegarder la base</button>
      <div id="backupResult" class="calc-note">Le chemin de sauvegarde apparaîtra ici.</div>
      ${table(backups.rows || [], ["NomFichier", "TailleOctets", "DateModification", "CheminComplet"], ["Fichier", "Taille", "Date", "Chemin"])}
    </section>
  `);
}

function aboutView() {
  return shell(`
    <section class="panel toolbar">
      <div><p class="eyebrow">À propos</p><strong>Propriétaire et contact</strong></div>
      <div class="toolbar-actions"><button title="Actualiser" data-refresh>↻ Actualiser</button></div>
    </section>
    <section class="panel">
      <h2>À propos de Boulangerie Lomoto Web Pro</h2>
      <div class="owner-card">
        <img src="/brand-assets/logo-boulangerie-lomoto.png" alt="Boulangerie Lomoto" />
        <div>
          <p class="eyebrow">Responsable</p>
          <h3>${OWNER.name}</h3>
          <p>${OWNER.name} est le responsable de ${OWNER.company} et l'initiateur de cette solution.</p>
          <p>Cette application accompagne la gestion quotidienne de la boulangerie : ventes, commandes, stock, production, caisse, travailleurs, rapports et suivi des activités.</p>
        </div>
      </div>
      <section class="contact-strip">
        <article>
          <span>Téléphone</span>
          <strong>${OWNER.phone}</strong>
        </article>
        <article>
          <span>E-mail principal</span>
          <strong>${OWNER.emailPrimary}</strong>
        </article>
        <article>
          <span>E-mail secondaire</span>
          <strong>${OWNER.emailSecondary}</strong>
        </article>
      </section>
    </section>
  `);
}

function forcedPasswordView() {
  return `
    <main class="login-page">
      <section class="login-card">
        <div class="brand-mark">
          <img src="/brand-assets/logo-boulangerie-lomoto.png" alt="Boulangerie Lomoto" />
          <span>Sécurité du compte</span>
        </div>
        <p class="eyebrow">Action obligatoire</p>
        <h1>CHANGER LE MOT DE PASSE</h1>
        <p class="lead">Le mot de passe initial doit être remplacé avant d'accéder aux données.</p>
        ${state.error ? `<div class="alert danger">${escapeHtml(state.error)}</div>` : ""}
        <form id="passwordForm" class="form-grid">
          <label>Mot de passe actuel <input name="currentPassword" type="password" autocomplete="current-password" required /></label>
          <label>Nouveau mot de passe <input name="newPassword" type="password" autocomplete="new-password" minlength="12" required /></label>
          <label>Confirmer <input name="confirmPassword" type="password" autocomplete="new-password" minlength="12" required /></label>
          <button class="primary wide" type="submit">Changer et me reconnecter</button>
        </form>
        <button id="logoutButton" type="button">Se déconnecter</button>
      </section>
    </main>
  `;
}

async function render() {
  if (state.setupRequired) {
    app.innerHTML = setupView();
    bindEvents();
    return;
  }
  if (!state.user) {
    app.innerHTML = loginView();
    bindEvents();
    return;
  }
  if (state.user.mustChangePassword) {
    app.innerHTML = forcedPasswordView();
    bindEvents();
    return;
  }
  const views = {
    dashboard: dashboardView,
    orders: ordersView,
    cash: cashView,
    stock: stockView,
    production: productionView,
    commissions: commissionsView,
    workers: workersView,
    reports: reportView,
    users: usersView,
    history: historyView,
    about: aboutView,
  };
  app.innerHTML = shell(`<section class="panel"><h2>Chargement...</h2><p>Le serveur prépare les données.</p></section>`);
  bindEvents();
  try {
    const html = await (views[state.active] || dashboardView)();
    app.innerHTML = html;
    bindEvents();
  } catch (error) {
    app.innerHTML = shell(`<div class="alert danger">${escapeHtml(error.message)}</div>`);
    bindEvents();
  }
}

function bindEvents() {
  document.querySelector("#setupForm")?.addEventListener("submit", submitSetup);
  const loginForm = document.querySelector("#loginForm");
  loginForm?.addEventListener("submit", login);
  prepareLoginCredentialControls();
  document.querySelector("#showPassword")?.addEventListener("change", (event) => {
    document.querySelector("#passwordInput").type = event.currentTarget.checked ? "text" : "password";
  });
  document.querySelectorAll('input[type="date"]').forEach((input) => {
    if (!input.dataset.allowFuture) input.max = todayIso();
  });
  document.querySelectorAll("[data-module]").forEach((button) => {
    button.addEventListener("click", () => setState({ active: button.dataset.module, error: "", notice: "" }));
  });
  document.querySelector("#mobileMenuToggle")?.addEventListener("click", (event) => {
    const sidebar = document.querySelector(".sidebar");
    const isOpen = sidebar?.classList.toggle("menu-open") || false;
    event.currentTarget.setAttribute("aria-expanded", String(isOpen));
    event.currentTarget.setAttribute("title", isOpen ? "Fermer le menu" : "Ouvrir le menu");
  });
  document.querySelector("#logoutButton")?.addEventListener("click", logout);
  document.querySelectorAll("[data-filter]").forEach((button) => button.addEventListener("click", () => updateFilter(button.dataset.filter)));
  document.querySelector("#orderStatusFilter")?.addEventListener("change", (event) => {
    state.filters.orderStatus = event.currentTarget.value;
    setState({ error: "", notice: "" });
  });
  document.querySelector("#orderForm")?.addEventListener("submit", submitOrder);
  document.querySelector("#cashForm")?.addEventListener("submit", submitCash);
  document.querySelector("#stockSupplyForm")?.addEventListener("submit", (event) => submitStock(event, "/api/stock/supply"));
  document.querySelector("#stockExitForm")?.addEventListener("submit", (event) => submitStock(event, "/api/stock/exit"));
  document.querySelector("#stockConfigForm")?.addEventListener("submit", submitStockConfig);
  document.querySelector("#productionForm")?.addEventListener("submit", submitProduction);
  document.querySelector("#workerForm")?.addEventListener("submit", submitWorker);
  document.querySelector("#payrollForm")?.addEventListener("submit", submitPayroll);
  document.querySelector("#userForm")?.addEventListener("submit", submitUser);
  document.querySelector("#passwordForm")?.addEventListener("submit", submitPassword);
  document.querySelector("#emailSettingsForm")?.addEventListener("submit", submitEmailSettings);
  document.querySelector("#emailTestButton")?.addEventListener("click", testEmailSending);
  document.querySelector("#emailRetryButton")?.addEventListener("click", retryEmails);
  document.querySelector("#reportGenerateForm")?.addEventListener("submit", submitGeneratedReport);
  document.querySelector("#reportsFolderButton")?.addEventListener("click", showReportsFolder);
  document.querySelector("#closureForm")?.addEventListener("submit", submitClosure);
  document.querySelector("#backupButton")?.addEventListener("click", createBackup);
  document.querySelector("#historyFilterButton")?.addEventListener("click", applyHistoryFilters);
  document.querySelectorAll("[data-refresh]").forEach((button) => {
    button.addEventListener("click", () => setState({ error: "", notice: "" }));
  });
  document.querySelectorAll("[data-row-action]").forEach((button) => {
    button.addEventListener("click", () => handleRowAction(button.dataset.rowAction, button.dataset.row));
  });
  document.querySelectorAll("[data-history-page]").forEach((button) => {
    button.addEventListener("click", () => {
      if (!button.disabled) setState({ historyPage: Number(button.dataset.historyPage || 1), error: "", notice: "" });
    });
  });
  bindCalculations();
  applyDirectorGeneralReadOnly();
}

function prepareLoginCredentialControls() {
  const form = document.querySelector("#loginForm");
  const identifiantInput = document.querySelector("#loginIdentifiant");
  const passwordInput = document.querySelector("#passwordInput");
  if (!form || !identifiantInput || !passwordInput) return;

  const lockAutofill = () => {
    form.setAttribute("autocomplete", "off");
    identifiantInput.setAttribute("autocomplete", "off");
    passwordInput.setAttribute("autocomplete", "new-password");
  };
  const clearLoginFields = () => {
    identifiantInput.value = "";
    passwordInput.value = "";
  };
  lockAutofill();
  [0, 80, 350, 900].forEach((delayMs) => window.setTimeout(clearLoginFields, delayMs));
}

function applyDirectorGeneralReadOnly() {
  if (!state.user || state.user.mustChangePassword) return;
  if (!isDirectorGeneral()) return;

  const mutationForms = [
    "#orderForm",
    "#cashForm",
    "#stockSupplyForm",
    "#stockExitForm",
    "#stockConfigForm",
    "#productionForm",
    "#workerForm",
    "#payrollForm",
    "#userForm",
    "#passwordForm",
  ];
  mutationForms.forEach((selector) => {
    document.querySelectorAll(`${selector} input, ${selector} select, ${selector} textarea, ${selector} button`).forEach((control) => {
      control.disabled = true;
      control.title = "Mode lecture seule pour le Directeur Général";
    });
  });

  document.querySelectorAll("[data-row-action]").forEach((button) => {
    button.disabled = true;
    button.title = "Mode lecture seule pour le Directeur Général";
  });

  const reopenButton = document.querySelector('[data-closure-action="reopen"]');
  if (reopenButton) {
    reopenButton.disabled = true;
    reopenButton.title = "La réouverture est réservée à l'Admin";
  }
  const reopenReason = document.querySelector('#closureForm input[name="reason"]');
  if (reopenReason) reopenReason.disabled = true;

  const backupButton = document.querySelector("#backupButton");
  if (backupButton) {
    backupButton.disabled = true;
    backupButton.title = "La sauvegarde est réservée à l'Admin";
  }
}

async function submitSetup(event) {
  event.preventDefault();
  const data = formObject(event.currentTarget);
  if (data.password !== data.confirmPassword) {
    setState({ error: "La confirmation du mot de passe ne correspond pas.", notice: "" });
    return;
  }
  try {
    await post("/api/setup", data);
    state.setupRequired = false;
    setState({ error: "", notice: "Configuration terminée. Connectez-vous avec le compte administrateur." });
  } catch (error) {
    setState({ error: error.message, notice: "" });
  }
}

async function login(event) {
  event.preventDefault();
  const identifiant = document.querySelector("#loginIdentifiant")?.value || "";
  const password = document.querySelector("#passwordInput")?.value || "";
  const submitLogin = async (forceSession = false) => {
    const [payload] = await Promise.all([
      post("/api/login", { identifiant, password, forceSession }),
      delay(850),
    ]);
    state.user = payload.user;
    setState({ active: "dashboard", loading: false, error: "", notice: "" });
  };
  setState({ loading: true, error: "" });
  try {
    await submitLogin(false);
  } catch (error) {
    if (error.sessionConflict) {
      const activeSession = error.payload?.activeSession || {};
      const platform = activeSession.Plateforme || "un autre appareil";
      const device = activeSession.NomAppareil ? `\nAppareil : ${activeSession.NomAppareil}` : "";
      const since = activeSession.DateConnexion ? `\nConnecte depuis : ${activeSession.DateConnexion}` : "";
      const shouldReplace = window.confirm(
        `Ce compte est deja connecte sur ${platform}.${device}${since}\n\nVoulez-vous fermer cette session et vous connecter ici ?`
      );
      if (shouldReplace) {
        try {
          setState({ loading: true, error: "" });
          await submitLogin(true);
          return;
        } catch (retryError) {
          setState({ loading: false, error: retryError.message });
          return;
        }
      }
    }
    setState({ loading: false, error: error.message });
  }
}

async function logout() {
  try {
    await post("/api/logout", {});
  } catch {
    // La déconnexion locale reste prioritaire.
  }
  localStorage.removeItem("lomoto.webpro.token");
  setState({ user: null, active: "dashboard", loading: false });
}

function updateFilter(mode) {
  if (mode === "today") {
    state.filters.date = todayIso();
    state.filters.all = false;
  } else if (mode === "all") {
    state.filters.all = true;
  } else if (mode === "period" || mode === "report") {
    state.filters.date = document.querySelector("#filterDate")?.value || state.filters.date;
    state.filters.start = document.querySelector("#filterStart")?.value || state.filters.start;
    state.filters.end = document.querySelector("#filterEnd")?.value || state.filters.end;
    state.filters.all = false;
  } else {
    state.filters.date = document.querySelector("#filterDate")?.value || todayIso();
    state.filters.all = false;
  }
  setState({ filters: state.filters, error: "", notice: "" });
}

function bindCalculations() {
  const order = document.querySelector("#orderForm");
  if (order) {
    const calculate = () => {
      const rate = orderRates[order.elements.status.value] || 0;
      const trays = Number(order.elements.trays.value || 0);
      const received = Number(order.elements.amountReceived.value || 0);
      const availableAdvance = Number(order.dataset.advance || 0);
      const due = trays * rate;
      const advanceUsed = Math.min(availableAdvance, due);
      const cashNeeded = Math.max(due - advanceUsed, 0);
      const debt = Math.max(cashNeeded - received, 0);
      const advanceGenerated = Math.max(received - cashNeeded, 0);
      order.elements.amountDue.value = Math.round(due);
      order.elements.advanceAvailable.value = Math.round(availableAdvance);
      order.elements.advanceUsed.value = Math.round(advanceUsed);
      order.elements.advanceGenerated.value = Math.round(advanceGenerated);
      order.elements.debt.value = Math.round(debt);
      const calc = document.querySelector("#orderCalc");
      calc.textContent = advanceGenerated > 0
        ? `${money(due)} affectés à la commande. ${money(advanceGenerated)} seront réservés pour une prochaine commande.`
        : advanceUsed > 0
          ? `${money(advanceUsed)} d'avance utilisés. Reste à payer aujourd'hui : ${money(cashNeeded)}.`
          : `${money(rate)} par bac. Dette calculée automatiquement.`;
      calc.classList.toggle("danger-text", debt > 0);
    };
    ["status", "trays", "amountReceived"].forEach((name) => order.elements[name].addEventListener("input", calculate));
    order.elements.client.addEventListener("blur", refreshOrderAdvance);
    order.elements.date.addEventListener("change", refreshOrderAdvance);
    calculate();
  }
  const cash = document.querySelector("#cashForm");
  if (cash) {
    const calculate = () => {
      const received = Number(cash.dataset.received || 0);
      const paidDebts = Number(cash.elements.paidDebts.value || 0);
      const expenses = Number(cash.elements.expenses.value || 0);
      cash.elements.entries.value = money(received + paidDebts);
      cash.elements.balance.value = money(received + paidDebts - expenses);
      document.querySelector("#cashCalc").textContent = `Entrées = ${money(received)} + ${money(paidDebts)}. Solde = entrées - dépenses.`;
    };
    ["paidDebts", "expenses"].forEach((name) => cash.elements[name].addEventListener("input", calculate));
    calculate();
  }
  const production = document.querySelector("#productionForm");
  if (production) {
    const calculate = () => {
      const names = ["depositaries", "mamas", "given", "samples", "remaining", "wasted"];
      const produced = names.reduce((sum, name) => sum + Number(production.elements[name].value || 0), 0);
      const ordered = Number(production.elements.ordered.value || 0);
      const coverage = ordered ? (produced * 100) / ordered : 0;
      document.querySelector("#productionCalc").textContent = `Total produit : ${produced} bacs. Écart : ${produced - ordered}. Couverture : ${number(coverage)} %.`;
    };
    ["ordered", "depositaries", "mamas", "given", "samples", "remaining", "wasted"].forEach((name) => production.elements[name].addEventListener("input", calculate));
    calculate();
  }
  const payroll = document.querySelector("#payrollForm");
  if (payroll) {
    const calculate = () => {
      const gross = Number(payroll.elements.gross.value || 0);
      const bonus = Number(payroll.elements.bonus.value || 0);
      const advance = Number(payroll.elements.advance.value || 0);
      const withholding = Number(payroll.elements.withholding.value || 0);
      const net = gross + bonus - advance - withholding;
      payroll.elements.net.value = money(Math.max(net, 0));
      document.querySelector("#payrollCalc").textContent = `Net = brut + prime - avance - retenue = ${money(net)}.`;
    };
    ["gross", "bonus", "advance", "withholding"].forEach((name) => payroll.elements[name].addEventListener("input", calculate));
    calculate();
  }
}

function formObject(form) {
  return Object.fromEntries(new FormData(form).entries());
}

async function submitOrder(event) {
  event.preventDefault();
  await refreshOrderAdvance();
  const data = formObject(event.currentTarget);
  await save("/api/orders", data, "Commande enregistrée.");
}

async function refreshOrderAdvance() {
  const form = document.querySelector("#orderForm");
  if (!form) return;
  const client = form.elements.client.value.trim();
  if (!client) {
    form.dataset.advance = "0";
    form.elements.amountReceived.dispatchEvent(new Event("input"));
    return;
  }
  try {
    const query = new URLSearchParams({
      client,
      date: form.elements.date.value || state.filters.date,
      excludeId: form.elements.id.value || "0",
    });
    const payload = await api(`/api/orders/advance?${query.toString()}`);
    form.dataset.advance = String(Number(payload.balance || 0));
    form.elements.amountReceived.dispatchEvent(new Event("input"));
  } catch (error) {
    setState({ error: error.message, notice: "" });
  }
}

async function submitCash(event) {
  event.preventDefault();
  await save("/api/cash", formObject(event.currentTarget), "Caisse enregistrée.");
}

async function submitStock(event, path) {
  event.preventDefault();
  await save(path, formObject(event.currentTarget), "Stock enregistré.");
}

async function submitStockConfig(event) {
  event.preventDefault();
  await save("/api/stock/config", formObject(event.currentTarget), "Paramètres du stock sauvegardés.");
}

async function submitProduction(event) {
  event.preventDefault();
  await save("/api/production", formObject(event.currentTarget), "Production enregistrée.");
}

async function submitWorker(event) {
  event.preventDefault();
  await save("/api/workers", formObject(event.currentTarget), "Travailleur enregistré.");
}

async function submitPayroll(event) {
  event.preventDefault();
  try {
    const payload = await post("/api/payrolls", formObject(event.currentTarget));
    const email = payload.email || {};
    const settings = payload.emailStatus?.settings || {};
    let notice = "Paie enregistrée.";
    if (Number(email.sent || 0) > 0) {
      notice += ` Notification envoyée par e-mail (${email.sent}).`;
    } else if (Number(email.queued || 0) > 0 || Number(email.workerStarted || 0) > 0) {
      notice += " Notification placee dans la file d'envoi.";
    } else if (!settings.configured) {
      notice += " Notification conservée en attente : configurez le service e-mail dans Utilisateurs.";
    } else if (Number(email.failed || 0) > 0) {
      notice += " L'envoi du mail a échoué; il reste disponible pour une nouvelle tentative.";
    } else if (Number(email.pending || 0) > 0) {
      notice += " Notification placée dans la file d'envoi.";
    }
    state.notice = notice;
    state.error = "";
    await render();
  } catch (error) {
    setState({ error: error.message, notice: "" });
  }
}

async function submitUser(event) {
  event.preventDefault();
  try {
    const payload = await post("/api/users", formObject(event.currentTarget));
    const email = payload.email || {};
    const settings = payload.emailStatus?.settings || {};
    let notice = "Utilisateur enregistré.";
    if (Number(email.sent || 0) > 0) {
      notice += ` E-mail envoyé (${email.sent}).`;
    } else if (Number(email.queued || 0) > 0 || Number(email.workerStarted || 0) > 0) {
      notice += " E-mail place dans la file d'envoi.";
    } else if (!settings.configured && Number(email.pending || 0) > 0) {
      notice += " E-mail en attente : configurez le service e-mail.";
    } else if (Number(email.failed || 0) > 0) {
      notice += " L'envoi e-mail a échoué; relancez depuis Notifications.";
    }
    setState({ notice, error: "" });
  } catch (error) {
    setState({ error: error.message, notice: "" });
  }
}

async function submitPassword(event) {
  event.preventDefault();
  const data = formObject(event.currentTarget);
  if (data.newPassword !== data.confirmPassword) {
    setState({ error: "La confirmation du mot de passe ne correspond pas.", notice: "" });
    return;
  }
  try {
    const payload = await post("/api/password", data);
    if (payload.reauthenticate) {
      setState({
        user: null,
        active: "dashboard",
        error: "",
        notice: "Mot de passe modifie. Le mail est place dans la file d'envoi. Reconnectez-vous avec le nouveau mot de passe.",
      });
      return;
    }
    setState({ notice: "Mot de passe sauvegardé.", error: "" });
  } catch (error) {
    setState({ error: error.message, notice: "" });
  }
}

async function submitEmailSettings(event) {
  event.preventDefault();
  const data = emailSettingsFormData(event.currentTarget);
  try {
    const payload = await post("/api/email/settings", data);
    const result = payload.result || {};
    setState({
      notice: payload.settings?.configured
        ? `Configuration e-mail enregistrée. ${result.sent || 0} message(s) envoyé(s).`
        : "Configuration enregistrée, mais le service n'est pas encore complet.",
      error: "",
    });
  } catch (error) {
    setState({ error: error.message, notice: "" });
  }
}

function emailSettingsFormData(form = document.querySelector("#emailSettingsForm")) {
  const data = formObject(form);
  data.smtpUseTls = Boolean(form.elements.smtpUseTls?.checked);
  data.smtpUseSsl = Boolean(form.elements.smtpUseSsl?.checked);
  return data;
}

async function testEmailSending() {
  const recipient = window.prompt("Adresse e-mail de test", OWNER.emailPrimary);
  if (!recipient) return;
  try {
    const form = document.querySelector("#emailSettingsForm");
    if (form) {
      const settingsPayload = await post("/api/email/settings", emailSettingsFormData(form));
      if (!settingsPayload.settings?.configured) {
        throw new Error("Collez le jeton Cloudflare Email Sending, puis relancez le test.");
      }
    }
    const payload = await post("/api/email/test", { recipient });
    const result = payload.result || {};
    setState({
      notice: `E-mail test envoyÃ© : ${result.message || "acceptÃ© par le service."}`,
      error: "",
    });
  } catch (error) {
    setState({ error: error.message, notice: "" });
  }
}

async function retryEmails() {
  try {
    const payload = await post("/api/email/retry", {});
    const result = payload.result || {};
    setState({
      notice: `Relance terminée : ${result.sent || 0} envoyé(s), ${result.failed || 0} échec(s).`,
      error: "",
    });
  } catch (error) {
    setState({ error: error.message, notice: "" });
  }
}

async function submitGeneratedReport(event) {
  event.preventDefault();
  const submitter = event.submitter;
  const data = formObject(event.currentTarget);
  data.format = submitter?.dataset?.reportFormat || "pdf";
  const reportWindow = window.open("about:blank", "_blank");
  try {
    const payload = await post("/api/reports/generate", data);
    document.querySelector("#reportResult").innerHTML = `
      Rapport généré : <a href="${escapeHtml(payload.url)}" target="_blank" rel="noopener">${escapeHtml(payload.name)}</a>
    `;
    if (reportWindow) {
      reportWindow.location.href = payload.url;
    } else {
      window.location.href = payload.url;
    }
    const localOpen = payload.openedLocally ? " Le fichier est aussi ouvert sur le PC serveur." : "";
    setState({ notice: `Rapport ${data.format.toUpperCase()} généré : ${payload.path}.${localOpen}`, error: "" });
  } catch (error) {
    if (reportWindow) reportWindow.close();
    setState({ error: error.message, notice: "" });
  }
}

async function showReportsFolder() {
  try {
    const payload = await post("/api/reports/folder", {});
    const target = document.querySelector("#reportsFolderResult");
    if (target) {
      target.innerHTML = `
        <div class="folder-result-heading">
          <strong>${payload.openedLocally ? "Dossier ouvert sur ce PC" : "Rapports disponibles"}</strong>
          <small>${escapeHtml(payload.path)}</small>
        </div>
        ${reportFilesList(payload.files || [])}
      `;
    }
    state.notice = payload.openedLocally
      ? "Le dossier des rapports est ouvert sur le PC serveur."
      : `${(payload.files || []).length} rapport(s) disponible(s).`;
    state.error = "";
  } catch (error) {
    setState({ error: error.message, notice: "" });
  }
}

async function submitClosure(event) {
  event.preventDefault();
  const action = event.submitter?.dataset?.closureAction || "close";
  const path = action === "reopen" ? "/api/closures/reopen" : "/api/closures/close";
  await save(path, formObject(event.currentTarget), action === "reopen" ? "Journée réouverte." : "Journée clôturée.");
}

async function createBackup() {
  try {
    const payload = await post("/api/backups/create", {});
    const target = document.querySelector("#backupResult");
    if (target) target.textContent = `Sauvegarde créée : ${payload.path}`;
    setState({ notice: `Sauvegarde créée : ${payload.path}`, error: "" });
  } catch (error) {
    setState({ error: error.message, notice: "" });
  }
}

function applyHistoryFilters() {
  setState({
    historyIdentifiant: document.querySelector("#historyIdentifiant")?.value || "",
    historyRole: document.querySelector("#historyRole")?.value || "",
    historyPage: 1,
    error: "",
    notice: "",
  });
}

async function save(path, data, notice) {
  try {
    await post(path, data);
    setState({ notice, error: "" });
  } catch (error) {
    setState({ error: error.message, notice: "" });
  }
}

function parseRow(rowText) {
  try {
    return JSON.parse(decodeURIComponent(rowText || ""));
  } catch {
    return {};
  }
}

async function handleRowAction(action, rowText) {
  const row = parseRow(rowText);
  if (action === "edit-order") {
    fillForm("#orderForm", {
      id: row.Id,
      date: row.DateCommande,
      client: row.Client,
      status: row.Statut,
      trays: row.NombreBacs,
      amountReceived: row.MontantRecu,
    });
    bindCalculations();
    await refreshOrderAdvance();
    scrollToForm("#orderForm");
    return;
  }
  if (action === "delete-order") return removeById("/api/orders", row.Id, "Commande supprimée.");
  if (action === "edit-cash") {
    fillForm("#cashForm", {
      id: row.Id,
      date: row.DateCaisse,
      expenses: row.MontantTotalDepenses,
      paidDebts: row.DettesPayeesAujourdHui,
      expenseDetails: row.DepensesEffectuees,
      paidDetails: row.DettesPayeesDetails,
    });
    bindCalculations();
    scrollToForm("#cashForm");
    return;
  }
  if (action === "delete-cash") return removeById("/api/cash", row.Id, "Caisse supprimée.");
  if (action === "edit-stock-supply") {
    fillForm("#stockSupplyForm", {
      id: row.Id,
      date: row.DateApprovisionnement,
      flour: row.SacsAjoutes,
      yeast: row.PaquetsAjoutes,
      salt: row.KgSelAjoutes,
      oil: row.LitresHuileAjoutes,
      observations: row.Observations,
    });
    scrollToForm("#stockSupplyForm");
    return;
  }
  if (action === "delete-stock-supply") return removeById("/api/stock/supply", row.Id, "Approvisionnement supprimé.");
  if (action === "edit-stock-exit") {
    fillForm("#stockExitForm", {
      id: row.Id,
      date: row.DateSortie,
      flour: row.SacsUtilises,
      yeast: row.PaquetsUtilises,
      salt: row.KgSelUtilises,
      oil: row.LitresHuileUtilises,
    });
    scrollToForm("#stockExitForm");
    return;
  }
  if (action === "delete-stock-exit") return removeById("/api/stock/exit", row.Id, "Sortie de stock supprimée.");
  if (action === "edit-production") {
    fillForm("#productionForm", {
      id: row.Id,
      date: row.DateProduction,
      ordered: row.NombreBacsCommandes,
      depositaries: row.NombreBacsLivresDepositaires,
      mamas: row.NombreBacsLivresMamans,
      given: row.NombreBacsDonnes,
      samples: row.NombreEchantillons,
      remaining: row.NombreBacsRestants,
      wasted: row.NombreBacsFoutus,
      sacks: row.NombreSacsUtilises,
      observations: row.Observations,
    });
    bindCalculations();
    scrollToForm("#productionForm");
    return;
  }
  if (action === "delete-production") return removeById("/api/production", row.Id, "Production supprimée.");
  if (action === "edit-worker") {
    fillForm("#workerForm", {
      id: row.Id,
      fullName: row.NomComplet,
      function: row.Fonction,
      phone: row.Telephone,
      email: row.Email,
      hireDate: row.DateEmbauche,
      salary: row.SalaireMensuel,
      status: row.Statut,
      address: row.Adresse,
      observations: row.Observations,
    });
    scrollToForm("#workerForm");
    return;
  }
  if (action === "delete-worker") return removeById("/api/workers", row.Id, "Travailleur supprimé.");
  if (action === "edit-payroll") {
    fillForm("#payrollForm", {
      id: row.Id,
      workerId: row.TravailleurId,
      payDate: row.DatePaie,
      period: row.Periode,
      gross: row.MontantBrut,
      bonus: row.Prime,
      advance: row.Avance,
      withholding: row.Retenue,
      paymentMode: row.ModePaiement,
      status: row.Statut,
      observations: row.Observations,
    });
    bindCalculations();
    scrollToForm("#payrollForm");
    return;
  }
  if (action === "delete-payroll") return removeById("/api/payrolls", row.Id, "Paie supprimée.");
  if (action === "edit-user") {
    const form = document.querySelector("#userForm");
    if (!form) return;
    const detail = await api(`/api/users/detail?identifiant=${encodeURIComponent(row.Identifiant || "")}`);
    const user = detail.user || row;
    form.elements.originalIdentifiant.value = user.Identifiant || "";
    form.elements.fullName.value = user.NomComplet || "";
    form.elements.identifiant.value = user.Identifiant || "";
    form.elements.email.value = user.Email || "";
    form.elements.password.value = "";
    form.elements.role.value = user.Role || "Caissier";
    form.elements.identifiant.readOnly = true;
    document.querySelector("#userFormNote").textContent =
      "Le mot de passe actuel n'est jamais affiché. Laissez ce champ vide pour le conserver, ou saisissez un mot de passe fort conforme au rôle.";
    form.scrollIntoView({ behavior: "smooth", block: "start" });
    return;
  }
  if (action === "delete-user") {
    if (!row.Identifiant) return;
    if (!confirm(`Supprimer le compte ${row.Identifiant} ?`)) return;
    await remove(`/api/users?identifiant=${encodeURIComponent(row.Identifiant)}`, "Utilisateur supprimé.");
    return;
  }
  if (action === "disconnect-user") {
    if (!row.Identifiant) return;
    if (!confirm(`Fermer la session de ${row.Identifiant} ?`)) return;
    await post("/api/users/disconnect", { identifiant: row.Identifiant });
    setState({ notice: `Session fermee pour ${row.Identifiant}.`, error: "" });
  }
}

function fillForm(selector, values) {
  const form = document.querySelector(selector);
  if (!form) return;
  Object.entries(values).forEach(([name, value]) => {
    if (form.elements[name]) {
      form.elements[name].value = value ?? "";
    }
  });
}

function scrollToForm(selector) {
  document.querySelector(selector)?.closest(".panel")?.scrollIntoView({ behavior: "smooth", block: "start" });
}

async function removeById(path, id, notice) {
  if (!id) return;
  if (!confirm("Supprimer cet enregistrement ?")) return;
  await remove(`${path}?id=${encodeURIComponent(id)}`, notice);
}

async function remove(path, notice) {
  try {
    const csrfToken = state.user?.csrfToken || "";
    const response = await fetch(path, {
      method: "DELETE",
      credentials: "same-origin",
      headers: {
        ...(csrfToken ? { "X-CSRF-Token": csrfToken } : {}),
      },
    });
    const payload = await response.json().catch(() => ({ ok: false, error: "Réponse serveur illisible." }));
    if (!response.ok || !payload.ok) {
      throw new Error(payload.error || `Erreur HTTP ${response.status}`);
    }
    setState({ notice, error: "" });
  } catch (error) {
    setState({ error: error.message, notice: "" });
  }
}

boot();

if ("serviceWorker" in navigator) {
  window.addEventListener("load", () => {
    navigator.serviceWorker.register("/service-worker.js").catch(() => {});
  });
}
