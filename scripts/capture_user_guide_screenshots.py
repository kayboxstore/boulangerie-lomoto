from __future__ import annotations

import ctypes
import os
import shutil
import sqlite3
import sys
import time
from datetime import date
from pathlib import Path

import tkinter as tk
import win32con  # type: ignore
import win32gui  # type: ignore
from PIL import ImageGrab


PROJECT_ROOT = Path(__file__).resolve().parent.parent
GUIDE_DIR = PROJECT_ROOT / "presentations" / "guide-utilisateur"
SCREENSHOT_DIR = GUIDE_DIR / "assets" / "screenshots"
DEMO_DATA_DIR = GUIDE_DIR / "demo-data"
DEMO_DATE = date(2026, 5, 18)

if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

os.environ["BOULANGERIE_APPDATA_DIR"] = str(DEMO_DATA_DIR)

from boulangerie_app.app import (  # noqa: E402
    APP_BACKGROUND,
    ExcelReportWindow,
    DashboardWindow,
    LoginWindow,
    OrdersWindow,
    PdfReportWindow,
    StockWindow,
    UsersWindow,
    CashWindow,
    CommissionsWindow,
    apply_window_icon,
    center_window,
    configure_styles,
)
from boulangerie_app.database import AuthenticatedUser, DatabaseHelper  # noqa: E402
from boulangerie_app.version import APP_NAME, APP_VERSION  # noqa: E402


def set_dpi_awareness() -> None:
    try:
        ctypes.windll.shcore.SetProcessDpiAwareness(2)
    except Exception:
        try:
            ctypes.windll.user32.SetProcessDPIAware()
        except Exception:
            return


def ensure_clean_demo_environment() -> None:
    if GUIDE_DIR.exists():
        GUIDE_DIR.mkdir(parents=True, exist_ok=True)
    if DEMO_DATA_DIR.exists():
        shutil.rmtree(DEMO_DATA_DIR, ignore_errors=True)
    if SCREENSHOT_DIR.exists():
        shutil.rmtree(SCREENSHOT_DIR, ignore_errors=True)
    SCREENSHOT_DIR.mkdir(parents=True, exist_ok=True)


def seed_demo_data() -> None:
    DatabaseHelper.set_storage_root(DEMO_DATA_DIR)
    DatabaseHelper.db_path.parent.mkdir(parents=True, exist_ok=True)
    DatabaseHelper.backups_dir.mkdir(parents=True, exist_ok=True)
    DatabaseHelper.reports_dir.mkdir(parents=True, exist_ok=True)
    with DatabaseHelper.connect() as connection:
        DatabaseHelper._create_tables(connection)
        DatabaseHelper._migrate_orders_table(connection)
        DatabaseHelper._migrate_commissions_table(connection)
        DatabaseHelper._normalize_status_values(connection)
        DatabaseHelper._insert_default_admin(connection)
        DatabaseHelper._insert_default_stock_config(connection)
    with sqlite3.connect(DatabaseHelper.db_path) as connection:
        connection.execute("PRAGMA journal_mode = WAL")

    demo_users = [
        ("Ismaël Mfumu", "is.mfumu", "060606", "Admin"),
        ("Grâce Mbala", "g.mbala", "060606", "Caissier"),
        ("Patrick Nsimba", "p.nsimba", "060606", "Gestionnaire de stock"),
        ("Ruth Mansi", "r.mansi", "060606", "Gestionnaire des commandes"),
    ]
    for user in demo_users:
        DatabaseHelper.add_user(*user)

    DatabaseHelper.update_stock_configuration(120, 72, 40, 36)
    DatabaseHelper.initialize_stock_day(DEMO_DATE)
    DatabaseHelper.add_stock_exit(DEMO_DATE, 6, 4, 3, 5)
    DatabaseHelper.add_stock_exit(DEMO_DATE, 8, 5, 4, 3)
    DatabaseHelper.add_stock_exit(DEMO_DATE, 4, 2, 1, 2)
    DatabaseHelper.update_stock_closing(DEMO_DATE)

    demo_orders = [
        ("Café Horizon", "Maman", 12, 72000, 72000, 0),
        ("Boutique Espoir", "Vente cash", 8, 48000, 48000, 0),
        ("Dépôt Matonge", "Dépositaire", 15, 90000, 61500, 28500),
        ("Marché Central", "Maman", 6, 36000, 30000, 6000),
    ]
    for client, status, trays, due, received, debt in demo_orders:
        DatabaseHelper.add_order(DEMO_DATE, client, status, trays, due, received, debt)

    demo_clients = ["Café Horizon", "Boutique Espoir", "Dépôt Matonge", "Marché Central"]
    for client in demo_clients:
        synthesis = DatabaseHelper.get_commission_synthesis_from_orders(DEMO_DATE, client)
        if not synthesis:
            continue
        DatabaseHelper.add_commission(
            DEMO_DATE,
            client,
            str(synthesis.get("Statut", "")),
            int(synthesis.get("NombreBacs", 0) or 0),
            float(synthesis.get("MontantPaye", 0) or 0),
            float(synthesis.get("Commissions", 0) or 0),
            float(synthesis.get("Dettes", 0) or 0),
            float(synthesis.get("NetAPayer", 0) or 0),
        )

    DatabaseHelper.save_cash_day(
        DEMO_DATE,
        18500,
        "Transport : 7 000 FC\nCarburant : 6 500 FC\nDivers : 5 000 FC",
    )


def bring_to_front(window: tk.Misc) -> int:
    window.update_idletasks()
    window.lift()
    try:
        window.attributes("-topmost", True)
    except tk.TclError:
        pass
    window.update()
    time.sleep(0.4)
    hwnd = int(window.winfo_id())
    try:
        win32gui.ShowWindow(hwnd, win32con.SW_RESTORE)
        win32gui.SetForegroundWindow(hwnd)
    except Exception:
        pass
    window.update()
    time.sleep(0.5)
    return hwnd


def capture_window(window: tk.Misc, output_name: str) -> Path:
    hwnd = bring_to_front(window)
    left, top, right, bottom = win32gui.GetWindowRect(hwnd)
    image = ImageGrab.grab(bbox=(left, top, right, bottom), all_screens=True)
    output_path = SCREENSHOT_DIR / output_name
    image.save(output_path)
    try:
        window.attributes("-topmost", False)
    except tk.TclError:
        pass
    return output_path


def capture_login_screen() -> None:
    root = tk.Tk()
    root.title(f"{APP_NAME} - Connexion - v{APP_VERSION}")
    root.geometry("580x380")
    root.minsize(580, 380)
    root.configure(bg=APP_BACKGROUND)
    apply_window_icon(root)
    configure_styles()
    LoginWindow(root, None)
    center_window(root)
    root.update()
    capture_window(root, "01-connexion.png")
    root.destroy()


def capture_application_screens() -> None:
    root = tk.Tk()
    root.withdraw()
    configure_styles()

    DashboardWindow.start_weekly_update_check = lambda self: None  # type: ignore[method-assign]

    admin_user = AuthenticatedUser(
        identifiant="is.mfumu",
        role="Admin",
        full_name="Ismaël Mfumu",
    )
    dashboard = DashboardWindow(root, admin_user, lambda: None, None)
    root.update()
    capture_window(dashboard, "02-tableau-de-bord.png")

    users_window = UsersWindow(dashboard)
    root.update()
    capture_window(users_window, "03-utilisateurs.png")
    users_window.destroy()

    stock_window = StockWindow(dashboard)
    root.update()
    capture_window(stock_window, "04-stock.png")
    stock_window.destroy()

    orders_window = OrdersWindow(dashboard)
    root.update()
    capture_window(orders_window, "05-commandes.png")
    orders_window.destroy()

    cash_window = CashWindow(dashboard)
    root.update()
    capture_window(cash_window, "06-caisse.png")
    cash_window.destroy()

    commissions_window = CommissionsWindow(dashboard)
    root.update()
    capture_window(commissions_window, "07-commissions.png")
    commissions_window.destroy()

    pdf_window = PdfReportWindow(dashboard)
    root.update()
    capture_window(pdf_window, "08-rapport-pdf.png")
    pdf_window.destroy()

    excel_window = ExcelReportWindow(dashboard)
    root.update()
    capture_window(excel_window, "09-rapport-excel.png")
    excel_window.destroy()

    dashboard.destroy()
    root.destroy()


def main() -> None:
    set_dpi_awareness()
    ensure_clean_demo_environment()
    seed_demo_data()
    capture_login_screen()
    capture_application_screens()
    print(f"Captures enregistrées dans : {SCREENSHOT_DIR}")


if __name__ == "__main__":
    main()
