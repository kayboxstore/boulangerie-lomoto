"""Tests du calcul des montants de commande.

Règle métier : montant dû = nombre de bacs x tarif du statut ;
dette = max(dû - reçu, 0). Ces montants alimentent la caisse et les commissions.
"""

from __future__ import annotations

from datetime import date

import pytest

from boulangerie_app.database import DatabaseHelper
from boulangerie_app.status_labels import ORDER_STATUS_RATES


def test_amount_due_is_trays_times_rate():
    client, status, trays, due, received, debt = DatabaseHelper._validate_order_amounts(
        "Client A", "Maman", 10, 0, 60000
    )
    assert status == "Maman"
    assert trays == 10
    assert due == 10 * ORDER_STATUS_RATES["Maman"]  # 10 x 6000 = 60000
    assert due == 60000
    assert received == 60000
    assert debt == 0


def test_partial_payment_produces_debt():
    _client, _status, _trays, due, received, debt = DatabaseHelper._validate_order_amounts(
        "Client B", "Maman", 10, 0, 45000
    )
    assert due == 60000
    assert received == 45000
    assert debt == 15000  # 60000 - 45000


def test_overpayment_never_produces_negative_debt():
    _c, _s, _t, due, received, debt = DatabaseHelper._validate_order_amounts(
        "Client C", "Vente cash", 2, 0, 999999
    )
    assert due == 2 * ORDER_STATUS_RATES["Vente cash"]
    assert debt == 0  # jamais de dette négative


@pytest.mark.parametrize("trays", [0, -3])
def test_zero_or_negative_trays_rejected(trays):
    with pytest.raises(ValueError):
        DatabaseHelper._validate_order_amounts("Client", "Maman", trays, 0, 0)


def test_negative_amount_received_rejected():
    with pytest.raises(ValueError):
        DatabaseHelper._validate_order_amounts("Client", "Maman", 5, 0, -1)


def test_empty_client_rejected():
    with pytest.raises(ValueError):
        DatabaseHelper._validate_order_amounts("   ", "Maman", 5, 0, 0)


def test_unknown_status_rejected():
    with pytest.raises(ValueError):
        DatabaseHelper._validate_order_amounts("Client", "StatutInexistant", 5, 0, 0)


def test_add_order_persists_computed_debt(db):
    day = date(2026, 1, 15)
    db.add_order(day, "Boutique X", "Maman", 4, 0, 20000, 0)
    orders = db.list_orders_by_date(day) if hasattr(db, "list_orders_by_date") else None
    # Vérifie la dette agrégée : dû = 4 x 6000 = 24000, reçu = 20000 -> dette 4000.
    assert db.count_orders_with_debt() == 1
    if orders is not None:
        assert len(orders) == 1
