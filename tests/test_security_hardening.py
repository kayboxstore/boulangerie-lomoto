"""Régressions de sécurité pour l'authentification et le mode connecté."""

from __future__ import annotations

from email.message import Message
import sqlite3

import pytest

from boulangerie_app.connected_mode import (
    ConnectionSettings,
    RemoteDatabaseClient,
    RemoteDatabaseError,
    is_secure_remote_url,
)
from boulangerie_app.connected_server import (
    _is_loopback_address,
    _is_method_allowed_for_session,
)
from boulangerie_app.database import DatabaseHelper
from boulangerie_web_pro.server import WebProHandler, _has_native_rpc_auth


ADMIN_PASSWORD = "Adm9$SecureRoot!2026"
TEMP_PASSWORD = "Tmp9$SecureUser!2026"
NEW_PASSWORD = "New9$SecureUser!2027"


def _create_admin(db) -> None:
    db.create_initial_admin(
        full_name="Alice Directrice",
        identifiant="a.dir",
        email="alice@example.com",
        password=ADMIN_PASSWORD,
    )


def _notification_bodies(db) -> str:
    with db.connect() as connection:
        rows = connection.execute(
            "SELECT CorpsTexte, CorpsHtml FROM NotificationsEmail ORDER BY Id"
        ).fetchall()
    return "\n".join(f"{row['CorpsTexte']}\n{row['CorpsHtml']}" for row in rows)


def test_passwords_are_never_queued_in_email_and_temporary_password_is_forced(db):
    _create_admin(db)
    db.add_user(
        full_name="Claire Caisse",
        identifiant="c.caisse",
        password=TEMP_PASSWORD,
        role="Caissier",
        email="claire@example.com",
    )

    assert db.is_using_default_password("a.dir") is False
    assert db.is_using_default_password("c.caisse") is True
    assert TEMP_PASSWORD not in _notification_bodies(db)

    db.change_user_password("c.caisse", TEMP_PASSWORD, NEW_PASSWORD)

    assert db.is_using_default_password("c.caisse") is False
    bodies = _notification_bodies(db)
    assert TEMP_PASSWORD not in bodies
    assert NEW_PASSWORD not in bodies


def test_admin_password_reset_forces_rotation_without_exposing_password(db):
    _create_admin(db)
    db.add_user("Claire Caisse", "c.caisse", TEMP_PASSWORD, "Caissier", "claire@example.com")

    reset_password = "Rst9$SecureUser!2028"
    assert db.update_user("c.caisse", "Claire Caisse", reset_password, "Caissier") == 1

    assert db.is_using_default_password("c.caisse") is True
    assert reset_password not in _notification_bodies(db)


def test_schema_migration_forces_existing_accounts_to_rotate_password(tmp_path):
    DatabaseHelper.set_storage_root(tmp_path)
    DatabaseHelper.legacy_db_path = tmp_path / "legacy-inexistante.db"
    DatabaseHelper.apply_connection_settings(ConnectionSettings(mode="local"), persist=False)

    connection = sqlite3.connect(DatabaseHelper.db_path)
    connection.execute(
        """
        CREATE TABLE Utilisateurs (
            Id INTEGER PRIMARY KEY AUTOINCREMENT,
            NomComplet TEXT NOT NULL,
            Identifiant TEXT NOT NULL UNIQUE,
            Email TEXT NOT NULL DEFAULT '',
            MotDePasse TEXT NOT NULL,
            MotDePasseLisible TEXT NOT NULL DEFAULT '',
            Role TEXT NOT NULL,
            EchecsConnexion INTEGER NOT NULL DEFAULT 0,
            NiveauBlocage INTEGER NOT NULL DEFAULT 0,
            VerrouilleJusqua TEXT NOT NULL DEFAULT ''
        )
        """
    )
    connection.execute(
        """
        INSERT INTO Utilisateurs
            (NomComplet, Identifiant, Email, MotDePasse, MotDePasseLisible, Role)
        VALUES (?, ?, ?, ?, '', ?)
        """,
        (
            "Utilisateur Historique",
            "legacy.user",
            "legacy@example.com",
            DatabaseHelper.hash_password(TEMP_PASSWORD),
            "Caissier",
        ),
    )
    connection.execute("PRAGMA user_version = 1")
    connection.commit()
    connection.close()

    DatabaseHelper.initialize_local_database()

    assert DatabaseHelper.is_using_default_password("legacy.user") is True


def test_legacy_password_notifications_are_scrubbed(db):
    with db.connect() as connection:
        connection.execute(
            """
            INSERT INTO NotificationsEmail
                (TypeNotification, Destinataire, Sujet, CorpsTexte, CorpsHtml, DateCreation)
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            (
                "Création utilisateur",
                "legacy@example.com",
                "Ancienne notification",
                "Mot de passe temporaire : Secret9!Ancien",
                "<td>Mot de passe temporaire</td><td>Secret9!Ancien</td>",
                "2026-01-01T00:00:00",
            ),
        )
        db._scrub_legacy_password_notifications(connection)

    assert "Secret9!Ancien" not in _notification_bodies(db)


def _session(role: str, identifiant: str = "utilisateur") -> dict[str, str]:
    return {"role": role, "identifiant": identifiant}


def test_connected_rpc_permissions_are_explicit_per_role():
    stock = _session("Gestionnaire de stock")
    assert _is_method_allowed_for_session("get_stock_summary", [], stock)
    assert _is_method_allowed_for_session("add_stock_supply", [], stock)
    assert not _is_method_allowed_for_session("get_total_cash", [], stock)
    assert not _is_method_allowed_for_session("list_orders", [], stock)

    production = _session("Chargé de la production")
    assert _is_method_allowed_for_session("get_production_for_date", [], production)
    assert _is_method_allowed_for_session("get_orders_summary_for_date", [], production)
    assert not _is_method_allowed_for_session("list_stock_supplies", [], production)

    orders = _session("Gestionnaire des commandes")
    assert _is_method_allowed_for_session("list_orders", [], orders)
    assert _is_method_allowed_for_session("list_commissions", [], orders)
    assert not _is_method_allowed_for_session("get_total_cash", [], orders)

    cashier = _session("Caissier")
    assert _is_method_allowed_for_session("get_total_cash", [], cashier)
    assert _is_method_allowed_for_session("list_workers", [], cashier)
    assert _is_method_allowed_for_session("is_using_default_password", ["utilisateur"], cashier)
    assert not _is_method_allowed_for_session("is_using_default_password", ["autre"], cashier)
    assert not _is_method_allowed_for_session("get_stock_configuration", [], cashier)


def test_director_general_can_change_only_own_password():
    director = _session("Directeur Général", "dg.lomoto")
    assert _is_method_allowed_for_session(
        "change_user_password",
        ["DG.LOMOTO", "ancien", "nouveau"],
        director,
    )
    assert not _is_method_allowed_for_session(
        "change_user_password",
        ["autre.compte", "ancien", "nouveau"],
        director,
    )


def test_unknown_role_cannot_use_read_or_report_methods():
    unknown = _session("Role inconnu")
    assert not _is_method_allowed_for_session("list_orders", [], unknown)
    assert not _is_method_allowed_for_session("get_monthly_report_obligation", [], unknown)


def _web_handler(peer_address: str, forwarded_address: str = "") -> WebProHandler:
    handler = object.__new__(WebProHandler)
    handler.client_address = (peer_address, 12345)
    handler.headers = Message()
    if forwarded_address:
        handler.headers["CF-Connecting-IP"] = forwarded_address
        handler.headers["CF-Ray"] = "test-ray"
    return handler


def test_initial_setup_is_limited_to_server_console():
    assert _web_handler("127.0.0.1")._is_server_console_client()
    assert not _web_handler("192.168.1.25")._is_server_console_client()
    assert not _web_handler("127.0.0.1", "203.0.113.25")._is_server_console_client()


def test_native_rpc_auth_requires_session_or_matching_api_token(monkeypatch):
    assert _has_native_rpc_auth({"session_token": "session-secrete"}, "")
    assert _has_native_rpc_auth({"token": "api-secrete"}, "api-secrete")
    assert not _has_native_rpc_auth({"token": "mauvaise"}, "api-secrete")
    assert not _has_native_rpc_auth({}, "api-secrete")
    monkeypatch.setenv("BOULANGERIE_REQUIRE_SESSION_AUTH", "0")
    assert not _has_native_rpc_auth({"session_token": "session-secrete"}, "")


def test_remote_transport_requires_https_except_for_loopback():
    assert is_secure_remote_url("https://app.boulangerie-lomoto.com")
    assert is_secure_remote_url("http://127.0.0.1:8765")
    assert is_secure_remote_url("http://localhost:8765")
    assert not is_secure_remote_url("http://192.168.1.10:8765")
    assert ConnectionSettings(mode="remote", server_url="app.boulangerie-lomoto.com").normalized_url() == (
        "https://app.boulangerie-lomoto.com"
    )

    RemoteDatabaseClient("https://app.boulangerie-lomoto.com")
    RemoteDatabaseClient("http://127.0.0.1:8765")
    with pytest.raises(RemoteDatabaseError):
        RemoteDatabaseClient("http://192.168.1.10:8765")

    try:
        DatabaseHelper.apply_connection_settings(
            ConnectionSettings(mode="remote", server_url="http://192.168.1.10:8765"),
            persist=False,
        )
        assert DatabaseHelper.get_connection_settings().normalized_url() == (
            "https://app.boulangerie-lomoto.com"
        )
    finally:
        DatabaseHelper.apply_connection_settings(ConnectionSettings(mode="local"), persist=False)


def test_loopback_address_detection_rejects_lan_clients():
    assert _is_loopback_address("127.0.0.1")
    assert _is_loopback_address("::1")
    assert not _is_loopback_address("192.168.1.10")
