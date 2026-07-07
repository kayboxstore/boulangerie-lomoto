"""Tests du versionnage de schéma et de la sauvegarde avant migration."""

from __future__ import annotations

import sqlite3
from pathlib import Path

import pytest

from boulangerie_app.connected_mode import ConnectionSettings
from boulangerie_app.database import SCHEMA_VERSION, DatabaseHelper


def _user_version(db) -> int:
    connection = sqlite3.connect(db.db_path)
    try:
        return int(connection.execute("PRAGMA user_version").fetchone()[0] or 0)
    finally:
        connection.close()


def test_fresh_database_is_stamped_with_current_version(db):
    # La fixture a déjà initialisé la base : elle doit porter la version courante.
    assert _user_version(db) == SCHEMA_VERSION


def test_existing_old_database_triggers_one_safety_backup(tmp_path: Path):
    # Prépare une base « ancienne » (user_version = 0) hors du flux de migration.
    DatabaseHelper.set_storage_root(tmp_path)
    DatabaseHelper.legacy_db_path = tmp_path / "legacy-inexistante.db"
    DatabaseHelper.apply_connection_settings(ConnectionSettings(mode="local"), persist=False)

    raw = sqlite3.connect(DatabaseHelper.db_path)
    raw.execute("CREATE TABLE Vieux (Id INTEGER)")
    raw.execute("PRAGMA user_version = 0")
    raw.commit()
    raw.close()

    backups_before = list(DatabaseHelper.backups_dir.glob("avant-migration-*.db"))
    assert backups_before == []

    DatabaseHelper.initialize_local_database()

    # Une sauvegarde de sécurité a été créée et la version est désormais à jour.
    backups_after = list(DatabaseHelper.backups_dir.glob("avant-migration-v0-*.db"))
    assert len(backups_after) == 1
    assert _user_version(DatabaseHelper) == SCHEMA_VERSION

    # Un second démarrage ne recrée pas de sauvegarde (schéma déjà à jour).
    DatabaseHelper.initialize_local_database()
    assert len(list(DatabaseHelper.backups_dir.glob("avant-migration-v0-*.db"))) == 1
