from __future__ import annotations

import sqlite3
import sys
import threading
from http.server import ThreadingHTTPServer
from pathlib import Path

import servicemanager  # type: ignore
import win32event  # type: ignore
import win32service  # type: ignore
import win32serviceutil  # type: ignore

from .connected_server import start_embedded_server, stop_embedded_server
from .server_host import (
    WINDOWS_SERVICE_DESCRIPTION,
    WINDOWS_SERVICE_DISPLAY_NAME,
    WINDOWS_SERVICE_NAME,
    ensure_central_server_token,
    load_central_server_settings,
    save_central_server_settings,
)
from .version import APP_NAME
from boulangerie_web_pro.server import WebProHandler


WEB_PRO_PORT = 8787


def inspect_sqlite_database(database_path: str | Path) -> tuple[str, int]:
    path = Path(database_path)
    if not path.is_file():
        raise FileNotFoundError(f"Sauvegarde SQLite introuvable : {path}")
    connection = sqlite3.connect(str(path))
    try:
        connection.execute("PRAGMA query_only = ON")
        integrity = str(connection.execute("PRAGMA integrity_check").fetchone()[0] or "")
        table_count = int(
            connection.execute("SELECT COUNT(*) FROM sqlite_master WHERE type = 'table'").fetchone()[0] or 0
        )
    finally:
        connection.close()
    if integrity.lower() != "ok" or table_count < 5:
        raise sqlite3.DatabaseError(f"Integrity={integrity}; tables={table_count}")
    return integrity, table_count


def run_sqlite_integrity_check(database_path: str | Path) -> int:
    try:
        integrity, table_count = inspect_sqlite_database(database_path)
    except Exception as exc:  # noqa: BLE001 - message required by scheduled task
        print(f"ECHEC controle SQLite : {exc}", file=sys.stderr)
        return 1
    print(f"OK integrity={integrity}; tables={table_count}")
    return 0


class CentralServerWindowsService(win32serviceutil.ServiceFramework):
    _svc_name_ = WINDOWS_SERVICE_NAME
    _svc_display_name_ = WINDOWS_SERVICE_DISPLAY_NAME
    _svc_description_ = WINDOWS_SERVICE_DESCRIPTION

    def __init__(self, args: list[str]) -> None:
        super().__init__(args)
        self.stop_event = win32event.CreateEvent(None, 0, 0, None)
        self.web_server: ThreadingHTTPServer | None = None
        self.web_thread: threading.Thread | None = None

    def SvcStop(self) -> None:  # noqa: N802
        self.ReportServiceStatus(win32service.SERVICE_STOP_PENDING)
        servicemanager.LogInfoMsg(f"{APP_NAME} - arret du service Windows du serveur central.")
        if self.web_server is not None:
            self.web_server.shutdown()
            self.web_server.server_close()
        stop_embedded_server()
        win32event.SetEvent(self.stop_event)

    def SvcDoRun(self) -> None:  # noqa: N802
        servicemanager.LogInfoMsg(f"{APP_NAME} - demarrage du service Windows du serveur central.")
        self.main()

    def main(self) -> None:
        settings = ensure_central_server_token(load_central_server_settings())
        save_central_server_settings(settings)
        start_embedded_server(
            host="0.0.0.0",
            port=settings.normalized_port(),
            api_token=settings.normalized_token(),
            data_dir=settings.normalized_data_dir(),
        )
        self.web_server = ThreadingHTTPServer(("127.0.0.1", WEB_PRO_PORT), WebProHandler)
        self.web_thread = threading.Thread(
            target=self.web_server.serve_forever,
            name="boulangerie-web-pro",
            daemon=True,
        )
        self.web_thread.start()
        servicemanager.LogInfoMsg(
            f"{APP_NAME} - Web Pro disponible sur le port {WEB_PRO_PORT}."
        )
        win32event.WaitForSingleObject(self.stop_event, win32event.INFINITE)
        stop_embedded_server()


def main() -> None:
    if len(sys.argv) == 3 and sys.argv[1] == "--check-sqlite":
        raise SystemExit(run_sqlite_integrity_check(sys.argv[2]))
    if len(sys.argv) == 1:
        servicemanager.Initialize()
        servicemanager.PrepareToHostSingle(CentralServerWindowsService)
        servicemanager.StartServiceCtrlDispatcher()
        return

    win32serviceutil.HandleCommandLine(CentralServerWindowsService)
