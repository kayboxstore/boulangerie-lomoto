from __future__ import annotations

import base64
import hashlib
import hmac
import json
import os
import platform
import secrets
import uuid
from dataclasses import dataclass
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.parse import urlparse
from urllib.request import Request, urlopen

from .client_config import (
    get_allowed_domains,
    get_client_id,
    get_license_offline_grace_days,
    get_license_online_check_interval_hours,
    get_license_public_key,
    get_license_server_url,
    is_license_online_required,
    is_license_required,
)
from .license_crypto import verify as verify_ed25519_signature


LICENSE_PREFIX = "WL2"
LEGACY_LICENSE_PREFIX = "WL1"
PAYLOAD_SCHEMA = 1


@dataclass(frozen=True)
class LicenseStatus:
    ok: bool
    code: str
    message: str
    payload: dict[str, Any]
    license_path: Path
    registry_path: Path

    @property
    def client_name(self) -> str:
        return str(self.payload.get("clientName") or self.payload.get("appName") or "")

    @property
    def valid_until(self) -> str:
        return str(self.payload.get("validUntil") or "")

    @property
    def max_devices(self) -> int:
        try:
            return int(self.payload.get("maxDevices") or 0)
        except (TypeError, ValueError):
            return 0


def _activation_dir(base_dir: Path) -> Path:
    return Path(base_dir) / "activation"


def _now_utc() -> datetime:
    return datetime.now(timezone.utc)


def _now_text() -> str:
    return _now_utc().strftime("%Y-%m-%dT%H:%M:%SZ")


def _parse_time(value: str) -> datetime | None:
    try:
        return datetime.strptime(str(value or ""), "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=timezone.utc)
    except ValueError:
        return None


def default_license_path(base_dir: Path) -> Path:
    configured = os.environ.get("BOULANGERIE_LICENSE_FILE", "").strip()
    if configured:
        return Path(configured)
    return _activation_dir(base_dir) / "license.key"


def default_registry_path(base_dir: Path) -> Path:
    configured = os.environ.get("BOULANGERIE_ACTIVATION_REGISTRY", "").strip()
    if configured:
        return Path(configured)
    return _activation_dir(base_dir) / "activation.json"


def online_status_path(base_dir: Path) -> Path:
    return _activation_dir(base_dir) / "online-status.json"


def _b64url_encode(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).decode("ascii").rstrip("=")


def _b64url_decode(value: str) -> bytes:
    return base64.urlsafe_b64decode((value + ("=" * (-len(value) % 4))).encode("ascii"))


def _canonical_json(data: Any) -> bytes:
    return json.dumps(data, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")


def _license_id(payload: dict[str, Any]) -> str:
    existing = str(payload.get("licenseId") or "").strip()
    if existing:
        return existing
    client_id = str(payload.get("clientId") or get_client_id() or "client").strip()
    valid_until = str(payload.get("validUntil") or "permanent").strip()
    return f"{client_id}-{valid_until}"


def _secret() -> str:
    return os.environ.get("BOULANGERIE_LICENSE_SECRET", "").strip() or os.environ.get("WHITE_LABEL_LICENSE_SECRET", "").strip()


def normalize_domain(value: str) -> str:
    value = str(value or "").strip().lower()
    if not value:
        return ""
    if "://" not in value:
        value = "https://" + value
    parsed = urlparse(value)
    return (parsed.hostname or "").strip(".").lower()


def domain_matches(domain: str, allowed_domains: list[str]) -> bool:
    domain = normalize_domain(domain)
    if not domain:
        return True
    for item in allowed_domains:
        allowed = normalize_domain(str(item))
        if not allowed:
            continue
        if domain == allowed:
            return True
        if allowed.startswith("*.") and domain.endswith(allowed[1:]) and domain != allowed[2:]:
            return True
    return False


def parse_license_key(key: str) -> tuple[str, dict[str, Any], str]:
    parts = str(key or "").strip().split(".")
    if len(parts) != 3 or parts[0] not in {LICENSE_PREFIX, LEGACY_LICENSE_PREFIX}:
        raise ValueError("Format de licence invalide.")
    payload = json.loads(_b64url_decode(parts[1]).decode("utf-8"))
    if not isinstance(payload, dict):
        raise ValueError("Contenu de licence invalide.")
    return parts[0], payload, parts[2]


def verify_license_key(key: str, *, domain: str = "", client_id: str = "", now: date | None = None) -> tuple[bool, str, str, dict[str, Any]]:
    try:
        prefix, payload, signature = parse_license_key(key)
    except Exception as exc:
        return False, "invalid-format", str(exc), {}

    signed_payload = _canonical_json(payload)
    if prefix == LICENSE_PREFIX:
        public_key = get_license_public_key()
        if not public_key:
            return False, "missing-public-key", "Cle publique de licence manquante.", payload
        if not verify_ed25519_signature(public_key, signed_payload, signature):
            return False, "bad-signature", "Signature de licence invalide.", payload
    else:
        secret = _secret()
        if not secret:
            return False, "legacy-missing-secret", "Ancienne licence detectee. Generez une licence WL2 signee.", payload
        expected = _b64url_encode(hmac.new(secret.encode("utf-8"), signed_payload, hashlib.sha256).digest())
        if not hmac.compare_digest(signature, expected):
            return False, "bad-signature", "Signature de licence invalide.", payload

    if payload.get("schema") != PAYLOAD_SCHEMA:
        return False, "bad-schema", "Version de licence non supportee.", payload

    expected_client = client_id or get_client_id()
    if expected_client and str(payload.get("clientId") or "") != expected_client:
        return False, "client-mismatch", "Cette licence ne correspond pas a ce client.", payload

    current = now or datetime.now(timezone.utc).date()
    try:
        valid_from = datetime.strptime(str(payload.get("validFrom")), "%Y-%m-%d").date()
        valid_until = datetime.strptime(str(payload.get("validUntil")), "%Y-%m-%d").date()
    except ValueError:
        return False, "bad-date", "Dates de licence invalides.", payload
    if current < valid_from:
        return False, "not-started", "La licence n'est pas encore active.", payload
    if current > valid_until:
        return False, "expired", "La licence est expiree.", payload

    allowed = [str(item) for item in payload.get("allowedDomains") or get_allowed_domains()]
    if domain and not domain_matches(domain, allowed):
        return False, "domain-mismatch", "Le domaine n'est pas autorise par cette licence.", payload

    try:
        if int(payload.get("maxDevices") or 0) < 1:
            return False, "bad-device-limit", "La limite de postes est invalide.", payload
    except (TypeError, ValueError):
        return False, "bad-device-limit", "La limite de postes est invalide.", payload
    return True, "ok", "Licence valide.", payload


def default_device_id(seed: str = "") -> str:
    raw = "|".join([platform.node(), platform.system(), platform.machine(), str(uuid.getnode()), seed])
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()[:32]


def default_device_name() -> str:
    name = platform.node().strip()
    system = platform.system().strip()
    return f"{name} ({system})" if name and system else name or system or "Poste inconnu"


def read_activation_registry(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {"schema": 1, "clientId": "", "activations": []}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {"schema": 1, "clientId": "", "activations": []}
    if not isinstance(data, dict):
        return {"schema": 1, "clientId": "", "activations": []}
    data.setdefault("schema", 1)
    data.setdefault("clientId", "")
    data.setdefault("activations", [])
    return data


def write_activation_registry(path: Path, registry: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(registry, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def activate_device(
    key: str,
    base_dir: Path,
    *,
    domain: str = "",
    device_id: str = "",
    device_name: str = "",
) -> LicenseStatus:
    license_path = default_license_path(base_dir)
    registry_path = default_registry_path(base_dir)
    ok, code, message, payload = verify_license_key(key, domain=domain)
    if not ok:
        return LicenseStatus(False, code, message, payload, license_path, registry_path)

    client_id = str(payload.get("clientId") or get_client_id())
    max_devices = int(payload.get("maxDevices") or 1)
    registry = read_activation_registry(registry_path)
    existing_client = str(registry.get("clientId") or client_id)
    if existing_client != client_id:
        return LicenseStatus(False, "registry-client-mismatch", "Registre d'activation lie a un autre client.", payload, license_path, registry_path)
    registry["clientId"] = client_id

    activations = registry.get("activations") or []
    device_id = device_id or default_device_id(client_id)
    device_name = device_name or default_device_name()
    online_ok, online_code, online_message, key = _check_online_license(
        key,
        base_dir,
        payload,
        domain=domain,
        device_id=device_id,
        device_name=device_name,
        action="activate",
        force=True,
    )
    if not online_ok:
        return LicenseStatus(False, online_code, online_message, payload, license_path, registry_path)
    timestamp = _now_text()
    for activation in activations:
        if activation.get("deviceId") == device_id:
            activation["deviceName"] = device_name
            activation["lastSeenAt"] = timestamp
            write_activation_registry(registry_path, registry)
            save_license_key(key, base_dir)
            return LicenseStatus(True, "already-activated", "Ce poste est deja active.", payload, license_path, registry_path)
    if len(activations) >= max_devices:
        return LicenseStatus(False, "device-limit-exceeded", f"La licence autorise {max_devices} poste(s). Limite atteinte.", payload, license_path, registry_path)

    activations.append({"deviceId": device_id, "deviceName": device_name, "activatedAt": timestamp, "lastSeenAt": timestamp})
    registry["activations"] = activations
    write_activation_registry(registry_path, registry)
    save_license_key(key, base_dir)
    return LicenseStatus(True, "activated", "Poste active avec succes.", payload, license_path, registry_path)


def save_license_key(key: str, base_dir: Path) -> Path:
    path = default_license_path(base_dir)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(str(key or "").strip() + "\n", encoding="utf-8")
    return path


def load_license_key(base_dir: Path) -> str:
    env_key = os.environ.get("BOULANGERIE_LICENSE_KEY", "").strip()
    if env_key:
        return env_key
    path = default_license_path(base_dir)
    if not path.exists():
        return ""
    return path.read_text(encoding="utf-8").strip()


def validate_current_license(base_dir: Path, *, domain: str = "") -> LicenseStatus:
    license_path = default_license_path(base_dir)
    registry_path = default_registry_path(base_dir)
    if not is_license_required():
        return LicenseStatus(True, "not-required", "Licence non obligatoire pour cette edition.", {}, license_path, registry_path)
    key = load_license_key(base_dir)
    if not key:
        return LicenseStatus(False, "missing-license", "Aucune licence active n'a ete trouvee.", {}, license_path, registry_path)
    ok, code, message, payload = verify_license_key(key, domain=domain)
    if not ok:
        return LicenseStatus(False, code, message, payload, license_path, registry_path)

    client_id = str(payload.get("clientId") or get_client_id())
    device_id = default_device_id(client_id)
    registry = read_activation_registry(registry_path)
    activations = registry.get("activations") or []
    matching_activation = None
    for activation in activations:
        if activation.get("deviceId") == device_id:
            matching_activation = activation
            break
    if matching_activation is None:
        return activate_device(key, base_dir, domain=domain, device_id=device_id)

    online_ok, online_code, online_message, _key = _check_online_license(
        key,
        base_dir,
        payload,
        domain=domain,
        device_id=device_id,
        device_name=str(matching_activation.get("deviceName") or default_device_name()),
        action="check",
    )
    if not online_ok:
        return LicenseStatus(False, online_code, online_message, payload, license_path, registry_path)

    matching_activation["lastSeenAt"] = _now_text()
    registry["activations"] = activations
    write_activation_registry(registry_path, registry)
    return LicenseStatus(True, "ok", "Licence valide.", payload, license_path, registry_path)


def list_activations(base_dir: Path) -> list[dict[str, Any]]:
    registry = read_activation_registry(default_registry_path(base_dir))
    activations = registry.get("activations") or []
    return [item for item in activations if isinstance(item, dict)]


def deactivate_device(base_dir: Path, device_id: str) -> bool:
    registry_path = default_registry_path(base_dir)
    registry = read_activation_registry(registry_path)
    activations = registry.get("activations") or []
    kept = [item for item in activations if str(item.get("deviceId") or "") != device_id]
    if len(kept) == len(activations):
        return False
    registry["activations"] = kept
    write_activation_registry(registry_path, registry)
    return True


def read_online_status(base_dir: Path) -> dict[str, Any]:
    path = online_status_path(base_dir)
    if not path.exists():
        return {"schema": 1, "checks": {}}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {"schema": 1, "checks": {}}
    if not isinstance(data, dict):
        return {"schema": 1, "checks": {}}
    data.setdefault("schema", 1)
    data.setdefault("checks", {})
    return data


def write_online_status(base_dir: Path, status: dict[str, Any]) -> None:
    path = online_status_path(base_dir)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(status, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def _online_cache_key(payload: dict[str, Any], device_id: str) -> str:
    return f"{_license_id(payload)}:{device_id}"


def _online_check_due(base_dir: Path, payload: dict[str, Any], device_id: str) -> bool:
    cache = read_online_status(base_dir)
    entry = (cache.get("checks") or {}).get(_online_cache_key(payload, device_id)) or {}
    checked_at = _parse_time(str(entry.get("lastCheckedAt") or ""))
    if checked_at is None:
        return True
    interval = timedelta(hours=get_license_online_check_interval_hours())
    return _now_utc() - checked_at >= interval


def _online_cached_entry(base_dir: Path, payload: dict[str, Any], device_id: str) -> dict[str, Any]:
    cache = read_online_status(base_dir)
    entry = (cache.get("checks") or {}).get(_online_cache_key(payload, device_id)) or {}
    return entry if isinstance(entry, dict) else {}


def _online_grace_ok(base_dir: Path, payload: dict[str, Any], device_id: str) -> bool:
    cache = read_online_status(base_dir)
    entry = (cache.get("checks") or {}).get(_online_cache_key(payload, device_id)) or {}
    last_ok = _parse_time(str(entry.get("lastOkAt") or ""))
    if last_ok is None:
        return not is_license_online_required()
    grace = timedelta(days=get_license_offline_grace_days())
    return _now_utc() - last_ok <= grace


def _save_online_result(
    base_dir: Path,
    payload: dict[str, Any],
    device_id: str,
    *,
    ok: bool,
    code: str,
    message: str,
    server_data: dict[str, Any] | None = None,
) -> None:
    cache = read_online_status(base_dir)
    checks = cache.setdefault("checks", {})
    key = _online_cache_key(payload, device_id)
    previous = checks.get(key) or {}
    timestamp = _now_text()
    entry = {
        "licenseId": _license_id(payload),
        "deviceId": device_id,
        "ok": bool(ok),
        "code": code,
        "message": message,
        "lastCheckedAt": timestamp,
        "lastOkAt": timestamp if ok else previous.get("lastOkAt", ""),
        "serverData": server_data or {},
    }
    checks[key] = entry
    write_online_status(base_dir, cache)


def _post_license_server(path: str, payload: dict[str, Any]) -> dict[str, Any]:
    base_url = get_license_server_url().rstrip("/")
    if not base_url:
        raise RuntimeError("Serveur d'activation non configure.")
    request = Request(
        f"{base_url}{path}",
        data=json.dumps(payload, ensure_ascii=False).encode("utf-8"),
        headers={
            "Accept": "application/json",
            "Content-Type": "application/json",
            "User-Agent": f"BoulangerieLicenseClient/{os.environ.get('BOULANGERIE_APP_VERSION', '1')}",
        },
        method="POST",
    )
    try:
        with urlopen(request, timeout=8) as response:
            data = json.loads(response.read().decode("utf-8-sig") or "{}")
    except HTTPError as exc:
        try:
            data = json.loads(exc.read().decode("utf-8-sig") or "{}")
        except Exception as inner_exc:
            raise RuntimeError(str(exc.reason)) from inner_exc
    except (URLError, OSError, TimeoutError, ValueError) as exc:
        raise RuntimeError(str(exc)) from exc
    if not isinstance(data, dict):
        raise RuntimeError("Reponse serveur invalide.")
    return data


def _check_online_license(
    key: str,
    base_dir: Path,
    payload: dict[str, Any],
    *,
    domain: str = "",
    device_id: str = "",
    device_name: str = "",
    action: str = "check",
    force: bool = False,
) -> tuple[bool, str, str, str]:
    if not get_license_server_url():
        return True, "offline-disabled", "Controle en ligne non configure.", key
    if action == "check" and not force and not _online_check_due(base_dir, payload, device_id):
        cached = _online_cached_entry(base_dir, payload, device_id)
        if cached and not bool(cached.get("ok", True)):
            return False, str(cached.get("code") or "online-blocked"), str(cached.get("message") or "Licence bloquee par le serveur."), key
        return True, "online-cache-valid", "Controle en ligne recent.", key

    request_payload = {
        "licenseKey": key,
        "clientId": str(payload.get("clientId") or get_client_id()),
        "domain": domain,
        "deviceId": device_id,
        "installationCode": generate_installation_code(base_dir),
        "deviceName": device_name or default_device_name(),
        "platform": platform.platform(),
        "appVersion": os.environ.get("BOULANGERIE_APP_VERSION", ""),
    }
    try:
        response = _post_license_server("/api/v1/activate" if action == "activate" else "/api/v1/check", request_payload)
    except RuntimeError as exc:
        if _online_grace_ok(base_dir, payload, device_id):
            _save_online_result(
                base_dir,
                payload,
                device_id,
                ok=True,
                code="online-unreachable-grace",
                message=f"Serveur d'activation indisponible. Grace hors ligne active: {exc}",
            )
            return True, "online-unreachable-grace", "Serveur d'activation indisponible. Grace hors ligne active.", key
        return False, "online-unreachable", "Serveur d'activation indisponible et grace hors ligne expiree.", key

    ok = bool(response.get("ok"))
    code = str(response.get("code") or ("ok" if ok else "blocked"))
    message = str(response.get("message") or "")
    data = response.get("data") if isinstance(response.get("data"), dict) else {}
    new_key = str(data.get("licenseKey") or key).strip() or key
    _save_online_result(base_dir, payload, device_id, ok=ok, code=code, message=message, server_data=data)
    if ok and new_key != key:
        save_license_key(new_key, base_dir)
        try:
            _prefix, refreshed_payload, _signature = parse_license_key(new_key)
            payload.clear()
            payload.update(refreshed_payload)
        except Exception:
            pass
    return ok, code, message, new_key


def generate_installation_code(base_dir: Path) -> str:
    seed_file = _activation_dir(base_dir) / "installation.id"
    if not seed_file.exists():
        seed_file.parent.mkdir(parents=True, exist_ok=True)
        seed_file.write_text(secrets.token_hex(16), encoding="utf-8")
    seed = seed_file.read_text(encoding="utf-8").strip()
    return default_device_id(seed)


def status_payload(base_dir: Path, *, domain: str = "") -> dict[str, Any]:
    status = validate_current_license(base_dir, domain=domain)
    return {
        "ok": status.ok,
        "code": status.code,
        "message": status.message,
        "clientName": status.client_name,
        "validUntil": status.valid_until,
        "maxDevices": status.max_devices,
        "licensePath": str(status.license_path),
        "registryPath": str(status.registry_path),
        "installationCode": generate_installation_code(base_dir),
        "activations": list_activations(base_dir),
        "online": read_online_status(base_dir),
        "activationServerUrl": get_license_server_url(),
        "required": is_license_required(),
        "payload": status.payload if status.ok else {},
    }
