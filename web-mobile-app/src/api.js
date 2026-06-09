const CONFIG_KEY = "lomoto.web.config";
const SESSION_KEY = "lomoto.web.session";

export function todayIso() {
  return new Date().toISOString().slice(0, 10);
}

function isHostedApp() {
  return typeof window !== "undefined" && window.location.protocol === "https:";
}

function isUnsafeHostedApiUrl(apiUrl) {
  const value = String(apiUrl || "").trim().toLowerCase();
  if (!value) return true;
  if (value.startsWith("http://127.") || value.startsWith("http://localhost")) return true;
  if (value.startsWith("http://192.168.") || value.startsWith("http://10.") || value.startsWith("http://172.")) return true;
  return isHostedApp() && !value.startsWith("https://");
}

export function loadConfig() {
  const fallbackUrl = import.meta.env?.VITE_API_URL || "http://127.0.0.1:8765";
  const fallbackToken = import.meta.env?.VITE_API_TOKEN || "";
  if (isHostedApp()) {
    return { apiUrl: fallbackUrl, token: fallbackToken };
  }
  try {
    const saved = JSON.parse(localStorage.getItem(CONFIG_KEY) || "{}");
    const savedApiUrl = String(saved.apiUrl || "").trim();
    const safeApiUrl = isHostedApp() && isUnsafeHostedApiUrl(savedApiUrl) ? fallbackUrl : savedApiUrl || fallbackUrl;
    return {
      apiUrl: safeApiUrl,
      token: saved.token || fallbackToken,
    };
  } catch {
    return { apiUrl: fallbackUrl, token: fallbackToken };
  }
}

export function saveConfig(config) {
  const fallbackUrl = import.meta.env?.VITE_API_URL || "http://127.0.0.1:8765";
  const fallbackToken = import.meta.env?.VITE_API_TOKEN || "";
  if (isHostedApp()) {
    localStorage.setItem(CONFIG_KEY, JSON.stringify({ apiUrl: fallbackUrl, token: fallbackToken }));
    return;
  }
  const apiUrl = isHostedApp() && isUnsafeHostedApiUrl(config.apiUrl) ? fallbackUrl : config.apiUrl;
  localStorage.setItem(CONFIG_KEY, JSON.stringify({ ...config, apiUrl }));
}

export function loadSession() {
  try {
    return JSON.parse(localStorage.getItem(SESSION_KEY) || "null");
  } catch {
    return null;
  }
}

export function saveSession(user) {
  localStorage.setItem(SESSION_KEY, JSON.stringify(user));
}

export function clearSession() {
  localStorage.removeItem(SESSION_KEY);
}

export function asRemoteDate(value) {
  return { __type__: "date", value };
}

export function deserialize(value) {
  if (Array.isArray(value)) {
    return value.map((item) => deserialize(item));
  }
  if (!value || typeof value !== "object") {
    return value;
  }
  if (value.__type__ === "date" || value.__type__ === "datetime" || value.__type__ === "path") {
    return value.value;
  }
  if (value.__type__ === "tuple") {
    return deserialize(value.items || []);
  }
  if (value.__type__ === "dataclass") {
    return deserialize(value.fields || {});
  }
  return Object.fromEntries(Object.entries(value).map(([key, item]) => [key, deserialize(item)]));
}

export function formatFc(value) {
  const number = Number(value || 0);
  return `${number.toLocaleString("fr-FR", { maximumFractionDigits: 0 })} FC`;
}

export function formatNumber(value) {
  const number = Number(value || 0);
  return Number.isInteger(number)
    ? String(number)
    : number.toLocaleString("fr-FR", { maximumFractionDigits: 2 });
}

export async function rpc(method, args = [], kwargs = {}) {
  const config = loadConfig();
  const session = loadSession();
  const endpoint = `${config.apiUrl.replace(/\/+$/, "")}/rpc`;
  const response = await fetch(endpoint, {
    method: "POST",
    headers: { "Content-Type": "application/json", Accept: "application/json" },
    body: JSON.stringify({
      token: config.token || "",
      session_token: session?.sessionToken || "",
      method,
      args,
      kwargs,
    }),
  });

  let payload;
  try {
    payload = await response.json();
  } catch (error) {
    throw new Error("Réponse illisible du serveur central.");
  }

  if (!response.ok || !payload.ok) {
    const message = payload?.error?.message || `Erreur HTTP ${response.status}`;
    throw new Error(message);
  }
  return deserialize(payload.result);
}

export async function login(identifiant, password) {
  let user;
  const cleanIdentifiant = String(identifiant || "").trim().toLowerCase();
  const cleanPassword = String(password || "").trim();
  try {
    user = await rpc("web_login", [cleanIdentifiant, cleanPassword]);
  } catch (error) {
    if (!String(error.message || "").toLowerCase().includes("autoris")) {
      throw error;
    }
    user = await rpc("find_user_for_login", [cleanIdentifiant, cleanPassword]);
  }
  if (!user) {
    throw new Error("Identifiant ou mot de passe incorrect.");
  }
  const session = {
    identifiant: user.identifiant || user.Identifiant || cleanIdentifiant,
    role: user.role || user.Role || "Utilisateur",
    fullName: user.fullName || user.full_name || user.NomComplet || user.identifiant || cleanIdentifiant,
    sessionToken: user.sessionToken || "",
  };
  saveSession(session);
  return session;
}
