from __future__ import annotations

import json
import sys
import urllib.error
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
from boulangerie_app.email_service import load_email_settings


def call(endpoint: str) -> dict:
    settings = load_email_settings()
    request = urllib.request.Request(
        f"https://api.cloudflare.com/client/v4/accounts/{settings.account_id}/email/sending{endpoint}",
        headers={
            "Authorization": f"Bearer {settings.api_token}",
            "Accept": "application/json",
            "User-Agent": "Boulangerie-Lomoto-Email-Diagnostic/1.0",
        },
    )
    try:
        with urllib.request.urlopen(request, timeout=25) as response:
            payload = json.loads(response.read().decode("utf-8-sig") or "{}")
    except urllib.error.HTTPError as exc:
        try:
            payload = json.loads(exc.read().decode("utf-8-sig") or "{}")
        except Exception:
            payload = {"success": False, "errors": [{"message": str(exc)}]}
    except Exception as exc:
        payload = {"success": False, "errors": [{"message": str(exc)}]}
    return {
        "success": bool(payload.get("success")),
        "result": payload.get("result"),
        "errors": payload.get("errors", []),
    }


def main() -> None:
    settings = load_email_settings()
    print(
        json.dumps(
            {
                "configured": settings.configured,
                "provider": settings.normalized_provider,
                "from_address": settings.from_address,
                "reply_to": settings.reply_to,
                "account_id": settings.account_id,
                "limits": call("/limits"),
                "suppressions": call("/suppression?page=1&per_page=10&order=created_at&direction=desc"),
            },
            ensure_ascii=False,
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
