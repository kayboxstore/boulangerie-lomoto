"""Régressions des corrections P2 de la version 1.5.5."""

from __future__ import annotations

import csv
from datetime import date
import json
import os
from pathlib import Path
import subprocess

import pytest

from boulangerie_app.app import parse_float, parse_optional_float
from boulangerie_app.connected_server import _reject_non_finite_json as reject_connected_constant
from boulangerie_app.demo_data import (
    DEMO_ADMIN_PASSWORD,
    DEMO_ADMIN_USERNAME,
    DEMO_USER_IDENTIFIERS,
    DEMO_USER_PASSWORD,
    seed_demo_database_if_empty,
)
from boulangerie_app.excel_reports import _safe_text
from boulangerie_app.spreadsheet_security import sanitize_spreadsheet_value
from boulangerie_web_pro.server import (
    _int,
    _money,
    _reject_non_finite_json as reject_web_constant,
)


@pytest.mark.parametrize("constant", ["NaN", "Infinity", "-Infinity"])
def test_json_entry_points_reject_non_finite_constants(constant):
    payload = f'{{"value": {constant}}}'
    with pytest.raises(ValueError):
        json.loads(payload, parse_constant=reject_web_constant)
    with pytest.raises(ValueError):
        json.loads(payload, parse_constant=reject_connected_constant)


@pytest.mark.parametrize("value", ["NaN", "Infinity", "-Infinity"])
def test_numeric_parsers_reject_non_finite_values(value):
    with pytest.raises(ValueError):
        parse_float(value, "Montant")
    with pytest.raises(ValueError):
        parse_optional_float(value)
    with pytest.raises(ValueError):
        _money(value)
    with pytest.raises(ValueError):
        _int(value)


def test_database_rejects_non_finite_business_values(db):
    with pytest.raises(ValueError, match="nombre fini"):
        db.add_worker(
            full_name="Jean Ouvrier",
            function="Boulanger",
            phone="",
            email="",
            address="",
            hire_date="2025-01-01",
            monthly_salary=float("inf"),
            status="Actif",
        )
    with pytest.raises(ValueError, match="nombre fini"):
        db.update_stock_configuration(float("nan"), 10, 10, 10)
    with pytest.raises(ValueError, match="nombre fini"):
        db.add_stock_supply(date.today(), 1, float("inf"), 1, 1)


@pytest.mark.parametrize(
    ("value", "expected"),
    [
        ("=HYPERLINK(\"https://example.invalid\")", "'=HYPERLINK(\"https://example.invalid\")"),
        (" +SUM(A1:A2)", "' +SUM(A1:A2)"),
        ("-10+20", "'-10+20"),
        ("@malicious", "'@malicious"),
        ("Texte normal", "Texte normal"),
        (-1500, -1500),
    ],
)
def test_spreadsheet_values_are_neutralized(value, expected):
    assert sanitize_spreadsheet_value(value) == expected


def test_excel_text_helper_and_csv_archive_neutralize_formulas(db):
    assert _safe_text("=CMD()") == "'=CMD()"
    db.log_activity(
        "a.test",
        "Alice Test",
        "Admin",
        "Historique",
        "=WEBSERVICE(\"https://example.invalid\")",
        "+commande",
    )

    archive_path = db.archive_activity_logs()

    assert archive_path is not None
    with archive_path.open("r", encoding="utf-8-sig", newline="") as handle:
        row = next(csv.DictReader(handle))
    assert row["Action"].startswith("'=")
    assert row["Details"].startswith("'+")


def test_demo_seed_creates_working_accounts_and_data(db):
    seed_demo_database_if_empty(date(2026, 7, 17))

    assert db.find_user_for_login(DEMO_ADMIN_USERNAME, DEMO_ADMIN_PASSWORD) is not None
    for username in DEMO_USER_IDENTIFIERS:
        assert db.find_user_for_login(username, DEMO_USER_PASSWORD) is not None
        assert db.is_using_default_password(username) is False
    assert db.list_orders()


def test_web_dates_use_local_calendar_day():
    root = Path(__file__).resolve().parents[1]
    for relative_path in (
        Path("boulangerie_web_pro/static/app.js"),
        Path("web-mobile-app/src/api.js"),
    ):
        source = (root / relative_path).read_text(encoding="utf-8")
        assert "toISOString().slice(0, 10)" not in source
        assert "getFullYear()" in source
        assert "getMonth()" in source
        assert "getDate()" in source


@pytest.mark.skipif(os.name != "nt", reason="Script PowerShell destiné à Windows")
def test_firewall_script_has_valid_powershell_syntax():
    script_path = Path(__file__).resolve().parents[1] / "scripts" / "autoriser-web-pro-pare-feu.ps1"
    command = (
        "$errors = $null; "
        f"[void][System.Management.Automation.Language.Parser]::ParseFile('{script_path}', [ref]$null, [ref]$errors); "
        "if ($errors.Count) { $errors | ForEach-Object { Write-Error $_.Message }; exit 1 }"
    )
    result = subprocess.run(
        ["powershell.exe", "-NoProfile", "-NonInteractive", "-Command", command],
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 0, result.stderr
