from __future__ import annotations

import ctypes
import json
import os
import shutil
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Sequence

from .connected_mode import REMOTE_DEFAULT_PORT, REMOTE_DISCOVERY_PORT
from .connected_server import list_local_server_urls
from .version import APP_NAME

WINDOWS_SERVICE_NAME = "BoulangerieLomotoCentralServer"
WINDOWS_SERVICE_DISPLAY_NAME = f"{APP_NAME} - Serveur central"
WINDOWS_SERVICE_DESCRIPTION = (
    "Service Windows du serveur central Boulangerie Lomoto pour le mode connecté."
)
WINDOWS_SERVICE_EXECUTABLE_NAME = "Boulangerie Lomoto Service.exe"
SERVER_HOST_SETTINGS_FILENAME = "server-host-settings.json"
SERVER_DATA_FOLDER_NAME = "central-server-data"
FIREWALL_RULE_TCP_NAME = f"{APP_NAME} - Serveur central TCP"
FIREWALL_RULE_UDP_NAME = f"{APP_NAME} - Découverte serveur UDP"


def get_server_root_dir() -> Path:
    program_data = os.environ.get("PROGRAMDATA", r"C:\ProgramData").strip() or r"C:\ProgramData"
    return Path(program_data) / "BoulangerieLomoto"


def get_server_settings_path() -> Path:
    return get_server_root_dir() / SERVER_HOST_SETTINGS_FILENAME


def get_default_server_data_dir() -> Path:
    return get_server_root_dir() / SERVER_DATA_FOLDER_NAME


def get_service_runtime_directory() -> Path:
    if getattr(sys, "frozen", False):
        return Path(sys.executable).resolve().parent
    return Path(__file__).resolve().parent.parent


def get_service_management_command_prefix() -> list[str]:
    runtime_dir = get_service_runtime_directory()
    bundled_service_executable = runtime_dir / WINDOWS_SERVICE_EXECUTABLE_NAME
    if bundled_service_executable.exists():
        return [str(bundled_service_executable)]

    project_root = Path(__file__).resolve().parent.parent
    python_executable = project_root / ".venv" / "Scripts" / "python.exe"
    service_script = project_root / "serveur_windows_service.py"
    if python_executable.exists() and service_script.exists():
        return [str(python_executable), str(service_script)]

    raise FileNotFoundError(
        "Le programme du service Windows est introuvable. Regénérez d'abord l'application."
    )


@dataclass
class CentralServerSettings:
    port: int = REMOTE_DEFAULT_PORT
    api_token: str = ""
    data_dir: str = ""

    def normalized_port(self) -> int:
        port = int(self.port or REMOTE_DEFAULT_PORT)
        if port < 1 or port > 65535:
            return REMOTE_DEFAULT_PORT
        return port

    def normalized_token(self) -> str:
        return self.api_token.strip()

    def normalized_data_dir(self) -> Path:
        raw_value = self.data_dir.strip()
        if not raw_value:
            return get_default_server_data_dir()
        return Path(raw_value).expanduser()

    def to_dict(self) -> dict[str, str | int]:
        return {
            "port": self.normalized_port(),
            "api_token": self.normalized_token(),
            "data_dir": str(self.normalized_data_dir()),
        }


@dataclass
class WindowsServiceStatus:
    installed: bool
    state: str
    message: str

    @property
    def is_running(self) -> bool:
        return self.state == "running"

    @property
    def is_stopped(self) -> bool:
        return self.state == "stopped"


def load_central_server_settings() -> CentralServerSettings:
    settings_path = get_server_settings_path()
    if not settings_path.exists():
        return CentralServerSettings()

    try:
        payload = json.loads(settings_path.read_text(encoding="utf-8-sig"))
    except (OSError, ValueError):
        return CentralServerSettings()

    if not isinstance(payload, dict):
        return CentralServerSettings()

    return CentralServerSettings(
        port=int(payload.get("port", REMOTE_DEFAULT_PORT) or REMOTE_DEFAULT_PORT),
        api_token=str(payload.get("api_token", "")),
        data_dir=str(payload.get("data_dir", "")),
    )


def save_central_server_settings(settings: CentralServerSettings) -> Path:
    root_dir = get_server_root_dir()
    root_dir.mkdir(parents=True, exist_ok=True)
    settings_path = get_server_settings_path()
    settings_path.write_text(
        json.dumps(settings.to_dict(), ensure_ascii=True, indent=2),
        encoding="utf-8",
    )
    settings.normalized_data_dir().mkdir(parents=True, exist_ok=True)
    return settings_path


def prepare_central_server_data(source_data_dir: str | Path | None = None) -> bool:
    settings = load_central_server_settings()
    target_dir = settings.normalized_data_dir()
    target_dir.mkdir(parents=True, exist_ok=True)

    target_database = target_dir / "boulangerie.db"
    if target_database.exists():
        return False

    candidates: list[Path] = []
    if source_data_dir:
        candidates.append(Path(source_data_dir))

    local_app_data = os.environ.get("LOCALAPPDATA", "").strip()
    if local_app_data:
        candidates.append(Path(local_app_data) / "BoulangerieLomoto")

    seen: set[str] = set()
    for candidate_dir in candidates:
        try:
            resolved_candidate = str(candidate_dir.resolve())
        except OSError:
            resolved_candidate = str(candidate_dir)
        if resolved_candidate in seen:
            continue
        seen.add(resolved_candidate)

        source_database = candidate_dir / "boulangerie.db"
        if not source_database.exists():
            continue

        shutil.copy2(source_database, target_database)
        for folder_name in ("sauvegardes", "rapports"):
            source_folder = candidate_dir / folder_name
            target_folder = target_dir / folder_name
            if source_folder.exists():
                shutil.copytree(source_folder, target_folder, dirs_exist_ok=True)
        return True

    return False


def build_local_server_addresses(port: int | None = None) -> list[str]:
    settings = load_central_server_settings()
    return list_local_server_urls(port or settings.normalized_port())


def is_running_as_administrator() -> bool:
    try:
        return bool(ctypes.windll.shell32.IsUserAnAdmin())
    except Exception:
        return False


def relaunch_current_process_as_administrator() -> bool:
    executable = sys.executable
    if getattr(sys, "frozen", False):
        arguments = sys.argv[1:]
    else:
        arguments = [sys.argv[0], *sys.argv[1:]]

    parameter_text = subprocess.list2cmdline(arguments)
    try:
        result = ctypes.windll.shell32.ShellExecuteW(
            None,
            "runas",
            executable,
            parameter_text,
            None,
            1,
        )
    except Exception:
        return False
    return result > 32


def _run_text_command(command: Sequence[str], timeout_seconds: int = 90) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        list(command),
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        timeout=timeout_seconds,
    )


def _format_command_error(result: subprocess.CompletedProcess[str], fallback_message: str) -> str:
    output_parts = [fallback_message]
    combined = "\n".join(part.strip() for part in (result.stdout, result.stderr) if part.strip())
    if combined:
        output_parts.append(combined)
    return "\n\n".join(output_parts)


def _refresh_firewall_rule(rule_name: str, protocol: str, local_port: int) -> None:
    _run_text_command(
        [
            "netsh",
            "advfirewall",
            "firewall",
            "delete",
            "rule",
            f"name={rule_name}",
        ],
        timeout_seconds=20,
    )
    result = _run_text_command(
        [
            "netsh",
            "advfirewall",
            "firewall",
            "add",
            "rule",
            f"name={rule_name}",
            "dir=in",
            "action=allow",
            f"protocol={protocol}",
            f"localport={local_port}",
            "profile=any",
            "enable=yes",
        ],
        timeout_seconds=20,
    )
    if result.returncode != 0:
        raise RuntimeError(
            _format_command_error(
                result,
                f"Impossible d'ouvrir automatiquement le pare-feu Windows pour {protocol} {local_port}.",
            )
        )


def ensure_windows_firewall_rules(port: int | None = None) -> str:
    tcp_port = int(port or load_central_server_settings().normalized_port())
    _refresh_firewall_rule(FIREWALL_RULE_TCP_NAME, "TCP", tcp_port)
    _refresh_firewall_rule(FIREWALL_RULE_UDP_NAME, "UDP", REMOTE_DISCOVERY_PORT)
    return (
        "Les règles du pare-feu Windows ont été configurées pour "
        f"TCP {tcp_port} et UDP {REMOTE_DISCOVERY_PORT}."
    )


def get_windows_service_status() -> WindowsServiceStatus:
    result = _run_text_command(["sc.exe", "query", WINDOWS_SERVICE_NAME], timeout_seconds=20)
    combined_text = "\n".join(part for part in (result.stdout, result.stderr) if part).lower()
    if result.returncode != 0:
        if "1060" in combined_text or "does not exist" in combined_text or "n'existe pas" in combined_text:
            return WindowsServiceStatus(
                installed=False,
                state="not_installed",
                message="Le service Windows n'est pas encore installe.",
            )
        return WindowsServiceStatus(
            installed=False,
            state="error",
            message=_format_command_error(result, "Impossible de lire l'etat du service Windows."),
        )

    state = "unknown"
    message = "Le service Windows est installe."
    for line in result.stdout.splitlines():
        if "STATE" not in line.upper():
            continue
        upper_line = line.upper()
        if "RUNNING" in upper_line:
            state = "running"
            message = "Le service Windows est actif."
        elif "STOPPED" in upper_line:
            state = "stopped"
            message = "Le service Windows est installe mais arrete."
        elif "START_PENDING" in upper_line:
            state = "start_pending"
            message = "Le service Windows est en cours de demarrage."
        elif "STOP_PENDING" in upper_line:
            state = "stop_pending"
            message = "Le service Windows est en cours d'arret."
        break

    return WindowsServiceStatus(installed=True, state=state, message=message)


def install_or_update_windows_service(settings: CentralServerSettings, source_data_dir: str | Path | None = None) -> str:
    save_central_server_settings(settings)
    prepare_central_server_data(source_data_dir)
    firewall_message = ensure_windows_firewall_rules(settings.normalized_port())
    command = get_service_management_command_prefix()
    result = _run_text_command([*command, "--startup", "auto", "install"], timeout_seconds=120)
    if result.returncode != 0:
        raise RuntimeError(_format_command_error(result, "Impossible d'installer ou mettre a jour le service Windows."))
    _run_text_command(
        ["sc.exe", "description", WINDOWS_SERVICE_NAME, WINDOWS_SERVICE_DESCRIPTION],
        timeout_seconds=20,
    )
    service_message = "\n".join(part.strip() for part in (result.stdout, result.stderr) if part.strip()) or (
        "Le service Windows a ete installe ou mis a jour."
    )
    return f"{service_message}\n{firewall_message}"


def start_windows_service(wait_seconds: int = 30) -> str:
    firewall_message = ensure_windows_firewall_rules()
    result = _run_text_command(
        [*get_service_management_command_prefix(), "--wait", str(wait_seconds), "start"],
        timeout_seconds=max(wait_seconds + 20, 60),
    )
    if result.returncode != 0:
        raise RuntimeError(_format_command_error(result, "Impossible de démarrer le service Windows."))
    service_message = "\n".join(part.strip() for part in (result.stdout, result.stderr) if part.strip()) or (
        "Le service Windows a démarré."
    )
    return f"{service_message}\n{firewall_message}"


def stop_windows_service(wait_seconds: int = 30) -> str:
    result = _run_text_command(
        [*get_service_management_command_prefix(), "--wait", str(wait_seconds), "stop"],
        timeout_seconds=max(wait_seconds + 20, 60),
    )
    if result.returncode != 0:
        raise RuntimeError(_format_command_error(result, "Impossible d'arreter le service Windows."))
    return "\n".join(part.strip() for part in (result.stdout, result.stderr) if part.strip()) or (
        "Le service Windows a ete arrete."
    )


def remove_windows_service() -> str:
    result = _run_text_command([*get_service_management_command_prefix(), "remove"], timeout_seconds=120)
    if result.returncode != 0:
        raise RuntimeError(_format_command_error(result, "Impossible de désinstaller le service Windows."))
    return "\n".join(part.strip() for part in (result.stdout, result.stderr) if part.strip()) or (
        "Le service Windows a ete desinstalle."
    )
