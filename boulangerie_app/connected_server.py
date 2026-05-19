from __future__ import annotations

import argparse
import json
import socket
import threading
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

    @property
    def preferred_url(self) -> str:
        if self.urls:
            return self.urls[0]
        return f"http://127.0.0.1:{self.port}"

    def stop(self) -> None:
        if self.discovery_stop_event is not None:
            self.discovery_stop_event.set()
        self.server.shutdown()
        self.server.server_close()
        if self.discovery_thread is not None:
            self.discovery_thread.join(timeout=5)
        self.thread.join(timeout=5)


_embedded_server_handle: EmbeddedServerHandle | None = None


def _database_helper():
    from .database import DatabaseHelper

    return DatabaseHelper


class SyncRequestHandler(BaseHTTPRequestHandler):
    server_version = f"{APP_NAME} Sync/{APP_VERSION}"

    def do_GET(self) -> None:  # noqa: N802
        if self.path.rstrip("/") != "/health":
            self._send_json(404, {"ok": False, "error": {"message": "Route introuvable."}})
            return

        self._send_json(
            200,
            {
                "ok": True,
                "app_name": APP_NAME,
                "app_version": APP_VERSION,
                "server_port": self.server.server_port,
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
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)


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

    _embedded_server_handle = EmbeddedServerHandle(
        server=server,
        thread=thread,
        host=host,
        port=port,
        api_token=api_token.strip(),
        urls=list_local_server_urls(port),
        discovery_thread=discovery_thread,
        discovery_stop_event=discovery_stop_event,
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
    parser.add_argument("--port", default=REMOTE_DEFAULT_PORT, type=int, help="Port TCP du serveur central.")
    parser.add_argument("--token", default="", help="Jeton d'acces optionnel.")
    parser.add_argument(
        "--data-dir",
        default="",
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
