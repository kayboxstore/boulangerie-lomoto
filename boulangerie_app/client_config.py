from __future__ import annotations

import json
import os
import re
import sys
from functools import lru_cache
from pathlib import Path
from typing import Any


DEFAULT_APP_NAME = "Boulangerie Lomoto"
DEFAULT_PUBLISHER = "General Investment Services (GIS)"
DEFAULT_PUBLIC_URL = "https://app.boulangerie-lomoto.com"
DEFAULT_EMAIL_DOMAIN = "boulangerie-lomoto.com"
DEFAULT_CONTACT_EMAIL = "contact@boulangerie-lomoto.com"
DEFAULT_CONTACT_PHONE = "+243 991 599 600"
DEFAULT_PRIMARY_COLOR = "#b22222"
DEFAULT_ACCENT_COLOR = "#1f4e78"
DEFAULT_RESPONSIBLE_NAME = "Christian Lomoto"
DEFAULT_INITIATOR_NAME = "Augustin Kayembe"
DEFAULT_LEGAL_NOTICE = (
    "Application de gestion commerciale developpee pour Boulangerie Lomoto. "
    "Toute reproduction, distribution ou modification non autorisee est interdite."
)
DEFAULT_TRAY_PRICES = {
    "Maman": 6000,
    "Vente cash": 4350,
    "Depositaire": 4100,
    "Depositaire 6.000Fc": 6000,
}
DEFAULT_LICENSE_PUBLIC_KEY = "ed25519:0cwFhHx6QT-1wAgV5Vbw4RcanENaW5BHGXY40RXCYwI"


def _clean(value: Any) -> str:
    return str(value or "").strip()


def _safe_identifier(value: str, fallback: str = "BoulangerieLomoto") -> str:
    text = re.sub(r"[^A-Za-z0-9._-]+", "", _clean(value))
    return text or fallback


def _deep_merge(base: dict[str, Any], override: dict[str, Any]) -> dict[str, Any]:
    result = dict(base)
    for key, value in override.items():
        if isinstance(value, dict) and isinstance(result.get(key), dict):
            result[key] = _deep_merge(result[key], value)
        else:
            result[key] = value
    return result


def _default_config() -> dict[str, Any]:
    return {
        "clientId": "lomoto",
        "companyName": DEFAULT_APP_NAME,
        "appName": DEFAULT_APP_NAME,
        "publisher": DEFAULT_PUBLISHER,
        "domain": "app.boulangerie-lomoto.com",
        "publicUrl": DEFAULT_PUBLIC_URL,
        "emailDomain": DEFAULT_EMAIL_DOMAIN,
        "branding": {
            "primaryColor": DEFAULT_PRIMARY_COLOR,
            "accentColor": DEFAULT_ACCENT_COLOR,
            "logoPath": "",
            "watermarkPath": "",
        },
        "businessRules": {
            "currency": "FC",
            "trayPrices": dict(DEFAULT_TRAY_PRICES),
        },
        "roles": {},
        "license": {
            "required": False,
            "publicKey": DEFAULT_LICENSE_PUBLIC_KEY,
            "activationServerUrl": "",
            "onlineRequired": False,
            "onlineCheckIntervalHours": 24,
            "offlineGraceDays": 7,
            "allowedDomains": [
                "app.boulangerie-lomoto.com",
                "boulangerie-lomoto.com",
                "www.boulangerie-lomoto.com",
            ],
        },
        "contacts": {
            "responsibleName": DEFAULT_RESPONSIBLE_NAME,
            "initiatorName": DEFAULT_INITIATOR_NAME,
            "phone": DEFAULT_CONTACT_PHONE,
            "email": DEFAULT_CONTACT_EMAIL,
        },
        "legal": {
            "notice": DEFAULT_LEGAL_NOTICE,
        },
        "android": {
            "appId": "com.gis.boulangerielomoto",
            "appName": DEFAULT_APP_NAME,
        },
        "installation": {
            "appDataDirName": "BoulangerieLomoto",
            "windowsServiceName": "BoulangerieLomotoCentralServer",
            "windowsServiceExeName": "Boulangerie Lomoto Service.exe",
            "windowsFirewallRuleName": "Boulangerie Lomoto Web Pro 8787",
        },
    }


def _bundled_config_candidates() -> list[Path]:
    candidates: list[Path] = []
    if getattr(sys, "frozen", False):
        runtime_dir = Path(sys.executable).resolve().parent
        bundled_root = Path(getattr(sys, "_MEIPASS", runtime_dir))
        candidates.extend(
            [
                runtime_dir / "client-config.json",
                runtime_dir / "boulangerie_app" / "client-config.json",
                bundled_root / "client-config.json",
                bundled_root / "boulangerie_app" / "client-config.json",
            ]
        )
    project_root = Path(__file__).resolve().parent.parent
    candidates.extend(
        [
            project_root / "client-config.json",
            Path(__file__).resolve().parent / "client-config.json",
        ]
    )
    return candidates


@lru_cache(maxsize=1)
def load_client_config() -> dict[str, Any]:
    config = _default_config()
    config_path = _clean(os.environ.get("BOULANGERIE_CLIENT_CONFIG"))
    if config_path:
        path = Path(config_path)
        if path.exists():
            loaded = json.loads(path.read_text(encoding="utf-8-sig"))
            if isinstance(loaded, dict):
                config = _deep_merge(config, loaded)
    else:
        for path in _bundled_config_candidates():
            if not path.exists():
                continue
            loaded = json.loads(path.read_text(encoding="utf-8-sig"))
            if isinstance(loaded, dict):
                config = _deep_merge(config, loaded)
                break

    config["appName"] = _clean(os.environ.get("BOULANGERIE_APP_NAME")) or _clean(config.get("appName")) or _clean(config.get("companyName")) or DEFAULT_APP_NAME
    config["publisher"] = _clean(os.environ.get("BOULANGERIE_APP_PUBLISHER")) or _clean(config.get("publisher")) or DEFAULT_PUBLISHER
    config["publicUrl"] = _clean(os.environ.get("BOULANGERIE_PUBLIC_URL")) or _clean(config.get("publicUrl")) or DEFAULT_PUBLIC_URL
    config["emailDomain"] = _clean(os.environ.get("BOULANGERIE_EMAIL_DOMAIN")) or _clean(config.get("emailDomain")) or DEFAULT_EMAIL_DOMAIN
    contacts = config.setdefault("contacts", {})
    contacts["email"] = _clean(os.environ.get("BOULANGERIE_CONTACT_EMAIL")) or _clean(contacts.get("email")) or DEFAULT_CONTACT_EMAIL
    contacts["phone"] = _clean(os.environ.get("BOULANGERIE_CONTACT_PHONE")) or _clean(contacts.get("phone")) or DEFAULT_CONTACT_PHONE
    contacts["responsibleName"] = _clean(contacts.get("responsibleName")) or DEFAULT_RESPONSIBLE_NAME
    contacts["initiatorName"] = _clean(contacts.get("initiatorName")) or DEFAULT_INITIATOR_NAME
    license_config = config.setdefault("license", {})
    license_config["publicKey"] = _clean(os.environ.get("BOULANGERIE_LICENSE_PUBLIC_KEY")) or _clean(license_config.get("publicKey")) or DEFAULT_LICENSE_PUBLIC_KEY
    license_config["activationServerUrl"] = _clean(os.environ.get("BOULANGERIE_LICENSE_SERVER_URL")) or _clean(license_config.get("activationServerUrl"))
    license_config["onlineRequired"] = _clean(os.environ.get("BOULANGERIE_LICENSE_ONLINE_REQUIRED")).lower() in {"1", "true", "yes", "oui", "on"} if _clean(os.environ.get("BOULANGERIE_LICENSE_ONLINE_REQUIRED")) else bool(license_config.get("onlineRequired"))
    installation = config.setdefault("installation", {})
    installation["appDataDirName"] = _clean(os.environ.get("BOULANGERIE_APPDATA_DIRNAME")) or _clean(installation.get("appDataDirName")) or _safe_identifier(config["appName"])
    installation["windowsServiceName"] = _clean(os.environ.get("BOULANGERIE_WINDOWS_SERVICE_NAME")) or _clean(installation.get("windowsServiceName")) or f"{_safe_identifier(config['appName'])}CentralServer"
    installation["windowsServiceExeName"] = _clean(os.environ.get("BOULANGERIE_WINDOWS_SERVICE_EXE")) or _clean(installation.get("windowsServiceExeName")) or f"{config['appName']} Service.exe"
    installation["windowsFirewallRuleName"] = _clean(os.environ.get("BOULANGERIE_WINDOWS_FIREWALL_RULE")) or _clean(installation.get("windowsFirewallRuleName")) or f"{config['appName']} Web Pro 8787"
    return config


def reload_client_config() -> dict[str, Any]:
    load_client_config.cache_clear()
    return load_client_config()


def get_client_id() -> str:
    return _clean(load_client_config().get("clientId")) or "client"


def get_company_name() -> str:
    config = load_client_config()
    return _clean(config.get("companyName")) or get_app_name()


def get_app_name() -> str:
    return _clean(load_client_config().get("appName")) or DEFAULT_APP_NAME


def get_publisher() -> str:
    return _clean(load_client_config().get("publisher")) or DEFAULT_PUBLISHER


def get_public_url() -> str:
    return _clean(load_client_config().get("publicUrl")) or DEFAULT_PUBLIC_URL


def get_email_domain() -> str:
    return _clean(load_client_config().get("emailDomain")) or DEFAULT_EMAIL_DOMAIN


def get_contact_email() -> str:
    return _clean((load_client_config().get("contacts") or {}).get("email")) or DEFAULT_CONTACT_EMAIL


def get_contact_phone() -> str:
    return _clean((load_client_config().get("contacts") or {}).get("phone")) or DEFAULT_CONTACT_PHONE


def get_responsible_name() -> str:
    return _clean((load_client_config().get("contacts") or {}).get("responsibleName")) or DEFAULT_RESPONSIBLE_NAME


def get_initiator_name() -> str:
    return _clean((load_client_config().get("contacts") or {}).get("initiatorName")) or DEFAULT_INITIATOR_NAME


def get_legal_notice() -> str:
    legal = load_client_config().get("legal") or {}
    return _clean(legal.get("notice")) or DEFAULT_LEGAL_NOTICE


def get_primary_color() -> str:
    branding = load_client_config().get("branding") or {}
    return _clean(branding.get("primaryColor")) or DEFAULT_PRIMARY_COLOR


def get_accent_color() -> str:
    branding = load_client_config().get("branding") or {}
    return _clean(branding.get("accentColor")) or DEFAULT_ACCENT_COLOR


def get_logo_path() -> str:
    branding = load_client_config().get("branding") or {}
    return _clean(os.environ.get("BOULANGERIE_LOGO_PATH")) or _clean(branding.get("logoPath"))


def get_watermark_path() -> str:
    branding = load_client_config().get("branding") or {}
    return _clean(branding.get("watermarkPath"))


def get_allowed_domains() -> list[str]:
    config = load_client_config()
    license_config = config.get("license") or {}
    raw = license_config.get("allowedDomains") or [config.get("domain")]
    return [_clean(item).lower() for item in raw if _clean(item)]


def get_license_public_key() -> str:
    license_config = load_client_config().get("license") or {}
    return _clean(license_config.get("publicKey")) or DEFAULT_LICENSE_PUBLIC_KEY


def get_license_server_url() -> str:
    license_config = load_client_config().get("license") or {}
    return _clean(license_config.get("activationServerUrl"))


def is_license_online_required() -> bool:
    license_config = load_client_config().get("license") or {}
    return bool(license_config.get("onlineRequired"))


def get_license_online_check_interval_hours() -> int:
    license_config = load_client_config().get("license") or {}
    try:
        return max(int(license_config.get("onlineCheckIntervalHours") or 24), 1)
    except (TypeError, ValueError):
        return 24


def get_license_offline_grace_days() -> int:
    license_config = load_client_config().get("license") or {}
    try:
        return max(int(license_config.get("offlineGraceDays") or 7), 0)
    except (TypeError, ValueError):
        return 7


def get_app_data_dir_name() -> str:
    installation = load_client_config().get("installation") or {}
    return _safe_identifier(_clean(installation.get("appDataDirName")) or get_app_name())


def get_windows_service_name() -> str:
    installation = load_client_config().get("installation") or {}
    return _safe_identifier(_clean(installation.get("windowsServiceName")) or f"{get_app_data_dir_name()}CentralServer")


def get_windows_service_exe_name() -> str:
    installation = load_client_config().get("installation") or {}
    return _clean(installation.get("windowsServiceExeName")) or f"{get_app_name()} Service.exe"


def get_windows_firewall_rule_name() -> str:
    installation = load_client_config().get("installation") or {}
    return _clean(installation.get("windowsFirewallRuleName")) or f"{get_app_name()} Web Pro 8787"


def get_tray_prices() -> dict[str, int]:
    business = load_client_config().get("businessRules") or {}
    raw_prices = business.get("trayPrices") or {}
    prices = dict(DEFAULT_TRAY_PRICES)
    for key, value in raw_prices.items():
        try:
            prices[_clean(key)] = int(float(value))
        except (TypeError, ValueError):
            continue
    if "Depositaire" in prices:
        prices.setdefault("Dépositaire", prices["Depositaire"])
        prices.setdefault("DÃ©positaire", prices["Depositaire"])
    return prices


def get_roles_config() -> dict[str, list[str]]:
    roles = load_client_config().get("roles") or {}
    normalized: dict[str, list[str]] = {}
    if not isinstance(roles, dict):
        return normalized
    for role, modules in roles.items():
        if isinstance(modules, list):
            normalized[_clean(role)] = [_clean(item) for item in modules if _clean(item)]
    return {role: modules for role, modules in normalized.items() if role}


def is_license_required() -> bool:
    edition = _clean(os.environ.get("BOULANGERIE_APP_EDITION")).lower()
    if edition == "white-label":
        return True
    license_config = load_client_config().get("license") or {}
    return bool(license_config.get("required"))


def client_summary() -> dict[str, Any]:
    return {
        "clientId": get_client_id(),
        "companyName": get_company_name(),
        "appName": get_app_name(),
        "publisher": get_publisher(),
        "publicUrl": get_public_url(),
        "emailDomain": get_email_domain(),
        "contactEmail": get_contact_email(),
        "contactPhone": get_contact_phone(),
        "responsibleName": get_responsible_name(),
        "initiatorName": get_initiator_name(),
        "legalNotice": get_legal_notice(),
        "allowedDomains": get_allowed_domains(),
        "licenseRequired": is_license_required(),
        "trayPrices": get_tray_prices(),
        "roles": get_roles_config(),
        "licensePublicKey": get_license_public_key(),
        "licenseServerUrl": get_license_server_url(),
        "appDataDirName": get_app_data_dir_name(),
    }
