from __future__ import annotations

import json
import threading
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from itertools import zip_longest
from pathlib import Path
from queue import Queue
from time import monotonic
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

from .database import DatabaseHelper
from .version import (
    APP_VERSION,
    DEFAULT_UPDATE_MANIFEST_URL,
    UPDATE_CHECK_INTERVAL_DAYS,
    UPDATE_MANDATORY_AFTER_DAYS,
)


UTC = timezone.utc


@dataclass
class UpdateInfo:
    version: str
    download_url: str
    notes: str = ""
    published_at: str = ""


@dataclass
class UpdateCheckResult:
    status: str
    update_info: UpdateInfo | None = None
    error_message: str = ""
    mandatory: bool = False
    first_seen_at: str = ""
    days_since_available: int = 0
    mandatory_after_days: int = UPDATE_MANDATORY_AFTER_DAYS


@dataclass
class SessionNotice:
    message: str
    duration_ms: int = 60_000
    foreground: str = "#1f6f43"
    expires_at: float = 0.0

    @classmethod
    def create(
        cls,
        message: str,
        duration_ms: int = 60_000,
        foreground: str = "#1f6f43",
    ) -> "SessionNotice":
        return cls(
            message=message,
            duration_ms=duration_ms,
            foreground=foreground,
            expires_at=monotonic() + (duration_ms / 1000),
        )

    def remaining_ms(self) -> int:
        return max(int((self.expires_at - monotonic()) * 1000), 0)


class UpdateChecker:
    state_path = DatabaseHelper.app_data_dir / "update_state.json"
    config_path = DatabaseHelper.app_data_dir / "update_config.json"
    app_state_path = DatabaseHelper.app_data_dir / "app_state.json"

    @classmethod
    def ensure_config_file(cls) -> None:
        cls.config_path.parent.mkdir(parents=True, exist_ok=True)
        if cls.config_path.exists():
            return

        content = {
            "manifest_url": DEFAULT_UPDATE_MANIFEST_URL,
            "check_interval_days": UPDATE_CHECK_INTERVAL_DAYS,
        }
        cls.config_path.write_text(
            json.dumps(content, indent=2, ensure_ascii=True),
            encoding="utf-8",
        )

    @classmethod
    def load_config(cls) -> dict[str, Any]:
        cls.ensure_config_file()
        defaults = {
            "manifest_url": DEFAULT_UPDATE_MANIFEST_URL,
            "check_interval_days": UPDATE_CHECK_INTERVAL_DAYS,
        }
        try:
            loaded = json.loads(cls.config_path.read_text(encoding="utf-8-sig"))
        except (OSError, json.JSONDecodeError):
            return defaults

        if not isinstance(loaded, dict):
            return defaults

        merged = {
            "manifest_url": str(loaded.get("manifest_url") or defaults["manifest_url"]).strip(),
            "check_interval_days": loaded.get("check_interval_days", defaults["check_interval_days"]),
        }

        try:
            interval = int(merged["check_interval_days"])
        except (TypeError, ValueError):
            interval = defaults["check_interval_days"]

        merged["check_interval_days"] = max(interval, 1)

        if merged != loaded:
            try:
                cls.config_path.write_text(
                    json.dumps(merged, indent=2, ensure_ascii=True),
                    encoding="utf-8",
                )
            except OSError:
                pass

        return merged

    @classmethod
    def load_state(cls) -> dict[str, Any]:
        if not cls.state_path.exists():
            return {}
        try:
            return json.loads(cls.state_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return {}

    @classmethod
    def save_state(cls, state: dict[str, Any]) -> None:
        cls.state_path.parent.mkdir(parents=True, exist_ok=True)
        cls.state_path.write_text(
            json.dumps(state, indent=2, ensure_ascii=True),
            encoding="utf-8",
        )

    @classmethod
    def load_app_state(cls) -> dict[str, Any]:
        if not cls.app_state_path.exists():
            return {}
        try:
            return json.loads(cls.app_state_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return {}

    @classmethod
    def save_app_state(cls, state: dict[str, Any]) -> None:
        cls.app_state_path.parent.mkdir(parents=True, exist_ok=True)
        cls.app_state_path.write_text(
            json.dumps(state, indent=2, ensure_ascii=True),
            encoding="utf-8",
        )

    @classmethod
    def consume_post_update_notice(cls) -> SessionNotice | None:
        state = cls.load_app_state()
        previous_version = str(state.get("last_started_version") or "").strip()
        state["last_started_version"] = APP_VERSION
        cls.save_app_state(state)

        if not previous_version or previous_version == APP_VERSION:
            return None

        if not cls.is_newer_version(APP_VERSION, previous_version):
            return None

        return SessionNotice.create(
            f"Mise a jour reussie : vous utilisez maintenant la version {APP_VERSION} "
            f"(ancienne version : {previous_version})."
        )

    @classmethod
    def get_manifest_url(cls) -> str:
        config = cls.load_config()
        return str(config.get("manifest_url") or "").strip()

    @classmethod
    def get_interval_days(cls) -> int:
        config = cls.load_config()
        raw_value = config.get("check_interval_days", UPDATE_CHECK_INTERVAL_DAYS)
        try:
            interval = int(raw_value)
        except (TypeError, ValueError):
            interval = UPDATE_CHECK_INTERVAL_DAYS
        return max(interval, 1)

    @classmethod
    def should_check_now(cls) -> bool:
        manifest_url = cls.get_manifest_url()
        if not manifest_url:
            return False

        state = cls.load_state()
        last_attempt = cls.parse_datetime(state.get("last_attempt_at", ""))
        if last_attempt is None:
            return True

        next_attempt = last_attempt + timedelta(days=cls.get_interval_days())
        return datetime.now(UTC) >= next_attempt

    @classmethod
    def run_weekly_check_async(cls, result_queue: Queue[UpdateCheckResult]) -> bool:
        if not cls.should_check_now():
            return False

        return cls._start_worker(result_queue)

    @classmethod
    def run_startup_check_async(cls, result_queue: Queue[UpdateCheckResult]) -> bool:
        if not cls.get_manifest_url():
            return False

        return cls._start_worker(result_queue)

    @classmethod
    def _start_worker(cls, result_queue: Queue[UpdateCheckResult]) -> bool:
        worker = threading.Thread(
            target=cls._worker,
            args=(result_queue,),
            daemon=True,
        )
        worker.start()
        return True

    @classmethod
    def _build_update_result(
        cls,
        state: dict[str, Any],
        update_info: UpdateInfo,
        now: datetime,
    ) -> UpdateCheckResult:
        available_versions = state.get("available_versions")
        if not isinstance(available_versions, dict):
            available_versions = {}

        version_state = available_versions.get(update_info.version)
        if not isinstance(version_state, dict):
            version_state = {}

        first_seen = cls.parse_datetime(str(version_state.get("first_seen_at", "")))
        if first_seen is None:
            first_seen = now
            version_state["first_seen_at"] = first_seen.isoformat()

        version_state["last_seen_at"] = now.isoformat()
        available_versions[update_info.version] = version_state
        state["available_versions"] = available_versions

        days_since_available = max((now.date() - first_seen.date()).days, 0)
        return UpdateCheckResult(
            status="update_available",
            update_info=update_info,
            mandatory=days_since_available >= UPDATE_MANDATORY_AFTER_DAYS,
            first_seen_at=first_seen.isoformat(),
            days_since_available=days_since_available,
            mandatory_after_days=UPDATE_MANDATORY_AFTER_DAYS,
        )

    @classmethod
    def _worker(cls, result_queue: Queue[UpdateCheckResult]) -> None:
        manifest_url = cls.get_manifest_url()
        now = datetime.now(UTC)
        state = cls.load_state()
        state["last_attempt_at"] = now.isoformat()
        state["last_error"] = ""
        cls.save_state(state)

        try:
            update_info = cls.fetch_update_info(manifest_url)
            state["last_success_at"] = now.isoformat()
            state["last_available_version"] = update_info.version

            if cls.is_newer_version(update_info.version, APP_VERSION):
                update_result = cls._build_update_result(state, update_info, now)
                cls.save_state(state)
                result_queue.put(update_result)
            else:
                cls.save_state(state)
                result_queue.put(UpdateCheckResult(status="up_to_date"))
        except Exception as exc:
            state["last_error"] = str(exc)
            cls.save_state(state)
            result_queue.put(UpdateCheckResult(status="error", error_message=str(exc)))

    @classmethod
    def fetch_update_info(cls, manifest_url: str) -> UpdateInfo:
        request = Request(
            manifest_url,
            headers={"User-Agent": f"BoulangerieLomoto/{APP_VERSION}"},
        )
        try:
            with urlopen(request, timeout=10) as response:
                payload = json.loads(response.read().decode("utf-8-sig"))
        except HTTPError as exc:
            raise RuntimeError(f"Échec HTTP pendant la vérification des mises à jour : {exc.code}") from exc
        except URLError as exc:
            raise RuntimeError("Impossible de contacter le serveur de mise à jour.") from exc
        except json.JSONDecodeError as exc:
            raise RuntimeError("Le manifeste de mise à jour n'est pas un JSON valide.") from exc

        version = str(payload.get("version", "")).strip()
        if not version:
            raise RuntimeError("Le manifeste de mise à jour ne contient pas de numéro de version.")

        download_url = str(payload.get("download_url") or manifest_url).strip()
        notes = str(payload.get("notes", "")).strip()
        published_at = str(payload.get("published_at", "")).strip()

        return UpdateInfo(
            version=version,
            download_url=download_url,
            notes=notes,
            published_at=published_at,
        )

    @staticmethod
    def parse_datetime(value: str) -> datetime | None:
        text = str(value).strip()
        if not text:
            return None
        try:
            parsed = datetime.fromisoformat(text)
        except ValueError:
            return None
        if parsed.tzinfo is None:
            return parsed.replace(tzinfo=UTC)
        return parsed.astimezone(UTC)

    @staticmethod
    def version_parts(version: str) -> list[int]:
        parts: list[int] = []
        current = ""
        for character in version:
            if character.isdigit():
                current += character
            else:
                if current:
                    parts.append(int(current))
                    current = ""
        if current:
            parts.append(int(current))
        return parts or [0]

    @classmethod
    def is_newer_version(cls, candidate_version: str, current_version: str) -> bool:
        candidate_parts = cls.version_parts(candidate_version)
        current_parts = cls.version_parts(current_version)

        for candidate, current in zip_longest(candidate_parts, current_parts, fillvalue=0):
            if candidate > current:
                return True
            if candidate < current:
                return False
        return False
