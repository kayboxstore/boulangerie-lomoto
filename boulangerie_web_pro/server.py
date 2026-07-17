from __future__ import annotations

import argparse
import ctypes
import html
import hmac
import ipaddress
import json
import mimetypes
import os
import secrets
import shutil
import sys
import threading
import time
import traceback
import webbrowser
from dataclasses import asdict, is_dataclass
from datetime import date, datetime
from http import HTTPStatus
from http.cookies import SimpleCookie
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.parse import parse_qs, quote, urlparse
from urllib.request import Request, urlopen


ROOT = Path(__file__).resolve().parents[1]
STATIC_DIR = Path(__file__).resolve().parent / "static"
BRAND_ASSETS_DIR = ROOT / "boulangerie_app" / "assets"

if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from boulangerie_app.client_config import (  # noqa: E402
    client_summary,
    get_allowed_domains,
    get_logo_path,
    get_public_url,
    get_roles_config,
    get_watermark_path,
)
from boulangerie_app.database import APP_PUBLIC_URL, DatabaseHelper  # noqa: E402
from boulangerie_app.license_manager import (  # noqa: E402
    activate_device,
    deactivate_device,
    status_payload,
    validate_current_license,
)
from boulangerie_app.connected_mode import ConnectionSettings  # noqa: E402
from boulangerie_app.excel_reports import (  # noqa: E402
    create_daily_excel_report,
    create_monthly_excel_report,
    create_period_excel_report,
)
from boulangerie_app.reports import (  # noqa: E402
    create_daily_pdf_report,
    create_monthly_pdf_report,
    create_period_pdf_report,
)
from boulangerie_app.server_host import load_central_server_settings  # noqa: E402
from boulangerie_app.status_labels import normalize_status_form_label  # noqa: E402
from boulangerie_app.version import APP_NAME, APP_VERSION  # noqa: E402


SESSION_IDLE_TTL_SECONDS = 15 * 60
SESSION_ABSOLUTE_TTL_SECONDS = 8 * 60 * 60
MAX_JSON_BODY_BYTES = 256 * 1024
LOGIN_WINDOW_SECONDS = 15 * 60
LOGIN_FAILURES_PER_IP = 10
LOGIN_BLOCK_SECONDS = 15 * 60
SESSIONS: dict[str, dict[str, Any]] = {}
SESSIONS_LOCK = threading.Lock()
LOGIN_FAILURES: dict[str, list[float]] = {}
LOGIN_BLOCKED_UNTIL: dict[str, float] = {}
LOGIN_LOCK = threading.Lock()
ERROR_LOG_LOCK = threading.Lock()
REPORT_FILE_TOKENS: dict[str, dict[str, Any]] = {}
REPORT_FILE_TOKENS_LOCK = threading.Lock()
REPORT_FILE_TOKEN_TTL_SECONDS = 15 * 60
MAINTENANCE_TOKEN_FILENAME = "maintenance-token.txt"
PUBLIC_HOSTS = {
    "boulangerie-lomoto.com",
    "www.boulangerie-lomoto.com",
    "app.boulangerie-lomoto.com",
    *get_allowed_domains(),
}
LOCAL_HOSTS = {"localhost", "127.0.0.1", "::1"}
INTERNAL_MAINTENANCE_POST_PATHS = {
    "/api/internal/maintenance/automatic-backup",
    "/api/internal/maintenance/email-drain",
}
CSRF_EXEMPT_POST_PATHS = {
    "/api/login",
    "/api/setup",
    "/api/license/activate",
    *INTERNAL_MAINTENANCE_POST_PATHS,
}
RPC_CSRF_EXEMPT_METHODS = {"get_setup_status", "create_initial_admin", "web_login", "find_user_for_login"}


def _has_native_rpc_auth(payload: Any, expected_api_token: str) -> bool:
    if not isinstance(payload, dict):
        return False
    session_auth_required = str(
        os.environ.get("BOULANGERIE_REQUIRE_SESSION_AUTH", "1")
    ).strip().lower() not in {"0", "false", "no", "off"}
    if session_auth_required and str(payload.get("session_token", "") or "").strip():
        return True
    provided_token = str(payload.get("token", "") or "").strip()
    expected_token = str(expected_api_token or "").strip()
    return bool(
        provided_token
        and expected_token
        and hmac.compare_digest(provided_token, expected_token)
    )


ROLE_MODULES = {
    "Admin": [
        "dashboard",
        "cash",
        "stock",
        "production",
        "orders",
        "commissions",
        "workers",
        "users",
        "reports",
        "history",
        "activation",
        "system",
        "about",
    ],
    "Directeur Général": [
        "dashboard",
        "cash",
        "stock",
        "production",
        "orders",
        "commissions",
        "workers",
        "users",
        "reports",
        "history",
        "about",
    ],
    "Caissier": ["dashboard", "cash", "production", "orders", "commissions", "workers", "reports", "about"],
    "Chargé de la production": ["dashboard", "production", "reports", "about"],
    "Gestionnaire de stock": ["dashboard", "stock", "reports", "about"],
    "Gestionnaire des commandes": ["dashboard", "orders", "commissions", "reports", "about"],
}


def _apply_configured_role_modules() -> None:
    configured_roles = get_roles_config()
    if not configured_roles:
        return
    for role, modules in configured_roles.items():
        web_modules = [module for module in modules if module]
        if role == "Admin":
            for required_module in ("activation", "system", "about"):
                if required_module not in web_modules:
                    web_modules.append(required_module)
        if "about" not in web_modules:
            web_modules.append("about")
        if web_modules:
            ROLE_MODULES[role] = web_modules


_apply_configured_role_modules()

WRITE_MODULES_BY_ROLE = {
    "Admin": {"orders", "cash", "stock", "production", "workers", "users", "history", "closures", "backups"},
    "Directeur Général": {"history"},
    "Caissier": {"cash", "workers"},
    "Chargé de la production": {"production"},
    "Gestionnaire des commandes": {"orders"},
    "Gestionnaire de stock": {"stock"},
}

READ_ONLY_MODULES_BY_ROLE = {
    "Directeur Général": {"orders", "cash", "stock", "production", "commissions", "workers", "users"},
    "Caissier": {"orders", "production", "commissions"},
}

FULL_VISIBILITY_ROLES = {"Admin", "Directeur Général"}
CLOSURE_ROLES = {"Admin", "Directeur Général"}


class RateLimitError(Exception):
    def __init__(self, message: str, retry_after: int) -> None:
        super().__init__(message)
        self.retry_after = max(int(retry_after), 1)


def _json_default(value: Any) -> Any:
    if isinstance(value, (datetime, date)):
        return value.isoformat()
    if isinstance(value, Path):
        return str(value)
    if is_dataclass(value):
        return asdict(value)
    return str(value)


def _today() -> str:
    return date.today().isoformat()


def _current_month_start() -> str:
    return date.today().replace(day=1).isoformat()


def _date_value(value: Any) -> date:
    if isinstance(value, date) and not isinstance(value, datetime):
        return value
    text = _clean(value)
    if not text:
        return date.today()
    return datetime.strptime(text, "%Y-%m-%d").date()


def _money(value: Any) -> float:
    try:
        return float(value or 0)
    except (TypeError, ValueError):
        return 0.0


def _int(value: Any) -> int:
    try:
        return int(float(value or 0))
    except (TypeError, ValueError):
        return 0


def _clean(value: Any) -> str:
    return str(value or "").strip()


def _maintenance_token_path() -> Path:
    return DatabaseHelper.app_data_dir / MAINTENANCE_TOKEN_FILENAME


def _get_or_create_maintenance_token() -> str:
    token_path = _maintenance_token_path()
    try:
        token_path.parent.mkdir(parents=True, exist_ok=True)
        if token_path.exists():
            token = token_path.read_text(encoding="utf-8-sig").strip()
            if len(token) >= 32:
                return token
        token = secrets.token_urlsafe(48)
        temporary = token_path.with_suffix(".tmp")
        temporary.write_text(token, encoding="utf-8")
        os.replace(temporary, token_path)
        if os.name == "nt":
            os.system(
                f'icacls "{token_path}" /inheritance:r /grant:r "SYSTEM:(F)" "Administrators:(F)" >nul 2>&1'
            )
        return token
    except OSError as exc:
        raise RuntimeError("Jeton de maintenance local indisponible.") from exc


def _path_is_under(path: Path, root: Path) -> bool:
    try:
        path.resolve().relative_to(root.resolve())
        return True
    except (OSError, ValueError):
        return False


def _configured_asset_path(configured_path: str) -> Path | None:
    configured_path = str(configured_path or "").strip()
    if not configured_path:
        return None
    path = Path(configured_path)
    candidates = [path]
    if not path.is_absolute():
        candidates.extend([ROOT / path, BRAND_ASSETS_DIR / path.name, Path.cwd() / path])
    for candidate in candidates:
        if candidate.exists() and candidate.is_file():
            return candidate
    return None


def _brand_asset_path(asset_name: str) -> Path:
    normalized = asset_name.strip().lower()
    if normalized == "logo-boulangerie-lomoto.png":
        configured = _configured_asset_path(get_logo_path())
        if configured is not None:
            return configured
    if normalized == "logo-boulangerie-lomoto-watermark.png":
        configured = _configured_asset_path(get_watermark_path())
        if configured is not None:
            return configured
    return BRAND_ASSETS_DIR / asset_name


def _query_value(query: dict[str, list[str]], key: str, default: str = "") -> str:
    values = query.get(key)
    if not values:
        return default
    return values[0] or default


def _orders_summary_from_rows(rows: list[dict[str, Any]]) -> dict[str, Any]:
    accounted_received = sum(
        max(_money(row.get("MontantRecuCommande", _money(row.get("MontantRecu")) - _money(row.get("AvanceGeneree")))), 0)
        for row in rows
    )
    return {
        "NombreTotalBacs": sum(_int(row.get("NombreBacs")) for row in rows),
        "MontantAttendu": sum(_money(row.get("MontantAPercevoir")) for row in rows),
        "MontantRecu": accounted_received,
        "MontantRecuCommande": accounted_received,
        "MontantRecuBrut": sum(_money(row.get("MontantRecu")) for row in rows),
        "AvancesUtilisees": sum(_money(row.get("AvanceUtilisee")) for row in rows),
        "AvancesGenerees": sum(_money(row.get("AvanceGeneree")) for row in rows),
        "TotalDettes": sum(_money(row.get("Dette")) for row in rows),
    }


def _create_session(user: Any) -> dict[str, Any]:
    token = secrets.token_urlsafe(32)
    identifiant = str(getattr(user, "identifiant", "") or "")
    role = str(getattr(user, "role", "") or "")
    full_name = str(getattr(user, "full_name", "") or "").strip() or identifiant
    now = time.time()
    session = {
        "token": token,
        "csrfToken": secrets.token_urlsafe(32),
        "identifiant": identifiant,
        "role": role,
        "fullName": full_name,
        "createdAt": now,
        "expiresAt": now + SESSION_IDLE_TTL_SECONDS,
        "mustChangePassword": DatabaseHelper.is_using_default_password(identifiant),
    }
    with SESSIONS_LOCK:
        SESSIONS[token] = session
    return session


def _get_session(token: str) -> dict[str, Any] | None:
    if not token:
        return None
    now = time.time()
    with SESSIONS_LOCK:
        expired = [
            key
            for key, session in SESSIONS.items()
            if float(session.get("expiresAt", 0) or 0) < now
            or float(session.get("createdAt", 0) or 0) + SESSION_ABSOLUTE_TTL_SECONDS < now
        ]
        for key in expired:
            SESSIONS.pop(key, None)
        session = SESSIONS.get(token)
        if session is None:
            return None
        absolute_expiry = float(session.get("createdAt", now) or now) + SESSION_ABSOLUTE_TTL_SECONDS
        session["expiresAt"] = min(now + SESSION_IDLE_TTL_SECONDS, absolute_expiry)
        session_copy = dict(session)
    try:
        if not DatabaseHelper.validate_active_session(
            str(session_copy.get("identifiant", "")),
            token,
        ):
            _delete_session(token)
            return None
    except Exception:
        _delete_session(token)
        return None
    return session_copy


def _delete_session(token: str) -> None:
    with SESSIONS_LOCK:
        SESSIONS.pop(token, None)


def _delete_user_sessions(identifiant: str) -> None:
    with SESSIONS_LOCK:
        for token in [
            token
            for token, session in SESSIONS.items()
            if str(session.get("identifiant", "")).lower() == identifiant.lower()
        ]:
            SESSIONS.pop(token, None)
    try:
        DatabaseHelper.close_active_session(identifiant)
    except Exception:
        pass


def _trigger_email_delivery(limit: int = 20) -> dict[str, Any]:
    try:
        return DatabaseHelper.trigger_email_delivery_async(limit)
    except Exception:
        _log_internal_error("email delivery trigger")
        return {"queued": 0, "workerStarted": 0, "error": 1}


def _ensure_login_allowed(client_ip: str) -> None:
    now = time.time()
    with LOGIN_LOCK:
        blocked_until = float(LOGIN_BLOCKED_UNTIL.get(client_ip, 0) or 0)
        if blocked_until > now:
            raise RateLimitError(
                "Trop de tentatives de connexion. Réessayez dans quelques minutes.",
                int(blocked_until - now),
            )
        LOGIN_BLOCKED_UNTIL.pop(client_ip, None)
        LOGIN_FAILURES[client_ip] = [
            attempt
            for attempt in LOGIN_FAILURES.get(client_ip, [])
            if attempt > now - LOGIN_WINDOW_SECONDS
        ]


def _record_login_failure(client_ip: str) -> None:
    now = time.time()
    with LOGIN_LOCK:
        attempts = [
            attempt
            for attempt in LOGIN_FAILURES.get(client_ip, [])
            if attempt > now - LOGIN_WINDOW_SECONDS
        ]
        attempts.append(now)
        if len(attempts) >= LOGIN_FAILURES_PER_IP:
            LOGIN_FAILURES.pop(client_ip, None)
            LOGIN_BLOCKED_UNTIL[client_ip] = now + LOGIN_BLOCK_SECONDS
            raise RateLimitError(
                "Trop de tentatives de connexion. Réessayez dans 15 minutes.",
                LOGIN_BLOCK_SECONDS,
            )
        LOGIN_FAILURES[client_ip] = attempts


def _clear_login_failures(client_ip: str) -> None:
    with LOGIN_LOCK:
        LOGIN_FAILURES.pop(client_ip, None)
        LOGIN_BLOCKED_UNTIL.pop(client_ip, None)


def _log_login_failure(identifiant: str, client_ip: str) -> None:
    try:
        safe_identifiant = identifiant[:120] or "inconnu"
        DatabaseHelper.log_activity(
            safe_identifiant,
            safe_identifiant,
            "Non authentifié",
            "Sécurité",
            "Échec de connexion",
            f"Adresse IP : {client_ip[:64]}",
        )
    except Exception:
        return


def _log_internal_error(context: str) -> None:
    try:
        log_dir = DatabaseHelper.app_data_dir / "logs"
        log_dir.mkdir(parents=True, exist_ok=True)
        log_path = log_dir / "web-pro-errors.log"
        if log_path.exists() and log_path.stat().st_size > 2_000_000:
            rotated = log_dir / "web-pro-errors.previous.log"
            if rotated.exists():
                rotated.unlink()
            log_path.replace(rotated)
        entry = (
            f"\n[{datetime.now().isoformat(timespec='seconds')}] {context}\n"
            f"{traceback.format_exc()}"
        )
        with ERROR_LOG_LOCK:
            with log_path.open("a", encoding="utf-8") as stream:
                stream.write(entry)
    except Exception:
        return


def _create_report_file_token(session: dict[str, Any], file_path: Path) -> str:
    token = secrets.token_urlsafe(32)
    now = time.time()
    with REPORT_FILE_TOKENS_LOCK:
        expired = [
            key
            for key, value in REPORT_FILE_TOKENS.items()
            if float(value.get("expiresAt", 0) or 0) < now
        ]
        for key in expired:
            REPORT_FILE_TOKENS.pop(key, None)
        REPORT_FILE_TOKENS[token] = {
            "path": str(file_path.resolve()),
            "identifiant": str(session.get("identifiant", "")),
            "expiresAt": now + REPORT_FILE_TOKEN_TTL_SECONDS,
        }
    return token


def _get_report_file(token: str, session: dict[str, Any]) -> Path | None:
    now = time.time()
    with REPORT_FILE_TOKENS_LOCK:
        value = REPORT_FILE_TOKENS.get(token)
        if value is None or float(value.get("expiresAt", 0) or 0) < now:
            REPORT_FILE_TOKENS.pop(token, None)
            return None
        token_owner = str(value.get("identifiant", ""))
        session_owner = str(session.get("identifiant", ""))
        if not hmac.compare_digest(token_owner, session_owner):
            return None
        report_path = Path(str(value.get("path", ""))).resolve()
        reports_dir = DatabaseHelper.get_reports_dir_for_user(session_owner).resolve()
        if not _path_is_under(report_path, reports_dir):
            return None
        return report_path


def _modules_for(role: str) -> list[str]:
    return ROLE_MODULES.get(role, ["dashboard"])


def _can_write(role: str, module: str) -> bool:
    return module in WRITE_MODULES_BY_ROLE.get(role, set())


def _is_read_only(role: str, module: str) -> bool:
    return module in READ_ONLY_MODULES_BY_ROLE.get(role, set())


def _require_module(session: dict[str, Any], module: str, *, write: bool = False) -> None:
    role = str(session.get("role", ""))
    if module not in _modules_for(role):
        raise PermissionError("Module non autorisé pour votre rôle.")
    if write and not _can_write(role, module):
        raise PermissionError("Votre rôle peut consulter ce module, mais ne peut pas le modifier.")


def _require_admin(session: dict[str, Any], action: str = "cette action") -> None:
    if str(session.get("role", "")) != "Admin":
        raise PermissionError(f"Seul l'administrateur peut effectuer {action}.")


def _is_admin(session: dict[str, Any]) -> bool:
    return str(session.get("role", "")) == "Admin"


def _require_closure_role(session: dict[str, Any]) -> None:
    if str(session.get("role", "")) not in CLOSURE_ROLES:
        raise PermissionError("Seuls l'Admin et le Directeur Général peuvent clôturer une journée.")


def _log_web_activity(session: dict[str, Any], module: str, action: str, details: str = "") -> None:
    try:
        DatabaseHelper.log_activity(
            str(session.get("identifiant", "")),
            str(session.get("fullName", "") or session.get("identifiant", "")),
            str(session.get("role", "")),
            module,
            action,
            details,
        )
    except Exception:
        return


def _open_local_path(path: Path) -> bool:
    if os.name == "nt":
        try:
            session_id = ctypes.c_ulong()
            if not ctypes.windll.kernel32.ProcessIdToSessionId(
                os.getpid(),
                ctypes.byref(session_id),
            ):
                return False
            if session_id.value == 0:
                return False
        except Exception:
            return False
    try:
        target = Path(path)
        if hasattr(os, "startfile"):
            os.startfile(str(target))
        else:
            webbrowser.open(target.as_uri())
        return True
    except Exception:
        return False


def _report_destination(
    session: dict[str, Any],
    report_type: str,
    report_format: str,
    selected_date: date,
    start: date,
    end: date,
) -> Path:
    reports_dir = DatabaseHelper.get_reports_dir_for_user(str(session.get("identifiant", "")))
    reports_dir.mkdir(parents=True, exist_ok=True)
    timestamp = datetime.now().strftime("%H%M%S")
    if report_format == "excel":
        extension = ".xlsx"
        if report_type == "monthly":
            stem = f"rapport-excel-mensuel-{selected_date.strftime('%Y%m')}"
        elif report_type == "period":
            stem = f"rapport-excel-periode-{start.strftime('%Y%m%d')}-{end.strftime('%Y%m%d')}"
        else:
            stem = f"rapport-excel-journalier-{selected_date.strftime('%Y%m%d')}"
    else:
        extension = ".pdf"
        if report_type == "monthly":
            stem = f"rapport-mensuel-{selected_date.strftime('%Y%m')}"
        elif report_type == "period":
            stem = f"rapport-periode-{start.strftime('%Y%m%d')}-{end.strftime('%Y%m%d')}"
        else:
            stem = f"rapport-journalier-{selected_date.strftime('%Y%m%d')}"
    return reports_dir / f"{stem}-{timestamp}{extension}"


def _public_session(session: dict[str, Any]) -> dict[str, Any]:
    role = str(session.get("role", ""))
    return {
        "identifiant": session.get("identifiant", ""),
        "role": role,
        "fullName": session.get("fullName", ""),
        "appName": APP_NAME,
        "appVersion": APP_VERSION,
        "client": client_summary(),
        "modules": _modules_for(role),
        "readOnlyModules": sorted(READ_ONLY_MODULES_BY_ROLE.get(role, set())),
        "csrfToken": session.get("csrfToken", ""),
        "mustChangePassword": bool(session.get("mustChangePassword", False)),
    }


def _dashboard_payload(session: dict[str, Any]) -> dict[str, Any]:
    role = str(session.get("role", ""))
    today = _today()
    month_start = _current_month_start()
    payload: dict[str, Any] = {
        "today": today,
        "periodLabel": datetime.strptime(month_start, "%Y-%m-%d").strftime("%m/%Y"),
        "cards": [],
        "alerts": [],
        "recentActivity": [],
        "charts": [],
    }
    full_visibility = role in FULL_VISIBILITY_ROLES

    if full_visibility or role == "Gestionnaire de stock":
        stock = DatabaseHelper.get_stock_summary()
        payload["stock"] = stock
        payload["cards"].append({"label": "Farine restante", "value": stock.get("FarineRestante", 0), "unit": "sacs", "primary": True})
        payload["cards"].append({"label": "Approvisionnements du mois", "value": DatabaseHelper.count_stock_supplies_for_period(month_start, today), "unit": "entrées"})
        payload["cards"].append({"label": "Sorties stock du mois", "value": DatabaseHelper.count_stock_exits_for_period(month_start, today), "unit": "sorties"})
        payload["charts"].append(
            {
                "title": "Stock matières",
                "type": "bars",
                "items": [
                    {"label": "Farine", "value": stock.get("FarineRestante", 0), "unit": "sacs"},
                    {"label": "Levure", "value": stock.get("LevureRestante", 0), "unit": "paquets"},
                    {"label": "Sel", "value": stock.get("SelRestant", 0), "unit": "kg"},
                    {"label": "Huile", "value": stock.get("HuileRestante", 0), "unit": "L"},
                ],
            }
        )
        payload["alerts"].extend(
            {
                "type": "stock",
                "title": str(row.get("Article", "")),
                "message": f"Stock restant : {row.get('StockRestant', 0)} {row.get('Unite', '')}",
            }
            for row in DatabaseHelper.get_low_stock_alerts()
        )

    if full_visibility or role in {"Gestionnaire des commandes", "Caissier"}:
        orders = DatabaseHelper.get_orders_summary_for_period(month_start, today)
        outstanding_orders = DatabaseHelper.get_global_orders_summary()
        orders["TotalDettes"] = outstanding_orders.get("TotalDettes", 0)
        orders["NombreAvecDette"] = outstanding_orders.get("NombreAvecDette", 0)
        orders["AvancesDisponibles"] = outstanding_orders.get("AvancesDisponibles", 0)
        payload["orders"] = orders
        payload["cards"].append({"label": "Commandes du mois", "value": orders.get("NombreCommandes", 0), "unit": "commandes"})
        payload["cards"].append({"label": "Reçu commandes ce mois", "value": orders.get("MontantRecu", 0), "unit": "FC", "money": True, "primary": True})
        payload["cards"].append({"label": "Dettes non payées", "value": orders.get("TotalDettes", 0), "unit": "FC", "money": True, "primary": True})
        payload["cards"].append({"label": "Avances clients", "value": orders.get("AvancesDisponibles", 0), "unit": "FC", "money": True})
        payload["charts"].append(
            {
                "title": "Commandes et paiements",
                "type": "bars",
                "items": [
                    {"label": "Attendu", "value": orders.get("MontantAttendu", 0), "unit": "FC", "money": True},
                    {"label": "Reçu", "value": orders.get("MontantRecu", 0), "unit": "FC", "money": True},
                    {"label": "Dettes", "value": orders.get("TotalDettes", 0), "unit": "FC", "money": True},
                    {"label": "Avances", "value": orders.get("AvancesDisponibles", 0), "unit": "FC", "money": True},
                ],
            }
        )
        payload["charts"].append(
            {
                "title": "Santé commandes",
                "type": "donut",
                "items": [
                    {
                        "label": "Sans dette",
                        "value": max(_int(orders.get("NombreCommandes")) - _int(orders.get("NombreAvecDette")), 0),
                        "unit": "cmd",
                    },
                    {"label": "Avec dette", "value": orders.get("NombreAvecDette", 0), "unit": "cmd"},
                ],
            }
        )
        payload["alerts"].extend(
            {
                "type": "debt",
                "title": str(row.get("Client", "")),
                "message": f"Dette totale : {row.get('DetteTotale', 0)} FC",
            }
            for row in DatabaseHelper.get_debt_alerts(6)
        )

    if full_visibility or role == "Chargé de la production":
        production = DatabaseHelper.get_production_summary_for_period(month_start, today)
        payload["production"] = production
        payload["cards"].extend(
            [
                {"label": "Bacs commandés ce mois", "value": production.get("TotalBacsCommandes", 0), "unit": "bacs"},
                {"label": "Bacs produits ce mois", "value": production.get("TotalBacsProduits", 0), "unit": "bacs"},
                {"label": "Bacs restants ce mois", "value": production.get("TotalBacsRestants", 0), "unit": "bacs"},
                {"label": "Bacs foutus ce mois", "value": production.get("TotalBacsFoutus", 0), "unit": "bacs"},
            ]
        )
        payload["charts"].append(
            {
                "title": "Production mensuelle",
                "type": "bars",
                "items": [
                    {"label": "Commandés", "value": production.get("TotalBacsCommandes", 0), "unit": "bacs"},
                    {"label": "Produits", "value": production.get("TotalBacsProduits", 0), "unit": "bacs"},
                    {"label": "Restants", "value": production.get("TotalBacsRestants", 0), "unit": "bacs"},
                    {"label": "Foutus", "value": production.get("TotalBacsFoutus", 0), "unit": "bacs"},
                ],
            }
        )

    if full_visibility or role == "Caissier":
        workers = DatabaseHelper.get_workers_payroll_summary(month_start, today)
        payload["workers"] = workers
        cash_total = DatabaseHelper.get_cash_total_for_period(month_start, today)
        payload["cards"].append({"label": "Solde caisse du mois", "value": cash_total, "unit": "FC", "money": True, "primary": True})
        payload["cards"].append({"label": "Travailleurs actifs", "value": workers.get("TravailleursActifs", 0), "unit": "personnes"})
        payload["cards"].append({"label": "Paies payées du mois", "value": workers.get("TotalPaye", 0), "unit": "FC", "money": True})
        payload["cards"].append({"label": "Paies non payées", "value": workers.get("TotalNonPaye", 0), "unit": "FC", "money": True, "primary": True})
        payload["charts"].append(
            {
                "title": "Caisse et paies",
                "type": "bars",
                "items": [
                    {"label": "Caisse", "value": cash_total, "unit": "FC", "money": True},
                    {"label": "Paies payées", "value": workers.get("TotalPaye", 0), "unit": "FC", "money": True},
                    {"label": "Paies non payées", "value": workers.get("TotalNonPaye", 0), "unit": "FC", "money": True},
                ],
            }
        )

    if full_visibility or role == "Gestionnaire des commandes":
        commission_total = DatabaseHelper.get_total_commissions()
        payload["cards"].append({"label": "Commissions non payées", "value": commission_total, "unit": "FC", "money": True, "primary": True})
        payload["charts"].append(
            {
                "title": "Commissions",
                "type": "bars",
                "items": [
                    {"label": "Non payées", "value": commission_total, "unit": "FC", "money": True},
                    {"label": "Commandes dette", "value": DatabaseHelper.count_orders_with_debt(), "unit": "clients"},
                ],
            }
        )

    if full_visibility:
        payload["cards"].append({"label": "Utilisateurs", "value": DatabaseHelper.count_users(), "unit": "comptes"})
        payload["cards"].append({"label": "Commandes avec dette", "value": DatabaseHelper.count_orders_with_debt(), "unit": "clients"})
        payload["recentActivity"] = DatabaseHelper.get_recent_activity_summary(10)

    return payload


def _format_system_bytes(size: int | float) -> str:
    value = float(size or 0)
    units = ["o", "Ko", "Mo", "Go", "To"]
    unit_index = 0
    while value >= 1024 and unit_index < len(units) - 1:
        value /= 1024
        unit_index += 1
    if unit_index == 0:
        return f"{int(value)} {units[unit_index]}"
    return f"{value:.1f} {units[unit_index]}"


def _system_status_payload() -> dict[str, Any]:
    DatabaseHelper.initialize_database()
    db_path = DatabaseHelper.db_path
    db_size = db_path.stat().st_size if db_path.exists() else 0
    storage_root = DatabaseHelper.app_data_dir
    try:
        disk = shutil.disk_usage(storage_root)
        disk_payload = {
            "total": disk.total,
            "used": disk.used,
            "free": disk.free,
            "totalLabel": _format_system_bytes(disk.total),
            "usedLabel": _format_system_bytes(disk.used),
            "freeLabel": _format_system_bytes(disk.free),
        }
    except OSError:
        disk_payload = {}

    archives_dir = DatabaseHelper.reports_dir / "archives"
    archive_files: list[dict[str, Any]] = []
    if archives_dir.exists():
        for archive_path in sorted(archives_dir.glob("*.csv"), key=lambda path: path.stat().st_mtime, reverse=True)[:5]:
            try:
                stat = archive_path.stat()
            except OSError:
                continue
            archive_files.append(
                {
                    "NomFichier": archive_path.name,
                    "CheminComplet": archive_path,
                    "TailleOctets": stat.st_size,
                    "Taille": _format_system_bytes(stat.st_size),
                    "DateModification": datetime.fromtimestamp(stat.st_mtime),
                }
            )

    backups = DatabaseHelper.list_backup_files(8)
    for backup in backups:
        backup["Taille"] = _format_system_bytes(int(backup.get("TailleOctets", 0) or 0))
    automatic_backups = [
        backup
        for backup in backups
        if str(backup.get("NomFichier", "")).startswith("sauvegarde-automatique-")
    ]
    maintenance_token_exists = _maintenance_token_path().exists()

    return {
        "appName": APP_NAME,
        "version": APP_VERSION,
        "publicUrl": APP_PUBLIC_URL,
        "serverTime": datetime.now().isoformat(timespec="seconds"),
        "database": {
            "path": db_path,
            "exists": db_path.exists(),
            "size": db_size,
            "sizeLabel": _format_system_bytes(db_size),
        },
        "paths": {
            "data": storage_root,
            "reports": DatabaseHelper.reports_dir,
            "backups": DatabaseHelper.backups_dir,
            "archives": archives_dir,
        },
        "disk": disk_payload,
        "backups": backups,
        "automaticBackups": {
            "last": automatic_backups[0] if automatic_backups else None,
            "tokenReady": maintenance_token_exists,
            "tokenPath": _maintenance_token_path(),
            "localStatusUrl": "http://127.0.0.1:8787/api/internal/maintenance/status",
        },
        "archives": archive_files,
        "email": DatabaseHelper.get_email_notification_status(),
        "sessions": DatabaseHelper.list_active_sessions(),
        "license": status_payload(DatabaseHelper.app_data_dir, domain=APP_PUBLIC_URL),
    }


def _public_config_payload() -> dict[str, Any]:
    return {
        "appName": APP_NAME,
        "appVersion": APP_VERSION,
        "client": client_summary(),
    }


def _safe_license_payload(data: dict[str, Any], *, include_private: bool = False) -> dict[str, Any]:
    safe = dict(data)
    if not include_private:
        safe.pop("licensePath", None)
        safe.pop("registryPath", None)
        safe.pop("payload", None)
        safe["activations"] = [
            {
                "deviceName": item.get("deviceName", ""),
                "activatedAt": item.get("activatedAt", ""),
                "lastSeenAt": item.get("lastSeenAt", ""),
            }
            for item in safe.get("activations", [])
            if isinstance(item, dict)
        ]
    return safe


class WebProHandler(BaseHTTPRequestHandler):
    server_version = APP_NAME
    sys_version = ""

    def do_OPTIONS(self) -> None:  # noqa: N802
        if not self._require_allowed_host():
            return
        if self._redirect_external_http_to_https():
            return
        self.send_response(HTTPStatus.NO_CONTENT)
        self._common_headers()
        self.end_headers()

    def do_GET(self) -> None:  # noqa: N802
        if not self._require_allowed_host():
            return
        if self._redirect_external_http_to_https():
            return
        parsed = urlparse(self.path)
        try:
            if parsed.path == "/health":
                settings = load_central_server_settings()
                self._send_json(
                    {
                        "ok": True,
                        "app_name": APP_NAME,
                        "app_version": APP_VERSION,
                        "server_port": settings.normalized_port(),
                        "token_required": bool(settings.normalized_token()),
                    }
                )
                return
            if parsed.path.startswith("/api/"):
                self._handle_api_get(parsed.path, parse_qs(parsed.query))
                return
            self._serve_static(parsed.path)
        except PermissionError as exc:
            self._send_json({"ok": False, "error": str(exc)}, HTTPStatus.FORBIDDEN)
        except Exception:
            _log_internal_error(f"GET {parsed.path}")
            self._send_json(
                {"ok": False, "error": "Une erreur interne est survenue."},
                HTTPStatus.INTERNAL_SERVER_ERROR,
            )

    def do_POST(self) -> None:  # noqa: N802
        if not self._require_allowed_host():
            return
        if self._redirect_external_http_to_https():
            return
        parsed = urlparse(self.path)
        try:
            self._require_same_origin()
            if parsed.path not in CSRF_EXEMPT_POST_PATHS and parsed.path != "/rpc":
                self._require_valid_csrf()
            if parsed.path == "/rpc":
                self._proxy_rpc_request()
                return
            self._handle_api_post(parsed.path, self._read_json())
        except RateLimitError as exc:
            self._send_json(
                {"ok": False, "error": str(exc)},
                HTTPStatus.TOO_MANY_REQUESTS,
                [("Retry-After", str(exc.retry_after))],
            )
        except PermissionError as exc:
            self._send_json({"ok": False, "error": str(exc)}, HTTPStatus.FORBIDDEN)
        except ValueError as exc:
            self._send_json({"ok": False, "error": str(exc)}, HTTPStatus.BAD_REQUEST)
        except Exception:
            _log_internal_error(f"POST {parsed.path}")
            self._send_json(
                {"ok": False, "error": "Une erreur interne est survenue."},
                HTTPStatus.INTERNAL_SERVER_ERROR,
            )

    def do_DELETE(self) -> None:  # noqa: N802
        if not self._require_allowed_host():
            return
        if self._redirect_external_http_to_https():
            return
        parsed = urlparse(self.path)
        try:
            self._require_same_origin()
            self._require_valid_csrf()
            self._handle_api_delete(parsed.path, parse_qs(parsed.query))
        except PermissionError as exc:
            self._send_json({"ok": False, "error": str(exc)}, HTTPStatus.FORBIDDEN)
        except ValueError as exc:
            self._send_json({"ok": False, "error": str(exc)}, HTTPStatus.BAD_REQUEST)
        except Exception:
            _log_internal_error(f"DELETE {parsed.path}")
            self._send_json(
                {"ok": False, "error": "Une erreur interne est survenue."},
                HTTPStatus.INTERNAL_SERVER_ERROR,
            )

    def log_message(self, format: str, *args: Any) -> None:  # noqa: A003
        return

    def _client_ip(self) -> str:
        if self.headers.get("CF-Ray") and self.headers.get("CF-Connecting-IP"):
            return str(self.headers.get("CF-Connecting-IP", "")).strip()
        return str(self.client_address[0] or "").strip()

    def _request_host(self) -> str:
        host_header = str(self.headers.get("Host", "") or "").split(",", 1)[0].strip().lower()
        if host_header.startswith("[") and "]" in host_header:
            return host_header[1:].split("]", 1)[0].rstrip(".")
        return host_header.split(":", 1)[0].rstrip(".")

    def _require_allowed_host(self) -> bool:
        host = self._request_host()
        if host in PUBLIC_HOSTS or host in LOCAL_HOSTS:
            return True
        try:
            address = ipaddress.ip_address(host)
            if address.is_private or address.is_loopback:
                return True
        except ValueError:
            pass

        payload = {"ok": False, "error": "Hôte non autorisé."}
        data = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        self.send_response(HTTPStatus.MISDIRECTED_REQUEST)
        self._common_headers(content_type="application/json; charset=utf-8", content_length=len(data))
        self.end_headers()
        self.wfile.write(data)
        return False

    def _is_local_client(self) -> bool:
        try:
            address = ipaddress.ip_address(self._client_ip())
            return bool(address.is_private or address.is_loopback)
        except ValueError:
            return False

    def _is_server_console_client(self) -> bool:
        if any(
            str(self.headers.get(header_name, "") or "").strip()
            for header_name in ("CF-Connecting-IP", "X-Forwarded-For", "Forwarded")
        ):
            return False
        try:
            peer_address = ipaddress.ip_address(str(self.client_address[0] or "").split("%", 1)[0])
            effective_address = ipaddress.ip_address(self._client_ip().split("%", 1)[0])
            return bool(peer_address.is_loopback and effective_address.is_loopback)
        except ValueError:
            return False

    def _license_domain(self) -> str:
        host = self._request_host()
        if host in LOCAL_HOSTS:
            return ""
        try:
            address = ipaddress.ip_address(host)
            if address.is_private or address.is_loopback:
                return ""
        except ValueError:
            pass
        return host

    def _require_license_active(self) -> None:
        data = status_payload(DatabaseHelper.app_data_dir, domain=self._license_domain())
        if data.get("required") and not data.get("ok"):
            raise PermissionError(str(data.get("message") or "Licence non valide."))

    def _require_internal_maintenance_token(self) -> None:
        if not self._is_local_client():
            raise PermissionError("Maintenance locale reservee au PC serveur.")
        provided = str(self.headers.get("X-Lomoto-Maintenance-Token", "") or "").strip()
        if not provided:
            provided = self._bearer_token()
        expected = _get_or_create_maintenance_token()
        if not provided or not hmac.compare_digest(provided, expected):
            raise PermissionError("Jeton de maintenance invalide.")

    def _require_same_origin(self) -> None:
        origin = str(self.headers.get("Origin", "") or "").strip()
        if not origin:
            return
        parsed_origin = urlparse(origin)
        origin_host = (parsed_origin.hostname or "").lower()
        request_host = str(self.headers.get("Host", "")).split(":", 1)[0].strip().lower()
        forwarded_host = (
            str(self.headers.get("X-Forwarded-Host", "")).split(",", 1)[0].split(":", 1)[0].strip().lower()
        )
        if origin_host and origin_host in {request_host, forwarded_host}:
            return
        if self.headers.get("CF-Ray") and parsed_origin.scheme.lower() == "https" and origin_host in PUBLIC_HOSTS:
            return
        raise PermissionError("Origine de la requête non autorisée.")

    def _require_valid_csrf(self) -> None:
        session = _get_session(self._session_token())
        if session is None:
            raise PermissionError("Session expirée. Veuillez vous reconnecter.")
        expected = str(session.get("csrfToken", "") or "")
        provided = str(self.headers.get("X-CSRF-Token", "") or "").strip()
        if not expected or not provided or not hmac.compare_digest(expected, provided):
            raise PermissionError("Jeton de sécurité invalide. Rechargez la page puis recommencez.")

    def _is_public_https(self) -> bool:
        forwarded_scheme = str(self.headers.get("X-Forwarded-Proto", "")).split(",", 1)[0].strip().lower()
        if forwarded_scheme == "https":
            return True
        try:
            cf_visitor = json.loads(str(self.headers.get("CF-Visitor", "") or "{}"))
            return str(cf_visitor.get("scheme", "")).strip().lower() == "https"
        except (TypeError, ValueError):
            return False

    def _session_token(self) -> str:
        bearer = self._bearer_token()
        if bearer:
            return bearer
        cookie = SimpleCookie()
        try:
            cookie.load(str(self.headers.get("Cookie", "") or ""))
        except Exception:
            return ""
        for name in ("__Host-lomoto_session", "lomoto_local_session"):
            if name in cookie:
                return str(cookie[name].value or "").strip()
        return ""

    def _session_cookie_headers(self, token: str = "", *, clear: bool = False) -> list[tuple[str, str]]:
        max_age = 0 if clear else SESSION_ABSOLUTE_TTL_SECONDS
        value = "" if clear else token
        suffix = f"Path=/; Max-Age={max_age}; HttpOnly; SameSite=Strict"
        headers = [
            ("Set-Cookie", f"lomoto_local_session={value}; {suffix}"),
            ("Set-Cookie", f"__Host-lomoto_session={value}; {suffix}; Secure"),
        ]
        if not clear:
            return [headers[1] if self._is_public_https() else headers[0]]
        return headers

    def _redirect_external_http_to_https(self) -> bool:
        forwarded_scheme = str(self.headers.get("X-Forwarded-Proto", "")).split(",", 1)[0].strip().lower()
        if not forwarded_scheme:
            try:
                cf_visitor = json.loads(str(self.headers.get("CF-Visitor", "") or "{}"))
                forwarded_scheme = str(cf_visitor.get("scheme", "")).strip().lower()
            except (TypeError, ValueError):
                forwarded_scheme = ""
        if forwarded_scheme != "http":
            return False

        requested_host = str(self.headers.get("Host", "")).split(":", 1)[0].strip().lower()
        target_host = requested_host if requested_host in PUBLIC_HOSTS else "app.boulangerie-lomoto.com"
        self.send_response(HTTPStatus.PERMANENT_REDIRECT)
        self.send_header("Location", f"https://{target_host}{self.path}")
        self._common_headers(content_length=0)
        self.end_headers()
        return True

    def _proxy_rpc_request(self) -> None:
        length = int(self.headers.get("Content-Length", "0") or 0)
        if length < 0 or length > MAX_JSON_BODY_BYTES:
            raise ValueError("La requête dépasse la taille autorisée.")
        body = self.rfile.read(length) if length else b"{}"
        try:
            rpc_payload = json.loads(body.decode("utf-8-sig") or "{}")
        except (UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise ValueError("Requête distante invalide.") from exc
        method_name = str(rpc_payload.get("method", "") if isinstance(rpc_payload, dict) else "").strip()
        settings = load_central_server_settings()
        if method_name not in RPC_CSRF_EXEMPT_METHODS and not _has_native_rpc_auth(
            rpc_payload,
            settings.normalized_token(),
        ):
            self._require_valid_csrf()
        client_ip = self._client_ip()
        if method_name == "create_initial_admin" and not self._is_server_console_client():
            raise PermissionError("La configuration initiale doit être effectuée sur le PC serveur.")
        if method_name in {"web_login", "find_user_for_login"}:
            _ensure_login_allowed(client_ip)
        if isinstance(rpc_payload, dict) and settings.normalized_token():
            rpc_payload["token"] = settings.normalized_token()
            body = json.dumps(rpc_payload, ensure_ascii=True, default=_json_default).encode("utf-8")
        request = Request(
            f"http://127.0.0.1:{settings.normalized_port()}/rpc",
            data=body,
            headers={"Content-Type": "application/json", "Accept": "application/json"},
            method="POST",
        )
        try:
            with urlopen(request, timeout=30) as response:
                response_body = response.read()
                status = response.status
        except HTTPError as exc:
            response_body = exc.read()
            status = exc.code
        except URLError as exc:
            raise RuntimeError("Le serveur central de données est indisponible.") from exc

        if method_name in {"web_login", "find_user_for_login"}:
            try:
                rpc_response = json.loads(response_body.decode("utf-8-sig") or "{}")
                result = rpc_response.get("result") if isinstance(rpc_response, dict) else None
                if status >= 400 or not result:
                    _record_login_failure(client_ip)
                else:
                    _clear_login_failures(client_ip)
            except (UnicodeDecodeError, json.JSONDecodeError):
                _record_login_failure(client_ip)

        self.send_response(status)
        self._common_headers(
            content_type="application/json; charset=utf-8",
            content_length=len(response_body),
        )
        self.end_headers()
        self.wfile.write(response_body)

    def _handle_api_get(self, path: str, query: dict[str, list[str]]) -> None:
        if path == "/api/health":
            self._send_json({"ok": True, "app": APP_NAME, "version": APP_VERSION})
            return
        if path == "/api/config":
            self._send_json({"ok": True, **_public_config_payload()})
            return
        if path == "/api/setup/status":
            self._send_json({"ok": True, "required": DatabaseHelper.count_users() == 0})
            return
        if path == "/api/internal/maintenance/status":
            self._require_internal_maintenance_token()
            self._send_json(
                {
                    "ok": True,
                    "app": APP_NAME,
                    "version": APP_VERSION,
                    "serverTime": datetime.now().isoformat(timespec="seconds"),
                    "database": str(DatabaseHelper.db_path),
                    "backups": DatabaseHelper.list_backup_files(5),
                    "email": DatabaseHelper.get_email_notification_status(),
                }
            )
            return
        if path == "/api/license/status":
            session = _get_session(self._session_token())
            include_private = bool(session and str(session.get("role", "")) == "Admin")
            self._send_json(
                {
                    "ok": True,
                    "status": _safe_license_payload(
                        status_payload(DatabaseHelper.app_data_dir, domain=self._license_domain()),
                        include_private=include_private,
                    ),
                }
            )
            return
        if path == "/api/reports/file":
            self._require_license_active()
            session = self._require_session()
            report_path = _get_report_file(_query_value(query, "token", ""), session)
            if report_path is None or not report_path.exists() or not report_path.is_file():
                raise PermissionError("Ce lien de rapport est expiré ou invalide.")
            self._send_path(report_path)
            return

        self._require_license_active()
        session = self._require_session()
        if path == "/api/me":
            self._send_json({"ok": True, "user": _public_session(session)})
            return
        if path == "/api/session/ping":
            self._send_json({"ok": True, "user": _public_session(session)})
            return
        if session.get("mustChangePassword"):
            raise PermissionError("Vous devez changer le mot de passe initial avant de continuer.")
        if path == "/api/dashboard":
            self._send_json({"ok": True, "data": _dashboard_payload(session)})
            return
        if path == "/api/system/status":
            _require_admin(session, "l'etat systeme")
            self._send_json({"ok": True, "data": _system_status_payload()})
            return
        if path == "/api/orders":
            _require_module(session, "orders")
            selected_date = _query_value(query, "date", _today())
            selected_date_value = _date_value(selected_date)
            show_all = _query_value(query, "all", "0") == "1"
            status_filter = _query_value(query, "status", "all").strip()
            rows = DatabaseHelper.list_orders() if show_all else DatabaseHelper.list_orders_by_date(selected_date_value)
            if status_filter in {"Maman", "Dépositaire"}:
                rows = [row for row in rows if str(row.get("Statut", "")) == status_filter]
                summary = _orders_summary_from_rows(rows)
            elif show_all:
                summary = _orders_summary_from_rows(rows)
            else:
                summary = DatabaseHelper.get_orders_summary_for_date(selected_date_value)
            self._send_json({"ok": True, "rows": rows, "summary": summary, "statusFilter": status_filter})
            return
        if path == "/api/orders/advance":
            _require_module(session, "orders")
            client = _query_value(query, "client", "")
            target_date = _query_value(query, "date", _today())
            exclude_id = _int(_query_value(query, "excludeId", "0"))
            self._send_json(
                {
                    "ok": True,
                    "balance": DatabaseHelper.get_client_advance_balance(
                        client,
                        target_date,
                        exclude_id,
                    ),
                }
            )
            return
        if path == "/api/cash":
            _require_module(session, "cash")
            selected_date = _query_value(query, "date", _today())
            selected_date_value = _date_value(selected_date)
            show_all = _query_value(query, "all", "0") == "1"
            rows = DatabaseHelper.list_cash_days() if show_all else DatabaseHelper.list_cash_days_by_date(selected_date_value)
            self._send_json(
                {
                    "ok": True,
                    "rows": rows,
                    "summary": DatabaseHelper.get_cash_for_date(selected_date_value),
                    "orders": DatabaseHelper.get_orders_summary_for_date(selected_date_value),
                    "accumulated": DatabaseHelper.get_accumulated_debt_totals_for_date(selected_date_value),
                }
            )
            return
        if path == "/api/stock":
            _require_module(session, "stock")
            selected_date = _query_value(query, "date", _today())
            selected_date_value = _date_value(selected_date)
            show_all = _query_value(query, "all", "0") == "1"
            self._send_json(
                {
                    "ok": True,
                    "summary": DatabaseHelper.get_stock_summary(),
                    "supplies": DatabaseHelper.list_stock_supplies() if show_all else DatabaseHelper.list_stock_supplies_by_date(selected_date_value),
                    "exits": DatabaseHelper.list_stock_exits() if show_all else DatabaseHelper.list_stock_exits_by_date(selected_date_value),
                }
            )
            return
        if path == "/api/stock/config":
            _require_module(session, "stock")
            self._send_json({"ok": True, "config": DatabaseHelper.get_stock_configuration(), "editable": _is_admin(session)})
            return
        if path == "/api/production":
            _require_module(session, "production")
            selected_date = _query_value(query, "date", _today())
            selected_date_value = _date_value(selected_date)
            show_all = _query_value(query, "all", "0") == "1"
            self._send_json(
                {
                    "ok": True,
                    "rows": DatabaseHelper.list_productions() if show_all else DatabaseHelper.list_productions_by_date(selected_date_value),
                    "summary": DatabaseHelper.get_production_summary_for_date(selected_date_value),
                }
            )
            return
        if path == "/api/commissions":
            _require_module(session, "commissions")
            selected_date = _query_value(query, "date", _today())
            selected_date_value = _date_value(selected_date)
            show_all = _query_value(query, "all", "0") == "1"
            status_filter = normalize_status_form_label(_query_value(query, "status", "Tous") or "Tous")
            rows = DatabaseHelper.list_commissions() if show_all else DatabaseHelper.list_commissions_by_date(selected_date_value)
            if status_filter and status_filter != "Tous":
                rows = [
                    row
                    for row in rows
                    if normalize_status_form_label(str(row.get("Statut", ""))) == status_filter
                ]
            summary = DatabaseHelper.get_commissions_summary(
                None if show_all else selected_date_value,
                None if show_all else selected_date_value,
                status_filter,
            )
            self._send_json(
                {
                    "ok": True,
                    "rows": rows,
                    "summary": summary,
                    "total": _money(summary.get("TotalCommissions")),
                }
            )
            return
        if path == "/api/workers":
            _require_module(session, "workers")
            start = _query_value(query, "start", _current_month_start())
            end = _query_value(query, "end", _today())
            self._send_json(
                {
                    "ok": True,
                    "workers": DatabaseHelper.list_workers(True),
                    "payrolls": DatabaseHelper.list_payrolls(0, start, end),
                    "summary": DatabaseHelper.get_workers_payroll_summary(start, end),
                }
            )
            return
        if path == "/api/users":
            _require_module(session, "users")
            self._send_json({"ok": True, "rows": DatabaseHelper.list_users()})
            return
        if path == "/api/email/status":
            _require_admin(session, "le suivi des notifications par e-mail")
            self._send_json({"ok": True, "data": DatabaseHelper.get_email_notification_status()})
            return
        if path == "/api/users/detail":
            _require_module(session, "users")
            _require_admin(session, "la consultation du mot de passe d'un utilisateur")
            identifiant = _query_value(query, "identifiant", "").strip().lower()
            if not identifiant:
                raise ValueError("Identifiant utilisateur manquant.")
            self._send_json({"ok": True, "user": DatabaseHelper.get_user_for_admin_edit(identifiant)})
            return
        if path == "/api/history":
            _require_module(session, "history")
            self._send_json(
                {
                    "ok": True,
                    "rows": DatabaseHelper.list_activity_logs(
                        _int(_query_value(query, "limit", "300")) or 300,
                        _query_value(query, "identifiant", ""),
                        _query_value(query, "role", ""),
                    ),
                }
            )
            return
        if path == "/api/closures":
            _require_module(session, "history")
            target_date = _query_value(query, "date", _today())
            self._send_json(
                {
                    "ok": True,
                    "closure": DatabaseHelper.get_day_closure(target_date),
                    "rows": DatabaseHelper.list_day_closures(240),
                }
            )
            return
        if path == "/api/report":
            self._send_json({"ok": True, "data": self._build_report(session, query)})
            return
        if path == "/api/reports/list":
            _require_module(session, "reports")
            self._send_json({"ok": True, **self._report_files(session)})
            return
        if path == "/api/backups":
            _require_module(session, "history")
            self._send_json({"ok": True, "rows": DatabaseHelper.list_backup_files(100)})
            return
        raise ValueError("Route API introuvable.")

    def _handle_api_post(self, path: str, payload: dict[str, Any]) -> None:
        if path == "/api/internal/maintenance/automatic-backup":
            self._require_internal_maintenance_token()
            backup_path = DatabaseHelper.create_automatic_backup_if_needed(force=bool(payload.get("force")))
            self._send_json(
                {
                    "ok": True,
                    "created": backup_path is not None,
                    "path": str(backup_path) if backup_path is not None else "",
                    "message": "Sauvegarde creee." if backup_path is not None else "Sauvegarde quotidienne deja presente.",
                }
            )
            return

        if path == "/api/internal/maintenance/email-drain":
            self._require_internal_maintenance_token()
            result = DatabaseHelper.process_pending_email_notifications(_int(payload.get("limit")) or 20)
            self._send_json({"ok": True, "result": result})
            return

        if path == "/api/setup":
            if not self._is_server_console_client():
                raise PermissionError("La configuration initiale doit être effectuée sur le PC serveur.")
            DatabaseHelper.create_initial_admin(
                _clean(payload.get("fullName")),
                _clean(payload.get("identifiant")),
                _clean(payload.get("email")),
                _clean(payload.get("password")),
            )
            self._send_json({"ok": True})
            return

        if path == "/api/license/activate":
            session = _get_session(self._session_token())
            if session is None and not self._is_server_console_client():
                raise PermissionError("L'activation sans session Admin doit etre effectuee depuis le PC serveur.")
            if session is not None:
                _require_admin(session, "l'activation du produit")
            key = _clean(payload.get("key"))
            if not key:
                raise ValueError("Cle d'activation manquante.")
            result = activate_device(key, DatabaseHelper.app_data_dir, domain=self._license_domain())
            if session is not None:
                _log_web_activity(
                    session,
                    "Activation",
                    "Licence activee" if result.ok else "Activation refusee",
                    result.message,
                )
            status = _safe_license_payload(
                status_payload(DatabaseHelper.app_data_dir, domain=self._license_domain()),
                include_private=bool(session and str(session.get("role", "")) == "Admin"),
            )
            if not result.ok:
                self._send_json({"ok": False, "error": result.message, "status": status}, HTTPStatus.BAD_REQUEST)
                return
            self._send_json({"ok": True, "message": result.message, "status": status})
            return

        if path == "/api/login":
            self._require_license_active()
            identifiant = _clean(payload.get("identifiant")).lower()
            password = _clean(payload.get("password"))
            force_session = bool(payload.get("forceSession") or payload.get("force"))
            client_ip = self._client_ip()
            _ensure_login_allowed(client_ip)
            if not identifiant or not password or len(identifiant) > 254 or len(password) > 256:
                _log_login_failure(identifiant, client_ip)
                _record_login_failure(client_ip)
                raise PermissionError("Identifiant ou mot de passe incorrect.")
            try:
                user = DatabaseHelper.find_user_for_login(identifiant, password)
            except ValueError:
                _log_login_failure(identifiant, client_ip)
                _record_login_failure(client_ip)
                raise PermissionError("Identifiant ou mot de passe incorrect.") from None
            if user is None:
                _log_login_failure(identifiant, client_ip)
                _record_login_failure(client_ip)
                raise PermissionError("Identifiant ou mot de passe incorrect.")
            _clear_login_failures(client_ip)
            existing_token = self._session_token()
            existing_session = _get_session(existing_token)
            if existing_session is not None and str(existing_session.get("identifiant", "")).lower() == str(user.identifiant).lower():
                _log_web_activity(existing_session, "Connexion", "Session web reprise", "Reconnexion sur le meme navigateur.")
                self._send_json(
                    {"ok": True, "user": _public_session(existing_session)},
                    extra_headers=self._session_cookie_headers(existing_token),
                )
                return
            session = _create_session(user)
            session_result = DatabaseHelper.open_active_session(
                str(session.get("identifiant", "")),
                "Web",
                str(session.get("token", "")),
                str(self.headers.get("User-Agent", "") or "")[:120],
                client_ip,
                force_session,
            )
            if not session_result.get("ok", False):
                _delete_session(str(session.get("token", "")))
                self._send_json(
                    {
                        "ok": False,
                        "sessionConflict": True,
                        "activeSession": session_result.get("activeSession") or {},
                        "error": "Ce compte est deja connecte sur un autre appareil.",
                    },
                    HTTPStatus.CONFLICT,
                )
                return
            _log_web_activity(session, "Connexion", "Connexion réussie", f"Ouverture du tableau de bord en tant que {session.get('role', '')}.")
            self._send_json(
                {"ok": True, "user": _public_session(session)},
                extra_headers=self._session_cookie_headers(session["token"]),
            )
            return

        if path == "/api/logout":
            token = self._session_token()
            session = _get_session(token)
            if session is not None:
                DatabaseHelper.close_active_session(str(session.get("identifiant", "")), token)
            _delete_session(token)
            self._send_json({"ok": True}, extra_headers=self._session_cookie_headers(clear=True))
            return

        self._require_license_active()
        session = self._require_session()
        if session.get("mustChangePassword") and path != "/api/password":
            raise PermissionError("Vous devez changer le mot de passe initial avant de continuer.")
        if path == "/api/password":
            DatabaseHelper.change_user_password(
                str(session.get("identifiant", "")),
                _clean(payload.get("currentPassword")),
                _clean(payload.get("newPassword")),
            )
            email_result = _trigger_email_delivery(20)
            _log_web_activity(session, "Utilisateurs", "Mot de passe modifié", str(session.get("identifiant", "")))
            _delete_user_sessions(str(session.get("identifiant", "")))
            self._send_json(
                {"ok": True, "reauthenticate": True, "email": email_result},
                extra_headers=self._session_cookie_headers(clear=True),
            )
            return
        if path == "/api/users/disconnect":
            _require_admin(session, "la deconnexion d'un utilisateur")
            identifiant = _clean(payload.get("identifiant")).lower()
            if not identifiant:
                raise ValueError("Identifiant utilisateur manquant.")
            if identifiant == str(session.get("identifiant", "")).lower():
                raise ValueError("Vous ne pouvez pas fermer votre propre session depuis cette action.")
            _delete_user_sessions(identifiant)
            _log_web_activity(session, "Utilisateurs", "Session utilisateur fermee", identifiant)
            self._send_json({"ok": True, "rows": DatabaseHelper.list_users()})
            return
        if path == "/api/history/clear":
            _require_admin(session, "l'effacement de l'historique")
            archive_path = DatabaseHelper.archive_activity_logs()
            deleted = DatabaseHelper.clear_activity_logs(archive=False)
            details = f"{deleted} action(s) supprimee(s)."
            if archive_path is not None:
                details += f" Archive : {archive_path}"
            _log_web_activity(session, "Historique", "Historique efface", details)
            self._send_json(
                {
                    "ok": True,
                    "deleted": deleted,
                    "archivePath": str(archive_path) if archive_path is not None else "",
                }
            )
            return
        if path == "/api/email/retry":
            _require_admin(session, "la relance des notifications par e-mail")
            result = DatabaseHelper.retry_email_notifications(100)
            self._send_json(
                {
                    "ok": True,
                    "result": result,
                    "data": DatabaseHelper.get_email_notification_status(),
                }
            )
            return
        if path == "/api/email/test":
            _require_admin(session, "le test d'envoi d'e-mail")
            from boulangerie_app.email_service import send_transactional_email

            recipient = DatabaseHelper._normalize_email(_clean(payload.get("recipient")))
            if not recipient:
                raise ValueError("Veuillez saisir une adresse e-mail de test.")
            result = send_transactional_email(
                recipient,
                f"Test e-mail - {APP_NAME}",
                (
                    "Bonjour,\n\n"
                    f"Ceci est un e-mail de test envoye depuis {APP_NAME}.\n"
                    "Si vous le recevez, la configuration d'envoi est operationnelle."
                ),
                (
                    "<p>Bonjour,</p>"
                    f"<p>Ceci est un e-mail de test envoye depuis <strong>{html.escape(APP_NAME)}</strong>.</p>"
                    "<p>Si vous le recevez, la configuration d'envoi est operationnelle.</p>"
                ),
            )
            if not result.sent:
                raise ValueError(result.message or "Echec de l'envoi du test.")
            self._send_json(
                {
                    "ok": True,
                    "result": {
                        "sent": 1,
                        "status": result.status,
                        "message": result.message,
                    },
                    "data": DatabaseHelper.get_email_notification_status(),
                }
            )
            return
        if path == "/api/email/settings":
            _require_admin(session, "la configuration des notifications par e-mail")
            from boulangerie_app.email_service import save_email_settings

            status = save_email_settings(
                {
                    "provider": _clean(payload.get("provider")) or "cloudflare",
                    "account_id": _clean(payload.get("accountId")),
                    "api_token": _clean(payload.get("apiToken")),
                    "gateway_url": _clean(payload.get("gatewayUrl")),
                    "gateway_token": _clean(payload.get("gatewayToken")),
                    "smtp_host": _clean(payload.get("smtpHost")),
                    "smtp_port": _int(payload.get("smtpPort")) or 587,
                    "smtp_username": _clean(payload.get("smtpUsername")),
                    "smtp_password": _clean(payload.get("smtpPassword")),
                    "smtp_use_tls": bool(payload.get("smtpUseTls", True)),
                    "smtp_use_ssl": bool(payload.get("smtpUseSsl", False)),
                    "from_address": _clean(payload.get("fromAddress")),
                    "from_name": _clean(payload.get("fromName")) or APP_NAME,
                    "reply_to": _clean(payload.get("replyTo")),
                }
            )
            result = DatabaseHelper.retry_email_notifications(100) if status.get("configured") else {}
            _log_web_activity(
                session,
                "Utilisateurs",
                "Configuration e-mail modifiée",
                f"Fournisseur : {status.get('provider', '')}",
            )
            self._send_json(
                {
                    "ok": True,
                    "settings": status,
                    "result": result,
                    "data": DatabaseHelper.get_email_notification_status(),
                }
            )
            return
        if path == "/api/orders":
            _require_module(session, "orders", write=True)
            amount_due = _money(payload.get("amountDue"))
            amount_received = _money(payload.get("amountReceived"))
            args = [
                _date_value(payload.get("date") or _today()),
                _clean(payload.get("client")),
                _clean(payload.get("status")),
                _int(payload.get("trays")),
                amount_due,
                amount_received,
                max(amount_due - amount_received, 0),
            ]
            record_id = _int(payload.get("id"))
            if record_id:
                DatabaseHelper.update_order(record_id, *args)
                _log_web_activity(session, "Commandes", "Commande modifiée", f"{args[0].isoformat()} | {args[1]} | {args[2]} | {args[3]} bac(s)")
            else:
                DatabaseHelper.add_order(*args)
                _log_web_activity(session, "Commandes", "Commande enregistrée", f"{args[0].isoformat()} | {args[1]} | {args[2]} | {args[3]} bac(s)")
            self._send_json({"ok": True})
            return
        if path == "/api/cash":
            _require_module(session, "cash", write=True)
            cash_date = _date_value(payload.get("date") or _today())
            DatabaseHelper.save_cash_day(
                cash_date,
                _money(payload.get("expenses")),
                _clean(payload.get("expenseDetails")),
                _money(payload.get("paidDebts")),
                _clean(payload.get("paidDetails")),
            )
            _log_web_activity(session, "Caisse", "Fiche de caisse enregistrée", cash_date.isoformat())
            self._send_json({"ok": True})
            return
        if path == "/api/stock/supply":
            _require_module(session, "stock", write=True)
            record_id = _int(payload.get("id"))
            args = [
                _date_value(payload.get("date") or _today()),
                _money(payload.get("flour")),
                _money(payload.get("yeast")),
                _money(payload.get("salt")),
                _money(payload.get("oil")),
                _clean(payload.get("observations")),
            ]
            if record_id:
                DatabaseHelper.update_stock_supply(record_id, *args)
                _log_web_activity(session, "Stock", "Approvisionnement modifié", f"{args[0].isoformat()} | Farine {args[1]} | Levure {args[2]} | Sel {args[3]} | Huile {args[4]}")
            else:
                DatabaseHelper.add_stock_supply(*args)
                _log_web_activity(session, "Stock", "Approvisionnement ajouté", f"{args[0].isoformat()} | Farine {args[1]} | Levure {args[2]} | Sel {args[3]} | Huile {args[4]}")
            self._send_json({"ok": True})
            return
        if path == "/api/stock/exit":
            _require_module(session, "stock", write=True)
            record_id = _int(payload.get("id"))
            args = [
                _date_value(payload.get("date") or _today()),
                _money(payload.get("flour")),
                _money(payload.get("yeast")),
                _money(payload.get("salt")),
                _money(payload.get("oil")),
            ]
            if record_id:
                DatabaseHelper.update_stock_exit(record_id, *args)
                _log_web_activity(session, "Stock", "Sortie de stock modifiée", f"{args[0].isoformat()} | Farine {args[1]} | Levure {args[2]} | Sel {args[3]} | Huile {args[4]}")
            else:
                DatabaseHelper.add_stock_exit(*args)
                _log_web_activity(session, "Stock", "Sortie de stock ajoutée", f"{args[0].isoformat()} | Farine {args[1]} | Levure {args[2]} | Sel {args[3]} | Huile {args[4]}")
            self._send_json({"ok": True})
            return
        if path == "/api/stock/config":
            _require_admin(session, "la modification des paramètres du stock")
            _require_module(session, "stock", write=True)
            DatabaseHelper.update_stock_configuration(
                _money(payload.get("flourInitial")),
                _money(payload.get("yeastInitial")),
                _money(payload.get("saltInitial")),
                _money(payload.get("oilInitial")),
                _money(payload.get("flourAlert")),
                _money(payload.get("yeastAlert")),
                _money(payload.get("saltAlert")),
                _money(payload.get("oilAlert")),
            )
            _log_web_activity(session, "Stock", "Configuration du stock modifiée", "Paramètres initiaux et seuils d'alerte")
            self._send_json({"ok": True})
            return
        if path == "/api/production":
            _require_module(session, "production", write=True)
            production_date = _date_value(payload.get("date") or _today())
            DatabaseHelper.save_production_day(
                production_date,
                _int(payload.get("ordered")),
                _int(payload.get("depositaries")),
                _int(payload.get("mamas")),
                _int(payload.get("given")),
                _int(payload.get("samples")),
                _int(payload.get("remaining")),
                _int(payload.get("wasted")),
                _money(payload.get("sacks")),
                _clean(payload.get("observations")),
            )
            _log_web_activity(session, "Production", "Production enregistrée", production_date.isoformat())
            self._send_json({"ok": True})
            return
        if path == "/api/workers":
            _require_module(session, "workers", write=True)
            args = [
                _clean(payload.get("fullName")),
                _clean(payload.get("function")),
                _clean(payload.get("phone")),
                _clean(payload.get("email")),
                _clean(payload.get("address")),
                _date_value(payload.get("hireDate") or _today()),
                _money(payload.get("salary")),
                _clean(payload.get("status")) or "Actif",
                _clean(payload.get("observations")),
            ]
            record_id = _int(payload.get("id"))
            if record_id:
                DatabaseHelper.update_worker(record_id, *args)
                _log_web_activity(session, "Travailleurs", "Travailleur modifié", f"{record_id} - {args[0]}")
            else:
                worker_id = DatabaseHelper.add_worker(*args)
                _log_web_activity(session, "Travailleurs", "Travailleur ajouté", f"{worker_id} - {args[0]}")
            self._send_json({"ok": True})
            return
        if path == "/api/payrolls":
            _require_module(session, "workers", write=True)
            gross = _money(payload.get("gross"))
            bonus = _money(payload.get("bonus"))
            advance = _money(payload.get("advance"))
            withholding = _money(payload.get("withholding"))
            if gross + bonus - advance - withholding < 0:
                raise ValueError("Le net à payer ne peut pas être négatif.")
            args = [
                _int(payload.get("workerId")),
                _date_value(payload.get("payDate") or _today()),
                _clean(payload.get("period")),
                gross,
                bonus,
                advance,
                withholding,
                _clean(payload.get("paymentMode")) or "Espèces",
                _clean(payload.get("status")) or "Payée",
                _clean(payload.get("observations")),
            ]
            record_id = _int(payload.get("id"))
            if record_id:
                DatabaseHelper.update_payroll(record_id, *args)
                _log_web_activity(session, "Travailleurs", "Paie modifiée", f"{record_id} | {args[1].isoformat()} | Travailleur {args[0]}")
            else:
                payroll_id = DatabaseHelper.add_payroll(*args)
                _log_web_activity(session, "Travailleurs", "Paie enregistrée", f"{payroll_id} | {args[1].isoformat()} | Travailleur {args[0]}")
            email_result = _trigger_email_delivery(20)
            self._send_json(
                {
                    "ok": True,
                    "email": email_result,
                    "emailStatus": DatabaseHelper.get_email_notification_status(),
                }
            )
            return
        if path == "/api/users":
            _require_module(session, "users", write=True)
            full_name = _clean(payload.get("fullName"))
            identifiant = _clean(payload.get("identifiant")).lower()
            email = _clean(payload.get("email")).lower()
            password = _clean(payload.get("password"))
            role = _clean(payload.get("role")) or "Caissier"
            original_identifiant = _clean(payload.get("originalIdentifiant")).lower()
            valid_roles = set(ROLE_MODULES)
            if not full_name:
                raise ValueError("Le nom complet est obligatoire.")
            if not identifiant:
                raise ValueError("L'identifiant est obligatoire.")
            if role not in valid_roles:
                raise ValueError("Rôle utilisateur invalide.")
            if role == "Directeur Général":
                director_count = DatabaseHelper.count_directors_general()
                current_role = DatabaseHelper.get_user_role(original_identifiant) if original_identifiant else ""
                if director_count >= 1 and current_role != "Directeur Général":
                    raise ValueError("Un seul Directeur Général peut être enregistré.")
            if original_identifiant:
                if original_identifiant == session.get("identifiant") and role != "Admin":
                    raise ValueError("Vous ne pouvez pas retirer votre propre rôle administrateur.")
                if original_identifiant != identifiant:
                    raise ValueError("L'identifiant ne peut pas être modifié. Supprimez puis recréez le compte si nécessaire.")
                if role != "Admin" and DatabaseHelper.get_user_role(original_identifiant) == "Admin" and DatabaseHelper.count_admins() <= 1:
                    raise ValueError("Impossible de retirer le dernier administrateur.")
                updated = DatabaseHelper.update_user(original_identifiant, full_name, password, role, email)
                if not updated:
                    raise ValueError("Utilisateur introuvable.")
                _log_web_activity(session, "Utilisateurs", "Utilisateur modifié", f"{identifiant} | {role}")
            else:
                if not password:
                    raise ValueError("Le mot de passe est obligatoire pour un nouvel utilisateur.")
                DatabaseHelper.add_user(full_name, identifiant, password, role, email)
                _log_web_activity(session, "Utilisateurs", "Utilisateur ajouté", f"{identifiant} | {role}")
            email_result = _trigger_email_delivery(20)
            self._send_json({"ok": True, "email": email_result, "emailStatus": DatabaseHelper.get_email_notification_status()})
            return
        if path == "/api/reports/generate":
            _require_module(session, "reports")
            report_type = _clean(payload.get("type")) or "daily"
            report_format = (_clean(payload.get("format")) or "pdf").lower()
            selected_date = _date_value(payload.get("date"))
            start = _date_value(payload.get("start") or payload.get("date"))
            end = _date_value(payload.get("end") or payload.get("date"))
            if max(selected_date, start, end) > date.today():
                raise ValueError("Impossible de générer un rapport pour une date future.")
            if end < start:
                raise ValueError("La date de fin doit être après la date de début.")
            role = str(session.get("role", ""))
            generated_by = str(session.get("fullName", "") or session.get("identifiant", ""))
            destination = _report_destination(session, report_type, report_format, selected_date, start, end)
            if report_format == "pdf":
                if report_type == "monthly":
                    report_path = create_monthly_pdf_report(selected_date, destination, role=role, generated_by=generated_by, generated_role=role)
                elif report_type == "period":
                    report_path = create_period_pdf_report(start, end, destination, role=role, generated_by=generated_by, generated_role=role)
                else:
                    report_path = create_daily_pdf_report(selected_date, destination, role=role, generated_by=generated_by, generated_role=role)
            elif report_format == "excel":
                if report_type == "monthly":
                    report_path = create_monthly_excel_report(selected_date, destination, role=role, generated_by=generated_by, generated_role=role)
                elif report_type == "period":
                    report_path = create_period_excel_report(start, end, destination, role=role, generated_by=generated_by, generated_role=role)
                else:
                    report_path = create_daily_excel_report(selected_date, destination, role=role, generated_by=generated_by, generated_role=role)
            else:
                raise ValueError("Format de rapport invalide.")
            if report_type == "monthly":
                DatabaseHelper.record_monthly_report_generation(
                    selected_date.strftime("%Y-%m"),
                    report_type,
                    report_format,
                    str(session.get("identifiant", "")),
                    generated_by,
                    role,
                    str(report_path),
                )
            DatabaseHelper.log_activity(
                str(session.get("identifiant", "")),
                generated_by,
                role,
                "Rapports",
                "Rapport généré",
                f"Mode : {report_type} | Format : {report_format.upper()} | Fichier : {report_path}",
            )
            file_token = _create_report_file_token(session, Path(report_path))
            opened_locally = False
            forwarded_ip = str(self.headers.get("CF-Connecting-IP", "")).strip()
            if not forwarded_ip and self.client_address[0] in {"127.0.0.1", "::1"}:
                opened_locally = _open_local_path(Path(report_path))
            self._send_json(
                {
                    "ok": True,
                    "path": str(report_path),
                    "name": Path(report_path).name,
                    "url": f"/api/reports/file?token={quote(file_token)}",
                    "openedLocally": opened_locally,
                }
            )
            return
        if path == "/api/reports/folder":
            _require_module(session, "reports")
            reports_dir = DatabaseHelper.get_reports_dir_for_user(str(session.get("identifiant", "")))
            opened_locally = _open_local_path(reports_dir)
            _log_web_activity(session, "Rapports", "Dossier des rapports affiché", str(reports_dir))
            self._send_json(
                {
                    "ok": True,
                    "path": str(reports_dir),
                    "openedLocally": opened_locally,
                    **self._report_files(session),
                }
            )
            return
        if path == "/api/closures/close":
            _require_closure_role(session)
            _require_module(session, "history", write=True)
            closure = DatabaseHelper.close_day(
                _clean(payload.get("date")) or _today(),
                str(session.get("identifiant", "")),
                str(session.get("fullName", "") or session.get("identifiant", "")),
                str(session.get("role", "")),
            )
            self._send_json({"ok": True, "closure": closure})
            return
        if path == "/api/closures/reopen":
            _require_admin(session, "la réouverture d'une journée clôturée")
            _require_module(session, "history", write=True)
            closure = DatabaseHelper.reopen_day(
                _clean(payload.get("date")) or _today(),
                str(session.get("identifiant", "")),
                str(session.get("fullName", "") or session.get("identifiant", "")),
                str(session.get("role", "")),
                _clean(payload.get("reason")),
            )
            self._send_json({"ok": True, "closure": closure})
            return
        if path == "/api/backups/create":
            _require_admin(session, "la sauvegarde de la base")
            _require_module(session, "history", write=True)
            backup_path = DatabaseHelper.backup_database()
            DatabaseHelper.log_activity(
                str(session.get("identifiant", "")),
                str(session.get("fullName", "") or session.get("identifiant", "")),
                str(session.get("role", "")),
                "Sauvegarde",
                "Base sauvegardée",
                str(backup_path),
            )
            self._send_json({"ok": True, "path": str(backup_path)})
            return
        raise ValueError("Route API introuvable.")

    def _handle_api_delete(self, path: str, query: dict[str, list[str]]) -> None:
        self._require_license_active()
        session = self._require_session()
        if path == "/api/license/devices":
            _require_admin(session, "la gestion des postes actives")
            device_id = _query_value(query, "deviceId", "").strip()
            if not device_id:
                raise ValueError("Identifiant du poste manquant.")
            removed = deactivate_device(DatabaseHelper.app_data_dir, device_id)
            if not removed:
                raise ValueError("Poste introuvable dans le registre d'activation.")
            _log_web_activity(session, "Activation", "Poste desactive", device_id)
            self._send_json(
                {
                    "ok": True,
                    "status": _safe_license_payload(
                        status_payload(DatabaseHelper.app_data_dir, domain=self._license_domain()),
                        include_private=True,
                    ),
                }
            )
            return
        if path == "/api/users":
            _require_module(session, "users", write=True)
            identifiant = _query_value(query, "identifiant", "").strip().lower()
            if not identifiant:
                raise ValueError("Identifiant utilisateur manquant.")
            if identifiant == session.get("identifiant"):
                raise ValueError("Vous ne pouvez pas supprimer votre propre compte connecté.")
            if DatabaseHelper.get_user_role(identifiant) == "Admin" and DatabaseHelper.count_admins() <= 1:
                raise ValueError("Impossible de supprimer le dernier administrateur.")
            deleted = DatabaseHelper.delete_user(identifiant)
            if not deleted:
                raise ValueError("Utilisateur introuvable.")
            _log_web_activity(session, "Utilisateurs", "Utilisateur supprimé", identifiant)
            self._send_json({"ok": True})
            return

        record_id = _int(_query_value(query, "id", "0"))
        if record_id <= 0:
            raise ValueError("Identifiant de l'enregistrement manquant.")
        if path == "/api/orders":
            _require_module(session, "orders", write=True)
            DatabaseHelper.delete_order(record_id)
            _log_web_activity(session, "Commandes", "Commande supprimée", f"Id {record_id}")
            self._send_json({"ok": True})
            return
        if path == "/api/cash":
            _require_module(session, "cash", write=True)
            DatabaseHelper.delete_cash_day(record_id)
            _log_web_activity(session, "Caisse", "Fiche de caisse supprimée", f"Id {record_id}")
            self._send_json({"ok": True})
            return
        if path == "/api/stock/supply":
            _require_module(session, "stock", write=True)
            DatabaseHelper.delete_stock_supply(record_id)
            _log_web_activity(session, "Stock", "Approvisionnement supprimé", f"Id {record_id}")
            self._send_json({"ok": True})
            return
        if path == "/api/stock/exit":
            _require_module(session, "stock", write=True)
            DatabaseHelper.delete_stock_exit(record_id)
            _log_web_activity(session, "Stock", "Sortie de stock supprimée", f"Id {record_id}")
            self._send_json({"ok": True})
            return
        if path == "/api/production":
            _require_module(session, "production", write=True)
            DatabaseHelper.delete_production_day(record_id)
            _log_web_activity(session, "Production", "Production supprimée", f"Id {record_id}")
            self._send_json({"ok": True})
            return
        if path == "/api/workers":
            _require_module(session, "workers", write=True)
            DatabaseHelper.delete_worker(record_id)
            _log_web_activity(session, "Travailleurs", "Travailleur supprimé", f"Id {record_id}")
            self._send_json({"ok": True})
            return
        if path == "/api/payrolls":
            _require_module(session, "workers", write=True)
            DatabaseHelper.delete_payroll(record_id)
            _log_web_activity(session, "Travailleurs", "Paie supprimée", f"Id {record_id}")
            self._send_json({"ok": True})
            return
        raise ValueError("Route API introuvable.")

    def _build_report(self, session: dict[str, Any], query: dict[str, list[str]]) -> dict[str, Any]:
        role = str(session.get("role", ""))
        modules = set(_modules_for(role))
        selected_date = _query_value(query, "date", _today())
        start = _query_value(query, "start", selected_date)
        end = _query_value(query, "end", selected_date)
        selected_date_value = _date_value(selected_date)
        start_value = _date_value(start)
        end_value = _date_value(end)
        report: dict[str, Any] = {
            "date": selected_date,
            "start": start,
            "end": end,
            "generatedBy": session.get("fullName", ""),
            "role": role,
            "sections": {},
        }
        if "orders" in modules or role == "Admin":
            report["sections"]["orders"] = DatabaseHelper.get_orders_summary_for_date(selected_date_value)
        if "cash" in modules or role == "Admin":
            report["sections"]["cash"] = DatabaseHelper.get_cash_for_date(selected_date_value)
            report["sections"]["cashPeriod"] = DatabaseHelper.list_cash_balance_by_period(start_value, end_value)
        if "stock" in modules or role == "Admin":
            report["sections"]["stock"] = DatabaseHelper.get_stock_summary()
        if "production" in modules or role == "Admin":
            report["sections"]["production"] = DatabaseHelper.get_production_summary_for_date(selected_date_value)
        if "commissions" in modules or role == "Admin":
            commissions = DatabaseHelper.list_commissions_by_date(selected_date_value)
            report["sections"]["commissions"] = {
                "rows": commissions,
                "total": sum(_money(row.get("Commissions")) for row in commissions),
            }
        if "workers" in modules or role == "Admin":
            report["sections"]["workers"] = DatabaseHelper.get_workers_payroll_summary(start, end)
        return report

    def _serve_static(self, path: str) -> None:
        if path in {"", "/"}:
            file_path = STATIC_DIR / "index.html"
        elif path in {"/politique-confidentialite", "/privacy-policy"}:
            file_path = STATIC_DIR / "politique-confidentialite.html"
        elif path.startswith("/brand-assets/"):
            file_path = _brand_asset_path(path.replace("/brand-assets/", "", 1))
        else:
            relative = path.lstrip("/")
            file_path = STATIC_DIR / relative

        resolved = file_path.resolve()
        allowed_roots = [STATIC_DIR.resolve(), BRAND_ASSETS_DIR.resolve()]
        if not any(_path_is_under(resolved, root) for root in allowed_roots):
            self.send_error(HTTPStatus.FORBIDDEN)
            return
        if not resolved.exists() or not resolved.is_file():
            if path.startswith("/api/"):
                self._send_json({"ok": False, "error": "Route introuvable."}, HTTPStatus.NOT_FOUND)
                return
            resolved = STATIC_DIR / "index.html"

        content_type = mimetypes.guess_type(str(resolved))[0] or "application/octet-stream"
        data = resolved.read_bytes()
        self.send_response(HTTPStatus.OK)
        self._common_headers(content_type=content_type, content_length=len(data))
        self.end_headers()
        self.wfile.write(data)

    def _report_files(self, session: dict[str, Any]) -> dict[str, Any]:
        reports_dir = DatabaseHelper.get_reports_dir_for_user(str(session.get("identifiant", "")))
        reports_dir.mkdir(parents=True, exist_ok=True)
        files: list[dict[str, Any]] = []
        candidates = sorted(
            (
                path
                for path in reports_dir.iterdir()
                if path.is_file() and path.suffix.lower() in {".pdf", ".xlsx", ".xls"}
            ),
            key=lambda path: path.stat().st_mtime,
            reverse=True,
        )
        for report_path in candidates[:100]:
            stat = report_path.stat()
            token = _create_report_file_token(session, report_path)
            files.append(
                {
                    "name": report_path.name,
                    "format": report_path.suffix.lstrip(".").upper(),
                    "size": stat.st_size,
                    "modifiedAt": datetime.fromtimestamp(stat.st_mtime).isoformat(timespec="seconds"),
                    "url": f"/api/reports/file?token={quote(token)}",
                }
            )
        return {"files": files}

    def _send_path(self, file_path: Path) -> None:
        content_type = mimetypes.guess_type(str(file_path))[0] or "application/octet-stream"
        data = file_path.read_bytes()
        disposition = "inline" if file_path.suffix.lower() == ".pdf" else "attachment"
        self.send_response(HTTPStatus.OK)
        self._common_headers(content_type=content_type, content_length=len(data))
        self.send_header(
            "Content-Disposition",
            f"{disposition}; filename*=UTF-8''{quote(file_path.name)}",
        )
        self.send_header("X-Content-Type-Options", "nosniff")
        self.end_headers()
        self.wfile.write(data)

    def _read_json(self) -> dict[str, Any]:
        try:
            length = int(self.headers.get("Content-Length", "0"))
        except ValueError as exc:
            raise ValueError("Longueur de requête invalide.") from exc
        if length < 0 or length > MAX_JSON_BODY_BYTES:
            raise ValueError("La requête dépasse la taille autorisée.")
        raw = self.rfile.read(length).decode("utf-8-sig") if length else "{}"
        payload = json.loads(raw or "{}")
        if not isinstance(payload, dict):
            raise ValueError("Le corps de la requête doit être un objet JSON.")
        return payload

    def _bearer_token(self) -> str:
        header = self.headers.get("Authorization", "")
        if header.lower().startswith("bearer "):
            return header[7:].strip()
        return ""

    def _require_session(self) -> dict[str, Any]:
        session = _get_session(self._session_token())
        if session is None:
            raise PermissionError("Session expirée. Veuillez vous reconnecter.")
        return session

    def _send_json(
        self,
        payload: dict[str, Any],
        status: HTTPStatus = HTTPStatus.OK,
        extra_headers: list[tuple[str, str]] | None = None,
    ) -> None:
        data = json.dumps(payload, ensure_ascii=False, default=_json_default).encode("utf-8")
        self.send_response(status)
        self._common_headers(content_type="application/json; charset=utf-8", content_length=len(data))
        for name, value in extra_headers or []:
            self.send_header(name, value)
        self.end_headers()
        self.wfile.write(data)

    def _common_headers(self, *, content_type: str = "text/plain; charset=utf-8", content_length: int | None = None) -> None:
        self.send_header("Access-Control-Allow-Methods", "GET, POST, DELETE, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type, Authorization, X-CSRF-Token")
        self.send_header("Strict-Transport-Security", "max-age=31536000; includeSubDomains")
        self.send_header("X-Content-Type-Options", "nosniff")
        self.send_header("X-DNS-Prefetch-Control", "off")
        self.send_header("X-Permitted-Cross-Domain-Policies", "none")
        self.send_header("X-Frame-Options", "DENY")
        self.send_header("Cross-Origin-Opener-Policy", "same-origin")
        self.send_header("Cross-Origin-Resource-Policy", "same-origin")
        self.send_header("Referrer-Policy", "same-origin")
        self.send_header("Permissions-Policy", "camera=(), microphone=(), geolocation=()")
        self.send_header(
            "Content-Security-Policy",
            "default-src 'self'; "
            "base-uri 'self'; "
            "connect-src 'self'; "
            "font-src 'self'; "
            "form-action 'self'; "
            "frame-ancestors 'none'; "
            "img-src 'self' data:; "
            "object-src 'none'; "
            "script-src 'self'; "
            "style-src 'self' 'unsafe-inline'",
        )
        no_cache_prefixes = ("application/json", "text/html", "text/css", "text/javascript", "application/javascript")
        cache_control = "no-store" if content_type.startswith(no_cache_prefixes) else "public, max-age=3600"
        self.send_header("Cache-Control", cache_control)
        self.send_header("Content-Type", content_type)
        if content_length is not None:
            self.send_header("Content-Length", str(content_length))


def run(host: str = "0.0.0.0", port: int = 8787, data_dir: str = "") -> None:
    DatabaseHelper.apply_connection_settings(ConnectionSettings(), persist=False)
    if data_dir:
        DatabaseHelper.set_storage_root(Path(data_dir))
    DatabaseHelper.initialize_database()
    server = ThreadingHTTPServer((host, port), WebProHandler)
    print(f"{APP_NAME} Web Pro {APP_VERSION}")
    print(f"Adresse : http://{host}:{port}")
    print("Appuyez sur Ctrl+C pour arrêter.")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()


def main() -> None:
    parser = argparse.ArgumentParser(description="Démarre la version web professionnelle de Boulangerie Lomoto.")
    parser.add_argument("--host", default="0.0.0.0")
    parser.add_argument("--port", default=8787, type=int)
    parser.add_argument("--data-dir", default="")
    args = parser.parse_args()
    run(host=args.host, port=args.port, data_dir=args.data_dir)


if __name__ == "__main__":
    main()
