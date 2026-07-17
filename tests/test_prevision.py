"""Tests de non-régression du module Prévisions.

Régression : ``PREVISION_STATUSES`` et ``PREVISION_LOCATIONS`` étaient utilisées
dans ``PrevisionWindow`` sans jamais être définies -> le module « Prévisions »
plantait (NameError) dès son ouverture.
"""

from __future__ import annotations

from datetime import date, timedelta

from openpyxl import load_workbook

from boulangerie_app.app import ROLE_MODULE_ACCESS, ROLE_READ_ONLY_MODULES
from boulangerie_app.connected_server import _is_method_allowed_for_session
from boulangerie_app.database import DatabaseHelper
from boulangerie_app.excel_reports import create_prevision_excel_workbook
from boulangerie_app.status_labels import DEPOSITARY_STATUS


def test_prevision_constants_are_defined():
    import boulangerie_app.app as app

    assert isinstance(app.PREVISION_STATUSES, (list, tuple)) and app.PREVISION_STATUSES
    assert isinstance(app.PREVISION_LOCATIONS, (list, tuple)) and app.PREVISION_LOCATIONS
    # Seuls Dépositaire et Maman sont des statuts de prévision valides.
    assert set(app.PREVISION_STATUSES) == {DEPOSITARY_STATUS, "Maman"}


def test_prevision_order_roundtrip(db):
    today = date.today()
    db.add_prevision_order(today, "Dépôt 1", "Client Test", DEPOSITARY_STATUS, 5, 0, 3, 0)
    rows = db.list_previsions_by_date(today)
    assert len(rows) == 1
    assert rows[0]["Client"] == "Client Test"
    assert rows[0]["Localisation"] == "Dépôt 1"


def test_future_prevision_is_allowed(db):
    tomorrow = date.today() + timedelta(days=1)
    db.add_prevision_order(tomorrow, "Dépôt 2", "Client demain", DEPOSITARY_STATUS, 2, 1, 0, 0)

    rows = db.list_previsions_by_date(tomorrow)

    assert len(rows) == 1
    assert rows[0]["DatePrevision"] == tomorrow.isoformat()
    assert rows[0]["TotalArticles"] == 3


def test_prevision_module_is_visible_for_operational_roles():
    assert "Prévisions" in ROLE_MODULE_ACCESS["Admin"]
    assert "Prévisions" in ROLE_MODULE_ACCESS["Directeur Général"]
    assert "Prévisions" in ROLE_MODULE_ACCESS["Chargé de la production"]
    assert "Prévisions" in ROLE_MODULE_ACCESS["Gestionnaire des commandes"]
    assert "Prévisions" in ROLE_READ_ONLY_MODULES["Directeur Général"]
    assert "Prévisions" not in ROLE_MODULE_ACCESS["Caissier"]


def test_connected_prevision_permissions_match_desktop_roles():
    production = {"role": "Chargé de la production", "identifiant": "prod"}
    orders = {"role": "Gestionnaire des commandes", "identifiant": "cmd"}
    director = {"role": "Directeur Général", "identifiant": "dg"}
    cashier = {"role": "Caissier", "identifiant": "caisse"}

    assert _is_method_allowed_for_session("add_prevision_order", [], production)
    assert _is_method_allowed_for_session("add_prevision_order", [], orders)
    assert _is_method_allowed_for_session("list_previsions", [], director)
    assert not _is_method_allowed_for_session("add_prevision_order", [], director)
    assert not _is_method_allowed_for_session("list_previsions", [], cashier)


def test_prevision_excel_workbook_contains_three_printable_sheets_and_sanitizes_text(db, tmp_path):
    tomorrow = date.today() + timedelta(days=1)
    db.add_prevision_order(tomorrow, "Dépôt 1", "=2+3", DEPOSITARY_STATUS, 5, 0, 3, 0)
    db.add_prevision_order(tomorrow, "", "Maman Test", "Maman", 0, 2, 0, 1)
    destination = tmp_path / "previsions.xlsx"

    result = create_prevision_excel_workbook(
        tomorrow,
        destination,
        generated_by="Admin Test",
        generated_role="Admin",
    )

    assert result == destination
    workbook = load_workbook(destination, data_only=False)
    try:
        assert workbook.sheetnames == ["Résumé", "Dépositaires", "Mamans"]
        depositary_values = [cell.value for row in workbook["Dépositaires"].iter_rows() for cell in row]
        assert "'=2+3" in depositary_values
        assert "=2+3" not in depositary_values
        assert workbook["Dépositaires"].page_setup.orientation == "landscape"
        summary_values = [cell.value for row in workbook["Résumé"].iter_rows() for cell in row]
        assert 11 in summary_values
        assert 12000 in summary_values
    finally:
        workbook.close()
