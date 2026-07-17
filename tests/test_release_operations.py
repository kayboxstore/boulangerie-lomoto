from __future__ import annotations

import sqlite3
from pathlib import Path

import pytest

from boulangerie_app.connected_server import run_server
from boulangerie_app.windows_service import inspect_sqlite_database, run_sqlite_integrity_check


ROOT = Path(__file__).resolve().parents[1]


def test_service_integrity_checker_accepts_a_real_backup(db):
    integrity, table_count = inspect_sqlite_database(db.db_path)

    assert integrity == "ok"
    assert table_count >= 5
    assert run_sqlite_integrity_check(db.db_path) == 0


def test_service_integrity_checker_rejects_an_invalid_database(tmp_path):
    invalid = tmp_path / "invalid.db"
    invalid.write_bytes(b"not a sqlite database")

    with pytest.raises(sqlite3.DatabaseError):
        inspect_sqlite_database(invalid)
    assert run_sqlite_integrity_check(invalid) == 1


def test_cloud_runtime_refuses_to_start_without_configured_token(monkeypatch, tmp_path):
    monkeypatch.setenv("K_SERVICE", "lomoto-test")

    with pytest.raises(RuntimeError, match="BOULANGERIE_API_TOKEN"):
        run_server(host="127.0.0.1", port=0, api_token="", data_dir=tmp_path)


def test_cloud_run_deployment_uses_secret_manager_and_versioned_images():
    deploy_script = (ROOT / "cloud-run" / "deploy-cloud-run.ps1").read_text(encoding="utf-8")
    cloudbuild = (ROOT / "cloud-run" / "cloudbuild.yaml").read_text(encoding="utf-8")

    assert "[string]$Token" not in deploy_script
    assert "--set-secrets" in deploy_script
    assert "secretmanager.googleapis.com" in deploy_script
    assert "-AllowEphemeralSqlite" in deploy_script
    assert "1.3.18" not in deploy_script
    assert "${_TAG}" in cloudbuild
    assert ":latest" not in cloudbuild


def test_production_tasks_include_backup_watchdog_and_restore_validation():
    installer = (ROOT / "scripts" / "installer-taches-production-lomoto.ps1").read_text(encoding="utf-8")
    verifier = (ROOT / "scripts" / "verifier-taches-production-lomoto.ps1").read_text(encoding="utf-8")
    restore_script = (ROOT / "scripts" / "tester-restauration-sauvegarde-lomoto.ps1").read_text(
        encoding="utf-8"
    )

    for task_name in (
        "Boulangerie Lomoto - Sauvegarde quotidienne",
        "Boulangerie Lomoto - Sauvegarde externe hebdomadaire",
        "Boulangerie Lomoto - Surveillance service",
        "Boulangerie Lomoto - Test restauration hebdomadaire",
    ):
        assert task_name in installer
        assert task_name in verifier
    assert "--check-sqlite" in restore_script
    assert "Set-Content -LiteralPath $checkFile" not in restore_script
