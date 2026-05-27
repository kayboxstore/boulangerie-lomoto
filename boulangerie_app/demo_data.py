from __future__ import annotations

from datetime import date, timedelta

from .connected_mode import ConnectionSettings
from .database import DatabaseHelper
from .status_labels import DEPOSITARY_STATUS, ORDER_STATUS_RATES


DEMO_ADMIN_USERNAME = "demo.admin"
LEGACY_OFFICIAL_ADMIN_IDENTIFIERS = ("a.kayembe", "au.kayembe", "au.keyembe", "admin")


def _amount_due(status: str, trays: int) -> float:
    return float(ORDER_STATUS_RATES[status] * trays)


def _add_order(target_date: date, client: str, status: str, trays: int, received: float) -> None:
    due = _amount_due(status, trays)
    DatabaseHelper.add_order(target_date, client, status, trays, due, received, max(due - received, 0))


def _demo_database_needs_reset() -> bool:
    with DatabaseHelper.connect() as connection:
        demo_admin_exists = connection.execute(
            "SELECT COUNT(*) FROM Utilisateurs WHERE Identifiant = ?",
            (DEMO_ADMIN_USERNAME,),
        ).fetchone()[0]
        legacy_official_admin_exists = connection.execute(
            f"""
            SELECT COUNT(*)
            FROM Utilisateurs
            WHERE Identifiant IN ({",".join("?" for _ in LEGACY_OFFICIAL_ADMIN_IDENTIFIERS)})
            """,
            LEGACY_OFFICIAL_ADMIN_IDENTIFIERS,
        ).fetchone()[0]
    return not bool(demo_admin_exists) or bool(legacy_official_admin_exists)


def _reset_demo_database() -> None:
    with DatabaseHelper.connect() as connection:
        DatabaseHelper._clear_records_and_insert_defaults(connection)


def seed_demo_database_if_empty(base_date: date | None = None) -> None:
    """Prepare a realistic standalone dataset for the demo edition."""
    DatabaseHelper.apply_connection_settings(ConnectionSettings(), persist=True)

    with DatabaseHelper.local_calls_only():
        DatabaseHelper.initialize_local_database()
        if _demo_database_needs_reset():
            _reset_demo_database()
        if DatabaseHelper.list_orders():
            return

        today = base_date or date.today()
        day_1 = today - timedelta(days=5)
        day_2 = today - timedelta(days=4)
        day_3 = today - timedelta(days=3)
        day_4 = today - timedelta(days=2)
        day_5 = today - timedelta(days=1)

        demo_users = [
            ("Grâce Mbala", "demo.caisse", "060606", "Caissier"),
            ("Patrick Nsimba", "demo.stock", "060606", "Gestionnaire de stock"),
            ("Ruth Mansi", "demo.commandes", "060606", "Gestionnaire des commandes"),
        ]
        for full_name, username, password, role in demo_users:
            try:
                DatabaseHelper.add_user(full_name, username, password, role)
            except Exception:
                pass

        DatabaseHelper.update_stock_configuration(160, 90, 45, 40)
        stock_days = [
            (day_1, (42, 18, 10, 9), [(10, 5, 3, 2)]),
            (day_2, (0, 0, 0, 0), [(12, 6, 4, 3)]),
            (day_3, (35, 14, 8, 6), [(14, 7, 5, 4)]),
            (day_4, (0, 0, 0, 0), [(9, 5, 3, 3)]),
            (day_5, (25, 10, 6, 5), [(11, 5, 4, 3)]),
            (today, (30, 12, 8, 7), [(8, 4, 2, 2), (6, 3, 2, 2)]),
        ]
        for target_date, supply, exits in stock_days:
            DatabaseHelper.initialize_stock_day(target_date)
            if any(supply):
                DatabaseHelper.add_stock_supply(target_date, *supply, "Approvisionnement démo")
            for stock_exit in exits:
                DatabaseHelper.add_stock_exit(target_date, *stock_exit)
            DatabaseHelper.update_stock_closing(target_date)

        order_rows = {
            day_1: [
                ("Dépôt Matonge", DEPOSITARY_STATUS, 18, 18 * 4100),
                ("Maman Chantal", "Maman", 10, 55000),
                ("Boutique Espoir", "Vente cash", 8, 8 * 4350),
            ],
            day_2: [
                ("Dépôt Barumbu", DEPOSITARY_STATUS, 22, 80000),
                ("Maman Odette", "Maman", 11, 66000),
                ("Café Horizon", "Vente cash", 7, 7 * 4350),
            ],
            day_3: [
                ("Dépôt Limete", DEPOSITARY_STATUS, 20, 82000),
                ("Maman Bijou", "Maman", 9, 45000),
                ("Restaurant Fleuve", "Vente cash", 10, 10 * 4350),
            ],
            day_4: [
                ("Dépôt Ngaba", DEPOSITARY_STATUS, 24, 98400),
                ("Maman Grâce", "Maman", 12, 62000),
                ("Mini Market Kasa", "Vente cash", 9, 9 * 4350),
            ],
            day_5: [
                ("Dépôt Bandal", DEPOSITARY_STATUS, 19, 70000),
                ("Maman Esther", "Maman", 13, 78000),
                ("Cafétéria Victoire", "Vente cash", 8, 8 * 4350),
            ],
            today: [
                ("Dépôt Kin Marché", DEPOSITARY_STATUS, 25, 90000),
                ("Maman Sarah", "Maman", 14, 80000),
                ("Restaurant Boma", "Vente cash", 12, 12 * 4350),
                ("Maman Clarisse", "Maman", 8, 42000),
            ],
        }
        for target_date, rows in order_rows.items():
            for client, status, trays, received in rows:
                _add_order(target_date, client, status, trays, received)

        production_rows = [
            (day_1, 36, 16, 10, 2, 1, 5, 1, 10, "Journée normale."),
            (day_2, 40, 18, 11, 3, 1, 6, 1, 12, "Bonne couverture des commandes."),
            (day_3, 39, 17, 9, 2, 1, 7, 2, 14, "Quelques bacs foutus à surveiller."),
            (day_4, 45, 20, 12, 3, 2, 6, 2, 9, "Forte demande côté mamans."),
            (day_5, 40, 18, 13, 2, 1, 5, 1, 11, "Production stable."),
            (today, 59, 25, 22, 4, 2, 5, 1, 14, "Préparation exposition avec stock de sécurité."),
        ]
        for row in production_rows:
            DatabaseHelper.save_production_day(*row)

        cash_rows = [
            (day_1, 18000, "Transport : 8 000 FC\nDivers : 10 000 FC", 0, ""),
            (day_2, 21500, "Carburant : 12 000 FC\nManutention : 9 500 FC", 5000, "Maman Chantal : 5 000 FC"),
            (day_3, 17000, "Transport : 7 000 FC\nEmballages : 10 000 FC", 10000, "Dépôt Barumbu : 10 000 FC"),
            (day_4, 24000, "Carburant : 14 000 FC\nRéparation : 10 000 FC", 9000, "Maman Bijou : 9 000 FC"),
            (day_5, 19000, "Transport : 9 000 FC\nDivers : 10 000 FC", 10000, "Dépôt Barumbu : 10 000 FC"),
            (today, 26500, "Transport : 11 000 FC\nCarburant : 9 500 FC\nDivers : 6 000 FC", 8000, "Dépôt Bandal : 8 000 FC"),
        ]
        for target_date, expenses, details, paid_debts, paid_details in cash_rows:
            DatabaseHelper.save_cash_day(target_date, expenses, details, paid_debts, paid_details)

        DatabaseHelper.sync_all_commissions()
