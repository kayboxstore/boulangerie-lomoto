from __future__ import annotations

import json
import os
import subprocess
import time
import tomllib
import urllib.error
import urllib.request
from pathlib import Path


ACCOUNT_ID = os.environ.get(
    "CLOUDFLARE_ACCOUNT_ID",
    "7634d7e84b56bbe34519f047ceeac79a",
).strip()
ZONE_ID = os.environ.get(
    "CLOUDFLARE_ZONE_ID",
    "01ee99acead62defccbbee9a93833528",
).strip()
DOMAIN = os.environ.get("BOULANGERIE_DOMAIN", "boulangerie-lomoto.com").strip()
TUNNEL_NAME = "boulangerie-lomoto-production"
ORIGIN_URL = "http://127.0.0.1:8787"
SYNC_ORIGIN_URL = os.environ.get("BOULANGERIE_SYNC_ORIGIN_URL", "http://127.0.0.1:8765").strip()
ENABLE_PUBLIC_SYNC = os.environ.get("BOULANGERIE_ENABLE_PUBLIC_SYNC", "").strip() == "1"
CLOUDFLARED_PATHS = (
    Path(r"C:\Program Files (x86)\cloudflared\cloudflared.exe"),
    Path(r"C:\Program Files\cloudflared\cloudflared.exe"),
)
WRANGLER_CONFIG = (
    Path.home()
    / "AppData"
    / "Roaming"
    / "xdg.config"
    / ".wrangler"
    / "config"
    / "default.toml"
)
OUTPUT_PATH = Path(__file__).resolve().parents[1] / "outputs" / "cloudflare-production.json"


def _api_token() -> str:
    environment_token = os.environ.get("CLOUDFLARE_API_TOKEN", "").strip()
    if environment_token:
        return environment_token
    payload = tomllib.loads(WRANGLER_CONFIG.read_text(encoding="utf-8"))
    token = str(payload.get("oauth_token", "")).strip()
    if not token:
        raise RuntimeError(
            "Aucun jeton Cloudflare n'est disponible. Définissez CLOUDFLARE_API_TOKEN "
            "avec les droits Cloudflare Tunnel Edit et Zone DNS Edit."
        )
    return token


def _oauth_token() -> str:
    return _api_token()


def _verify_api_token(token: str) -> None:
    request = urllib.request.Request(
        "https://api.cloudflare.com/client/v4/user/tokens/verify",
        headers={
            "Authorization": f"Bearer {token}",
            "Accept": "application/json",
            "User-Agent": "BoulangerieLomoto-ProductionSetup/1.0",
        },
        method="GET",
    )
    try:
        with urllib.request.urlopen(request, timeout=30) as response:
            payload = json.loads(response.read().decode("utf-8-sig") or "{}")
    except urllib.error.HTTPError as exc:
        raise RuntimeError(
            "Le jeton Cloudflare est invalide ou incomplet. Copiez-le de nouveau "
            "depuis Cloudflare sans espace ni retour à la ligne."
        ) from exc
    result = payload.get("result") if isinstance(payload, dict) else None
    if (
        not isinstance(payload, dict)
        or not payload.get("success", False)
        or not isinstance(result, dict)
        or str(result.get("status", "")).lower() != "active"
    ):
        raise RuntimeError("Le jeton Cloudflare n'est pas actif.")


def _request(
    token: str,
    method: str,
    path: str,
    payload: dict[str, object] | None = None,
) -> object:
    body = None if payload is None else json.dumps(payload).encode("utf-8")
    request = urllib.request.Request(
        f"https://api.cloudflare.com/client/v4{path}",
        data=body,
        headers={
            "Authorization": f"Bearer {token}",
            "Accept": "application/json",
            "Content-Type": "application/json",
            "User-Agent": "BoulangerieLomoto-ProductionSetup/1.0",
        },
        method=method,
    )
    try:
        with urllib.request.urlopen(request, timeout=45) as response:
            response_payload = json.loads(response.read().decode("utf-8-sig") or "{}")
    except urllib.error.HTTPError as exc:
        details = exc.read().decode("utf-8-sig", "replace")
        if exc.code == 403:
            raise RuntimeError(
                "Le jeton est valide, mais Cloudflare refuse cette opération. "
                "Vérifiez les permissions Compte > Cloudflare Tunnel > Modifier "
                "et Zone > DNS > Modifier, avec la zone boulangerie-lomoto.com incluse. "
                f"Détails : {details}"
            ) from exc
        raise RuntimeError(f"Cloudflare HTTP {exc.code}: {details}") from exc

    if not response_payload.get("success", False):
        raise RuntimeError(f"Cloudflare a refusé l'opération : {response_payload.get('errors', [])}")
    return response_payload.get("result")


def _find_cloudflared() -> Path:
    for path in CLOUDFLARED_PATHS:
        if path.exists():
            return path
    raise RuntimeError("cloudflared.exe est introuvable.")


def _zone(token: str) -> dict[str, object]:
    result = _request(token, "GET", f"/zones?name={DOMAIN}")
    zones = result if isinstance(result, list) else []
    if not zones:
        raise RuntimeError(f"Le domaine {DOMAIN} n'est pas présent dans ce compte Cloudflare.")
    zone = zones[0]
    if str(zone.get("status", "")) != "active":
        raise RuntimeError(f"Le domaine {DOMAIN} n'est pas encore actif dans Cloudflare.")
    return zone


def _tunnel(token: str) -> dict[str, object]:
    result = _request(
        token,
        "GET",
        f"/accounts/{ACCOUNT_ID}/cfd_tunnel?is_deleted=false&name={TUNNEL_NAME}",
    )
    tunnels = result if isinstance(result, list) else []
    if tunnels:
        return tunnels[0]
    created = _request(
        token,
        "POST",
        f"/accounts/{ACCOUNT_ID}/cfd_tunnel",
        {"name": TUNNEL_NAME, "config_src": "cloudflare"},
    )
    if not isinstance(created, dict):
        raise RuntimeError("Réponse invalide pendant la création du tunnel.")
    return created


def _configure_ingress(token: str, tunnel_id: str) -> None:
    ingress = [
        {"hostname": f"app.{DOMAIN}", "service": ORIGIN_URL},
        {"hostname": DOMAIN, "service": ORIGIN_URL},
        {"hostname": f"www.{DOMAIN}", "service": ORIGIN_URL},
    ]
    if ENABLE_PUBLIC_SYNC:
        ingress.append({"hostname": f"sync.{DOMAIN}", "service": SYNC_ORIGIN_URL})
    ingress.append({"service": "http_status:404"})
    _request(
        token,
        "PUT",
        f"/accounts/{ACCOUNT_ID}/cfd_tunnel/{tunnel_id}/configurations",
        {
            "config": {
                "ingress": ingress,
                "originRequest": {
                    "connectTimeout": 15,
                    "noHappyEyeballs": False,
                },
            }
        },
    )


def _upsert_dns(token: str, zone_id: str, name: str, tunnel_id: str) -> None:
    result = _request(token, "GET", f"/zones/{zone_id}/dns_records?name={name}")
    records = result if isinstance(result, list) else []
    payload = {
        "type": "CNAME",
        "name": name,
        "content": f"{tunnel_id}.cfargotunnel.com",
        "proxied": True,
        "ttl": 1,
        "comment": "Boulangerie Lomoto - tunnel de production",
    }
    if records:
        record_id = str(records[0].get("id", ""))
        _request(token, "PUT", f"/zones/{zone_id}/dns_records/{record_id}", payload)
    else:
        _request(token, "POST", f"/zones/{zone_id}/dns_records", payload)


def _install_service(token: str, tunnel_id: str) -> None:
    tunnel_token = _request(
        token,
        "GET",
        f"/accounts/{ACCOUNT_ID}/cfd_tunnel/{tunnel_id}/token",
    )
    if not isinstance(tunnel_token, str) or not tunnel_token.strip():
        raise RuntimeError("Impossible d'obtenir le jeton du tunnel.")

    # HTTP/2 + IPv4 is more reliable on networks/VPNs that block QUIC or IPv6 egress.
    subprocess.run(
        [
            "setx.exe",
            "/M",
            "TUNNEL_TRANSPORT_PROTOCOL",
            "http2",
        ],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        check=False,
    )
    subprocess.run(
        [
            "setx.exe",
            "/M",
            "TUNNEL_EDGE_IP_VERSION",
            "4",
        ],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        check=False,
    )

    cloudflared = _find_cloudflared()
    subprocess.run(
        ["sc.exe", "stop", "cloudflared"],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        check=False,
    )
    subprocess.run(
        [str(cloudflared), "service", "uninstall"],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        check=False,
    )
    install = subprocess.run(
        [str(cloudflared), "service", "install", tunnel_token],
        capture_output=True,
        text=True,
        check=False,
    )
    if install.returncode:
        raise RuntimeError(
            "L'installation du service cloudflared a échoué : "
            f"{install.stderr.strip() or install.stdout.strip()}"
        )
    subprocess.run(
        ["sc.exe", "config", "cloudflared", "start=", "auto"],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        check=True,
    )
    subprocess.run(
        ["sc.exe", "start", "cloudflared"],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        check=False,
    )


def _set_zone_setting(token: str, zone_id: str, setting_id: str, value: str) -> bool:
    try:
        _request(token, "PATCH", f"/zones/{zone_id}/settings/{setting_id}", {"value": value})
        return True
    except RuntimeError as exc:
        print(f"Réglage Cloudflare ignoré ({setting_id}) : {exc}")
        return False


def _configure_zone_security(token: str, zone_id: str) -> None:
    for setting_id, value in (
        ("ssl", "full"),
        ("always_use_https", "on"),
        ("automatic_https_rewrites", "on"),
        ("min_tls_version", "1.2"),
        ("tls_1_3", "on"),
        ("browser_check", "on"),
        ("security_level", "medium"),
    ):
        _set_zone_setting(token, zone_id, setting_id, value)


def main() -> None:
    token = _api_token()
    _verify_api_token(token)
    tunnel = _tunnel(token)
    zone_id = ZONE_ID
    if not zone_id:
        zone_id = str(_zone(token).get("id", ""))
    tunnel_id = str(tunnel.get("id", ""))
    if not zone_id or not tunnel_id:
        raise RuntimeError("Identifiants Cloudflare incomplets.")

    _configure_ingress(token, tunnel_id)
    for hostname in (DOMAIN, f"www.{DOMAIN}", f"app.{DOMAIN}"):
        _upsert_dns(token, zone_id, hostname, tunnel_id)
    if ENABLE_PUBLIC_SYNC:
        _upsert_dns(token, zone_id, f"sync.{DOMAIN}", tunnel_id)
    _configure_zone_security(token, zone_id)
    if os.environ.get("BOULANGERIE_SKIP_CLOUDFLARED_SERVICE", "").strip() != "1":
        _install_service(token, tunnel_id)

    OUTPUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT_PATH.write_text(
        json.dumps(
            {
                "domain": DOMAIN,
                "primary_url": f"https://app.{DOMAIN}",
                "root_url": f"https://{DOMAIN}",
                "tunnel_name": TUNNEL_NAME,
                "tunnel_id": tunnel_id,
                "configured_at": time.strftime("%Y-%m-%dT%H:%M:%S%z"),
            },
            indent=2,
        ),
        encoding="utf-8",
    )
    print(f"Tunnel configuré : https://app.{DOMAIN}")


if __name__ == "__main__":
    main()
