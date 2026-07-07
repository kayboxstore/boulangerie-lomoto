from __future__ import annotations

import json
import os
import smtplib
import ssl
from dataclasses import asdict, dataclass
from email.message import EmailMessage
from pathlib import Path
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

from .client_config import get_app_data_dir_name, get_app_name


EMAIL_SETTINGS_FILENAME = "email-settings.json"


def email_settings_path() -> Path:
    program_data = os.environ.get("PROGRAMDATA", r"C:\ProgramData").strip() or r"C:\ProgramData"
    return Path(program_data) / get_app_data_dir_name() / EMAIL_SETTINGS_FILENAME


@dataclass
class EmailSettings:
    provider: str = "cloudflare"
    account_id: str = ""
    api_token: str = ""
    gateway_url: str = ""
    gateway_token: str = ""
    smtp_host: str = ""
    smtp_port: int = 587
    smtp_username: str = ""
    smtp_password: str = ""
    smtp_use_tls: bool = True
    smtp_use_ssl: bool = False
    from_address: str = ""
    from_name: str = get_app_name()
    reply_to: str = ""

    @property
    def normalized_provider(self) -> str:
        return self.provider.strip().lower() or "cloudflare"

    @property
    def configured(self) -> bool:
        provider = self.normalized_provider
        if provider == "cloudflare":
            return bool(self.account_id.strip() and self.api_token.strip() and self.from_address.strip())
        if provider == "gateway":
            return bool(self.gateway_url.strip() and self.gateway_token.strip())
        if provider == "smtp":
            return bool(self.smtp_host.strip() and self.from_address.strip())
        return False

    def public_status(self) -> dict[str, Any]:
        return {
            "provider": self.normalized_provider,
            "configured": self.configured,
            "from_address": self.from_address.strip(),
            "reply_to": self.reply_to.strip(),
            "smtp_host": self.smtp_host.strip(),
            "smtp_port": int(self.smtp_port or 587),
            "smtp_username": self.smtp_username.strip(),
            "gateway_url": self.gateway_url.strip(),
            "account_id": self.account_id.strip(),
            "settings_path": str(email_settings_path()),
        }


@dataclass
class EmailDeliveryResult:
    sent: bool
    status: str
    message: str = ""


def _bool_value(value: Any, default: bool = False) -> bool:
    if isinstance(value, bool):
        return value
    if value is None:
        return default
    return str(value).strip().lower() in {"1", "true", "yes", "oui", "on"}


def load_email_settings() -> EmailSettings:
    payload: dict[str, Any] = {}
    path = email_settings_path()
    if path.exists():
        try:
            parsed = json.loads(path.read_text(encoding="utf-8-sig"))
            if isinstance(parsed, dict):
                payload = parsed
        except (OSError, ValueError):
            payload = {}

    return EmailSettings(
        provider=os.environ.get("BOULANGERIE_EMAIL_PROVIDER", str(payload.get("provider", "cloudflare"))),
        account_id=os.environ.get("BOULANGERIE_EMAIL_ACCOUNT_ID", str(payload.get("account_id", ""))),
        api_token=os.environ.get("BOULANGERIE_EMAIL_API_TOKEN", str(payload.get("api_token", ""))),
        gateway_url=os.environ.get("BOULANGERIE_EMAIL_GATEWAY_URL", str(payload.get("gateway_url", ""))),
        gateway_token=os.environ.get(
            "BOULANGERIE_EMAIL_GATEWAY_TOKEN",
            str(payload.get("gateway_token", "")),
        ),
        smtp_host=os.environ.get("BOULANGERIE_SMTP_HOST", str(payload.get("smtp_host", ""))),
        smtp_port=int(os.environ.get("BOULANGERIE_SMTP_PORT", payload.get("smtp_port", 587)) or 587),
        smtp_username=os.environ.get(
            "BOULANGERIE_SMTP_USERNAME",
            str(payload.get("smtp_username", "")),
        ),
        smtp_password=os.environ.get(
            "BOULANGERIE_SMTP_PASSWORD",
            str(payload.get("smtp_password", "")),
        ),
        smtp_use_tls=_bool_value(
            os.environ.get("BOULANGERIE_SMTP_USE_TLS", payload.get("smtp_use_tls", True)),
            True,
        ),
        smtp_use_ssl=_bool_value(
            os.environ.get("BOULANGERIE_SMTP_USE_SSL", payload.get("smtp_use_ssl", False)),
            False,
        ),
        from_address=os.environ.get(
            "BOULANGERIE_EMAIL_FROM_ADDRESS",
            str(payload.get("from_address", "")),
        ),
        from_name=os.environ.get(
            "BOULANGERIE_EMAIL_FROM_NAME",
            str(payload.get("from_name", get_app_name())),
        ),
        reply_to=os.environ.get("BOULANGERIE_EMAIL_REPLY_TO", str(payload.get("reply_to", ""))),
    )


def save_email_settings(values: dict[str, Any]) -> dict[str, Any]:
    current = load_email_settings()
    merged = asdict(current)
    secret_fields = {"api_token", "gateway_token", "smtp_password"}
    for key in merged:
        if key not in values:
            continue
        value = values[key]
        if key in secret_fields and not str(value or "").strip():
            continue
        merged[key] = value

    settings = EmailSettings(
        provider=str(merged.get("provider", "cloudflare")),
        account_id=str(merged.get("account_id", "")),
        api_token=str(merged.get("api_token", "")),
        gateway_url=str(merged.get("gateway_url", "")),
        gateway_token=str(merged.get("gateway_token", "")),
        smtp_host=str(merged.get("smtp_host", "")),
        smtp_port=max(int(merged.get("smtp_port", 587) or 587), 1),
        smtp_username=str(merged.get("smtp_username", "")),
        smtp_password=str(merged.get("smtp_password", "")),
        smtp_use_tls=_bool_value(merged.get("smtp_use_tls"), True),
        smtp_use_ssl=_bool_value(merged.get("smtp_use_ssl"), False),
        from_address=str(merged.get("from_address", "")),
        from_name=str(merged.get("from_name", get_app_name())),
        reply_to=str(merged.get("reply_to", "")),
    )
    path = email_settings_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(".tmp")
    temporary.write_text(
        json.dumps(asdict(settings), ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    os.replace(temporary, path)
    if os.name == "nt":
        os.system(
            f'icacls "{path}" /inheritance:r /grant:r "SYSTEM:(F)" "Administrators:(F)" >nul 2>&1'
        )
    return settings.public_status()


def _cloudflare_send(
    settings: EmailSettings,
    recipient: str,
    subject: str,
    text_body: str,
    html_body: str,
) -> EmailDeliveryResult:
    endpoint = (
        "https://api.cloudflare.com/client/v4/accounts/"
        f"{settings.account_id.strip()}/email/sending/send"
    )
    payload: dict[str, Any] = {
        "to": recipient.strip(),
        "from": {
            "address": settings.from_address.strip(),
            "name": settings.from_name.strip() or get_app_name(),
        },
        "subject": subject.strip(),
        "text": text_body,
        "html": html_body,
    }
    if settings.reply_to.strip():
        payload["reply_to"] = settings.reply_to.strip()
    request = Request(
        endpoint,
        data=json.dumps(payload, ensure_ascii=False).encode("utf-8"),
        headers={
            "Authorization": f"Bearer {settings.api_token.strip()}",
            "Content-Type": "application/json",
            "Accept": "application/json",
            "User-Agent": f"{get_app_name()}-EmailService/1.0",
        },
        method="POST",
    )
    try:
        with urlopen(request, timeout=25) as response:
            response_payload = json.loads(response.read().decode("utf-8-sig") or "{}")
    except HTTPError as exc:
        try:
            error_payload = json.loads(exc.read().decode("utf-8-sig") or "{}")
            errors = error_payload.get("errors", [])
            message = str(errors[0].get("message", exc.reason)) if errors else str(exc.reason)
        except Exception:
            message = str(exc.reason)
        return EmailDeliveryResult(False, "failed", message)
    except (URLError, OSError, ValueError) as exc:
        return EmailDeliveryResult(False, "failed", str(exc))

    if not bool(response_payload.get("success", False)):
        errors = response_payload.get("errors", [])
        message = str(errors[0].get("message", "Échec de l'envoi.")) if errors else "Échec de l'envoi."
        return EmailDeliveryResult(False, "failed", message)
    result = response_payload.get("result", {})
    delivered = result.get("delivered", []) if isinstance(result, dict) else []
    queued = result.get("queued", []) if isinstance(result, dict) else []
    if recipient in delivered:
        return EmailDeliveryResult(True, "sent", "E-mail remis au destinataire.")
    if recipient in queued:
        return EmailDeliveryResult(True, "queued", "E-mail accepté et placé dans la file d'envoi.")
    return EmailDeliveryResult(True, "sent", "E-mail accepté par le service d'envoi.")


def _gateway_send(
    settings: EmailSettings,
    recipient: str,
    subject: str,
    text_body: str,
    html_body: str,
) -> EmailDeliveryResult:
    request = Request(
        settings.gateway_url.strip(),
        data=json.dumps(
            {
                "to": recipient.strip(),
                "subject": subject.strip(),
                "text": text_body,
                "html": html_body,
            },
            ensure_ascii=False,
        ).encode("utf-8"),
        headers={
            "Authorization": f"Bearer {settings.gateway_token.strip()}",
            "Content-Type": "application/json",
            "Accept": "application/json",
        },
        method="POST",
    )
    try:
        with urlopen(request, timeout=25) as response:
            payload = json.loads(response.read().decode("utf-8-sig") or "{}")
    except HTTPError as exc:
        return EmailDeliveryResult(False, "failed", exc.read().decode("utf-8-sig", "replace"))
    except (URLError, OSError, ValueError) as exc:
        return EmailDeliveryResult(False, "failed", str(exc))
    if not payload.get("ok", False):
        return EmailDeliveryResult(False, "failed", str(payload.get("error", "Échec de l'envoi.")))
    return EmailDeliveryResult(True, "sent", str(payload.get("message", "E-mail envoyé.")))


def _smtp_send(
    settings: EmailSettings,
    recipient: str,
    subject: str,
    text_body: str,
    html_body: str,
) -> EmailDeliveryResult:
    message = EmailMessage()
    message["To"] = recipient.strip()
    message["From"] = (
        f"{settings.from_name.strip()} <{settings.from_address.strip()}>"
        if settings.from_name.strip()
        else settings.from_address.strip()
    )
    if settings.reply_to.strip():
        message["Reply-To"] = settings.reply_to.strip()
    message["Subject"] = subject.strip()
    message.set_content(text_body)
    message.add_alternative(html_body, subtype="html")
    context = ssl.create_default_context()
    try:
        if settings.smtp_use_ssl:
            smtp: smtplib.SMTP = smtplib.SMTP_SSL(
                settings.smtp_host.strip(),
                settings.smtp_port,
                timeout=25,
                context=context,
            )
        else:
            smtp = smtplib.SMTP(settings.smtp_host.strip(), settings.smtp_port, timeout=25)
        with smtp:
            smtp.ehlo()
            if settings.smtp_use_tls and not settings.smtp_use_ssl:
                smtp.starttls(context=context)
                smtp.ehlo()
            if settings.smtp_username.strip():
                smtp.login(settings.smtp_username.strip(), settings.smtp_password)
            smtp.send_message(message)
    except (OSError, smtplib.SMTPException) as exc:
        return EmailDeliveryResult(False, "failed", str(exc))
    return EmailDeliveryResult(True, "sent", "E-mail remis au serveur SMTP.")


def send_transactional_email(
    recipient: str,
    subject: str,
    text_body: str,
    html_body: str,
) -> EmailDeliveryResult:
    settings = load_email_settings()
    if not settings.configured:
        return EmailDeliveryResult(
            sent=False,
            status="configuration_required",
            message="Le service d'envoi d'e-mails n'est pas encore configuré.",
        )
    provider = settings.normalized_provider
    if provider == "cloudflare":
        return _cloudflare_send(settings, recipient, subject, text_body, html_body)
    if provider == "gateway":
        return _gateway_send(settings, recipient, subject, text_body, html_body)
    if provider == "smtp":
        return _smtp_send(settings, recipient, subject, text_body, html_body)
    return EmailDeliveryResult(False, "configuration_required", "Fournisseur d'e-mail inconnu.")
