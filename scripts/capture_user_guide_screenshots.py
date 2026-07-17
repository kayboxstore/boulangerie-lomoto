from __future__ import annotations

import ctypes
import os
import shutil
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
os.environ["BOULANGERIE_APP_EDITION"] = "demo"
os.environ["BOULANGERIE_APP_NAME"] = "Boulangerie Lomoto Démo"
os.environ["BOULANGERIE_DEFAULT_ADMIN_FULL_NAME"] = "Administrateur Démo"
os.environ["BOULANGERIE_DEFAULT_ADMIN_USERNAME"] = "demo.admin"
os.environ["BOULANGERIE_DEFAULT_ADMIN_PASSWORD"] = "Essai#Four9Kivu!"

from boulangerie_app.app import (  # noqa: E402
    APP_BACKGROUND,
    ExcelReportWindow,
    DashboardWindow,
    LoginWindow,
    OrdersWindow,
    PdfReportWindow,
    ProductionWindow,
    StockWindow,
    StockSupplyDialog,
    UsersWindow,
    CashWindow,
    CommissionsWindow,
    apply_window_icon,
    center_window,
    configure_styles,
)
from boulangerie_app.database import AuthenticatedUser, DatabaseHelper  # noqa: E402
from boulangerie_app.demo_data import seed_demo_database_if_empty  # noqa: E402
from boulangerie_app.connected_mode import ConnectionSettings  # noqa: E402
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
    seed_demo_database_if_empty(DEMO_DATE)


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
    DatabaseHelper.apply_connection_settings(ConnectionSettings(mode="local"), persist=False)
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
    DatabaseHelper.apply_connection_settings(ConnectionSettings(mode="local"), persist=False)


def capture_application_screens() -> None:
    DatabaseHelper.set_storage_root(DEMO_DATA_DIR)
    DatabaseHelper.apply_connection_settings(ConnectionSettings(mode="local"), persist=False)
    root = tk.Tk()
    root.withdraw()
    configure_styles()

    DashboardWindow.start_weekly_update_check = lambda self: None  # type: ignore[method-assign]

    admin_user = AuthenticatedUser(
        identifiant="demo.admin",
        role="Admin",
        full_name="Administrateur Démo",
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
    stock_supply_window = StockSupplyDialog(stock_window)
    root.update()
    capture_window(stock_supply_window, "05-approvisionnement-stock.png")
    stock_supply_window.close_dialog()
    stock_window.destroy()

    orders_window = OrdersWindow(dashboard)
    root.update()
    capture_window(orders_window, "06-commandes.png")
    orders_window.destroy()

    production_window = ProductionWindow(dashboard)
    root.update()
    capture_window(production_window, "07-production.png")
    production_window.destroy()

    cash_window = CashWindow(dashboard)
    root.update()
    capture_window(cash_window, "08-caisse.png")
    cash_window.destroy()

    commissions_window = CommissionsWindow(dashboard)
    root.update()
    capture_window(commissions_window, "09-commissions.png")
    commissions_window.destroy()

    pdf_window = PdfReportWindow(dashboard)
    root.update()
    capture_window(pdf_window, "10-rapport-pdf.png")
    pdf_window.destroy()

    excel_window = ExcelReportWindow(dashboard)
    root.update()
    capture_window(excel_window, "11-rapport-excel.png")
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
