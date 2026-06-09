import "./styles.css";
import {
  asRemoteDate,
  clearSession,
  formatFc,
  formatNumber,
  loadConfig,
  loadSession,
  login,
  rpc,
  saveConfig,
  todayIso,
} from "./api.js";

const app = document.querySelector("#app");

const DEFAULT_FILTERS = {
  stock: { date: todayIso(), all: false },
  production: { date: todayIso(), all: false },
  orders: { date: todayIso(), all: false },
  cash: { date: todayIso(), all: false },
  commissions: { date: todayIso(), all: false },
  workers: { start: todayIso().slice(0, 8) + "01", end: todayIso(), all: true },
  reports: { date: todayIso(), start: todayIso(), end: todayIso(), type: "daily" },
  closures: { date: todayIso() },
};

let state = {
  user: loadSession(),
  activeModule: "dashboard",
  busy: false,
  error: "",
  notice: "",
  loginDraft: { identifiant: "" },
  filters: DEFAULT_FILTERS,
};

const MODULES_BY_ROLE = {
  Admin: [
    "dashboard",
    "stock",
    "production",
    "orders",
    "cash",
    "commissions",
    "workers",
    "reports",
    "users",
    "closures",
    "history",
    "backups",
    "account",
  ],
  Caissier: ["dashboard", "orders", "production", "cash", "commissions", "workers", "reports", "account"],
  "Gestionnaire de stock": ["dashboard", "stock", "reports", "account"],
  "Gestionnaire des commandes": ["dashboard", "production", "orders", "commissions", "reports", "account"],
};

const READ_ONLY = {
  Caissier: ["orders", "production", "commissions"],
};

const MODULE_LABELS = {
  dashboard: "Tableau de bord",
  stock: "Stock",
  production: "Production",
  orders: "Commandes",
  cash: "Caisse",
  commissions: "Commissions",
  workers: "Travailleurs et paies",
  reports: "Rapports",
  users: "Utilisateurs",
  closures: "Clôture journalière",
  history: "Historique",
  backups: "Sauvegardes",
  account: "Mon compte",
};

const ORDER_STATUS_RATES = {
  "Dépositaire": 4100,
  "Maman": 6000,
  "Vente cash": 4350,
};

function setState(patch) {
  state = { ...state, ...patch };
  render();
}

function canUse(moduleName) {
  return (MODULES_BY_ROLE[state.user?.role] || ["dashboard"]).includes(moduleName);
}

function isAdmin() {
  return state.user?.role === "Admin";
}

function isReadOnly(moduleName) {
  return (READ_ONLY[state.user?.role] || []).includes(moduleName);
}

function actionGuard(moduleName) {
  if (isReadOnly(moduleName)) {
    throw new Error("Votre profil peut consulter ces données, mais pas les modifier.");
  }
}

function escapeHtml(value) {
  return String(value ?? "")
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;")
    .replaceAll("'", "&#039;");
}

function encodeRow(row) {
  return encodeURIComponent(JSON.stringify(row));
}

function decodeRow(encoded) {
  return JSON.parse(decodeURIComponent(encoded || "%7B%7D"));
}

function pageShell(content) {
  const modules = MODULES_BY_ROLE[state.user?.role] || ["dashboard"];
  const config = loadConfig();
  const serverLabel = String(config.apiUrl || "").replace(/^https?:\/\//, "").replace(/\/+$/, "") || "Serveur central";
  return `
    <main class="app-shell">
      <aside class="sidebar">
        <div class="brand">
          <img src="/assets/logo-boulangerie-lomoto.png" alt="Logo Boulangerie Lomoto" />
          <div>
            <strong>BOULANGERIE LOMOTO</strong>
            <span>Pain Lia o Tonda</span>
          </div>
        </div>
        ${modules
          .map(
            (name) => `
              <button class="nav-link ${state.activeModule === name ? "active" : ""}" data-module="${name}">
                ${MODULE_LABELS[name]}
              </button>
            `,
          )
          .join("")}
        <button class="nav-link logout" id="logoutButton">Déconnexion</button>
      </aside>
      <section class="workspace">
        <header class="topbar">
          <div>
            <p class="eyebrow">Mode web et mobile</p>
            <h1>${MODULE_LABELS[state.activeModule] || "Boulangerie Lomoto"}</h1>
          </div>
          <div class="topbar-status">
            <div class="server-pill">
              <span class="live-dot"></span>
              <div>
                <strong>Connecté</strong>
                <small>${escapeHtml(serverLabel)}</small>
              </div>
            </div>
            <div class="user-pill">
              <span>${escapeHtml(state.user?.fullName || state.user?.identifiant || "")}</span>
              <strong>${escapeHtml(state.user?.role || "")}</strong>
              <small>${todayIso()}</small>
            </div>
          </div>
        </header>
        ${state.error ? `<div class="alert error">${escapeHtml(state.error)}</div>` : ""}
        ${state.notice ? `<div class="alert success">${escapeHtml(state.notice)}</div>` : ""}
        ${content}
      </section>
    </main>
  `;
}

function loginPage() {
  const config = loadConfig();
  return `
    <main class="login-page">
      <section class="login-card">
        <div class="login-logo">
          <img src="/assets/logo-boulangerie-lomoto.png" alt="Logo" />
        </div>
        <p class="eyebrow">Application connectée</p>
        <h1>BOULANGERIE LOMOTO</h1>
        <p class="lead">Connectez-vous au serveur central pour travailler depuis un PC, une tablette ou un téléphone Android.</p>
        ${state.error ? `<div class="alert error">${escapeHtml(state.error)}</div>` : ""}
        <form id="loginForm" class="form-grid">
          <label>Adresse du serveur central
            <input name="apiUrl" value="${escapeHtml(config.apiUrl)}" placeholder="https://votre-api.run.app" required />
          </label>
          <label>Jeton du serveur
            <input name="token" value="${escapeHtml(config.token)}" placeholder="Facultatif" />
          </label>
          <label>Identifiant
            <input name="identifiant" value="${escapeHtml(state.loginDraft.identifiant || "")}" autocomplete="username" autocapitalize="none" spellcheck="false" required />
          </label>
          <label>Mot de passe
            <input id="loginPassword" name="password" type="password" autocomplete="current-password" required />
          </label>
          <label class="inline-check">
            <input id="showLoginPassword" type="checkbox" />
            Afficher le mot de passe
          </label>
          <button class="primary" type="submit" ${state.busy ? "disabled" : ""}>${state.busy ? "Connexion..." : "Se connecter"}</button>
        </form>
      </section>
    </main>
  `;
}

function list(items) {
  return `<ul class="clean-list">${items.map((item) => `<li>${escapeHtml(item)}</li>`).join("")}</ul>`;
}

function dateTools(moduleName, title = "Filtrer") {
  const filter = state.filters[moduleName] || { date: todayIso(), all: false };
  return `
    <section class="panel toolbar">
      <div>
        <p class="eyebrow">${title}</p>
        <strong>${filter.all ? "Toutes les dates" : `Date sélectionnée : ${filter.date}`}</strong>
      </div>
      <div class="toolbar-actions">
        <input id="${moduleName}Date" type="date" value="${escapeHtml(filter.date)}" />
        <button type="button" data-filter-date="${moduleName}">Afficher la date</button>
        <button type="button" data-filter-today="${moduleName}">Aujourd'hui</button>
        <button type="button" data-filter-all="${moduleName}">Tout afficher</button>
      </div>
    </section>
  `;
}

function roleHint(moduleName) {
  return isReadOnly(moduleName)
    ? `<p class="alert warning">Lecture seule : vous pouvez consulter, mais pas modifier.</p>`
    : "";
}

async function dashboardPage() {
  const [
    stock,
    stockSupplies,
    stockExits,
    orders,
    production,
    cash,
    commissions,
    debts,
    lowStock,
    activities,
    users,
    workers,
  ] = await Promise.all([
    rpc("get_stock_summary"),
    rpc("count_stock_supplies"),
    rpc("count_stock_exits"),
    rpc("get_global_orders_summary"),
    rpc("get_global_production_summary"),
    rpc("get_total_cash"),
    rpc("get_total_commissions"),
    rpc("get_debt_alerts", [8]),
    rpc("get_low_stock_alerts"),
    isAdmin() ? rpc("get_recent_activity_summary", [8]) : Promise.resolve([]),
    isAdmin() ? rpc("count_users") : Promise.resolve(0),
    ["Admin", "Caissier"].includes(state.user?.role)
      ? rpc("get_workers_payroll_summary")
      : Promise.resolve({}),
  ]);

  const cards = [
    ["Stock farine", formatNumber(stock.FarineRestante), "Sacs restants"],
    ["Approvisionnements", stockSupplies, "Entrées de stock"],
    ["Sorties stock", stockExits, "Sorties enregistrées"],
    ["Commandes", orders.NombreCommandes || 0, `${orders.TotalBacs || 0} bacs cumulés`],
    ["Production", production.TotalBacsProduits || 0, `Écart : ${production.EcartCommandes || 0}`],
    ["Caisse", formatFc(cash), "Solde global"],
    ["Commissions", formatFc(commissions), "Total commissions"],
    ["Dettes", formatFc(orders.TotalDettes || 0), `${debts.length} alerte(s)`],
  ];
  if (isAdmin()) cards.push(["Utilisateurs", users || 0, "Comptes enregistrés"]);
  if (["Admin", "Caissier"].includes(state.user?.role)) {
    cards.push(["Travailleurs", workers.TravailleursActifs || 0, `${formatFc(workers.MasseSalarialeMensuelle || 0)} / mois`]);
    cards.push(["Paies", formatFc(workers.TotalNet || 0), `${workers.NombrePaies || 0} paiement(s)`]);
  }

  return pageShell(`
    <section class="hero-panel">
      <div>
        <p class="eyebrow">Vue générale</p>
        <h2>Les indicateurs donnent une image rapide de toute l'activité.</h2>
        <p>Chaque rôle voit les informations utiles à son travail, comme sur la version Windows.</p>
      </div>
      <img src="/assets/icon-baguette.png" alt="Baguette" />
    </section>
    <section class="metric-grid">
      ${cards
        .map(
          ([title, value, subtitle]) => `
            <article class="metric-card">
              <span>${escapeHtml(title)}</span>
              <strong>${escapeHtml(value)}</strong>
              <small>${escapeHtml(subtitle)}</small>
            </article>
          `,
        )
        .join("")}
    </section>
    <section class="two-columns">
      <article class="panel">
        <h3>Alertes stock</h3>
        ${lowStock.length ? list(lowStock.map((row) => `${row.Article} : ${formatNumber(row.StockRestant)} ${row.Unite}`)) : "<p>Aucune alerte de stock.</p>"}
      </article>
      <article class="panel">
        <h3>Dettes prioritaires</h3>
        ${debts.length ? list(debts.map((row) => `${row.Client} : ${formatFc(row.DetteTotale)}`)) : "<p>Aucune dette prioritaire.</p>"}
      </article>
    </section>
    ${
      isAdmin()
        ? `<section class="panel">
            <h3>Historique récent</h3>
            ${
              activities.length
                ? table(activities, ["DateAction", "NomComplet", "Role", "Module", "Action", "Details"], ["Date", "Utilisateur", "Rôle", "Module", "Action", "Détails"], { compact: true })
                : "<p>Aucune activité enregistrée.</p>"
            }
          </section>`
        : ""
    }
  `);
}

async function stockPage() {
  const filter = state.filters.stock;
  const [summary, supplies, exits] = await Promise.all([
    rpc("get_stock_summary"),
    filter.all ? rpc("list_stock_supplies") : rpc("list_stock_supplies_by_date", [asRemoteDate(filter.date)]),
    filter.all ? rpc("list_stock_exits") : rpc("list_stock_exits_by_date", [asRemoteDate(filter.date)]),
  ]);

  return pageShell(`
    ${dateTools("stock", "Stock")}
    <section class="metric-grid compact">
      <article class="metric-card"><span>Farine</span><strong>${formatNumber(summary.FarineRestante)}</strong><small>sacs</small></article>
      <article class="metric-card"><span>Levure</span><strong>${formatNumber(summary.LevureRestante)}</strong><small>paquets</small></article>
      <article class="metric-card"><span>Sel</span><strong>${formatNumber(summary.SelRestant)}</strong><small>kg</small></article>
      <article class="metric-card"><span>Huile</span><strong>${formatNumber(summary.HuileRestante)}</strong><small>litres</small></article>
    </section>
    ${roleHint("stock")}
    <section class="two-columns">
      <article class="panel">
        <h2>Approvisionnement en stock</h2>
        <form id="stockSupplyForm" class="form-grid module-form">
          <input name="id" type="hidden" />
          <label>Date <input name="date" type="date" value="${escapeHtml(filter.date)}" required /></label>
          <label>Farine <input name="sacs" type="number" min="0" step="0.01" /></label>
          <label>Levure <input name="paquets" type="number" min="0" step="0.01" /></label>
          <label>Sel <input name="sel" type="number" min="0" step="0.01" /></label>
          <label>Huile <input name="huile" type="number" min="0" step="0.01" /></label>
          <label class="wide">Observations <textarea name="observations"></textarea></label>
          <button class="primary wide" type="submit">Enregistrer l'approvisionnement</button>
        </form>
      </article>
      <article class="panel">
        <h2>Sortie de stock</h2>
        <form id="stockExitForm" class="form-grid module-form">
          <input name="id" type="hidden" />
          <label>Date <input name="date" type="date" value="${escapeHtml(filter.date)}" required /></label>
          <label>Farine utilisée <input name="sacs" type="number" min="0" step="0.01" /></label>
          <label>Levure utilisée <input name="paquets" type="number" min="0" step="0.01" /></label>
          <label>Sel utilisé <input name="sel" type="number" min="0" step="0.01" /></label>
          <label>Huile utilisée <input name="huile" type="number" min="0" step="0.01" /></label>
          <button class="primary wide" type="submit">Enregistrer la sortie</button>
        </form>
      </article>
    </section>
    ${tableWithActions(
      "Approvisionnements",
      supplies,
      ["DateApprovisionnement", "SacsAjoutes", "PaquetsAjoutes", "KgSelAjoutes", "LitresHuileAjoutes", "Observations"],
      ["Date", "Farine", "Levure", "Sel", "Huile", "Observations"],
      isReadOnly("stock") ? [] : [{ label: "Charger", action: "load-supply" }, { label: "Supprimer", action: "delete-supply", danger: true }],
    )}
    ${tableWithActions(
      "Sorties de stock",
      exits,
      ["DateSortie", "SacsUtilises", "PaquetsUtilises", "KgSelUtilises", "LitresHuileUtilises"],
      ["Date", "Farine", "Levure", "Sel", "Huile"],
      isReadOnly("stock") ? [] : [{ label: "Charger", action: "load-exit" }, { label: "Supprimer", action: "delete-exit", danger: true }],
    )}
  `);
}

async function productionPage() {
  const filter = state.filters.production;
  const rows = filter.all ? await rpc("list_productions") : await rpc("list_productions_by_date", [asRemoteDate(filter.date)]);

  return pageShell(`
    ${dateTools("production", "Production")}
    ${roleHint("production")}
    <section class="panel">
      <h2>Production journalière</h2>
      <form id="productionForm" class="form-grid module-form">
        <label>Date <input name="date" type="date" value="${escapeHtml(filter.date)}" required /></label>
        <label>Bacs commandés <input name="ordered" type="number" min="0" step="1" required /></label>
        <label>Bacs livrés dépositaires <input name="dep" type="number" min="0" step="1" required /></label>
        <label>Bacs livrés mamans <input name="mamans" type="number" min="0" step="1" required /></label>
        <label>Bacs donnés <input name="given" type="number" min="0" step="1" required /></label>
        <label>Échantillons <input name="samples" type="number" min="0" step="1" required /></label>
        <label>Bacs restants <input name="remaining" type="number" min="0" step="1" required /></label>
        <label>Bacs foutus <input name="wasted" type="number" min="0" step="1" required /></label>
        <label>Nombre de sacs utilisés <input name="sacks" type="number" min="0" step="0.01" required /></label>
        <label class="wide">Observations <textarea name="observations"></textarea></label>
        <button class="primary wide" type="submit">Enregistrer la production</button>
      </form>
    </section>
    ${tableWithActions(
      "Historique de production",
      rows,
      ["DateProduction", "NombreBacsCommandes", "NombreBacsLivresDepositaires", "NombreBacsLivresMamans", "NombreBacsDonnes", "NombreEchantillons", "NombreBacsRestants", "NombreBacsFoutus", "NombreBacsProduits", "NombreSacsUtilises", "EcartCommandes", "TauxCouverture", "Observations"],
      ["Date", "Commandés", "Livrés dép.", "Livrés mamans", "Donnés", "Échant.", "Restants", "Foutus", "Produits", "Sacs", "Écart", "Couverture", "Observations"],
      isReadOnly("production") ? [] : [{ label: "Charger", action: "load-production" }, { label: "Supprimer", action: "delete-production", danger: true }],
    )}
  `);
}

async function ordersPage() {
  const filter = state.filters.orders;
  const rows = filter.all ? await rpc("list_orders") : await rpc("list_orders_by_date", [asRemoteDate(filter.date)]);
  const summary = await rpc("get_orders_summary_for_date", [asRemoteDate(filter.date)]);

  return pageShell(`
    ${dateTools("orders", "Commandes")}
    <section class="metric-grid compact">
      <article class="metric-card"><span>Bacs</span><strong>${summary.NombreTotalBacs || 0}</strong><small>date affichée</small></article>
      <article class="metric-card"><span>Montant attendu</span><strong>${formatFc(summary.MontantAttendu || 0)}</strong><small>commandes</small></article>
      <article class="metric-card"><span>Montant reçu</span><strong>${formatFc(summary.MontantRecu || 0)}</strong><small>paiements</small></article>
      <article class="metric-card"><span>Dettes</span><strong>${formatFc(summary.TotalDettes || 0)}</strong><small>reste à payer</small></article>
    </section>
    ${roleHint("orders")}
    <section class="panel">
      <h2>Commande</h2>
      <form id="orderForm" class="form-grid module-form">
        <input name="id" type="hidden" />
        <label>Date <input name="date" type="date" value="${escapeHtml(filter.date)}" required /></label>
        <label>Client <input name="client" required /></label>
        <label>Statut
          <select name="status">
            <option>Dépositaire</option>
            <option>Maman</option>
            <option>Vente cash</option>
          </select>
        </label>
        <label>Nombre de bacs <input name="trays" type="number" min="0" step="1" required /></label>
        <label>Montant à percevoir <input name="due" type="number" min="0" step="1" readonly required /></label>
        <label>Montant reçu <input name="received" type="number" min="0" step="1" required /></label>
        <label>Dette <input name="debt" type="number" step="1" readonly required /></label>
        <div class="calculation-note wide" id="orderCalculationNote">Le montant à percevoir et la dette se calculent automatiquement.</div>
        <button class="primary wide" type="submit">Enregistrer la commande</button>
      </form>
    </section>
    ${tableWithActions(
      "Liste des commandes",
      rows,
      ["DateCommande", "Client", "Statut", "NombreBacs", "MontantAPercevoir", "MontantRecu", "Dette"],
      ["Date", "Client", "Statut", "Bacs", "À percevoir", "Reçu", "Dette"],
      isReadOnly("orders") ? [] : [{ label: "Charger", action: "load-order" }, { label: "Supprimer", action: "delete-order", danger: true }],
    )}
  `);
}

async function cashPage() {
  const filter = state.filters.cash;
  const [rows, summary, ordersSummary, accumulated] = await Promise.all([
    filter.all ? rpc("list_cash_days") : rpc("list_cash_days_by_date", [asRemoteDate(filter.date)]),
    rpc("get_cash_for_date", [asRemoteDate(filter.date)]),
    rpc("get_orders_summary_for_date", [asRemoteDate(filter.date)]),
    rpc("get_accumulated_debt_totals_for_date", [asRemoteDate(filter.date)]),
  ]);
  const totalEntries = Number(ordersSummary.MontantRecu || 0) + Number(summary.DettesPayeesAujourdHui || 0);
  const totalExpenses = Number(summary.MontantTotalDepenses || 0);
  const dayBalance = totalEntries - totalExpenses;

  return pageShell(`
    ${dateTools("cash", "Caisse")}
    <section class="metric-grid compact">
      <article class="metric-card"><span>Montant reçu</span><strong>${formatFc(ordersSummary.MontantRecu || 0)}</strong><small>commandes</small></article>
      <article class="metric-card"><span>Dettes accumulées</span><strong>${formatFc(accumulated.DettesAccumuleesAvantPaiement || 0)}</strong><small>jours précédents</small></article>
      <article class="metric-card"><span>Entrées</span><strong>${formatFc(totalEntries)}</strong><small>reçu + dettes payées</small></article>
      <article class="metric-card"><span>Solde</span><strong>${formatFc(dayBalance)}</strong><small>balance du jour</small></article>
    </section>
    <section class="panel">
      <h2>Caisse du jour</h2>
      <form id="cashForm" class="form-grid module-form">
        <label>Date <input name="date" type="date" value="${escapeHtml(filter.date)}" required /></label>
        <label>Dépenses <input name="expenses" type="number" min="0" step="1" value="${escapeHtml(summary.MontantTotalDepenses || 0)}" required /></label>
        <label>Dettes payées aujourd'hui <input name="paidDebts" type="number" min="0" step="1" value="${escapeHtml(summary.DettesPayeesAujourdHui || 0)}" /></label>
        <label>Total entrées <input name="totalEntries" value="${escapeHtml(formatFc(totalEntries))}" readonly /></label>
        <label>Solde du jour <input name="dayBalance" value="${escapeHtml(formatFc(dayBalance))}" readonly /></label>
        <label class="wide">Liste des dépenses <textarea name="expenseDetails" placeholder="Transport : 7 000 FC">${escapeHtml(summary.DepensesEffectuees || "")}</textarea></label>
        <label class="wide">Ceux qui ont payé <textarea name="paidDetails" placeholder="Nom : montant">${escapeHtml(summary.DettesPayeesDetails || "")}</textarea></label>
        <div class="calculation-note wide" data-cash-received="${Number(ordersSummary.MontantRecu || 0)}">Total entrées = montant reçu + dettes payées. Solde = total entrées - dépenses.</div>
        <button class="primary wide" type="submit">Enregistrer la caisse</button>
      </form>
    </section>
    ${tableWithActions(
      "Historique de caisse",
      rows,
      ["DateCaisse", "NombreTotalBacs", "MontantAttendu", "MontantRecu", "TotalDettes", "TotalDettesAccumulees", "DettesPayeesAujourdHui", "DettesAccumuleesRestantes", "TotalEntrees", "MontantTotalDepenses", "Solde", "DepensesEffectuees", "DettesPayeesDetails"],
      ["Date", "Bacs", "Attendu", "Reçu", "Dettes", "Dettes accum.", "Payées", "Restantes", "Entrées", "Dépenses", "Solde", "Liste dépenses", "Ceux qui ont payé"],
      [{ label: "Charger", action: "load-cash" }, { label: "Supprimer", action: "delete-cash", danger: true }],
    )}
  `);
}

async function commissionsPage() {
  const filter = state.filters.commissions;
  const rows = filter.all ? await rpc("list_commissions") : await rpc("list_commissions_by_date", [asRemoteDate(filter.date)]);
  const total = rows.reduce((sum, row) => sum + Number(row.Commissions || 0), 0);
  return pageShell(`
    ${dateTools("commissions", "Commissions")}
    ${roleHint("commissions")}
    <section class="panel">
      <h2>Commissions automatiques</h2>
      <p>Les commissions proviennent des commandes enregistrées. Les dépositaires n'ont pas de commission.</p>
      <p><strong>Total affiché :</strong> ${formatFc(total)}</p>
    </section>
    ${table(
      rows,
      ["DateCommission", "Nom", "Statut", "NombreBacs", "MontantPaye", "Commissions", "Dettes", "NetAPayer"],
      ["Date", "Nom", "Statut", "Bacs", "Payé", "Commission", "Dette", "Net"],
    )}
  `);
}

async function workersPage() {
  const filter = state.filters.workers || { start: todayIso().slice(0, 8) + "01", end: todayIso(), all: true };
  const [workers, payrolls, summary] = await Promise.all([
    rpc("list_workers", [true]),
    rpc("list_payrolls", [0, asRemoteDate(filter.start), asRemoteDate(filter.end)]),
    rpc("get_workers_payroll_summary", [asRemoteDate(filter.start), asRemoteDate(filter.end)]),
  ]);
  const activeWorkers = workers.filter((row) => row.Statut === "Actif");
  const workerOptions = activeWorkers
    .map((worker) => `<option value="${escapeHtml(worker.Id)}">${escapeHtml(worker.NomComplet)} - ${escapeHtml(worker.Fonction || "Travailleur")}</option>`)
    .join("");

  return pageShell(`
    <section class="panel toolbar">
      <div>
        <p class="eyebrow">Travailleurs</p>
        <strong>Paies du ${escapeHtml(filter.start)} au ${escapeHtml(filter.end)}</strong>
      </div>
      <form id="workersFilterForm" class="toolbar-actions">
        <input name="start" type="date" value="${escapeHtml(filter.start)}" />
        <input name="end" type="date" value="${escapeHtml(filter.end)}" />
        <button type="submit">Actualiser</button>
      </form>
    </section>
    <section class="metric-grid compact">
      <article class="metric-card"><span>Travailleurs actifs</span><strong>${summary.TravailleursActifs || 0}</strong><small>${summary.NombreTravailleurs || 0} au total</small></article>
      <article class="metric-card"><span>Masse salariale</span><strong>${formatFc(summary.MasseSalarialeMensuelle || 0)}</strong><small>prévision mensuelle</small></article>
      <article class="metric-card"><span>Net payé</span><strong>${formatFc(summary.TotalNet || 0)}</strong><small>période affichée</small></article>
      <article class="metric-card"><span>Avances/retenues</span><strong>${formatFc((Number(summary.TotalAvances || 0) + Number(summary.TotalRetenues || 0)))}</strong><small>contrôle paie</small></article>
    </section>
    <section class="two-columns">
      <article class="panel">
        <h2>Fiche travailleur</h2>
        <form id="workerForm" class="form-grid module-form">
          <input name="id" type="hidden" />
          <label>Nom complet <input name="fullName" required /></label>
          <label>Fonction <input name="function" placeholder="Boulanger, vendeur, livreur..." /></label>
          <label>Téléphone <input name="phone" /></label>
          <label>Date d'embauche <input name="hireDate" type="date" value="${todayIso()}" required /></label>
          <label>Salaire mensuel <input name="salary" type="number" min="0" step="1" required /></label>
          <label>Statut
            <select name="status">
              <option>Actif</option>
              <option>Inactif</option>
            </select>
          </label>
          <label class="wide">Adresse <textarea name="address"></textarea></label>
          <label class="wide">Observations <textarea name="observations"></textarea></label>
          <button class="primary wide" type="submit">Enregistrer le travailleur</button>
        </form>
      </article>
      <article class="panel">
        <h2>Paiement de salaire</h2>
        <form id="payrollForm" class="form-grid module-form">
          <input name="id" type="hidden" />
          <label>Travailleur
            <select name="workerId" required>
              <option value="">Choisir...</option>
              ${workerOptions}
            </select>
          </label>
          <label>Date de paie <input name="payDate" type="date" value="${todayIso()}" required /></label>
          <label>Période <input name="period" value="${todayIso().slice(5, 7)}/${todayIso().slice(0, 4)}" required /></label>
          <label>Montant brut <input name="gross" type="number" min="0" step="1" required /></label>
          <label>Prime <input name="bonus" type="number" min="0" step="1" value="0" /></label>
          <label>Avance <input name="advance" type="number" min="0" step="1" value="0" /></label>
          <label>Retenue <input name="withholding" type="number" min="0" step="1" value="0" /></label>
          <label>Net à payer <input name="net" readonly /></label>
          <label>Mode de paiement
            <select name="paymentMode">
              <option>Espèces</option>
              <option>Mobile Money</option>
              <option>Virement</option>
            </select>
          </label>
          <label>Statut
            <select name="status">
              <option>Payée</option>
              <option>En attente</option>
            </select>
          </label>
          <label class="wide">Observations <textarea name="observations"></textarea></label>
          <div class="calculation-note wide" id="payrollCalculationNote">Le net à payer se calcule automatiquement.</div>
          <button class="primary wide" type="submit">Enregistrer la paie</button>
        </form>
      </article>
    </section>
    ${tableWithActions(
      "Liste des travailleurs",
      workers,
      ["NomComplet", "Fonction", "Telephone", "DateEmbauche", "SalaireMensuel", "Statut", "TotalPaye", "DernierePaie", "Observations"],
      ["Nom", "Fonction", "Téléphone", "Embauche", "Salaire", "Statut", "Total payé", "Dernière paie", "Observations"],
      [{ label: "Charger", action: "load-worker" }, { label: "Supprimer", action: "delete-worker", danger: true }],
    )}
    ${tableWithActions(
      "Historique des paies",
      payrolls,
      ["DatePaie", "NomComplet", "Periode", "MontantBrut", "Prime", "Avance", "Retenue", "MontantNet", "ModePaiement", "Statut", "Observations"],
      ["Date", "Travailleur", "Période", "Brut", "Prime", "Avance", "Retenue", "Net", "Mode", "Statut", "Observations"],
      [{ label: "Charger", action: "load-payroll" }, { label: "Supprimer", action: "delete-payroll", danger: true }],
    )}
  `);
}

async function usersPage() {
  const rows = await rpc("list_users");
  return pageShell(`
    <section class="panel">
      <h2>Utilisateurs</h2>
      <form id="userForm" class="form-grid module-form">
        <input name="original" type="hidden" />
        <label>Nom complet <input name="fullName" required /></label>
        <label>Identifiant <input name="username" required /></label>
        <label>Mot de passe <input name="password" type="text" required /></label>
        <label>Rôle
          <select name="role">
            <option>Caissier</option>
            <option>Gestionnaire de stock</option>
            <option>Gestionnaire des commandes</option>
            <option>Admin</option>
          </select>
        </label>
        <button class="primary wide" type="submit">Enregistrer l'utilisateur</button>
      </form>
    </section>
    ${tableWithActions(
      "Comptes utilisateurs",
      rows,
      ["NomComplet", "Identifiant", "Role"],
      ["Nom complet", "Identifiant", "Rôle"],
      [{ label: "Charger", action: "load-user" }, { label: "Supprimer", action: "delete-user", danger: true }],
    )}
  `);
}

function reportModulesForRole() {
  if (state.user.role === "Admin") return ["orders", "production", "cash", "commissions", "stock", "workers"];
  if (state.user.role === "Caissier") return ["orders", "cash", "commissions", "workers"];
  if (state.user.role === "Gestionnaire des commandes") return ["orders", "production", "commissions"];
  if (state.user.role === "Gestionnaire de stock") return ["stock"];
  return [];
}

async function reportsPage() {
  const filter = state.filters.reports;
  const modules = reportModulesForRole();
  const selectedDate = filter.date || todayIso();
  const start = filter.start || selectedDate;
  const end = filter.end || selectedDate;
  const [
    orders,
    production,
    cash,
    commissions,
    stock,
    cashPeriod,
    workerSummary,
  ] = await Promise.all([
    modules.includes("orders") ? rpc("get_orders_summary_for_date", [asRemoteDate(selectedDate)]) : Promise.resolve({}),
    modules.includes("production") ? rpc("get_production_summary_for_date", [asRemoteDate(selectedDate)]) : Promise.resolve({}),
    modules.includes("cash") ? rpc("get_cash_for_date", [asRemoteDate(selectedDate)]) : Promise.resolve({}),
    modules.includes("commissions") ? rpc("list_commissions_by_date", [asRemoteDate(selectedDate)]) : Promise.resolve([]),
    modules.includes("stock") ? rpc("get_stock_summary") : Promise.resolve({}),
    modules.includes("cash") ? rpc("list_cash_balance_by_period", [asRemoteDate(start), asRemoteDate(end)]) : Promise.resolve([]),
    modules.includes("workers") ? rpc("get_workers_payroll_summary", [asRemoteDate(start), asRemoteDate(end)]) : Promise.resolve({}),
  ]);
  const reportEntries = Number(orders.MontantRecu || 0) + Number(cash.DettesPayeesAujourdHui || 0);
  const commissionTotal = commissions.reduce((sum, row) => sum + Number(row.Commissions || 0), 0);

  return pageShell(`
    <section class="panel toolbar">
      <div>
        <p class="eyebrow">Rapports</p>
        <strong>Rapport adapté au rôle : ${escapeHtml(state.user.role)}</strong>
      </div>
      <form id="reportFilterForm" class="toolbar-actions">
        <select name="type">
          <option value="daily" ${filter.type === "daily" ? "selected" : ""}>Journalier</option>
          <option value="period" ${filter.type === "period" ? "selected" : ""}>Entre deux dates</option>
        </select>
        <input name="date" type="date" value="${escapeHtml(selectedDate)}" />
        <input name="start" type="date" value="${escapeHtml(start)}" />
        <input name="end" type="date" value="${escapeHtml(end)}" />
        <button type="submit">Actualiser</button>
        <button type="button" class="primary" id="printReport">Imprimer / PDF</button>
        <button type="button" id="exportCsv">Exporter CSV</button>
      </form>
    </section>
    <section class="print-report" id="reportArea">
      <img class="watermark" src="/assets/logo-boulangerie-lomoto-watermark.png" alt="" />
      <div class="report-head">
        <img src="/assets/logo-boulangerie-lomoto.png" alt="Logo" />
        <div>
          <h2>BOULANGERIE LOMOTO</h2>
          <p>Rapport ${filter.type === "period" ? `du ${start} au ${end}` : `journalier - ${selectedDate}`}</p>
          <small>Généré par ${escapeHtml(state.user.fullName)} (${escapeHtml(state.user.role)})</small>
        </div>
        <img src="/assets/icon-baguette.png" alt="Baguette" />
      </div>
      <div class="report-grid">
        ${modules.includes("orders") ? `<p><strong>Commandes :</strong> ${orders.NombreTotalBacs || 0} bacs, attendu ${formatFc(orders.MontantAttendu || 0)}, reçu ${formatFc(orders.MontantRecu || 0)}, dettes ${formatFc(orders.TotalDettes || 0)}</p>` : ""}
        ${modules.includes("production") ? `<p><strong>Production :</strong> ${production.NombreBacsProduits || 0} bacs, ${formatNumber(production.NombreSacsUtilises || 0)} sacs utilisés, couverture ${formatNumber(production.TauxCouverture || 0)} %</p>` : ""}
        ${modules.includes("cash") ? `<p><strong>Montant reçu :</strong> ${formatFc(orders.MontantRecu || 0)}<br><strong>Dettes payées aujourd'hui :</strong> ${formatFc(cash.DettesPayeesAujourdHui || 0)}<br><strong>Total entrées :</strong> ${formatFc(reportEntries)}<br><strong class="green">Dépenses :</strong> ${formatFc(cash.MontantTotalDepenses || 0)}<br><strong class="red">Solde du jour :</strong> ${formatFc(reportEntries - Number(cash.MontantTotalDepenses || 0))}</p>` : ""}
        ${modules.includes("commissions") ? `<p><strong>Commissions :</strong> ${formatFc(commissionTotal)}</p>` : ""}
        ${modules.includes("stock") ? `<p><strong>Stock farine :</strong> ${formatNumber(stock.FarineRestante || 0)} sacs restants<br><strong>Levure :</strong> ${formatNumber(stock.LevureRestante || 0)} paquets</p>` : ""}
        ${modules.includes("workers") ? `<p><strong>Travailleurs :</strong> ${workerSummary.TravailleursActifs || 0} actif(s)<br><strong>Masse salariale :</strong> ${formatFc(workerSummary.MasseSalarialeMensuelle || 0)}<br><strong>Net payé sur la période :</strong> ${formatFc(workerSummary.TotalNet || 0)}</p>` : ""}
      </div>
      ${
        cashPeriod.length
          ? `<h3>Évolution de la caisse</h3>${table(cashPeriod, ["DateCaisse", "TotalEntrees", "MontantTotalDepenses", "Solde", "SoldeCumule"], ["Date", "Entrées", "Dépenses", "Solde", "Solde cumulé"], { compact: true })}`
          : ""
      }
      <p class="nb"><strong>NB :</strong> ce rapport résume les entrées, les sorties et les éléments critiques afin de comprendre rapidement la situation de l'activité.</p>
    </section>
  `);
}

async function closuresPage() {
  const selectedDate = state.filters.closures.date || todayIso();
  const [closure, closures] = await Promise.all([
    rpc("get_day_closure", [asRemoteDate(selectedDate)]),
    rpc("list_day_closures", [120]),
  ]);
  return pageShell(`
    <section class="panel">
      <h2>Clôture journalière</h2>
      <p>La clôture fige la journée, génère un rapport et crée une sauvegarde côté serveur.</p>
      <form id="closureForm" class="form-grid module-form">
        <label>Date à traiter <input name="date" type="date" value="${escapeHtml(selectedDate)}" required /></label>
        <label class="wide">Motif de réouverture <textarea name="reason" placeholder="Obligatoire uniquement pour rouvrir une journée"></textarea></label>
        <button class="primary" name="intent" value="close" type="submit">Clôturer la journée</button>
        <button name="intent" value="reopen" type="submit">Réouvrir la journée</button>
      </form>
      <div class="status-box">
        <strong>Statut :</strong>
        ${
          closure?.DateJour
            ? `${escapeHtml(closure.StatutAffichage || "")} par ${escapeHtml(closure.NomComplet || closure.Identifiant || "")}`
            : "Aucune clôture pour cette date."
        }
      </div>
    </section>
    ${table(closures, ["DateJour", "StatutAffichage", "NomComplet", "Role", "DateCloture", "ReouvertParNomComplet", "MotifReouverture"], ["Date", "Statut", "Clôturée par", "Rôle", "Date clôture", "Réouverte par", "Motif"])}
  `);
}

async function historyPage() {
  const rows = await rpc("list_activity_logs", [300, "", ""]);
  return pageShell(`
    <section class="panel">
      <h2>Historique complet</h2>
      <p>Seul l'administrateur voit l'historique des activités.</p>
    </section>
    ${table(rows, ["DateAction", "NomComplet", "Identifiant", "Role", "Module", "Action", "Details"], ["Date", "Nom", "Identifiant", "Rôle", "Module", "Action", "Détails"])}
  `);
}

async function backupsPage() {
  const rows = await rpc("list_backup_files", [200]);
  return pageShell(`
    <section class="panel">
      <h2>Sauvegarde et restauration</h2>
      <p>Les sauvegardes sont créées côté serveur central.</p>
      <button class="primary" id="backupNow">Sauvegarder maintenant</button>
    </section>
    ${tableWithActions(
      "Sauvegardes disponibles",
      rows,
      ["NomFichier", "TailleKo", "DateModification", "CheminComplet"],
      ["Fichier", "Taille Ko", "Date", "Chemin serveur"],
      [{ label: "Restaurer", action: "restore-backup", danger: true }],
    )}
  `);
}

function accountPage() {
  return pageShell(`
    <section class="panel">
      <h2>Changer mon mot de passe</h2>
      <form id="passwordForm" class="form-grid module-form">
        <label>Mot de passe actuel <input name="current" type="password" required /></label>
        <label>Nouveau mot de passe <input name="next" type="password" minlength="6" required /></label>
        <button class="primary wide" type="submit">Changer le mot de passe</button>
      </form>
    </section>
  `);
}

function table(rows, keys, headings, options = {}) {
  const tableClass = options.compact ? "compact-table" : "";
  return `
    <section class="panel table-panel ${tableClass}">
      <div class="table-wrap">
        <table>
          <thead><tr>${headings.map((heading) => `<th>${escapeHtml(heading)}</th>`).join("")}</tr></thead>
          <tbody>
            ${rows.length
              ? rows
                  .map((row) => `<tr>${keys.map((key) => `<td>${formatCell(key, row[key])}</td>`).join("")}</tr>`)
                  .join("")
              : `<tr><td colspan="${keys.length}">Aucune donnée disponible.</td></tr>`}
          </tbody>
        </table>
      </div>
    </section>
  `;
}

function tableWithActions(title, rows, keys, headings, actions = []) {
  const actionHead = actions.length ? "<th>Actions</th>" : "";
  return `
    <section class="panel table-panel">
      <h2>${escapeHtml(title)}</h2>
      <div class="table-wrap">
        <table>
          <thead><tr>${headings.map((heading) => `<th>${escapeHtml(heading)}</th>`).join("")}${actionHead}</tr></thead>
          <tbody>
            ${rows.length
              ? rows
                  .map(
                    (row) => `
                      <tr>
                        ${keys.map((key) => `<td>${formatCell(key, row[key])}</td>`).join("")}
                        ${
                          actions.length
                            ? `<td class="row-actions">${actions
                                .map(
                                  (action) => `
                                    <button type="button" class="${action.danger ? "danger" : ""}" data-action="${action.action}" data-row="${encodeRow(row)}">
                                      ${escapeHtml(action.label)}
                                    </button>
                                  `,
                                )
                                .join("")}</td>`
                            : ""
                        }
                      </tr>
                    `,
                  )
                  .join("")
              : `<tr><td colspan="${keys.length + (actions.length ? 1 : 0)}">Aucune donnée disponible.</td></tr>`}
          </tbody>
        </table>
      </div>
    </section>
  `;
}

function formatCell(key, value) {
  if (value === null || value === undefined || value === "") return "-";
  const lower = key.toLowerCase();
  if (
    lower.includes("montant") ||
    lower.includes("dette") ||
    lower.includes("solde") ||
    lower.includes("entree") ||
    lower.includes("commission") ||
    lower.includes("salaire") ||
    lower.includes("prime") ||
    lower.includes("avance") ||
    lower.includes("retenue") ||
    key === "NetAPayer"
  ) {
    return escapeHtml(formatFc(value));
  }
  if (key === "TauxCouverture") return `${escapeHtml(formatNumber(value))} %`;
  return escapeHtml(value);
}

async function renderAsync(pageFactory) {
  state.busy = true;
  app.innerHTML = pageShell(`<div class="panel"><h2>Chargement...</h2><p>Nous récupérons les données du serveur central.</p></div>`);
  bindEvents();
  try {
    const html = await pageFactory();
    app.innerHTML = html;
    bindEvents();
  } catch (error) {
    app.innerHTML = pageShell(`<div class="alert error">${escapeHtml(error.message)}</div>`);
    bindEvents();
  } finally {
    state.busy = false;
  }
}

function render() {
  if (!state.user) {
    app.innerHTML = loginPage();
    bindEvents();
    return;
  }
  if (!canUse(state.activeModule)) {
    state.activeModule = "dashboard";
  }

  const factories = {
    dashboard: dashboardPage,
    stock: stockPage,
    production: productionPage,
    orders: ordersPage,
    cash: cashPage,
    commissions: commissionsPage,
    workers: workersPage,
    reports: reportsPage,
    users: usersPage,
    closures: closuresPage,
    history: historyPage,
    backups: backupsPage,
    account: accountPage,
  };
  renderAsync(factories[state.activeModule] || dashboardPage);
}

function bindEvents() {
  document.querySelectorAll("[data-module]").forEach((button) => {
    button.addEventListener("click", () => setState({ activeModule: button.dataset.module, error: "", notice: "" }));
  });

  document.querySelector("#logoutButton")?.addEventListener("click", () => {
    clearSession();
    setState({ user: null, activeModule: "dashboard" });
  });

  document.querySelector("#loginForm")?.addEventListener("submit", handleLogin);
  document.querySelector("#showLoginPassword")?.addEventListener("change", (event) => {
    const passwordInput = document.querySelector("#loginPassword");
    if (passwordInput) passwordInput.type = event.currentTarget.checked ? "text" : "password";
  });
  document.querySelector("#stockSupplyForm")?.addEventListener("submit", submitStockSupply);
  document.querySelector("#stockExitForm")?.addEventListener("submit", submitStockExit);
  document.querySelector("#productionForm")?.addEventListener("submit", submitProduction);
  document.querySelector("#orderForm")?.addEventListener("submit", submitOrder);
  document.querySelector("#cashForm")?.addEventListener("submit", submitCash);
  document.querySelector("#workersFilterForm")?.addEventListener("submit", submitWorkersFilter);
  document.querySelector("#workerForm")?.addEventListener("submit", submitWorker);
  document.querySelector("#payrollForm")?.addEventListener("submit", submitPayroll);
  document.querySelector("#userForm")?.addEventListener("submit", submitUser);
  document.querySelector("#reportFilterForm")?.addEventListener("submit", submitReportFilter);
  document.querySelector("#closureForm")?.addEventListener("submit", submitClosure);
  document.querySelector("#passwordForm")?.addEventListener("submit", submitPassword);
  document.querySelector("#backupNow")?.addEventListener("click", createBackup);
  document.querySelector("#printReport")?.addEventListener("click", () => window.print());
  document.querySelector("#exportCsv")?.addEventListener("click", exportReportCsv);

  bindOrderAutoCalculations();
  bindProductionAutoCalculations();
  bindCashAutoCalculations();
  bindPayrollAutoCalculations();

  document.querySelectorAll("[data-filter-date]").forEach((button) => {
    button.addEventListener("click", () => updateDateFilter(button.dataset.filterDate, false));
  });
  document.querySelectorAll("[data-filter-all]").forEach((button) => {
    button.addEventListener("click", () => updateDateFilter(button.dataset.filterAll, true));
  });
  document.querySelectorAll("[data-filter-today]").forEach((button) => {
    button.addEventListener("click", () => {
      const moduleName = button.dataset.filterToday;
      state.filters[moduleName] = { ...(state.filters[moduleName] || {}), date: todayIso(), all: false };
      setState({ filters: { ...state.filters }, error: "", notice: "" });
    });
  });

  document.querySelectorAll("[data-action]").forEach((button) => {
    button.addEventListener("click", () => handleRowAction(button.dataset.action, decodeRow(button.dataset.row)));
  });
}

function moneyValue(value) {
  const parsed = Number(String(value || "0").replace(/\s/g, "").replace(",", "."));
  return Number.isFinite(parsed) ? parsed : 0;
}

function bindOrderAutoCalculations() {
  const form = document.querySelector("#orderForm");
  if (!form) return;
  const calculate = () => {
    const status = String(form.elements.status?.value || "Dépositaire");
    const trays = moneyValue(form.elements.trays?.value);
    const received = moneyValue(form.elements.received?.value);
    const rate = ORDER_STATUS_RATES[status] || 0;
    const due = trays * rate;
    const debt = due - received;
    const isOverpaid = received > due;
    form.elements.due.value = Math.round(due);
    form.elements.debt.value = Math.round(Math.max(debt, 0));
    form.elements.received?.setAttribute("max", String(Math.round(due)));
    form.elements.received?.setCustomValidity(
      isOverpaid ? "Le montant reçu ne peut pas dépasser le montant à percevoir." : ""
    );
    const note = document.querySelector("#orderCalculationNote");
    if (note) {
      note.classList.toggle("warning", isOverpaid);
      note.textContent = isOverpaid
        ? `Impossible : le montant reçu (${formatFc(received)}) dépasse le montant à percevoir (${formatFc(due)}).`
        : `${status} : ${formatFc(rate)} par bac. Dette calculée : ${formatFc(Math.max(debt, 0))}.`;
    }
  };
  if (!form.dataset.autoCalculationBound) {
    ["status", "trays", "received"].forEach((name) => {
      form.elements[name]?.addEventListener("input", calculate);
      form.elements[name]?.addEventListener("change", calculate);
    });
    form.dataset.autoCalculationBound = "1";
  }
  calculate();
}

function bindProductionAutoCalculations() {
  const form = document.querySelector("#productionForm");
  if (!form) return;
  let summary = document.querySelector("#productionAutoSummary");
  if (!summary) {
    summary = document.createElement("div");
    summary.id = "productionAutoSummary";
    summary.className = "calculation-note wide";
    const button = form.querySelector("button[type='submit']");
    form.insertBefore(summary, button);
  }
  const calculate = () => {
    const ordered = moneyValue(form.elements.ordered?.value);
    const produced =
      moneyValue(form.elements.dep?.value) +
      moneyValue(form.elements.mamans?.value) +
      moneyValue(form.elements.given?.value) +
      moneyValue(form.elements.samples?.value) +
      moneyValue(form.elements.remaining?.value) +
      moneyValue(form.elements.wasted?.value);
    const gap = produced - ordered;
    const coverage = ordered > 0 ? (produced * 100) / ordered : 0;
    summary.textContent = `Total bacs produits : ${formatNumber(produced)} | Écart avec commandes : ${formatNumber(gap)} | Taux de couverture : ${formatNumber(coverage)} %`;
  };
  if (!form.dataset.autoCalculationBound) {
    ["ordered", "dep", "mamans", "given", "samples", "remaining", "wasted"].forEach((name) => {
      form.elements[name]?.addEventListener("input", calculate);
      form.elements[name]?.addEventListener("change", calculate);
    });
    form.dataset.autoCalculationBound = "1";
  }
  calculate();
}

function bindCashAutoCalculations() {
  const form = document.querySelector("#cashForm");
  const note = document.querySelector("[data-cash-received]");
  if (!form || !note) return;
  const received = Number(note.dataset.cashReceived || 0);
  const calculate = () => {
    const paidDebts = moneyValue(form.elements.paidDebts?.value);
    const expenses = moneyValue(form.elements.expenses?.value);
    const totalEntries = received + paidDebts;
    const balance = totalEntries - expenses;
    form.elements.totalEntries.value = formatFc(totalEntries);
    form.elements.dayBalance.value = formatFc(balance);
    note.textContent = `Montant reçu : ${formatFc(received)} | Dettes payées : ${formatFc(paidDebts)} | Dépenses : ${formatFc(expenses)} | Solde : ${formatFc(balance)}`;
  };
  if (!form.dataset.autoCalculationBound) {
    ["paidDebts", "expenses"].forEach((name) => {
      form.elements[name]?.addEventListener("input", calculate);
      form.elements[name]?.addEventListener("change", calculate);
    });
    form.dataset.autoCalculationBound = "1";
  }
  calculate();
}

function bindPayrollAutoCalculations() {
  const form = document.querySelector("#payrollForm");
  if (!form) return;
  const note = document.querySelector("#payrollCalculationNote");
  const calculate = () => {
    const gross = moneyValue(form.elements.gross?.value);
    const bonus = moneyValue(form.elements.bonus?.value);
    const advance = moneyValue(form.elements.advance?.value);
    const withholding = moneyValue(form.elements.withholding?.value);
    const net = gross + bonus - advance - withholding;
    form.elements.net.value = formatFc(Math.max(net, 0));
    if (note) {
      note.classList.toggle("warning", net < 0);
      note.textContent = net < 0
        ? "Impossible : les avances et retenues dépassent le montant brut + prime."
        : `Net à payer = ${formatFc(gross)} + ${formatFc(bonus)} - ${formatFc(advance)} - ${formatFc(withholding)} = ${formatFc(net)}.`;
    }
    form.elements.gross?.setCustomValidity(net < 0 ? "Le net à payer ne peut pas être négatif." : "");
  };
  if (!form.dataset.autoCalculationBound) {
    ["gross", "bonus", "advance", "withholding"].forEach((name) => {
      form.elements[name]?.addEventListener("input", calculate);
      form.elements[name]?.addEventListener("change", calculate);
    });
    form.dataset.autoCalculationBound = "1";
  }
  calculate();
}

async function handleLogin(event) {
  event.preventDefault();
  const form = new FormData(event.currentTarget);
  const identifiant = String(form.get("identifiant") || "").trim().toLowerCase();
  const password = String(form.get("password") || "").trim();
  if (!identifiant || !password) {
    setState({
      busy: false,
      loginDraft: { identifiant },
      error: "Veuillez saisir l'identifiant et le mot de passe.",
    });
    return;
  }
  saveConfig({
    apiUrl: String(form.get("apiUrl") || "").trim(),
    token: String(form.get("token") || "").trim(),
  });
  setState({ busy: true, error: "", loginDraft: { identifiant } });
  try {
    const user = await login(identifiant, password);
    setState({ user, activeModule: "dashboard", busy: false, error: "", loginDraft: { identifiant: "" } });
  } catch (error) {
    setState({
      busy: false,
      loginDraft: { identifiant },
      error: `${error.message} Vérifiez bien : identifiant a.kayembe et mot de passe 010203.`,
    });
  }
}

function updateDateFilter(moduleName, showAll) {
  const input = document.querySelector(`#${moduleName}Date`);
  const date = input?.value || todayIso();
  state.filters[moduleName] = { ...(state.filters[moduleName] || {}), date, all: showAll };
  setState({ filters: { ...state.filters }, error: "", notice: "" });
}

async function submitStockSupply(event) {
  event.preventDefault();
  try {
    actionGuard("stock");
    const form = new FormData(event.currentTarget);
    const args = [
      asRemoteDate(form.get("date")),
      Number(form.get("sacs") || 0),
      Number(form.get("paquets") || 0),
      Number(form.get("sel") || 0),
      Number(form.get("huile") || 0),
      String(form.get("observations") || ""),
    ];
    const id = Number(form.get("id") || 0);
    if (id) await rpc("update_stock_supply", [id, ...args]);
    else await rpc("add_stock_supply", args);
    setState({ notice: "Approvisionnement enregistré.", error: "", activeModule: "stock" });
  } catch (error) {
    setState({ error: error.message });
  }
}

async function submitStockExit(event) {
  event.preventDefault();
  try {
    actionGuard("stock");
    const form = new FormData(event.currentTarget);
    const args = [
      asRemoteDate(form.get("date")),
      Number(form.get("sacs") || 0),
      Number(form.get("paquets") || 0),
      Number(form.get("sel") || 0),
      Number(form.get("huile") || 0),
    ];
    const id = Number(form.get("id") || 0);
    if (id) await rpc("update_stock_exit", [id, ...args]);
    else await rpc("add_stock_exit", args);
    setState({ notice: "Sortie de stock enregistrée.", error: "", activeModule: "stock" });
  } catch (error) {
    setState({ error: error.message });
  }
}

async function submitProduction(event) {
  event.preventDefault();
  try {
    actionGuard("production");
    const form = new FormData(event.currentTarget);
    await rpc("save_production_day", [
      asRemoteDate(form.get("date")),
      Number(form.get("ordered") || 0),
      Number(form.get("dep") || 0),
      Number(form.get("mamans") || 0),
      Number(form.get("given") || 0),
      Number(form.get("samples") || 0),
      Number(form.get("remaining") || 0),
      Number(form.get("wasted") || 0),
      Number(form.get("sacks") || 0),
      String(form.get("observations") || ""),
    ]);
    setState({ notice: "Production enregistrée.", error: "", activeModule: "production" });
  } catch (error) {
    setState({ error: error.message });
  }
}

async function submitOrder(event) {
  event.preventDefault();
  try {
    actionGuard("orders");
    const form = new FormData(event.currentTarget);
    const amountDue = Number(form.get("due") || 0);
    const amountReceived = Number(form.get("received") || 0);
    if (amountReceived > amountDue) {
      throw new Error("Le montant reçu ne peut pas dépasser le montant à percevoir.");
    }
    const args = [
      asRemoteDate(form.get("date")),
      String(form.get("client") || ""),
      String(form.get("status") || ""),
      Number(form.get("trays") || 0),
      amountDue,
      amountReceived,
      Number(form.get("debt") || 0),
    ];
    const id = Number(form.get("id") || 0);
    if (id) await rpc("update_order", [id, ...args]);
    else await rpc("add_order", args);
    setState({ notice: "Commande enregistrée.", error: "", activeModule: "orders" });
  } catch (error) {
    setState({ error: error.message });
  }
}

async function submitCash(event) {
  event.preventDefault();
  try {
    actionGuard("cash");
    const form = new FormData(event.currentTarget);
    await rpc("save_cash_day", [
      asRemoteDate(form.get("date")),
      Number(form.get("expenses") || 0),
      String(form.get("expenseDetails") || ""),
      Number(form.get("paidDebts") || 0),
      String(form.get("paidDetails") || ""),
    ]);
    setState({ notice: "Caisse enregistrée.", error: "", activeModule: "cash" });
  } catch (error) {
    setState({ error: error.message });
  }
}

function submitWorkersFilter(event) {
  event.preventDefault();
  const form = new FormData(event.currentTarget);
  state.filters.workers = {
    ...(state.filters.workers || {}),
    start: String(form.get("start") || todayIso().slice(0, 8) + "01"),
    end: String(form.get("end") || todayIso()),
  };
  setState({ filters: { ...state.filters }, error: "", notice: "" });
}

async function submitWorker(event) {
  event.preventDefault();
  try {
    actionGuard("workers");
    const form = new FormData(event.currentTarget);
    const args = [
      String(form.get("fullName") || ""),
      String(form.get("function") || ""),
      String(form.get("phone") || ""),
      String(form.get("address") || ""),
      asRemoteDate(form.get("hireDate")),
      Number(form.get("salary") || 0),
      String(form.get("status") || "Actif"),
      String(form.get("observations") || ""),
    ];
    const id = Number(form.get("id") || 0);
    if (id) await rpc("update_worker", [id, ...args]);
    else await rpc("add_worker", args);
    setState({ notice: "Travailleur enregistré.", error: "", activeModule: "workers" });
  } catch (error) {
    setState({ error: error.message });
  }
}

async function submitPayroll(event) {
  event.preventDefault();
  try {
    actionGuard("workers");
    const form = new FormData(event.currentTarget);
    const gross = Number(form.get("gross") || 0);
    const bonus = Number(form.get("bonus") || 0);
    const advance = Number(form.get("advance") || 0);
    const withholding = Number(form.get("withholding") || 0);
    if (gross + bonus - advance - withholding < 0) {
      throw new Error("Le net à payer ne peut pas être négatif.");
    }
    const args = [
      Number(form.get("workerId") || 0),
      asRemoteDate(form.get("payDate")),
      String(form.get("period") || ""),
      gross,
      bonus,
      advance,
      withholding,
      String(form.get("paymentMode") || "Espèces"),
      String(form.get("status") || "Payée"),
      String(form.get("observations") || ""),
    ];
    const id = Number(form.get("id") || 0);
    if (id) await rpc("update_payroll", [id, ...args]);
    else await rpc("add_payroll", args);
    setState({ notice: "Paie enregistrée.", error: "", activeModule: "workers" });
  } catch (error) {
    setState({ error: error.message });
  }
}

async function submitUser(event) {
  event.preventDefault();
  try {
    actionGuard("users");
    const form = new FormData(event.currentTarget);
    const original = String(form.get("original") || "").trim();
    if (original) {
      await rpc("update_user", [
        original,
        String(form.get("fullName") || ""),
        String(form.get("password") || ""),
        String(form.get("role") || ""),
      ]);
    } else {
      await rpc("add_user", [
        String(form.get("fullName") || ""),
        String(form.get("username") || ""),
        String(form.get("password") || ""),
        String(form.get("role") || ""),
      ]);
    }
    setState({ notice: "Utilisateur enregistré.", error: "", activeModule: "users" });
  } catch (error) {
    setState({ error: error.message });
  }
}

function submitReportFilter(event) {
  event.preventDefault();
  const form = new FormData(event.currentTarget);
  state.filters.reports = {
    type: String(form.get("type") || "daily"),
    date: String(form.get("date") || todayIso()),
    start: String(form.get("start") || todayIso()),
    end: String(form.get("end") || todayIso()),
  };
  setState({ filters: { ...state.filters }, error: "", notice: "" });
}

async function submitClosure(event) {
  event.preventDefault();
  const submitter = event.submitter;
  const form = new FormData(event.currentTarget);
  const targetDate = String(form.get("date") || todayIso());
  try {
    if (submitter?.value === "reopen") {
      await rpc("reopen_day", [
        asRemoteDate(targetDate),
        state.user.identifiant,
        state.user.fullName,
        state.user.role,
        String(form.get("reason") || ""),
      ]);
      setState({ notice: "Journée réouverte.", error: "", activeModule: "closures" });
    } else {
      await rpc("close_day", [asRemoteDate(targetDate), state.user.identifiant, state.user.fullName, state.user.role]);
      setState({ notice: "Journée clôturée.", error: "", activeModule: "closures" });
    }
    state.filters.closures.date = targetDate;
  } catch (error) {
    setState({ error: error.message });
  }
}

async function submitPassword(event) {
  event.preventDefault();
  const form = new FormData(event.currentTarget);
  try {
    await rpc("change_user_password", [
      state.user.identifiant,
      String(form.get("current") || ""),
      String(form.get("next") || ""),
    ]);
    setState({ notice: "Mot de passe changé avec succès.", error: "", activeModule: "account" });
  } catch (error) {
    setState({ error: error.message });
  }
}

async function createBackup() {
  try {
    await rpc("backup_database");
    setState({ notice: "Sauvegarde créée.", error: "", activeModule: "backups" });
  } catch (error) {
    setState({ error: error.message });
  }
}

async function handleRowAction(action, row) {
  try {
    if (action === "load-supply") return fillStockSupply(row);
    if (action === "load-exit") return fillStockExit(row);
    if (action === "load-production") return fillProduction(row);
    if (action === "load-order") return fillOrder(row);
    if (action === "load-cash") return fillCash(row);
    if (action === "load-worker") return fillWorker(row);
    if (action === "load-payroll") return fillPayroll(row);
    if (action === "load-user") return loadUser(row);

    if (action.startsWith("delete") && !window.confirm("Confirmer la suppression ?")) return;
    if (action === "delete-supply") await rpc("delete_stock_supply", [Number(row.Id)]);
    if (action === "delete-exit") await rpc("delete_stock_exit", [Number(row.Id)]);
    if (action === "delete-production") await rpc("delete_production_day", [Number(row.Id)]);
    if (action === "delete-order") await rpc("delete_order", [Number(row.Id)]);
    if (action === "delete-cash") await rpc("delete_cash_day", [Number(row.Id)]);
    if (action === "delete-worker") await rpc("delete_worker", [Number(row.Id)]);
    if (action === "delete-payroll") await rpc("delete_payroll", [Number(row.Id)]);
    if (action === "delete-user") await rpc("delete_user", [String(row.Identifiant || "")]);
    if (action === "restore-backup") {
      if (!window.confirm("Restaurer cette sauvegarde ? Les données actuelles seront remplacées côté serveur.")) return;
      await rpc("restore_database", [String(row.CheminComplet || "")]);
    }
    setState({ notice: "Action effectuée.", error: "" });
  } catch (error) {
    setState({ error: error.message });
  }
}

function fillForm(formId, values) {
  const form = document.querySelector(formId);
  if (!form) return;
  Object.entries(values).forEach(([name, value]) => {
    const field = form.elements[name];
    if (field) field.value = value ?? "";
  });
  window.scrollTo({ top: 0, behavior: "smooth" });
}

function fillStockSupply(row) {
  fillForm("#stockSupplyForm", {
    id: row.Id,
    date: row.DateApprovisionnement,
    sacs: row.SacsAjoutes,
    paquets: row.PaquetsAjoutes,
    sel: row.KgSelAjoutes,
    huile: row.LitresHuileAjoutes,
    observations: row.Observations,
  });
}

function fillStockExit(row) {
  fillForm("#stockExitForm", {
    id: row.Id,
    date: row.DateSortie,
    sacs: row.SacsUtilises,
    paquets: row.PaquetsUtilises,
    sel: row.KgSelUtilises,
    huile: row.LitresHuileUtilises,
  });
}

function fillProduction(row) {
  fillForm("#productionForm", {
    date: row.DateProduction,
    ordered: row.NombreBacsCommandes,
    dep: row.NombreBacsLivresDepositaires,
    mamans: row.NombreBacsLivresMamans,
    given: row.NombreBacsDonnes,
    samples: row.NombreEchantillons,
    remaining: row.NombreBacsRestants,
    wasted: row.NombreBacsFoutus,
    sacks: row.NombreSacsUtilises,
    observations: row.Observations,
  });
  bindProductionAutoCalculations();
}

function fillOrder(row) {
  fillForm("#orderForm", {
    id: row.Id,
    date: row.DateCommande,
    client: row.Client,
    status: row.Statut,
    trays: row.NombreBacs,
    due: row.MontantAPercevoir,
    received: row.MontantRecu,
    debt: row.Dette,
  });
  bindOrderAutoCalculations();
}

function fillCash(row) {
  fillForm("#cashForm", {
    date: row.DateCaisse,
    expenses: row.MontantTotalDepenses,
    paidDebts: row.DettesPayeesAujourdHui,
    expenseDetails: row.DepensesEffectuees,
    paidDetails: row.DettesPayeesDetails,
  });
  bindCashAutoCalculations();
}

function fillWorker(row) {
  fillForm("#workerForm", {
    id: row.Id,
    fullName: row.NomComplet,
    function: row.Fonction,
    phone: row.Telephone,
    address: row.Adresse,
    hireDate: row.DateEmbauche,
    salary: row.SalaireMensuel,
    status: row.Statut,
    observations: row.Observations,
  });
}

function fillPayroll(row) {
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
  bindPayrollAutoCalculations();
}

async function loadUser(row) {
  const details = await rpc("get_user_for_admin_edit", [String(row.Identifiant || "")]);
  fillForm("#userForm", {
    original: details.Identifiant,
    fullName: details.NomComplet,
    username: details.Identifiant,
    password: details.MotDePasse,
    role: details.Role,
  });
}

function exportReportCsv() {
  const rows = [...document.querySelectorAll("#reportArea table tr")].map((tr) =>
    [...tr.children].map((cell) => `"${cell.textContent.replaceAll('"', '""')}"`).join(","),
  );
  const blob = new Blob([rows.join("\n") || "Rapport Boulangerie Lomoto"], { type: "text/csv;charset=utf-8" });
  const url = URL.createObjectURL(blob);
  const link = document.createElement("a");
  link.href = url;
  link.download = `rapport-boulangerie-lomoto-${todayIso()}.csv`;
  link.click();
  URL.revokeObjectURL(url);
}

render();
