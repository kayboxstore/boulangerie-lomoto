from __future__ import annotations

import json
import socket
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import asdict, dataclass, is_dataclass
from datetime import date, datetime
from ipaddress import IPv4Address, IPv4Network
from pathlib import Path
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.parse import urlsplit, urlunsplit
from urllib.request import Request, urlopen


REMOTE_DEFAULT_PORT = 8765
REMOTE_DISCOVERY_PORT = 8766
REMOTE_DISCOVERY_TIMEOUT_SECONDS = 3.0
REMOTE_REFRESH_INTERVAL_MS = 5000
CONNECTION_CONFIG_FILENAME = "connection_settings.json"
PUBLIC_SERVER_DIRECTORY_URL = (
    "https://raw.githubusercontent.com/kayboxstore/boulangerie-lomoto-updates/main/server.json"
)
PUBLIC_SERVER_DIRECTORY_TIMEOUT_SECONDS = 4
DISCOVERY_APP_ID = "boulangerie-lomoto-sync"
DISCOVERY_REQUEST_ACTION = "discover_server"
DISCOVERY_RESPONSE_ACTION = "server_available"

REMOTE_DATABASE_METHODS = {
    "find_user_for_login",
    "is_using_default_password",
    "change_user_password",
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
    "get_day_closure",
    "is_day_closed",
    "list_day_closures",
    "ensure_day_open_for_write",
    "close_day",
    "reopen_day",
    "get_stock_configuration",
    "update_stock_configuration",
    "get_stock_summary",
    "get_low_stock_alerts",
    "initialize_stock_day",
    "get_stock_journal",
    "update_stock_closing",
    "count_stock_exits",
    "list_stock_exits",
    "list_stock_exits_by_date",
    "get_stock_sacks_used_for_date",
    "add_stock_exit",
    "update_stock_exit",
    "delete_stock_exit",
    "count_stock_supplies",
    "list_stock_supplies",
    "list_stock_supplies_by_date",
    "add_stock_supply",
    "update_stock_supply",
    "delete_stock_supply",
    "get_prevision_for_date",
    "get_prevision_summary_for_date",
    "list_previsions",
    "list_previsions_by_date",
    "get_global_prevision_summary",
    "add_prevision_order",
    "update_prevision_order",
    "save_prevision_day",
    "delete_prevision_day",
    "get_production_for_date",
    "get_production_summary_for_date",
    "list_productions",
    "list_productions_by_date",
    "get_global_production_summary",
    "save_production_day",
    "delete_production_day",
    "get_orders_summary_for_date",
    "get_global_orders_summary",
    "get_cash_for_date",
    "get_accumulated_debt_totals_for_date",
    "save_cash_day",
    "list_cash_days",
    "list_cash_days_by_date",
    "list_cash_balance_by_period",
    "delete_cash_day",
    "get_total_cash",
    "list_orders",
    "list_orders_by_date",
    "add_order",
    "count_orders_with_debt",
    "get_debt_alerts",
    "update_order",
    "delete_order",
    "find_existing_order",
    "find_similar_order",
    "list_commissions",
    "list_commissions_by_date",
    "list_clients_from_orders_by_date",
    "get_commission_synthesis_from_orders",
    "find_existing_commission",
    "get_total_commissions",
}


class RemoteDatabaseError(RuntimeError):
    pass


@dataclass
class DiscoveredServerInfo:
    server_url: str
    server_name: str
    app_version: str
    token_required: bool = False
    raw_address: str = ""

    @property
    def label(self) -> str:
        suffix = " - jeton requis" if self.token_required else ""
        return f"{self.server_name} - {self.server_url}{suffix}"


@dataclass
class ConnectionSettings:
    mode: str = "local"
    server_url: str = ""
    api_token: str = ""

    def normalized_mode(self) -> str:
        return "remote" if self.mode.strip().lower() == "remote" else "local"

    def normalized_url(self) -> str:
        url = self.server_url.strip().rstrip("/")
        if url and not url.startswith(("http://", "https://")):
            url = f"http://{url}"
        if url:
            parsed = urlsplit(url)
            try:
                parsed_port = parsed.port
            except ValueError:
                parsed_port = None
            if parsed.scheme == "http" and parsed.hostname and parsed_port is None:
                host = parsed.hostname
                if ":" in host and not host.startswith("["):
                    host = f"[{host}]"
                netloc = f"{host}:{REMOTE_DEFAULT_PORT}"
                if parsed.username:
                    credentials = parsed.username
                    if parsed.password:
                        credentials += f":{parsed.password}"
                    netloc = f"{credentials}@{netloc}"
                url = urlunsplit((parsed.scheme, netloc, parsed.path, parsed.query, parsed.fragment))
        return url

    def is_remote(self) -> bool:
        return self.normalized_mode() == "remote" and bool(self.normalized_url())

    def to_dict(self) -> dict[str, str]:
        return {
            "mode": self.normalized_mode(),
            "server_url": self.normalized_url(),
            "api_token": self.api_token.strip(),
        }


@dataclass
class PublicServerDirectoryInfo:
    enabled: bool = False
    required: bool = False
    server_url: str = ""
    api_token: str = ""
    label: str = "Serveur Internet"
    notes: str = ""
    updated_at: str = ""

    def to_connection_settings(self) -> ConnectionSettings | None:
        settings = ConnectionSettings(
            mode="remote",
            server_url=self.server_url,
            api_token=self.api_token,
        )
        return settings if self.enabled and settings.is_remote() else None


def connection_config_path(app_data_dir: Path) -> Path:
    return app_data_dir / CONNECTION_CONFIG_FILENAME


def load_connection_settings(app_data_dir: Path) -> ConnectionSettings:
    config_path = connection_config_path(app_data_dir)
    if not config_path.exists():
        return ConnectionSettings()

    try:
        payload = json.loads(config_path.read_text(encoding="utf-8-sig"))
    except (OSError, ValueError):
        return ConnectionSettings()

    if not isinstance(payload, dict):
        return ConnectionSettings()

    return ConnectionSettings(
        mode=str(payload.get("mode", "local")),
        server_url=str(payload.get("server_url", "")),
        api_token=str(payload.get("api_token", "")),
    )


def save_connection_settings(app_data_dir: Path, settings: ConnectionSettings) -> Path:
    app_data_dir.mkdir(parents=True, exist_ok=True)
    config_path = connection_config_path(app_data_dir)
    config_path.write_text(
        json.dumps(settings.to_dict(), ensure_ascii=True, indent=2),
        encoding="utf-8",
    )
    return config_path


def fetch_public_server_directory(
    directory_url: str = PUBLIC_SERVER_DIRECTORY_URL,
    timeout_seconds: int = PUBLIC_SERVER_DIRECTORY_TIMEOUT_SECONDS,
) -> PublicServerDirectoryInfo:
    request = Request(
        directory_url,
        headers={
            "Accept": "application/json",
            "Cache-Control": "no-cache",
            "User-Agent": "BoulangerieLomoto/remote-directory",
        },
        method="GET",
    )
    try:
        with urlopen(request, timeout=timeout_seconds) as response:
            payload = json.loads(response.read().decode("utf-8-sig"))
    except HTTPError as exc:
        raise RemoteDatabaseError(f"Echec HTTP pendant la lecture du serveur Internet : {exc.code}") from exc
    except URLError as exc:
        raise RemoteDatabaseError("Impossible de lire l'adresse Internet du serveur central.") from exc
    except json.JSONDecodeError as exc:
        raise RemoteDatabaseError("Le fichier du serveur Internet n'est pas un JSON valide.") from exc

    if not isinstance(payload, dict):
        raise RemoteDatabaseError("Le fichier du serveur Internet doit être un objet JSON.")

    return PublicServerDirectoryInfo(
        enabled=bool(payload.get("enabled", False)),
        required=bool(payload.get("required", False)),
        server_url=str(payload.get("server_url", "")).strip(),
        api_token=str(payload.get("api_token", "")).strip(),
        label=str(payload.get("label", "Serveur Internet")).strip() or "Serveur Internet",
        notes=str(payload.get("notes", "")).strip(),
        updated_at=str(payload.get("updated_at", "")).strip(),
    )


def _local_ipv4_addresses() -> list[str]:
    discovered: list[str] = []

    try:
        host_name = socket.gethostname()
        discovered.extend(socket.gethostbyname_ex(host_name)[2])
    except OSError:
        pass

    try:
        with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as sock:
            sock.connect(("8.8.8.8", 80))
            discovered.append(sock.getsockname()[0])
    except OSError:
        pass

    unique: list[str] = []
    seen: set[str] = set()
    for ip_address in discovered:
        ip_text = str(ip_address or "").strip()
        if not ip_text or ip_text.startswith(("127.", "169.254.")):
            continue
        try:
            IPv4Address(ip_text)
        except ValueError:
            continue
        if ip_text not in seen:
            seen.add(ip_text)
            unique.append(ip_text)
    return unique


def _discovery_targets(discovery_port: int) -> list[tuple[str, int]]:
    targets: list[tuple[str, int]] = [
        ("255.255.255.255", discovery_port),
        ("127.0.0.1", discovery_port),
    ]
    seen = {target[0] for target in targets}

    for local_ip in _local_ipv4_addresses():
        parts = local_ip.split(".")
        if len(parts) != 4:
            continue
        subnet_broadcast = ".".join([parts[0], parts[1], parts[2], "255"])
        if subnet_broadcast not in seen:
            seen.add(subnet_broadcast)
            targets.append((subnet_broadcast, discovery_port))
        try:
            network = IPv4Network(f"{local_ip}/24", strict=False)
        except ValueError:
            continue
        for host in network.hosts():
            host_text = str(host)
            if host_text == local_ip or host_text in seen:
                continue
            seen.add(host_text)
            targets.append((host_text, discovery_port))
    return targets


def _health_probe_server(ip_address: str, server_port: int) -> DiscoveredServerInfo | None:
    server_url = f"http://{ip_address}:{server_port}"
    request = Request(f"{server_url}/health", headers={"Accept": "application/json"}, method="GET")
    try:
        with urlopen(request, timeout=0.45) as response:
            payload = json.loads(response.read().decode("utf-8-sig"))
    except Exception:
        return None
    if not isinstance(payload, dict) or not payload.get("ok", False):
        return None
    if str(payload.get("app_name", "")).strip() not in {"", "Boulangerie Lomoto"}:
        return None
    detected_port = int(payload.get("server_port", server_port) or server_port)
    return DiscoveredServerInfo(
        server_url=f"http://{ip_address}:{detected_port}",
        server_name=str(payload.get("server_name") or ip_address),
        app_version=str(payload.get("app_version", "")),
        token_required=bool(payload.get("token_required", False)),
        raw_address=ip_address,
    )


def _merge_discovered_server(
    discovered: dict[tuple[str, int], DiscoveredServerInfo],
    discovered_info: DiscoveredServerInfo,
) -> None:
    try:
        server_port = int(urlsplit(discovered_info.server_url).port or REMOTE_DEFAULT_PORT)
    except ValueError:
        server_port = REMOTE_DEFAULT_PORT
    discovered_key = (discovered_info.server_name.lower(), server_port)
    existing_info = discovered.get(discovered_key)
    if existing_info is None:
        discovered[discovered_key] = discovered_info
        return

    existing_is_loopback = existing_info.raw_address.startswith("127.")
    current_is_loopback = discovered_info.raw_address.startswith("127.")
    if existing_is_loopback and not current_is_loopback:
        discovered[discovered_key] = discovered_info


def discover_remote_servers(
    timeout_seconds: float = REMOTE_DISCOVERY_TIMEOUT_SECONDS,
    discovery_port: int = REMOTE_DISCOVERY_PORT,
) -> list[DiscoveredServerInfo]:
    request_payload = json.dumps(
        {
            "app": DISCOVERY_APP_ID,
            "action": DISCOVERY_REQUEST_ACTION,
        },
        ensure_ascii=True,
    ).encode("utf-8")

    discovered: dict[tuple[str, int], DiscoveredServerInfo] = {}
    deadline = time.monotonic() + max(timeout_seconds, 0.3)

    try:
        with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as sock:
            sock.setsockopt(socket.SOL_SOCKET, socket.SO_BROADCAST, 1)
            sock.settimeout(0.35)
            sock.bind(("", 0))

            for target in _discovery_targets(discovery_port):
                try:
                    sock.sendto(request_payload, target)
                except OSError:
                    continue

            while time.monotonic() < deadline:
                try:
                    raw_payload, source_address = sock.recvfrom(4096)
                except socket.timeout:
                    continue
                except OSError:
                    break

                try:
                    payload = json.loads(raw_payload.decode("utf-8-sig"))
                except ValueError:
                    continue

                if not isinstance(payload, dict):
                    continue
                if str(payload.get("app", "")) != DISCOVERY_APP_ID:
                    continue
                if str(payload.get("action", "")) != DISCOVERY_RESPONSE_ACTION:
                    continue

                server_port = int(payload.get("server_port", REMOTE_DEFAULT_PORT) or REMOTE_DEFAULT_PORT)
                source_ip = str(source_address[0] or "")
                if not source_ip:
                    continue

                server_name = str(payload.get("server_name", source_ip))
                server_url = f"http://{source_ip}:{server_port}"
                discovered_info = DiscoveredServerInfo(
                    server_url=server_url,
                    server_name=server_name,
                    app_version=str(payload.get("app_version", "")),
                    token_required=bool(payload.get("token_required", False)),
                    raw_address=source_ip,
                )
                _merge_discovered_server(discovered, discovered_info)
    except OSError:
        pass

    if not discovered:
        candidates = ["127.0.0.1"]
        seen_candidates = set(candidates)
        for local_ip in _local_ipv4_addresses():
            try:
                network = IPv4Network(f"{local_ip}/24", strict=False)
            except ValueError:
                continue
            for host in network.hosts():
                host_text = str(host)
                if host_text in seen_candidates:
                    continue
                seen_candidates.add(host_text)
                candidates.append(host_text)

        with ThreadPoolExecutor(max_workers=min(64, max(len(candidates), 1))) as executor:
            future_map = {
                executor.submit(_health_probe_server, candidate, REMOTE_DEFAULT_PORT): candidate
                for candidate in candidates
            }
            for future in as_completed(future_map):
                try:
                    discovered_info = future.result()
                except Exception:
                    continue
                if discovered_info is not None:
                    _merge_discovered_server(discovered, discovered_info)
                    break

    return sorted(discovered.values(), key=lambda item: (item.server_name.lower(), item.server_url.lower()))


def serialize_value(value: Any) -> Any:
    if value is None or isinstance(value, (bool, int, float, str)):
        return value

    if isinstance(value, datetime):
        return {"__type__": "datetime", "value": value.isoformat()}

    if isinstance(value, date):
        return {"__type__": "date", "value": value.isoformat()}

    if isinstance(value, Path):
        return {"__type__": "path", "value": str(value)}

    if is_dataclass(value):
        return {
            "__type__": "dataclass",
            "class_name": value.__class__.__name__,
            "fields": serialize_value(asdict(value)),
        }

    if isinstance(value, tuple):
        return {"__type__": "tuple", "items": [serialize_value(item) for item in value]}

    if isinstance(value, list):
        return [serialize_value(item) for item in value]

    if isinstance(value, dict):
        return {str(key): serialize_value(item) for key, item in value.items()}

    raise TypeError(f"Type non pris en charge pour la synchronisation : {type(value)!r}")


def deserialize_value(value: Any) -> Any:
    if isinstance(value, list):
        return [deserialize_value(item) for item in value]

    if not isinstance(value, dict):
        return value

    value_type = value.get("__type__")
    if value_type == "datetime":
        return datetime.fromisoformat(str(value.get("value", "")))
    if value_type == "date":
        return date.fromisoformat(str(value.get("value", "")))
    if value_type == "path":
        return Path(str(value.get("value", "")))
    if value_type == "tuple":
        return tuple(deserialize_value(item) for item in value.get("items", []))
    if value_type == "dataclass":
        fields = deserialize_value(value.get("fields", {}))
        if isinstance(fields, dict):
            fields["__remote_dataclass__"] = str(value.get("class_name", ""))
        return fields

    return {str(key): deserialize_value(item) for key, item in value.items()}


class RemoteDatabaseClient:
    def __init__(
        self,
        server_url: str,
        api_token: str = "",
        timeout_seconds: int = 10,
        session_token: str = "",
    ) -> None:
        self.server_url = server_url.strip().rstrip("/")
        self.api_token = api_token.strip()
        self.timeout_seconds = timeout_seconds
        self.session_token = session_token.strip()

    @property
    def rpc_url(self) -> str:
        return f"{self.server_url}/rpc"

    @property
    def health_url(self) -> str:
        return f"{self.server_url}/health"

    def ping(self) -> dict[str, Any]:
        payload = self._request("GET", self.health_url)
        if not isinstance(payload, dict):
            raise RemoteDatabaseError("Réponse invalide du serveur central.")
        return payload

    def call(self, method_name: str, *args: Any, **kwargs: Any) -> Any:
        payload = {
            "method": method_name,
            "args": serialize_value(list(args)),
            "kwargs": serialize_value(kwargs),
        }
        if self.api_token:
            payload["token"] = self.api_token
        if self.session_token:
            payload["session_token"] = self.session_token

        response = self._request("POST", self.rpc_url, payload)
        if not isinstance(response, dict):
            raise RemoteDatabaseError("Réponse invalide du serveur central.")

        if not response.get("ok", False):
            message = str(response.get("error", {}).get("message", "Erreur inconnue du serveur central."))
            raise RemoteDatabaseError(message)

        return deserialize_value(response.get("result"))

    def _request(self, method: str, target_url: str, payload: dict[str, Any] | None = None) -> Any:
        request_body = None
        headers = {"Accept": "application/json"}
        if payload is not None:
            request_body = json.dumps(payload, ensure_ascii=True).encode("utf-8")
            headers["Content-Type"] = "application/json"

        request = Request(target_url, data=request_body, headers=headers, method=method)
        try:
            with urlopen(request, timeout=self.timeout_seconds) as response:
                body = response.read().decode("utf-8-sig")
        except HTTPError as exc:
            try:
                error_payload = json.loads(exc.read().decode("utf-8-sig"))
                message = str(error_payload.get("error", {}).get("message", exc.reason))
            except Exception:
                message = str(exc.reason)
            raise RemoteDatabaseError(f"Échec HTTP vers le serveur central : {message}") from exc
        except URLError as exc:
            raise RemoteDatabaseError(
                "Impossible de joindre le serveur central. Vérifiez l'adresse, le réseau et le port."
            ) from exc

        try:
            return json.loads(body) if body else {}
        except ValueError as exc:
            raise RemoteDatabaseError("Le serveur central a renvoyé une réponse non lisible.") from exc
