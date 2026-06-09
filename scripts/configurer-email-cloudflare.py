from __future__ import annotations

import getpass
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from boulangerie_app.connected_mode import ConnectionSettings
from boulangerie_app.database import DatabaseHelper
from boulangerie_app.email_service import (
    email_settings_path,
    load_email_settings,
    save_email_settings,
    send_transactional_email,
)
from boulangerie_app.server_host import load_central_server_settings


DEFAULT_ACCOUNT_ID = "7634d7e84b56bbe34519f047ceeac79a"
DEFAULT_FROM_ADDRESS = "notifications@boulangerie-lomoto.com"
DEFAULT_FROM_NAME = "Boulangerie Lomoto"
DEFAULT_REPLY_TO = "contact@boulangerie-lomoto.com"


def ask(label: str, default: str = "") -> str:
    suffix = f" [{default}]" if default else ""
    value = input(f"{label}{suffix} : ").strip()
    return value or default


def yes_no(label: str, default: bool = False) -> bool:
    suffix = "O/n" if default else "o/N"
    value = input(f"{label} [{suffix}] : ").strip().lower()
    if not value:
        return default
    return value in {"o", "oui", "y", "yes"}


def configure_storage_root() -> None:
    host_settings = load_central_server_settings()
    DatabaseHelper.set_storage_root(Path(host_settings.normalized_data_dir()))
    DatabaseHelper.apply_connection_settings(ConnectionSettings(), persist=False)
    DatabaseHelper.initialize_database()


def main() -> int:
    current = load_email_settings()
    print("Configuration Cloudflare Email Sending - Boulangerie Lomoto")
    print("Le jeton est saisi masque et stocke dans ProgramData avec ACL Windows.")
    print()

    account_id = ask("Compte Cloudflare", current.account_id or DEFAULT_ACCOUNT_ID)
    from_address = ask("Adresse d'envoi", current.from_address or DEFAULT_FROM_ADDRESS)
    from_name = ask("Nom d'envoi", current.from_name or DEFAULT_FROM_NAME)
    reply_to = ask("Repondre a", current.reply_to or DEFAULT_REPLY_TO)
    token_prompt = "Jeton Cloudflare Email Sending"
    if current.api_token.strip():
        token_prompt += " (laisser vide pour conserver l'actuel)"
    api_token = getpass.getpass(f"{token_prompt} : ").strip()

    status = save_email_settings(
        {
            "provider": "cloudflare",
            "account_id": account_id,
            "api_token": api_token,
            "from_address": from_address,
            "from_name": from_name,
            "reply_to": reply_to,
            "gateway_url": "",
            "gateway_token": "",
            "smtp_host": "",
            "smtp_port": 587,
            "smtp_username": "",
            "smtp_password": "",
            "smtp_use_tls": True,
            "smtp_use_ssl": False,
        }
    )
    print()
    print(f"Configuration enregistree : {email_settings_path()}")
    print(f"Service configure : {'oui' if status.get('configured') else 'non'}")

    if not status.get("configured"):
        print("Le compte, le jeton et l'adresse d'envoi sont obligatoires.")
        return 1

    test_recipient = ask("Adresse e-mail de test (laisser vide pour ignorer)", "")
    if test_recipient:
        result = send_transactional_email(
            test_recipient,
            "Test notifications - Boulangerie Lomoto",
            "Ceci est un test d'envoi depuis Boulangerie Lomoto.",
            "<p>Ceci est un test d'envoi depuis <strong>Boulangerie Lomoto</strong>.</p>",
        )
        print(f"Test : {result.status} - {result.message}")
        if not result.sent:
            return 2

    if yes_no("Relancer maintenant les notifications en attente", False):
        configure_storage_root()
        result = DatabaseHelper.retry_email_notifications(100)
        print(
            "Relance terminee : "
            f"{result.get('sent', 0)} envoye(s), "
            f"{result.get('failed', 0)} echec(s), "
            f"{result.get('pending', 0)} restant(s)."
        )

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
