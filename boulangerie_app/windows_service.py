from __future__ import annotations

import sys

import servicemanager  # type: ignore
import win32event  # type: ignore
import win32service  # type: ignore
import win32serviceutil  # type: ignore

from .connected_server import start_embedded_server, stop_embedded_server
from .server_host import (
    WINDOWS_SERVICE_DESCRIPTION,
    WINDOWS_SERVICE_DISPLAY_NAME,
    WINDOWS_SERVICE_NAME,
    load_central_server_settings,
)
from .version import APP_NAME


class CentralServerWindowsService(win32serviceutil.ServiceFramework):
    _svc_name_ = WINDOWS_SERVICE_NAME
    _svc_display_name_ = WINDOWS_SERVICE_DISPLAY_NAME
    _svc_description_ = WINDOWS_SERVICE_DESCRIPTION

    def __init__(self, args: list[str]) -> None:
        super().__init__(args)
        self.stop_event = win32event.CreateEvent(None, 0, 0, None)

    def SvcStop(self) -> None:  # noqa: N802
        self.ReportServiceStatus(win32service.SERVICE_STOP_PENDING)
        servicemanager.LogInfoMsg(f"{APP_NAME} - arret du service Windows du serveur central.")
        stop_embedded_server()
        win32event.SetEvent(self.stop_event)

    def SvcDoRun(self) -> None:  # noqa: N802
        servicemanager.LogInfoMsg(f"{APP_NAME} - demarrage du service Windows du serveur central.")
        self.main()

    def main(self) -> None:
        settings = load_central_server_settings()
        start_embedded_server(
            host="0.0.0.0",
            port=settings.normalized_port(),
            api_token=settings.normalized_token(),
            data_dir=settings.normalized_data_dir(),
        )
        win32event.WaitForSingleObject(self.stop_event, win32event.INFINITE)
        stop_embedded_server()


def main() -> None:
    if len(sys.argv) == 1:
        servicemanager.Initialize()
        servicemanager.PrepareToHostSingle(CentralServerWindowsService)
        servicemanager.StartServiceCtrlDispatcher()
        return

    win32serviceutil.HandleCommandLine(CentralServerWindowsService)
