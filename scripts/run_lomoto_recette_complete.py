from __future__ import annotations

import argparse
import http.cookiejar
import json
import os
import socket
import sqlite3
import subprocess
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Any, Callable


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
VERSION = "1.5.6"
DIRECTOR_ROLE = "Directeur G\u00e9n\u00e9ral"
PRODUCTION_ROLE = "Charg\u00e9 de la production"
DEPOSITARY_STATUS = "D\u00e9positaire"
PUBLIC_URL = "https://boulangerie-lomoto.com"


class ApiError(RuntimeError):
    def __init__(self, status: int, payload: dict[str, Any], body: str = "") -> None:
        self.status = status
        self.payload = payload
        self.body = body
        message = str(payload.get("error") or payload.get("message") or body or f"HTTP {status}")
        super().__init__(message)


@dataclass
class StepResult:
    name: str
    status: str
    duration_ms: int
    details: str = ""


class ApiClient:
    def __init__(self, base_url: str) -> None:
        self.base_url = base_url.rstrip("/")
        self.cookie_jar = http.cookiejar.CookieJar()
        self.opener = urllib.request.build_opener(urllib.request.HTTPCookieProcessor(self.cookie_jar))
        self.csrf_token = ""
        self.user: dict[str, Any] = {}

    def request(
        self,
        method: str,
        path: str,
        payload: dict[str, Any] | None = None,
        headers: dict[str, str] | None = None,
        allow_error: bool = False,
    ) -> dict[str, Any]:
        url = self.base_url + path
        data = None
        request_headers = {
            "Accept": "application/json",
            "User-Agent": "LomotoRecette/1.5.6",
        }
        if payload is not None:
            data = json.dumps(payload, ensure_ascii=False).encode("utf-8")
            request_headers["Content-Type"] = "application/json"
        if self.csrf_token and method.upper() in {"POST", "PUT", "PATCH", "DELETE"}:
            request_headers["X-CSRF-Token"] = self.csrf_token
        if headers:
            request_headers.update(headers)
        request = urllib.request.Request(url, data=data, headers=request_headers, method=method.upper())
        try:
            with self.opener.open(request, timeout=30) as response:
                body = response.read().decode("utf-8-sig")
                parsed = json.loads(body or "{}")
                if not parsed.get("ok", False) and not allow_error:
                    raise ApiError(response.status, parsed, body)
                return parsed
        except urllib.error.HTTPError as exc:
            body = exc.read().decode("utf-8-sig", errors="replace")
            try:
                parsed = json.loads(body or "{}")
            except json.JSONDecodeError:
                parsed = {"ok": False, "error": body}
            if allow_error:
                parsed.setdefault("status", exc.code)
                return parsed
            raise ApiError(exc.code, parsed, body) from None

    def get(self, path: str, allow_error: bool = False) -> dict[str, Any]:
        return self.request("GET", path, allow_error=allow_error)

    def post(
        self,
        path: str,
        payload: dict[str, Any] | None = None,
        headers: dict[str, str] | None = None,
        allow_error: bool = False,
    ) -> dict[str, Any]:
        return self.request("POST", path, payload or {}, headers=headers, allow_error=allow_error)

    def delete(self, path: str, allow_error: bool = False) -> dict[str, Any]:
        return self.request("DELETE", path, allow_error=allow_error)

    def text(self, path: str) -> str:
        request = urllib.request.Request(
            self.base_url + path,
            headers={"User-Agent": "LomotoRecette/1.5.6", "Cache-Control": "no-cache"},
            method="GET",
        )
        with self.opener.open(request, timeout=30) as response:
            return response.read().decode("utf-8-sig", errors="replace")

    def login(self, identifiant: str, password: str, *, force: bool = False) -> dict[str, Any]:
        payload = self.post("/api/login", {"identifiant": identifiant, "password": password, "forceSession": force})
        self.user = payload["user"]
        self.csrf_token = str(self.user.get("csrfToken") or "")
        return payload

class RecetteRunner:
    def __init__(self, keep_server: bool = False) -> None:
        timestamp = datetime.now().strftime("%Y%m%d-%H%M%S")
        self.output_dir = ROOT / "output" / f"recette-lomoto-{VERSION}-{timestamp}"
        self.data_dir = self.output_dir / "data"
        self.report_path = self.output_dir / f"rapport-recette-lomoto-{VERSION}.md"
        self.json_path = self.output_dir / f"rapport-recette-lomoto-{VERSION}.json"
        self.server_log_path = self.output_dir / "serveur-temporaire.log"
        self.keep_server = keep_server
        self.results: list[StepResult] = []
        self.failures = 0
        self.server: subprocess.Popen[str] | None = None
        self.port = self._find_free_port()
        self.base_url = f"http://127.0.0.1:{self.port}"
        self.admin = ApiClient(self.base_url)
        self.clients: dict[str, ApiClient] = {}
        self.today = date.today()
        self.yesterday = self.today - timedelta(days=1)
        self.tomorrow = self.today + timedelta(days=1)

    @staticmethod
    def _find_free_port() -> int:
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
            sock.bind(("127.0.0.1", 0))
            return int(sock.getsockname()[1])

    def run(self) -> None:
        self.output_dir.mkdir(parents=True, exist_ok=True)
        self.data_dir.mkdir(parents=True, exist_ok=True)
        try:
            self.step("Compilation Python des modules principaux", self.check_compileall)
            self.step("Sante du service installe local", self.check_installed_local_health)
            self.step("Sante du domaine public Cloudflare", self.check_public_health)
            self.start_temp_server()
            self.step("Sante du serveur temporaire de recette", self.check_temp_health)
            self.step("Maintenance locale protegee par jeton", self.check_internal_maintenance)
            self.step("Configuration initiale obligatoire sur base vide", self.check_initial_setup_required)
            self.step("Creation de l'administrateur initial", self.create_initial_admin)
            self.step("Connexion administrateur", self.login_admin)
            self.step("Page de connexion sans identifiants pre-remplis", self.check_manual_login_form)
            self.step("Tableau de bord administrateur", self.check_dashboard)
            self.step("Creation des roles et unicite du Directeur General", self.create_roles_and_check_director_unique)
            self.step("Acces par role et modules visibles", self.check_role_access)
            self.step("Session unique et deconnexion forcee par Admin", self.check_single_session_and_admin_disconnect)
            self.step("Previsions futures et droits du profil production", self.check_prevision_flow)
            self.step("Production journaliere", self.create_production)
            self.step("Stock : approvisionnement, sortie et parametres", self.create_stock_entries)
            self.step("Commandes : mamans, depositaires, dette et avance", self.create_orders_and_advances)
            self.step("Filtres commandes Maman / Depositaire", self.check_order_filters)
            self.step("Caisse journaliere", self.create_cash_day)
            self.step("Travailleurs, anciennete et paie", self.create_worker_and_payroll)
            self.step("Notifications e-mail mises en file d'attente", self.check_email_queue)
            self.step("Blocage des dates futures sur les modules", self.check_future_dates_blocked)
            self.step("Rapports PDF et Excel", self.generate_reports)
            self.step("Historique limite a 50 lignes cote API", self.check_history)
            self.step("Cloture DG, refus d'ecriture, reouverture Admin", self.check_closure_flow)
            self.step("Sauvegarde de la base temporaire", self.check_backup)
            self.step("Effacement et archivage de l'historique", self.check_history_clear)
        finally:
            self.stop_temp_server()
            self.write_reports()

    def step(self, name: str, func: Callable[[], str | None]) -> None:
        start = time.perf_counter()
        try:
            details = func() or ""
            status = "OK"
        except Exception as exc:  # noqa: BLE001 - recette report needs full failure list
            self.failures += 1
            status = "ECHEC"
            details = f"{type(exc).__name__}: {exc}"
        duration_ms = int((time.perf_counter() - start) * 1000)
        self.results.append(StepResult(name, status, duration_ms, details))
        print(f"[{status}] {name} ({duration_ms} ms) {details}")

    def expect_api_error(
        self,
        client: ApiClient,
        method: str,
        path: str,
        payload: dict[str, Any] | None = None,
        *,
        expected_status: int | None = None,
        contains: str = "",
    ) -> dict[str, Any]:
        try:
            if method == "POST":
                client.post(path, payload or {})
            elif method == "DELETE":
                client.delete(path)
            else:
                client.get(path)
        except ApiError as exc:
            if expected_status is not None and exc.status != expected_status:
                raise AssertionError(f"Statut attendu {expected_status}, recu {exc.status}: {exc}") from exc
            if contains and contains.lower() not in str(exc).lower():
                raise AssertionError(f"Message attendu contenant {contains!r}, recu: {exc}") from exc
            return exc.payload
        raise AssertionError(f"La requete {method} {path} aurait du etre refusee.")

    def start_temp_server(self) -> None:
        # Empêche la migration automatique de l'ancien boulangerie.db racine vers
        # la base de recette : on veut une installation réellement vide.
        sqlite3.connect(self.data_dir / "boulangerie.db").close()
        command = [
            sys.executable,
            "-m",
            "boulangerie_web_pro.server",
            "--host",
            "127.0.0.1",
            "--port",
            str(self.port),
            "--data-dir",
            str(self.data_dir),
        ]
        env = dict(os.environ)
        env["PYTHONUTF8"] = "1"
        log_handle = self.server_log_path.open("w", encoding="utf-8")
        self.server = subprocess.Popen(
            command,
            cwd=str(ROOT),
            stdout=log_handle,
            stderr=subprocess.STDOUT,
            text=True,
            env=env,
        )
        deadline = time.time() + 25
        while time.time() < deadline:
            if self.server.poll() is not None:
                raise RuntimeError(f"Le serveur temporaire s'est arrete. Voir {self.server_log_path}")
            try:
                payload = self.admin.get("/api/health")
                if payload.get("ok"):
                    return
            except Exception:
                time.sleep(0.3)
        raise RuntimeError("Le serveur temporaire n'a pas repondu dans le delai.")

    def stop_temp_server(self) -> None:
        if self.keep_server or self.server is None:
            return
        if self.server.poll() is None:
            self.server.terminate()
            try:
                self.server.wait(timeout=10)
            except subprocess.TimeoutExpired:
                self.server.kill()
                self.server.wait(timeout=10)

    def check_compileall(self) -> str:
        command = [
            sys.executable,
            "-m",
            "compileall",
            "-q",
            "boulangerie_app",
            "boulangerie_web_pro",
            "main.py",
            "serveur_windows_service.py",
        ]
        completed = subprocess.run(command, cwd=str(ROOT), capture_output=True, text=True, timeout=120)
        if completed.returncode != 0:
            raise AssertionError((completed.stdout + completed.stderr).strip())
        return "compileall OK"

    def check_installed_local_health(self) -> str:
        payload = fetch_json("http://127.0.0.1:8787/api/health")
        assert payload.get("ok") is True
        return f"{payload.get('app')} {payload.get('version')}"

    def check_public_health(self) -> str:
        payload = fetch_json(f"{PUBLIC_URL}/api/health", timeout=25)
        assert payload.get("ok") is True
        return f"{payload.get('app')} {payload.get('version')}"

    def check_temp_health(self) -> str:
        payload = self.admin.get("/api/health")
        assert payload.get("ok") is True
        return f"{self.base_url} | data={self.data_dir}"

    def check_internal_maintenance(self) -> str:
        # Jeton d'une instance de recette jetable ; surchargeable pour éviter
        # de figer une chaîne ressemblant à un secret dans le dépôt.
        token = os.environ.get(
            "LOMOTO_RECETTE_MAINTENANCE_TOKEN",
            "recette-maintenance-token-12345678901234567890",
        )
        token_path = self.data_dir / "maintenance-token.txt"
        token_path.write_text(token, encoding="utf-8")

        rejected = self.admin.request(
            "GET",
            "/api/internal/maintenance/status",
            headers={"X-Lomoto-Maintenance-Token": "mauvais-jeton"},
            allow_error=True,
        )
        assert rejected.get("ok") is False

        payload = self.admin.request(
            "GET",
            "/api/internal/maintenance/status",
            headers={"X-Lomoto-Maintenance-Token": token},
        )
        assert payload.get("ok") is True

        backup = self.admin.post(
            "/api/internal/maintenance/automatic-backup",
            {"force": True},
            headers={"X-Lomoto-Maintenance-Token": token},
        )
        backup_path = Path(str(backup.get("path", "")))
        assert backup.get("created") is True
        assert backup_path.exists() and backup_path.stat().st_size > 0
        return f"jeton OK, sauvegarde={backup_path.name}"

    def check_initial_setup_required(self) -> str:
        payload = self.admin.get("/api/setup/status")
        assert payload.get("required") is True
        return "setup requis sur base vide"

    def create_initial_admin(self) -> str:
        # Mot de passe de l'admin de recette (instance jetable) ; surchargeable.
        password = os.environ.get("LOMOTO_RECETTE_ADMIN_PASSWORD", "R7!mK2#pQ9xL4z")
        self.admin.post(
            "/api/setup",
            {
                "fullName": "Admin Recette Lomoto",
                "identifiant": "admin.recette",
                "email": "admin.recette@boulangerie-lomoto.com",
                "password": password,
            },
        )
        payload = self.admin.get("/api/setup/status")
        assert payload.get("required") is False
        self.clients["admin-password"] = password  # type: ignore[assignment]
        return "admin.recette cree"

    def login_admin(self) -> str:
        self.admin.login("admin.recette", str(self.clients["admin-password"]))  # type: ignore[index]
        assert self.admin.user.get("role") == "Admin"
        assert "dashboard" in self.admin.user.get("modules", [])
        return f"modules={len(self.admin.user.get('modules', []))}"

    def check_manual_login_form(self) -> str:
        html = self.admin.text("/")
        js = self.admin.text("/app.js?recette=1")
        assert "webpro-1.5.6-20260717" in html
        assert 'name="username"' in js
        assert 'autocomplete="username"' in js
        assert 'autocomplete="current-password"' in js
        assert 'value="" readonly required' in js
        assert "data-lpignore" not in js
        return "champs vides, gestionnaire de mots de passe autorise a la demande"

    def check_dashboard(self) -> str:
        payload = self.admin.get("/api/dashboard")
        data = payload.get("data") or {}
        assert "cards" in data
        assert "recentActivity" in data
        return f"{len(data.get('cards', []))} indicateurs"

    def create_roles_and_check_director_unique(self) -> str:
        users = [
            ("dg.recette", DIRECTOR_ROLE, "Directeur Recette Lomoto", "Q8!nV4#rT2xZ9p"),
            ("production.recette", PRODUCTION_ROLE, "Production Recette", "M5!pL8#sD3vY7q"),
            ("stock.recette", "Gestionnaire de stock", "Stock Recette", "W6!cH9#kR4tN2m"),
            ("commandes.recette", "Gestionnaire des commandes", "Commandes Recette", "J3!fS7#uP8bC5x"),
            ("caissier.recette", "Caissier", "Caissier Recette", "T2!zB6#qL9nD4v"),
        ]
        for identifiant, role, full_name, password in users:
            self.admin.post(
                "/api/users",
                {
                    "fullName": full_name,
                    "identifiant": identifiant,
                    "email": "" if identifiant == "stock.recette" else f"{identifiant}@boulangerie-lomoto.com",
                    "password": password,
                    "role": role,
                },
            )
            self.clients[f"{identifiant}:password"] = password  # type: ignore[assignment]
        self.expect_api_error(
            self.admin,
            "POST",
            "/api/users",
            {
                "fullName": "DG Doublon",
                "identifiant": "dg.doublon",
                "email": "dg.doublon@boulangerie-lomoto.com",
                "password": "H4!rP8#vN2xQ6s",
                "role": DIRECTOR_ROLE,
            },
            expected_status=400,
            contains="Un seul Directeur",
        )
        rows = self.admin.get("/api/users")["rows"]
        stock_user = next(row for row in rows if row["Identifiant"] == "stock.recette")
        assert stock_user["Email"] == "stock.recette@boulangerie-lomoto.com"
        return f"{len(rows)} utilisateurs, e-mail auto OK"

    def login_role(self, identifiant: str) -> ApiClient:
        client = ApiClient(self.base_url)
        password_key = f"{identifiant}:password"
        password = str(self.clients[password_key])  # type: ignore[index]
        client.login(identifiant, password)
        if client.user.get("mustChangePassword"):
            new_password = f"{password}N8!"
            client.post(
                "/api/password",
                {"currentPassword": password, "newPassword": new_password},
            )
            client.csrf_token = ""
            client.user = {}
            client.login(identifiant, new_password)
            self.clients[password_key] = new_password  # type: ignore[assignment]
        self.clients[identifiant] = client  # type: ignore[assignment]
        return client

    def check_role_access(self) -> str:
        dg = self.login_role("dg.recette")
        production = self.login_role("production.recette")
        stock = self.login_role("stock.recette")
        commandes = self.login_role("commandes.recette")
        caissier = self.login_role("caissier.recette")

        assert "orders" in dg.user.get("modules", [])
        assert "orders" in dg.user.get("readOnlyModules", [])
        self.expect_api_error(dg, "POST", "/api/orders", self.order_payload(self.today, "DG Test", "Maman", 1, 6000), expected_status=403)

        production.get(f"/api/production?date={self.today.isoformat()}")
        self.expect_api_error(production, "GET", f"/api/orders?date={self.today.isoformat()}", expected_status=403)

        stock.get(f"/api/stock?date={self.today.isoformat()}")
        self.expect_api_error(stock, "GET", f"/api/production?date={self.today.isoformat()}", expected_status=403)

        commandes.get(f"/api/orders?date={self.today.isoformat()}")
        self.expect_api_error(commandes, "POST", "/api/stock/supply", self.stock_supply_payload(self.today), expected_status=403)

        caissier.get(f"/api/cash?date={self.today.isoformat()}")
        caissier.get(f"/api/workers?start={self.today.replace(day=1).isoformat()}&end={self.today.isoformat()}")
        self.expect_api_error(caissier, "POST", "/api/orders", self.order_payload(self.today, "Caisse Test", "Maman", 1, 6000), expected_status=403)
        return "DG lecture seule, profils metier OK"

    def check_single_session_and_admin_disconnect(self) -> str:
        second_cash = ApiClient(self.base_url)
        try:
            second_cash.login("caissier.recette", str(self.clients["caissier.recette:password"]))  # type: ignore[index]
        except ApiError as exc:
            assert exc.status == 409
            assert exc.payload.get("sessionConflict") is True
        else:
            raise AssertionError("La double session du caissier a ete acceptee.")

        rows = self.admin.get("/api/users")["rows"]
        cashier_row = next(row for row in rows if row["Identifiant"] == "caissier.recette")
        assert cashier_row["SessionActive"] == 1
        self.admin.post("/api/users/disconnect", {"identifiant": "caissier.recette"})
        cashier = self.clients["caissier.recette"]  # type: ignore[assignment]
        assert isinstance(cashier, ApiClient)
        self.expect_api_error(cashier, "GET", "/api/dashboard", expected_status=403, contains="Session")
        cashier.login("caissier.recette", str(self.clients["caissier.recette:password"]))  # type: ignore[index]
        return "conflit 409 + deconnexion admin OK"

    @staticmethod
    def order_payload(target: date, client: str, status: str, trays: int, received: float) -> dict[str, Any]:
        return {
            "date": target.isoformat(),
            "client": client,
            "status": status,
            "trays": trays,
            "amountDue": 0,
            "amountReceived": received,
        }

    @staticmethod
    def stock_supply_payload(target: date) -> dict[str, Any]:
        return {
            "date": target.isoformat(),
            "flour": 40,
            "yeast": 3,
            "salt": 5,
            "oil": 12,
            "observations": "Recette automatique",
        }

    def create_production(self) -> str:
        production = self.clients["production.recette"]  # type: ignore[assignment]
        assert isinstance(production, ApiClient)
        production.post(
            "/api/production",
            {
                "date": self.today.isoformat(),
                "ordered": 20,
                "depositaries": 10,
                "mamas": 5,
                "given": 2,
                "samples": 1,
                "remaining": 2,
                "wasted": 0,
                "sacks": 2,
                "observations": "Production recette",
            },
        )
        summary = production.get(f"/api/production?date={self.today.isoformat()}")["summary"]
        assert int(summary.get("NombreBacsProduits") or 0) == 20
        return "20 bacs produits, 2 sacs"

    def check_prevision_flow(self) -> str:
        from boulangerie_app.connected_mode import ConnectionSettings
        from boulangerie_app.database import DatabaseHelper
        from boulangerie_app.excel_reports import create_prevision_excel_workbook

        DatabaseHelper.set_storage_root(self.data_dir)
        DatabaseHelper.apply_connection_settings(ConnectionSettings(mode="local"), persist=False)
        DatabaseHelper.initialize_local_database()
        DatabaseHelper.add_prevision_order(
            self.tomorrow, "Dépôt 1", "Client Prévision", DEPOSITARY_STATUS, 5, 0, 3, 0
        )
        DatabaseHelper.add_prevision_order(self.tomorrow, "", "Maman Prévision", "Maman", 0, 2, 0, 1)
        rows = DatabaseHelper.list_previsions_by_date(self.tomorrow)
        summary = DatabaseHelper.get_prevision_summary_for_date(self.tomorrow)
        workbook = create_prevision_excel_workbook(
            self.tomorrow,
            self.output_dir / "fiches-prevision-recette.xlsx",
            generated_by="Production Recette",
            generated_role=PRODUCTION_ROLE,
        )
        assert len(rows) == 2
        assert int(summary.get("TotalArticlesPrevus") or 0) == 11
        assert int(float(summary.get("MontantPrevu") or 0)) == 12000
        assert workbook.exists() and workbook.stat().st_size > 0
        return "2 lignes futures, 11 articles, 12 000 FC, export Excel OK"

    def create_stock_entries(self) -> str:
        stock = self.clients["stock.recette"]  # type: ignore[assignment]
        assert isinstance(stock, ApiClient)
        self.admin.post("/api/stock/config", {
            "flourInitial": 100,
            "yeastInitial": 10,
            "saltInitial": 10,
            "oilInitial": 25,
            "flourAlert": 10,
            "yeastAlert": 2,
            "saltAlert": 2,
            "oilAlert": 5,
        })
        stock.post("/api/stock/supply", self.stock_supply_payload(self.today))
        stock.post(
            "/api/stock/exit",
            {
                "date": self.today.isoformat(),
                "flour": 2,
                "yeast": 1,
                "salt": 1,
                "oil": 2,
            },
        )
        payload = stock.get(f"/api/stock?date={self.today.isoformat()}")
        assert len(payload.get("supplies", [])) == 1
        assert len(payload.get("exits", [])) == 1
        return "stock parametre, entree et sortie OK"

    def create_orders_and_advances(self) -> str:
        commandes = self.clients["commandes.recette"]  # type: ignore[assignment]
        assert isinstance(commandes, ApiClient)
        commandes.post("/api/orders", self.order_payload(self.yesterday, "Client Avance", DEPOSITARY_STATUS, 10, 50000))
        commandes.post("/api/orders", self.order_payload(self.today, "Client Avance", DEPOSITARY_STATUS, 10, 32000))
        commandes.post("/api/orders", self.order_payload(self.today, "Maman Recette", "Maman", 5, 30000))
        commandes.post("/api/orders", self.order_payload(self.today, "Client Dette", DEPOSITARY_STATUS, 10, 20000))
        rows = self.admin.get("/api/orders?all=1")["rows"]
        advance_source = next(row for row in rows if row["Client"] == "Client Avance" and row["DateCommande"] == self.yesterday.isoformat())
        advance_used = next(row for row in rows if row["Client"] == "Client Avance" and row["DateCommande"] == self.today.isoformat())
        assert int(float(advance_source.get("AvanceGeneree") or 0)) == 9000
        assert int(float(advance_used.get("AvanceUtilisee") or 0)) == 9000
        assert int(float(advance_used.get("Dette") or 0)) == 0
        assert int(float(advance_source.get("MontantRecuCommande") or 0)) == 41000
        return "avance 9 000 FC generee puis utilisee"

    def check_order_filters(self) -> str:
        maman = self.admin.get(f"/api/orders?date={self.today.isoformat()}&status={urllib.parse.quote('Maman')}")["rows"]
        depositary = self.admin.get(f"/api/orders?date={self.today.isoformat()}&status={urllib.parse.quote(DEPOSITARY_STATUS)}")["rows"]
        assert maman and all(row["Statut"] == "Maman" for row in maman)
        assert depositary and all(row["Statut"] == DEPOSITARY_STATUS for row in depositary)
        return f"Maman={len(maman)}, Depositaire={len(depositary)}"

    def create_cash_day(self) -> str:
        caissier = self.clients["caissier.recette"]  # type: ignore[assignment]
        assert isinstance(caissier, ApiClient)
        caissier.post(
            "/api/cash",
            {
                "date": self.today.isoformat(),
                "expenses": 3500,
                "expenseDetails": "Recette depenses",
                "paidDebts": 0,
                "paidDetails": "",
            },
        )
        summary = caissier.get(f"/api/cash?date={self.today.isoformat()}")["summary"]
        assert int(float(summary.get("Depenses") or summary.get("MontantTotalDepenses") or 0)) >= 3500
        return "fiche caisse OK"

    def create_worker_and_payroll(self) -> str:
        caissier = self.clients["caissier.recette"]  # type: ignore[assignment]
        assert isinstance(caissier, ApiClient)
        caissier.post(
            "/api/workers",
            {
                "fullName": "Travailleur Recette",
                "function": "Boulanger",
                "phone": "+243000000001",
                "email": "travailleur.recette@boulangerie-lomoto.com",
                "address": "Kinshasa",
                "hireDate": (self.today - timedelta(days=370)).isoformat(),
                "salary": 250000,
                "status": "Actif",
                "observations": "Recette anciennete",
            },
        )
        workers_payload = caissier.get(f"/api/workers?start={self.today.replace(day=1).isoformat()}&end={self.today.isoformat()}")
        worker = next(row for row in workers_payload["workers"] if row["NomComplet"] == "Travailleur Recette")
        assert int(worker.get("AncienneteAnnees") or 0) >= 1
        caissier.post(
            "/api/payrolls",
            {
                "workerId": worker["Id"],
                "payDate": self.today.isoformat(),
                "period": self.today.strftime("%m/%Y"),
                "gross": 100000,
                "bonus": 5000,
                "advance": 10000,
                "withholding": 2500,
                "paymentMode": "Especes",
                "status": "Payee",
                "observations": "Paie recette",
            },
        )
        payload = caissier.get(f"/api/workers?start={self.today.replace(day=1).isoformat()}&end={self.today.isoformat()}")
        payroll = next(row for row in payload["payrolls"] if int(row["TravailleurId"]) == int(worker["Id"]))
        assert int(float(payroll["MontantNet"])) == 92500
        return "anciennete >= 1 an, net 92 500 FC"

    def check_email_queue(self) -> str:
        status = self.admin.get("/api/email/status")["data"]
        pending = int(status.get("pending") or 0)
        assert pending >= 1
        return f"{pending} message(s) en attente sans configuration e-mail"

    def check_future_dates_blocked(self) -> str:
        future = self.tomorrow
        self.expect_api_error(self.admin, "POST", "/api/orders", self.order_payload(future, "Futur", "Maman", 1, 6000), expected_status=400, contains="date future")
        self.expect_api_error(self.admin, "POST", "/api/cash", {"date": future.isoformat(), "expenses": 1}, expected_status=400, contains="date future")
        self.expect_api_error(self.admin, "POST", "/api/stock/supply", self.stock_supply_payload(future), expected_status=400, contains="date future")
        self.expect_api_error(self.admin, "POST", "/api/production", {"date": future.isoformat(), "ordered": 1, "depositaries": 1, "mamas": 0, "given": 0, "samples": 0, "remaining": 0, "wasted": 0, "sacks": 0}, expected_status=400, contains="date future")
        self.expect_api_error(self.admin, "POST", "/api/workers", {"fullName": "Futur", "function": "Test", "phone": "", "email": "", "address": "", "hireDate": future.isoformat(), "salary": 1, "status": "Actif"}, expected_status=400, contains="date future")
        self.expect_api_error(self.admin, "POST", "/api/reports/generate", {"type": "daily", "format": "pdf", "date": future.isoformat(), "start": future.isoformat(), "end": future.isoformat()}, expected_status=400, contains="date future")
        self.expect_api_error(self.admin, "POST", "/api/closures/close", {"date": future.isoformat()}, expected_status=400, contains="future")
        return "commandes/caisse/stock/production/travailleurs/rapports/cloture"

    def generate_reports(self) -> str:
        anti_open_headers = {"CF-Connecting-IP": "203.0.113.10"}
        pdf = self.admin.post(
            "/api/reports/generate",
            {"type": "daily", "format": "pdf", "date": self.today.isoformat(), "start": self.today.isoformat(), "end": self.today.isoformat()},
            headers=anti_open_headers,
        )
        excel = self.admin.post(
            "/api/reports/generate",
            {"type": "period", "format": "excel", "date": self.today.isoformat(), "start": self.yesterday.isoformat(), "end": self.today.isoformat()},
            headers=anti_open_headers,
        )
        pdf_path = Path(str(pdf["path"]))
        excel_path = Path(str(excel["path"]))
        assert pdf_path.exists() and pdf_path.stat().st_size > 1000
        assert excel_path.exists() and excel_path.stat().st_size > 1000
        listed = self.admin.get("/api/reports/list")
        assert len(listed.get("files") or []) >= 2
        return f"PDF={pdf_path.name}, Excel={excel_path.name}"

    def check_history(self) -> str:
        rows = self.admin.get("/api/history?limit=50")["rows"]
        assert len(rows) <= 50
        assert any(row.get("Module") == "Commandes" for row in rows)
        return f"{len(rows)} ligne(s) retournees"

    def check_closure_flow(self) -> str:
        dg = self.clients["dg.recette"]  # type: ignore[assignment]
        commandes = self.clients["commandes.recette"]  # type: ignore[assignment]
        assert isinstance(dg, ApiClient)
        assert isinstance(commandes, ApiClient)
        closure = dg.post("/api/closures/close", {"date": self.today.isoformat()})["closure"]
        assert closure.get("DateJour") == self.today.isoformat()
        assert closure.get("CheminRapport")
        assert closure.get("CheminSauvegarde")
        self.expect_api_error(commandes, "POST", "/api/orders", self.order_payload(self.today, "Apres cloture", "Maman", 1, 6000), expected_status=400, contains="cl")
        self.expect_api_error(dg, "POST", "/api/closures/reopen", {"date": self.today.isoformat(), "reason": "Test"}, expected_status=403)
        reopened = self.admin.post("/api/closures/reopen", {"date": self.today.isoformat(), "reason": "Recette automatique"})["closure"]
        assert reopened.get("EstReouverte") is True
        commandes.post("/api/orders", self.order_payload(self.today, "Apres reouverture", "Maman", 1, 6000))
        return "DG cloture, Admin reouvre, ecriture reprise"

    def check_backup(self) -> str:
        payload = self.admin.post("/api/backups/create")
        backup_path = Path(str(payload["path"]))
        assert backup_path.exists() and backup_path.stat().st_size > 0
        listed = self.admin.get("/api/backups")["rows"]
        assert any(str(row.get("CheminComplet")) == str(backup_path) for row in listed)
        return backup_path.name

    def check_history_clear(self) -> str:
        payload = self.admin.post("/api/history/clear")
        assert int(payload.get("deleted") or 0) > 0
        archive_path = Path(str(payload.get("archivePath") or ""))
        assert archive_path.exists()
        rows = self.admin.get("/api/history?limit=50")["rows"]
        assert 1 <= len(rows) <= 50
        return f"{payload.get('deleted')} supprimees, archive={archive_path.name}"

    def write_reports(self) -> None:
        passed = sum(1 for item in self.results if item.status == "OK")
        failed = sum(1 for item in self.results if item.status != "OK")
        payload = {
            "version": VERSION,
            "date": datetime.now().isoformat(timespec="seconds"),
            "baseUrl": self.base_url,
            "dataDir": str(self.data_dir),
            "passed": passed,
            "failed": failed,
            "results": [item.__dict__ for item in self.results],
        }
        self.json_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
        lines = [
            f"# Rapport de recette complete - Boulangerie Lomoto {VERSION}",
            "",
            f"Date : {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}",
            f"Base temporaire : `{self.data_dir}`",
            f"Serveur temporaire : `{self.base_url}`",
            "",
            f"Resultat : **{passed} OK / {failed} echec(s)**",
            "",
            "| Statut | Scenario | Duree | Details |",
            "|---|---|---:|---|",
        ]
        for item in self.results:
            details = item.details.replace("|", "\\|").replace("\n", " ")
            lines.append(f"| {item.status} | {item.name} | {item.duration_ms} ms | {details} |")
        lines.extend(
            [
                "",
                "## Conclusion",
                "",
                "Recette validee automatiquement." if failed == 0 else "Recette avec ecarts a corriger avant livraison finale.",
                "",
                f"Journal serveur temporaire : `{self.server_log_path}`",
                f"Rapport JSON : `{self.json_path}`",
            ]
        )
        self.report_path.write_text("\n".join(lines) + "\n", encoding="utf-8")
        latest_path = ROOT / "docs" / f"validation-version-{VERSION}.md"
        latest_path.write_text("\n".join(lines) + "\n", encoding="utf-8")
        print(f"RAPPORT_MD={self.report_path}")
        print(f"RAPPORT_JSON={self.json_path}")
        print(f"RAPPORT_DOCS={latest_path}")


def fetch_json(url: str, timeout: int = 15) -> dict[str, Any]:
    request = urllib.request.Request(url, headers={"Accept": "application/json", "User-Agent": "LomotoRecette/1.5.6"})
    with urllib.request.urlopen(request, timeout=timeout) as response:
        return json.loads(response.read().decode("utf-8-sig"))


def main() -> int:
    parser = argparse.ArgumentParser(description="Recette complete automatisee de Boulangerie Lomoto.")
    parser.add_argument("--keep-server", action="store_true", help="Laisse le serveur temporaire ouvert apres la recette.")
    args = parser.parse_args()
    runner = RecetteRunner(keep_server=args.keep_server)
    runner.run()
    return 0 if runner.failures == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
