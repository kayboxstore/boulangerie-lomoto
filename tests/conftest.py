"""Configuration commune des tests.

Chaque test s'exécute sur une base SQLite neuve et isolée dans un dossier
temporaire, sans jamais toucher la base réelle de l'utilisateur ni le mode
connecté (serveur central). On force le stockage local via ``set_storage_root``.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

# Rendre le paquet importable quand pytest est lancé depuis la racine du dépôt.
ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from boulangerie_app.connected_mode import ConnectionSettings  # noqa: E402
from boulangerie_app.database import DatabaseHelper  # noqa: E402


@pytest.fixture()
def db(tmp_path: Path):
    """Fournit ``DatabaseHelper`` branché sur une base neuve et jetable.

    - Isole le stockage dans ``tmp_path`` (aucun accès à ``%LOCALAPPDATA%``).
    - Neutralise la recopie de la base « legacy » du dépôt.
    - Force le mode local (jamais d'appel réseau vers le serveur central).
    """
    DatabaseHelper.set_storage_root(tmp_path)
    # Empêche ``initialize_local_database`` de recopier boulangerie.db du dépôt.
    DatabaseHelper.legacy_db_path = tmp_path / "legacy-inexistante.db"
    DatabaseHelper.apply_connection_settings(ConnectionSettings(mode="local"), persist=False)
    DatabaseHelper.initialize_local_database()
    return DatabaseHelper


@pytest.fixture()
def make_worker(db):
    """Fabrique un travailleur minimal et renvoie son identifiant."""

    def _make(full_name: str = "Jean Ouvrier", salary: float = 100000) -> int:
        return db.add_worker(
            full_name=full_name,
            function="Boulanger",
            phone="",
            email="",
            address="",
            hire_date="2025-01-01",
            monthly_salary=salary,
            status="Actif",
        )

    return _make

