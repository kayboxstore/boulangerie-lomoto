from __future__ import annotations

import argparse
import json
import os
import secrets
import socket
import threading
import time
from dataclasses import dataclass
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any

from .connected_mode import (
    DISCOVERY_APP_ID,
    DISCOVERY_REQUEST_ACTION,
    DISCOVERY_RESPONSE_ACTION,
    REMOTE_DATABASE_METHODS,
    REMOTE_DEFAULT_PORT,
    REMOTE_DISCOVERY_PORT,
    deserialize_value,
    serialize_value,
)
from .version import APP_NAME, APP_VERSION


@dataclass
class EmbeddedServerHandle:
    server: ThreadingHTTPServer
    thread: threading.Thread
    host: str
    port: int
    api_token: str
    urls: list[str]
    discovery_thread: threading.Thread | None = None
    discovery_stop_event: threading.Event | None = None
    automatic_backup_thread: threading.Thread | None = None
    automatic_backup_stop_event: threading.Event | None = None

    @property
    def preferred_url(self) -> str:
        if self.urls:
            return self.urls[0]
        return f"http://127.0.0.1:{self.port}"

    def stop(self) -> None:
        if self.discovery_stop_event is not None:
            self.discovery_stop_event.set()
        if self.automatic_backup_stop_event is not None:
            self.automatic_backup_stop_event.set()
        self.server.shutdown()
        self.server.server_close()
        if self.discovery_thread is not None:
            self.discovery_thread.join(timeout=5)
        if self.automatic_backup_thread is not None:
            self.automatic_backup_thread.join(timeout=5)
        self.thread.join(timeout=5)


_embedded_server_handle: EmbeddedServerHandle | None = None
_web_sessions: dict[str, dict[str, Any]] = {}
_web_sessions_lock = threading.Lock()
_WEB_SESSION_TTL_SECONDS = 12 * 60 * 60
_AUTO_BACKUP_CHECK_INTERVAL_SECONDS = 60 * 60
_AUTO_BACKUP_RETRY_INTERVAL_SECONDS = 5 * 60

_READ_METHODS = {
    "get_stock_configuration",
    "get_stock_summary",
    "get_low_stock_alerts",
    "get_stock_journal",
    "count_stock_exits",
    "list_stock_exits",
    "list_stock_exits_by_date",
    "get_stock_sacks_used_for_date",
    "count_stock_supplies",
    "list_stock_supplies",
    "list_stock_supplies_by_date",
    "get_production_for_date",
    "get_production_summary_for_date",
    "list_productions",
    "list_productions_by_date",
    "get_global_production_summary",
    "get_orders_summary_for_date",
    "get_global_orders_summary",
    "get_cash_for_date",
    "get_accumulated_debt_totals_for_date",
    "list_cash_days",
    "list_cash_days_by_date",
    "list_cash_balance_by_period",
    "get_total_cash",
    "list_orders",
    "list_orders_by_date",
    "find_existing_order",
    "find_similar_order",
    "count_orders_with_debt",
    "get_debt_alerts",
    "list_commissions",
    "list_commissions_by_date",
    "list_clients_from_orders_by_date",
    "get_commission_synthesis_from_orders",
    "find_existing_commission",
    "get_total_commissions",
    "get_day_closure",
    "is_day_closed",
    "list_day_closures",
}

_STOCK_WRITE_METHODS = {
    "initialize_stock_day",
    "update_stock_closing",
    "add_stock_exit",
    "update_stock_exit",
    "delete_stock_exit",
    "add_stock_supply",
    "update_stock_supply",
    "delete_stock_supply",
}

_ORDER_WRITE_METHODS = {
    "save_production_day",
    "delete_production_day",
    "add_order",
    "update_order",
    "delete_order",
}

_CASH_WRITE_METHODS = {
    "save_cash_day",
    "delete_cash_day",
}

_ADMIN_METHODS = {
    "get_backups_directory",
    "list_backup_files",
    "backup_database",
    "restore_database",
    "add_user",
    "update_user",
    "search_users_by_identifiant",
    "get_user_for_admin_edit",
    "delete_user",
    "list_users",
    "count_admins",
    "get_user_role",
    "count_users",
    "log_activity",
    "list_activity_logs",
    "get_recent_activity_summary",
    "list_workers",
    "get_worker",
    "add_worker",
    "update_worker",
    "delete_worker",
    "list_payrolls",
    "add_payroll",
    "update_payroll",
    "delete_payroll",
    "get_workers_payroll_summary",
    "close_day",
    "reopen_day",
    "update_stock_configuration",
}


def _database_helper():
    from .database import DatabaseHelper

    return DatabaseHelper


def _session_auth_required() -> bool:
    value = os.environ.get("BOULANGERIE_REQUIRE_SESSION_AUTH", "1")
    return value.strip().lower() not in {"0", "false", "no", "off"}


def _get_user_fields(user: Any) -> dict[str, Any]:
    if isinstance(user, dict):
        return user
    return getattr(user, "__dict__", {})


def _build_login_result(user: Any, session: dict[str, Any] | None = None) -> dict[str, Any]:
    fields = _get_user_fields(user)
    identifiant = str(fields.get("identifiant") or fields.get("Identifiant") or "")
    role = str(fields.get("role") or fields.get("Role") or "Utilisateur")
    full_name = str(fields.get("full_name") or fields.get("NomComplet") or "").strip()
    session_token = str((session or {}).get("token") or "")
    return {
        "identifiant": identifiant,
        "role": role,
        "full_name": full_name,
        "fullName": full_name or identifiant,
        "sessionToken": session_token,
        "session_token": session_token,
        "__session_token__": session_token,
    }


def _create_web_session(user: Any) -> dict[str, Any]:
    token = secrets.token_urlsafe(32)
    fields = _get_user_fields(user)
    session = {
        "token": token,
        "identifiant": str(fields.get("identifiant") or fields.get("Identifiant") or ""),
        "role": str(fields.get("role") or fields.get("Role") or "Utilisateur"),
        "full_name": str(fields.get("full_name") or fields.get("NomComplet") or ""),
        "expires_at": time.time() + _WEB_SESSION_TTL_SECONDS,
    }
    with _web_sessions_lock:
        _web_sessions[token] = session
    return session


def _get_web_session(token: str) -> dict[str, Any] | None:
    if not token:
        return None
    now = time.time()
    with _web_sessions_lock:
        expired_tokens = [
            session_token
            for session_token, session in _web_sessions.items()
            if float(session.get("expires_at", 0) or 0) < now
        ]
        for expired_token in expired_tokens:
            _web_sessions.pop(expired_token, None)
        session = _web_sessions.get(token)
        if session is None:
            return None
        session["expires_at"] = now + _WEB_SESSION_TTL_SECONDS
        return dict(session)


def _is_method_allowed_for_session(method_name: str, args: list[Any], session: dict[str, Any]) -> bool:
    role = str(session.get("role", ""))
    if role == "Admin":
        return True

    if method_name == "change_user_password":
        return bool(args) and str(args[0]) == str(session.get("identifiant", ""))

    if method_name in _READ_METHODS:
        if role == "Gestionnaire de stock":
            method_text = method_name.lower()
            return "stock" in method_text or method_name in {"get_day_closure", "is_day_closed", "list_day_closures"}
        return True

    if role == "Gestionnaire de stock":
        return method_name in _STOCK_WRITE_METHODS
    if role == "Gestionnaire des commandes":
        return method_name in _ORDER_WRITE_METHODS
    if role == "Caissier":
        return method_name in _CASH_WRITE_METHODS
    return False


class SyncRequestHandler(BaseHTTPRequestHandler):
    server_version = f"{APP_NAME} Sync/{APP_VERSION}"

    def do_OPTIONS(self) -> None:  # noqa: N802
        self.send_response(204)
        self._send_common_headers(0)
        self.end_headers()

    def do_GET(self) -> None:  # noqa: N802
        if self.path.rstrip("/") != "/health":
            self._send_json(404, {"ok": False, "error": {"message": "Route introuvable."}})
            return

        server_token = str(getattr(self.server, "api_token", "") or "")
        self._send_json(
            200,
            {
                "ok": True,
                "app_name": APP_NAME,
                "app_version": APP_VERSION,
                "server_name": socket.gethostname(),
                "server_port": self.server.server_port,
                "discovery_port": REMOTE_DISCOVERY_PORT,
                "token_required": bool(server_token.strip()),
            },
        )

    def do_POST(self) -> None:  # noqa: N802
        if self.path.rstrip("/") != "/rpc":
            self._send_json(404, {"ok": False, "error": {"message": "Route introuvable."}})
            return

        payload = self._read_json_payload()
        if payload is None:
            return

        server_token = str(getattr(self.server, "api_token", "") or "")
        request_token = str(payload.get("token", "") or "")
        if server_token and request_token != server_token:
            self._send_json(403, {"ok": False, "error": {"message": "Jeton serveur invalide."}})
            return

        method_name = str(payload.get("method", "")).strip()
        if method_name in {"web_login", "find_user_for_login"}:
            try:
                args = deserialize_value(payload.get("args", []))
                if not isinstance(args, list) or len(args) < 2:
                    raise ValueError("Identifiant et mot de passe requis.")
                identifiant = str(args[0]).strip()
                password = str(args[1]).strip()
                DatabaseHelper = _database_helper()
                user = DatabaseHelper.invoke_local_method("find_user_for_login", identifiant, password)
                if not user and identifiant.lower() != identifiant:
                    user = DatabaseHelper.invoke_local_method("find_user_for_login", identifiant.lower(), password)
                if not user:
                    if method_name == "find_user_for_login":
                        self._send_json(200, {"ok": True, "result": None})
                        return
                    self._send_json(403, {"ok": False, "error": {"message": "Identifiant ou mot de passe incorrect."}})
                    return
                session = _create_web_session(user)
                self._send_json(
                    200,
                    {
                        "ok": True,
                        "result": serialize_value(_build_login_result(user, session)),
                    },
                )
                return
            except ValueError as exc:
                self._send_json(403, {"ok": False, "error": {"message": str(exc), "type": exc.__class__.__name__}})
                return
            except Exception as exc:
                self._send_json(500, {"ok": False, "error": {"message": str(exc), "type": exc.__class__.__name__}})
                return
        if method_name not in REMOTE_DATABASE_METHODS:
            self._send_json(400, {"ok": False, "error": {"message": "Méthode distante non autorisée."}})
            return

        try:
            args = deserialize_value(payload.get("args", []))
            kwargs = deserialize_value(payload.get("kwargs", {}))
            if not isinstance(args, list):
                raise ValueError("Liste d'arguments distante invalide.")
            if not isinstance(kwargs, dict):
                raise ValueError("Dictionnaire d'arguments nommes invalide.")

            if _session_auth_required():
                session = _get_web_session(str(payload.get("session_token", "") or ""))
                if session is None:
                    self._send_json(401, {"ok": False, "error": {"message": "Session expiree. Veuillez vous reconnecter."}})
                    return
                if not _is_method_allowed_for_session(method_name, args, session):
                    self._send_json(403, {"ok": False, "error": {"message": "Action non autorisee pour votre role."}})
                    return

            DatabaseHelper = _database_helper()
            result = DatabaseHelper.invoke_local_method(method_name, *args, **kwargs)
        except Exception as exc:
            self._send_json(500, {"ok": False, "error": {"message": str(exc), "type": exc.__class__.__name__}})
            return

        self._send_json(200, {"ok": True, "result": serialize_value(result)})

    def log_message(self, format: str, *args: Any) -> None:  # noqa: A003
        return

    def _read_json_payload(self) -> dict[str, Any] | None:
        try:
            content_length = int(self.headers.get("Content-Length", "0"))
        except ValueError:
            self._send_json(400, {"ok": False, "error": {"message": "Longueur de requete invalide."}})
            return None

        try:
            body = self.rfile.read(content_length).decode("utf-8-sig") if content_length else "{}"
            payload = json.loads(body)
        except ValueError:
            self._send_json(400, {"ok": False, "error": {"message": "Corps JSON invalide."}})
            return None

        if not isinstance(payload, dict):
            self._send_json(400, {"ok": False, "error": {"message": "Le corps JSON doit etre un objet."}})
            return None
        return payload

    def _send_json(self, status_code: int, payload: dict[str, Any]) -> None:
        body = json.dumps(payload, ensure_ascii=True).encode("utf-8")
        self.send_response(status_code)
        self._send_common_headers(len(body))
        self.end_headers()
        self.wfile.write(body)

    def _send_common_headers(self, content_length: int) -> None:
        # Le mobile web et l'APK peuvent appeler directement le serveur central depuis le réseau local.
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type, Accept")
        self.send_header("Access-Control-Max-Age", "86400")
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(content_length))


def list_local_server_urls(port: int) -> list[str]:
    loopback_url = f"http://127.0.0.1:{port}"
    urls: list[str] = []

    try:
        host_name = socket.gethostname()
        discovered = socket.gethostbyname_ex(host_name)[2]
    except OSError:
        discovered = []

    try:
        with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as sock:
            sock.connect(("8.8.8.8", 80))
            discovered.append(sock.getsockname()[0])
    except OSError:
        pass

    seen: set[str] = set()
    for ip_address in discovered:
        if not ip_address or ip_address.startswith("127."):
            continue
        url = f"http://{ip_address}:{port}"
        if url not in seen:
            seen.add(url)
            urls.append(url)

    if loopback_url not in seen:
        urls.append(loopback_url)

    return urls


def _run_discovery_listener(
    stop_event: threading.Event,
    server_port: int,
    api_token: str,
) -> None:
    try:
        with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as sock:
            sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            sock.setsockopt(socket.SOL_SOCKET, socket.SO_BROADCAST, 1)
            sock.bind(("", REMOTE_DISCOVERY_PORT))
            sock.settimeout(1.0)

            while not stop_event.is_set():
                try:
                    payload_bytes, source_address = sock.recvfrom(4096)
                except socket.timeout:
                    continue
                except OSError:
                    break

                try:
                    payload = json.loads(payload_bytes.decode("utf-8-sig"))
                except ValueError:
                    continue

                if not isinstance(payload, dict):
                    continue
                if str(payload.get("app", "")) != DISCOVERY_APP_ID:
                    continue
                if str(payload.get("action", "")) != DISCOVERY_REQUEST_ACTION:
                    continue

                response_payload = json.dumps(
                    {
                        "app": DISCOVERY_APP_ID,
                        "action": DISCOVERY_RESPONSE_ACTION,
                        "server_name": socket.gethostname(),
                        "app_name": APP_NAME,
                        "app_version": APP_VERSION,
                        "server_port": server_port,
                        "token_required": bool(api_token.strip()),
                    },
                    ensure_ascii=True,
                ).encode("utf-8")

                try:
                    sock.sendto(response_payload, source_address)
                except OSError:
                    continue
    except OSError:
        return


def _run_automatic_backup_loop(stop_event: threading.Event) -> None:
    while not stop_event.is_set():
        try:
            DatabaseHelper = _database_helper()
            DatabaseHelper.invoke_local_method("create_automatic_backup_if_needed")
            wait_seconds = _AUTO_BACKUP_CHECK_INTERVAL_SECONDS
        except Exception:
            wait_seconds = _AUTO_BACKUP_RETRY_INTERVAL_SECONDS
        stop_event.wait(wait_seconds)


def is_embedded_server_running() -> bool:
    return _embedded_server_handle is not None


def get_embedded_server_status() -> EmbeddedServerHandle | None:
    return _embedded_server_handle


def start_embedded_server(
    host: str = "0.0.0.0",
    port: int = REMOTE_DEFAULT_PORT,
    api_token: str = "",
    data_dir: str | Path | None = None,
) -> EmbeddedServerHandle:
    global _embedded_server_handle

    if _embedded_server_handle is not None:
        return _embedded_server_handle

    DatabaseHelper = _database_helper()
    if data_dir is not None:
        DatabaseHelper.set_storage_root(Path(data_dir))
    DatabaseHelper.initialize_local_database()

    server = ThreadingHTTPServer((host, port), SyncRequestHandler)
    server.api_token = api_token.strip()

    thread = threading.Thread(target=server.serve_forever, name="boulangerie-sync-server", daemon=True)
    thread.start()

    discovery_stop_event = threading.Event()
    discovery_thread = threading.Thread(
        target=_run_discovery_listener,
        args=(discovery_stop_event, port, api_token.strip()),
        name="boulangerie-sync-discovery",
        daemon=True,
    )
    discovery_thread.start()

    automatic_backup_stop_event = threading.Event()
    automatic_backup_thread = threading.Thread(
        target=_run_automatic_backup_loop,
        args=(automatic_backup_stop_event,),
        name="boulangerie-sync-auto-backup",
        daemon=True,
    )
    automatic_backup_thread.start()

    _embedded_server_handle = EmbeddedServerHandle(
        server=server,
        thread=thread,
        host=host,
        port=port,
        api_token=api_token.strip(),
        urls=list_local_server_urls(port),
        discovery_thread=discovery_thread,
        discovery_stop_event=discovery_stop_event,
        automatic_backup_thread=automatic_backup_thread,
        automatic_backup_stop_event=automatic_backup_stop_event,
    )
    return _embedded_server_handle


def stop_embedded_server() -> None:
    global _embedded_server_handle

    if _embedded_server_handle is None:
        return

    _embedded_server_handle.stop()
    _embedded_server_handle = None


def run_server(
    host: str = "0.0.0.0",
    port: int = REMOTE_DEFAULT_PORT,
    api_token: str = "",
    data_dir: str | Path | None = None,
) -> None:
    handle = start_embedded_server(host=host, port=port, api_token=api_token, data_dir=data_dir)
    print(f"{APP_NAME} - serveur central actif")
    print(f"Version : {APP_VERSION}")
    for url in handle.urls:
        print(f"Adresse : {url}")
    if handle.api_token:
        print("Jeton serveur actif.")
    print("Le serveur reste actif jusqu'a l'arret du programme.")

    try:
        handle.thread.join()
    except KeyboardInterrupt:
        pass
    finally:
        stop_embedded_server()


def main() -> None:
    parser = argparse.ArgumentParser(description="Demarre le serveur central Boulangerie Lomoto.")
    parser.add_argument("--host", default="0.0.0.0", help="Adresse d'ecoute du serveur.")
    parser.add_argument(
        "--port",
        default=int(os.environ.get("PORT", REMOTE_DEFAULT_PORT)),
        type=int,
        help="Port TCP du serveur central.",
    )
    parser.add_argument(
        "--token",
        default=os.environ.get("BOULANGERIE_API_TOKEN", ""),
        help="Jeton d'acces optionnel.",
    )
    parser.add_argument(
        "--data-dir",
        default=os.environ.get("BOULANGERIE_APPDATA_DIR", ""),
        help="Dossier qui contient la base centrale et les sauvegardes.",
    )
    args = parser.parse_args()
    run_server(
        host=args.host,
        port=args.port,
        api_token=args.token,
        data_dir=args.data_dir or None,
    )


if __name__ == "__main__":
    main()
