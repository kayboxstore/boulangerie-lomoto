"""Tests des commissions dérivées des commandes.

Règle métier : seules les commandes au statut « Maman » génèrent une commission
de 1650 Fc par bac, agrégée par client et par jour, diminuée de la dette
impayée. Les commissions ne sont jamais saisies à la main.
"""

from __future__ import annotations

from datetime import date

import pytest

from boulangerie_app.database import DatabaseHelper


def test_maman_order_generates_commission(db):
    day = date(2026, 2, 3)
    db.add_order(day, "Maman Bea", "Maman", 10, 0, 60000, 0)  # payée intégralement
    db.sync_all_commissions()

    summary = db.get_commissions_summary(day, day)
    assert summary["TotalBacs"] == 10
    assert summary["TotalCommissions"] == 10 * 1650  # 16500
    assert summary["TotalDettes"] == 0
    assert summary["TotalNetAPayer"] == 16500


def test_commission_reduced_by_outstanding_debt(db):
    day = date(2026, 2, 4)
    # 10 bacs Maman, seulement 50000 reçus sur 60000 -> dette 10000.
    db.add_order(day, "Maman Bea", "Maman", 10, 0, 50000, 0)
    db.sync_all_commissions()

    summary = db.get_commissions_summary(day, day)
    assert summary["TotalCommissions"] == 16500
    assert summary["TotalDettes"] == 10000
    assert summary["TotalNetAPayer"] == 16500 - 10000  # net diminué de la dette


def test_non_maman_orders_generate_no_commission(db):
    day = date(2026, 2, 5)
    db.add_order(day, "Client Cash", "Vente cash", 8, 0, 34800, 0)
    db.add_order(day, "Depot Y", "Dépositaire", 5, 0, 20500, 0)
    db.sync_all_commissions()

    summary = db.get_commissions_summary(day, day)
    assert summary["NombreCommissions"] == 0
    assert summary["TotalCommissions"] == 0


def test_commissions_aggregated_per_client_same_day(db):
    day = date(2026, 2, 6)
    db.add_order(day, "Maman Bea", "Maman", 4, 0, 24000, 0)
    db.add_order(day, "Maman Bea", "Maman", 6, 0, 36000, 0)  # même cliente, même jour
    db.sync_all_commissions()

    summary = db.get_commissions_summary(day, day)
    assert summary["NombreCommissions"] == 1  # une seule ligne agrégée
    assert summary["TotalBacs"] == 10
    assert summary["TotalCommissions"] == 16500


def test_manual_commission_insertion_is_forbidden(db):
    with pytest.raises(ValueError):
        db.add_commission(date(2026, 2, 6), "Quelquun", "Maman", 3, 0, 4950, 0, 4950)
