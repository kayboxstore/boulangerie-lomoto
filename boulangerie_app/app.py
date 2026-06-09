from __future__ import annotations

import calendar
import os
import secrets
import sys
import threading
import unicodedata
from pathlib import Path
from queue import Empty, Queue
import tkinter as tk
import webbrowser
from datetime import date, datetime, timedelta
from tkinter import filedialog, messagebox, simpledialog, ttk
from tkinter.scrolledtext import ScrolledText
from typing import Any, Callable

from PIL import Image, ImageTk

from .cash_reports import (
    create_cash_balance_excel_report,
    create_cash_balance_pdf_report,
    month_bounds as cash_month_bounds,
    week_bounds as cash_week_bounds,
)
from .connected_mode import (
    ConnectionSettings,
    DiscoveredServerInfo,
    REMOTE_DEFAULT_PORT,
    REMOTE_DISCOVERY_TIMEOUT_SECONDS,
    REMOTE_REFRESH_INTERVAL_MS,
    RemoteDatabaseClient,
    RemoteDatabaseError,
    discover_remote_servers,
    fetch_public_server_directory,
    load_connection_settings,
)
from .connected_server import (
    get_embedded_server_status,
    is_embedded_server_running,
    start_embedded_server,
    stop_embedded_server,
)
from .database import AUTO_BACKUP_PREFIX, ActiveSessionConflictError, AuthenticatedUser, DatabaseHelper
from .excel_reports import create_daily_excel_report, create_monthly_excel_report, create_period_excel_report
from .reports import (
    ReportGenerationError,
    create_daily_pdf_report,
    create_monthly_pdf_report,
    create_period_pdf_report,
    get_report_scope_description,
    get_report_scope_label,
)
from .server_host import (
    CentralServerSettings,
    build_local_server_addresses,
    ensure_windows_firewall_rules,
    get_windows_service_status,
    install_or_update_windows_service,
    is_running_as_administrator,
    is_server_installation,
    load_central_server_settings,
    prepare_central_server_data,
    relaunch_current_process_as_administrator,
    remove_windows_service,
    save_central_server_settings,
    start_windows_service,
    stop_windows_service,
)
from .status_labels import (
    COMMISSION_FILTERS,
    DEPOSITARY_STATUS,
    ORDER_STATUS_RATES,
    ORDER_STATUSES,
    is_depositary_status,
    is_legacy_depositary_6000_status,
    normalize_status_form_label,
    normalize_status_label,
)
from .updater import SessionNotice, UpdateCheckResult, UpdateChecker, UpdateInfo
from .version import APP_DEMO, APP_NAME, APP_VERSION

UI_FONT_FAMILY = "Poppins"
UI_FONT_SIZE = 11
UI_FONT = (UI_FONT_FAMILY, UI_FONT_SIZE)
APP_BACKGROUND = "#dfeaf4"
MODULE_BACKGROUND = "#eef3f8"
SURFACE_BACKGROUND = "#fff8ed"
SURFACE_ALT_BACKGROUND = "#eef3f8"
PRIMARY_COLOR = "#b22222"
PRIMARY_DARK_COLOR = "#8b0000"
ACCENT_COLOR = "#1f4e78"
ACCENT_DARK_COLOR = "#1b2d5d"
WARNING_COLOR = "#b36b00"
TEXT_COLOR = "#111827"
MUTED_TEXT_COLOR = "#5a6570"
SUCCESS_COLOR = "#2f5d3a"
DANGER_COLOR = "#8b0000"
BORDER_COLOR = "#c8d4df"
TABLE_SELECTED_COLOR = "#d9ecff"
OWNER_NAME = "Augustin Kayembe"
OWNER_PHONE = "+243 991 599 600"
OWNER_EMAIL_PRIMARY = "kayboxstore@gmail.com"
OWNER_EMAIL_SECONDARY = "kayboxstore@outlook.fr"
FORM_LOGO_SIZE = 68
DASHBOARD_LOGO_SIZE = 80
SETTINGS_LOGO_SIZE = 70
STOCK_DIALOG_LOGO_SIZE = 60
AUTO_LOCK_TIMEOUT_MS = 10 * 60 * 1000
AUTO_LOCK_EVENT_SEQUENCES = ("<KeyPress>", "<Button>", "<MouseWheel>", "<B1-Motion>")
NO_DEBT_PAYMENT_MESSAGE = "Personne n'a payé aujourd'hui parce qu'il n'y a pas de dettes accumulées."

_BRAND_IMAGE_CACHE: dict[tuple[str, int, int], ImageTk.PhotoImage] = {}


ROLES = [
    "Admin",
    "Directeur Général",
    "Caissier",
    "Chargé de la production",
    "Gestionnaire de stock",
    "Gestionnaire des commandes",
]
ROLE_MODULE_ACCESS = {
    "Admin": {"Caisse", "Stock", "Production", "Commandes", "Commissions", "Travailleurs", "Utilisateurs"},
    "Directeur Général": {"Caisse", "Stock", "Production", "Commandes", "Commissions", "Travailleurs", "Utilisateurs"},
    "Caissier": {"Caisse", "Production", "Commandes", "Commissions", "Travailleurs"},
    "Chargé de la production": {"Production"},
    "Gestionnaire de stock": {"Stock"},
    "Gestionnaire des commandes": {"Commandes", "Commissions"},
}
ROLE_READ_ONLY_MODULES = {
    "Directeur Général": {"Caisse", "Stock", "Production", "Commandes", "Commissions", "Travailleurs", "Utilisateurs"},
    "Caissier": {"Production", "Commandes", "Commissions"},
}

FULL_VISIBILITY_ROLES = {"Admin", "Directeur Général"}
CLOSURE_ROLES = {"Admin", "Directeur Général"}


def _package_root() -> Path:
    if getattr(sys, "frozen", False) and hasattr(sys, "_MEIPASS"):
        return Path(sys._MEIPASS) / "boulangerie_app"
    return Path(__file__).resolve().parent


def assets_dir() -> Path:
    return _package_root() / "assets"


def get_logo_png_path() -> Path:
    return assets_dir() / "logo-boulangerie-lomoto.png"


def get_logo_ico_path() -> Path:
    return assets_dir() / "logo-boulangerie-lomoto.ico"


def _load_logo_photo(size: int, opacity: int = 255) -> ImageTk.PhotoImage | None:
    logo_path = get_logo_png_path()
    if not logo_path.exists():
        return None

    normalized_size = max(size, 16)
    normalized_opacity = max(16, min(opacity, 255))
    cache_key = (str(logo_path), normalized_size, normalized_opacity)
    cached = _BRAND_IMAGE_CACHE.get(cache_key)
    if cached is not None:
        return cached

    image = Image.open(logo_path).convert("RGBA")
    image.thumbnail((normalized_size, normalized_size), Image.LANCZOS)
    if normalized_opacity < 255:
        alpha_channel = image.getchannel("A").point(
            lambda alpha: int(alpha * normalized_opacity / 255)
        )
        image.putalpha(alpha_channel)

    photo = ImageTk.PhotoImage(image)
    _BRAND_IMAGE_CACHE[cache_key] = photo
    return photo


def apply_window_icon(window: tk.Tk | tk.Toplevel) -> None:
    logo_icon = _load_logo_photo(48)
    if logo_icon is not None:
        try:
            window.iconphoto(True, logo_icon)
            setattr(window, "_brand_icon_image", logo_icon)
        except tk.TclError:
            pass

    if os.name != "nt":
        return

    logo_ico_path = get_logo_ico_path()
    if not logo_ico_path.exists():
        return

    try:
        window.iconbitmap(default=str(logo_ico_path))
    except tk.TclError:
        pass


def create_logo_widget(
    parent: tk.Misc,
    size: int,
    *,
    opacity: int = 255,
    background: str | None = None,
    use_ttk: bool = True,
) -> tk.Label | ttk.Label | None:
    logo_image = _load_logo_photo(size, opacity)
    if logo_image is None:
        return None

    if use_ttk:
        widget: tk.Label | ttk.Label = ttk.Label(parent, image=logo_image)
    else:
        widget = tk.Label(
            parent,
            image=logo_image,
            bg=background or APP_BACKGROUND,
            bd=0,
            highlightthickness=0,
        )
    setattr(widget, "_brand_image", logo_image)
    return widget


def create_branded_header(
    parent: tk.Misc,
    title: str,
    *,
    logo_size: int,
    wraplength: int = 780,
    bottom_padding: int = 12,
) -> ttk.Frame:
    header = ttk.Frame(parent)
    header.pack(fill="x", pady=(0, bottom_padding))
    header.columnconfigure(1, weight=1)

    logo = create_logo_widget(header, logo_size)
    spacer_width = max(logo_size + 14, 72) if logo is not None else 0
    if logo is not None:
        logo.grid(row=0, column=0, sticky="nw", padx=(0, 10))
        setattr(header, "_header_logo", logo)

    title_frame = ttk.Frame(header)
    title_frame.grid(row=0, column=1, sticky="ew")
    title_frame.columnconfigure(0, weight=1)
    ttk.Label(
        title_frame,
        text=title,
        style="Header.TLabel",
        justify="center",
        anchor="center",
        wraplength=wraplength,
    ).grid(row=0, column=0, sticky="ew")

    if spacer_width > 0:
        spacer = ttk.Frame(header, width=spacer_width)
        spacer.grid(row=0, column=2, sticky="nsew")
        spacer.grid_propagate(False)

    return header


def current_copyright_text() -> str:
    year = date.today().year
    return f"© {year} {APP_NAME} - {OWNER_NAME} / Kay Box Store. Tous droits réservés."


def copyright_legal_notice() -> str:
    return (
        "Application de gestion commerciale développée pour Boulangerie Lomoto. "
        "Toute reproduction, distribution ou modification non autorisée est interdite."
    )


class CopyrightFooter(ttk.Frame):
    REFRESH_INTERVAL_MS = 60 * 60 * 1000

    def __init__(self, parent: tk.Misc, *, wraplength: int = 900) -> None:
        super().__init__(parent)
        self.wraplength = wraplength
        self.text_var = tk.StringVar(value=self._build_text())
        ttk.Separator(self).pack(fill="x", pady=(6, 5))
        ttk.Label(
            self,
            textvariable=self.text_var,
            foreground=MUTED_TEXT_COLOR,
            justify="center",
            wraplength=self.wraplength,
        ).pack(fill="x")
        self.after(self.REFRESH_INTERVAL_MS, self.refresh_text)

    def _build_text(self) -> str:
        return f"{current_copyright_text()}\n{copyright_legal_notice()}"

    def refresh_text(self) -> None:
        self.text_var.set(self._build_text())
        self.after(self.REFRESH_INTERVAL_MS, self.refresh_text)


def add_copyright_footer(parent: tk.Misc, *, wraplength: int = 900) -> CopyrightFooter:
    return CopyrightFooter(parent, wraplength=wraplength)


class AboutWindow(tk.Toplevel):
    def __init__(self, parent: tk.Misc) -> None:
        owner = parent.winfo_toplevel()
        super().__init__(owner)
        self.title(f"À propos - {APP_NAME}")
        self.geometry("640x520")
        self.minsize(600, 480)
        self.configure(bg=APP_BACKGROUND)
        self.resizable(True, True)
        apply_window_icon(self)
        self.transient(owner)
        self.grab_set()
        self.protocol("WM_DELETE_WINDOW", self.close_window)
        self.build_ui()
        center_window(self)

    def build_ui(self) -> None:
        container = ttk.Frame(self, padding=(22, 18, 22, 18))
        container.pack(fill="both", expand=True)
        logo = create_logo_widget(container, 92)
        if logo is not None:
            logo.pack(anchor="center", pady=(0, 8))

        ttk.Label(
            container,
            text=APP_NAME.upper(),
            font=(UI_FONT_FAMILY, 24, "bold"),
            foreground=PRIMARY_COLOR,
            justify="center",
        ).pack(fill="x")
        ttk.Label(
            container,
            text=f"Version {APP_VERSION}",
            foreground=MUTED_TEXT_COLOR,
            justify="center",
        ).pack(fill="x", pady=(2, 14))

        description = (
            f"{OWNER_NAME} est le responsable de Kay Box Store et l'initiateur de cette solution. "
            "Cette application accompagne la gestion quotidienne de la boulangerie : ventes, commandes, "
            "stock, production, caisse, travailleurs, rapports et suivi des activités."
        )
        ttk.Label(
            container,
            text=description,
            wraplength=560,
            justify="center",
        ).pack(fill="x", pady=(0, 14))

        contact_frame = ttk.LabelFrame(container, text="Contact", style="Card.TLabelframe")
        contact_frame.pack(fill="x", pady=(0, 14))
        ttk.Label(contact_frame, text=f"Téléphone : {OWNER_PHONE}", justify="center").pack(fill="x", pady=2)
        ttk.Label(
            contact_frame,
            text=f"E-mails : {OWNER_EMAIL_PRIMARY} / {OWNER_EMAIL_SECONDARY}",
            justify="center",
            wraplength=520,
        ).pack(fill="x", pady=2)

        ttk.Label(
            container,
            text=f"{current_copyright_text()}\n{copyright_legal_notice()}",
            foreground=MUTED_TEXT_COLOR,
            wraplength=560,
            justify="center",
        ).pack(fill="x", pady=(0, 16))
        ttk.Button(container, text="Fermer", style="Primary.TButton", command=self.close_window).pack(anchor="center")

    def close_window(self) -> None:
        self.destroy()


def run_app() -> None:
    if os.name == "nt" and not is_running_as_administrator():
        if relaunch_current_process_as_administrator():
            return
        return

    setup_required = prepare_startup_connection()
    DatabaseHelper.initialize_database()
    post_update_notice = UpdateChecker.consume_post_update_notice()
    root = tk.Tk()
    root.title(f"{APP_NAME} - Connexion - v{APP_VERSION}")
    root.geometry("660x500")
    root.minsize(620, 470)
    root.configure(bg=APP_BACKGROUND)
    apply_window_icon(root)
    configure_styles()
    root.resizable(True, True)

    def show_login_after_setup() -> None:
        root.title(f"{APP_NAME} - Connexion - v{APP_VERSION}")
        root.geometry("660x500")
        LoginWindow(root, post_update_notice)
        center_window(root)

    if setup_required:
        root.title(f"{APP_NAME} - Première configuration - v{APP_VERSION}")
        root.geometry("720x650")
        FirstRunSetupWindow(root, show_login_after_setup)
    else:
        LoginWindow(root, post_update_notice)
    center_window(root)
    root.mainloop()


def prepare_startup_connection() -> bool:
    if APP_DEMO:
        DatabaseHelper.apply_connection_settings(ConnectionSettings(), persist=False)
        DatabaseHelper.initialize_local_database()
        return bool(DatabaseHelper.get_setup_status().get("required", False))

    candidates: list[ConnectionSettings] = []
    seen: set[str] = set()

    def add_candidate(settings: ConnectionSettings | None) -> None:
        if settings is None or not settings.is_remote():
            return
        url = settings.normalized_url()
        if url in seen:
            return
        seen.add(url)
        candidates.append(settings)

    if is_server_installation():
        service_status = get_windows_service_status()
        if service_status.installed and not service_status.is_running:
            try:
                start_windows_service()
            except Exception:
                pass
        host_settings = load_central_server_settings()
        for server_url in build_local_server_addresses(host_settings.normalized_port()):
            add_candidate(
                ConnectionSettings(
                    mode="remote",
                    server_url=server_url,
                    api_token=host_settings.normalized_token(),
                )
            )

    saved_settings = load_connection_settings(DatabaseHelper.app_data_dir)
    add_candidate(saved_settings)
    try:
        add_candidate(fetch_public_server_directory().to_connection_settings())
    except Exception:
        pass

    for settings in candidates:
        try:
            RemoteDatabaseClient(
                settings.normalized_url(),
                api_token=settings.api_token,
                timeout_seconds=3,
            ).ping()
            DatabaseHelper.apply_connection_settings(settings, persist=False)
            status = DatabaseHelper.get_setup_status()
            return bool(status.get("required", False)) and is_server_installation()
        except Exception:
            continue

    DatabaseHelper.apply_connection_settings(ConnectionSettings(), persist=False)
    return False


def configure_styles() -> None:
    style = ttk.Style()
    try:
        style.theme_use("clam")
    except tk.TclError:
        pass
    default_root = tk._default_root
    if default_root is not None:
        default_root.option_add("*Font", UI_FONT)
        default_root.option_add("*TCombobox*Listbox.font", UI_FONT)
        default_root.option_add("*Text.font", UI_FONT)
    style.configure(".", font=UI_FONT)
    style.configure("TLabel", font=UI_FONT)
    style.configure("TButton", font=UI_FONT)
    style.configure("TEntry", font=UI_FONT)
    style.configure("TCombobox", font=UI_FONT)
    style.configure("TCheckbutton", font=UI_FONT)
    style.configure("TRadiobutton", font=UI_FONT)
    style.configure("TSpinbox", font=UI_FONT)
    style.configure("Treeview", font=UI_FONT, rowheight=28)
    style.configure("Treeview.Heading", font=(UI_FONT_FAMILY, UI_FONT_SIZE, "bold"))
    style.configure("Header.TLabel", font=(UI_FONT_FAMILY, 44, "bold"), foreground="#B30000")
    style.configure("DayLock.TLabel", font=(UI_FONT_FAMILY, UI_FONT_SIZE, "bold"), foreground="#8b0000")
    style.configure("Card.TLabelframe", padding=8)
    style.configure("Card.TLabelframe.Label", font=(UI_FONT_FAMILY, UI_FONT_SIZE, "bold"))
    style.configure("Primary.TButton", padding=(12, 8))


def today_iso() -> str:
    return date.today().strftime("%Y-%m-%d")


def tomorrow_iso() -> str:
    return (date.today() + timedelta(days=1)).strftime("%Y-%m-%d")


def parse_date(value: str) -> date:
    text = value.strip()
    for fmt in ("%Y-%m-%d", "%d/%m/%Y"):
        try:
            return datetime.strptime(text, fmt).date()
        except ValueError:
            continue
    raise ValueError("Date invalide. Utilisez AAAA-MM-JJ ou JJ/MM/AAAA.")


def parse_float(value: str, field_name: str) -> float:
    text = value.strip().replace(" ", "").replace(",", ".")
    if not text:
        raise ValueError(f"Veuillez renseigner le champ « {field_name} ».")
    return float(text)


def parse_optional_float(value: str) -> float:
    text = value.strip().replace(" ", "").replace(",", ".")
    if not text:
        return 0.0
    return float(text)


def format_fc(value: float) -> str:
    return f"{value:,.0f}".replace(",", " ") + " FC"


def format_number(value: float) -> str:
    if abs(value - int(value)) < 1e-9:
        return f"{int(value)}"
    return f"{value:.2f}".rstrip("0").rstrip(".")


def format_file_size(value: int | float) -> str:
    size = float(value)
    units = ["o", "Ko", "Mo", "Go"]
    unit_index = 0
    while size >= 1024 and unit_index < len(units) - 1:
        size /= 1024
        unit_index += 1
    if unit_index == 0:
        return f"{int(size)} {units[unit_index]}"
    return f"{size:.1f} {units[unit_index]}"


def describe_latest_automatic_backup(data_dir: Path) -> str:
    backup_dir = Path(data_dir) / "sauvegardes"
    try:
        backup_files = sorted(
            backup_dir.glob(f"{AUTO_BACKUP_PREFIX}-*.db"),
            key=lambda path: path.stat().st_mtime,
            reverse=True,
        )
    except OSError:
        backup_files = []

    if not backup_files:
        return "Sauvegarde automatique : en attente de la première sauvegarde quotidienne."

    latest_backup = backup_files[0]
    try:
        stat = latest_backup.stat()
    except OSError:
        return "Sauvegarde automatique : dernière sauvegarde momentanément illisible."

    modified_at = datetime.fromtimestamp(stat.st_mtime).strftime("%d/%m/%Y %H:%M")
    return (
        "Sauvegarde automatique : "
        f"{latest_backup.name} | {modified_at} | {format_file_size(stat.st_size)}"
    )


def compact_multiline_text(value: Any) -> str:
    if value is None:
        return ""
    parts = [line.strip() for line in str(value).splitlines() if line.strip()]
    return " | ".join(parts)


def _measure_window_size(window: tk.Misc) -> tuple[int, int]:
    width = window.winfo_width()
    height = window.winfo_height()

    if width > 1 and height > 1:
        return width, height

    geometry = str(window.winfo_geometry()).split("+")[0]
    if "x" in geometry:
        width_text, height_text = geometry.split("x", 1)
        try:
            return int(width_text), int(height_text)
        except ValueError:
            pass

    return window.winfo_reqwidth(), window.winfo_reqheight()


def _measure_requested_content_size(window: tk.Misc) -> tuple[int, int]:
    scrollable_content = getattr(window, "scrollable_content", None)
    content = getattr(scrollable_content, "content", None)
    footer = getattr(window, "fixed_footer", None)
    if content is not None:
        content.update_idletasks()
        requested_width = content.winfo_reqwidth()
        requested_height = content.winfo_reqheight()
    else:
        requested_width = window.winfo_reqwidth()
        requested_height = window.winfo_reqheight()

    if footer is not None:
        footer.update_idletasks()
        requested_width = max(requested_width, footer.winfo_reqwidth())
        requested_height += footer.winfo_reqheight()

    return requested_width, requested_height


def get_work_area_geometry(window: tk.Misc) -> tuple[int, int, int, int]:
    """Return the visible desktop area, excluding the Windows taskbar when available."""
    screen_width = window.winfo_screenwidth()
    screen_height = window.winfo_screenheight()
    if os.name != "nt":
        return 0, 0, screen_width, screen_height

    try:
        import ctypes

        class RECT(ctypes.Structure):
            _fields_ = [
                ("left", ctypes.c_long),
                ("top", ctypes.c_long),
                ("right", ctypes.c_long),
                ("bottom", ctypes.c_long),
            ]

        rect = RECT()
        spi_get_work_area = 0x0030
        if ctypes.windll.user32.SystemParametersInfoW(spi_get_work_area, 0, ctypes.byref(rect), 0):
            width = max(int(rect.right - rect.left), 320)
            height = max(int(rect.bottom - rect.top), 240)
            return int(rect.left), int(rect.top), width, height
    except Exception:
        pass

    return 0, 0, screen_width, screen_height


def center_window(window: tk.Misc) -> None:
    window.update_idletasks()
    width, height = _measure_window_size(window)

    requested_width, requested_height = _measure_requested_content_size(window)
    required_width = requested_width + 24
    required_height = requested_height + 36
    work_x, work_y, work_width, work_height = get_work_area_geometry(window)
    max_width = max(int(work_width * 0.96), 320)
    max_height = max(int(work_height * 0.94), 240)

    width = min(max(width, required_width), max_width)
    height = min(max(height, required_height), max_height)

    x = work_x + max((work_width - width) // 2, 0)
    y = work_y + max((work_height - height) // 2, 0)
    window.geometry(f"{width}x{height}+{x}+{y}")
    if hasattr(window, "minsize"):
        window.minsize(width, height)


def fit_window_to_work_area(
    window: tk.Misc,
    preferred_width: int,
    preferred_height: int,
    *,
    min_width: int = 640,
    min_height: int = 420,
    margin: int = 10,
) -> None:
    """Keep a dialog entirely inside the visible desktop, above the taskbar."""
    window.update_idletasks()
    work_x, work_y, work_width, work_height = get_work_area_geometry(window)
    available_width = max(work_width - (margin * 2), 320)
    available_height = max(work_height - (margin * 2), 240)
    requested_width, requested_height = _measure_requested_content_size(window)

    width = min(max(preferred_width, requested_width + 24, min_width), available_width)
    height = min(max(preferred_height, min_height), available_height)
    x = work_x + max((work_width - width) // 2, margin)
    y = work_y + max((work_height - height) // 2, margin)

    window.geometry(f"{width}x{height}+{x}+{y}")
    if hasattr(window, "minsize"):
        window.minsize(min(min_width, width), min(min_height, height))
    if hasattr(window, "maxsize"):
        window.maxsize(available_width, available_height)


def maximize_window(window: tk.Misc, min_width: int = 760, min_height: int = 520) -> None:
    window.update_idletasks()
    work_x, work_y, work_width, work_height = get_work_area_geometry(window)
    requested_width, requested_height = _measure_requested_content_size(window)
    safe_min_width = max(min_width, min(requested_width + 24, work_width))
    safe_min_height = max(min_height, min(requested_height + 36, work_height))
    if hasattr(window, "minsize"):
        window.minsize(safe_min_width, safe_min_height)

    try:
        if os.name == "nt":
            window.state("zoomed")
            return
        window.attributes("-zoomed", True)
        return
    except tk.TclError:
        pass

    window.geometry(f"{work_width}x{work_height}+{work_x}+{work_y}")


def restore_maximized_window(window: tk.Misc, min_width: int = 760, min_height: int = 520) -> None:
    if not window.winfo_exists():
        return
    try:
        window.deiconify()
        window.state("normal")
    except tk.TclError:
        pass
    work_x, work_y, work_width, work_height = get_work_area_geometry(window)
    try:
        window.geometry(f"{work_width}x{work_height}+{work_x}+{work_y}")
        window.update_idletasks()
    except tk.TclError:
        return
    maximize_window(window, min_width, min_height)
    window.lift()
    try:
        window.focus_force()
    except tk.TclError:
        pass


def deferred_ui_command(widget: tk.Misc, callback: Callable[[], None], delay_ms: int = 0) -> Callable[[], None]:
    def wrapper() -> None:
        try:
            widget.update_idletasks()
        except tk.TclError:
            return
        widget.after(delay_ms, callback)

    return wrapper



def open_folder(target_path: str | Path) -> None:
    path = Path(target_path)
    path.mkdir(parents=True, exist_ok=True)
    if hasattr(os, "startfile"):
        os.startfile(str(path))
        return
    webbrowser.open(path.as_uri())


def open_file(target_path: str | Path) -> None:
    path = Path(target_path)
    if hasattr(os, "startfile"):
        os.startfile(str(path))
        return
    webbrowser.open(path.as_uri())


def email_delivery_message(result: dict[str, Any] | None) -> str:
    if not isinstance(result, dict):
        return ""
    sent = int(result.get("sent", 0) or 0)
    failed = int(result.get("failed", 0) or 0)
    pending = int(result.get("pending", 0) or 0)
    configuration_required = bool(result.get("configurationRequired", 0))
    if sent:
        return f" Notification e-mail envoyée ({sent})."
    if configuration_required and pending:
        return " Notification e-mail en attente : configurez le service e-mail dans Utilisateurs."
    if failed:
        return " Notification e-mail non envoyée : consultez les notifications e-mail."
    if pending:
        return " Notification e-mail en attente."
    return ""


def process_email_notifications_for_ui(limit: int = 20) -> str:
    try:
        return email_delivery_message(DatabaseHelper.process_pending_email_notifications(limit))
    except Exception as exc:
        return f" Notification e-mail non traitée : {exc}"


def resolve_dashboard_user(widget: tk.Misc) -> AuthenticatedUser | None:
    current: Any = widget
    while current is not None:
        user = getattr(current, "user", None)
        if isinstance(user, AuthenticatedUser):
            return user
        current = getattr(current, "parent", None)
    return None


def log_user_action(widget: tk.Misc, module: str, action: str, details: str = "") -> None:
    user = resolve_dashboard_user(widget)
    if user is None:
        return
    try:
        DatabaseHelper.log_activity(
            user.identifiant,
            user.display_name,
            user.role,
            module,
            action,
            details,
        )
    except Exception:
        return


def is_remote_method_not_authorized_error(exc: Exception) -> bool:
    if not isinstance(exc, RemoteDatabaseError):
        return False
    message = str(exc).lower()
    return (
        "méthode distante non autorisée" in message
        or "methode distante non autorisee" in message
        or "non autorisée" in message
        or "non autorisee" in message
    )


def format_activity_timestamp(value: Any) -> str:
    raw = str(value or "").strip()
    if not raw:
        return ""
    try:
        return datetime.fromisoformat(raw).strftime("%d/%m/%Y %H:%M:%S")
    except ValueError:
        return raw


def build_day_lock_notice(target_date: date, closure: dict[str, Any], module_label: str) -> str:
    closed_by = str(closure.get("NomComplet") or closure.get("Identifiant") or "Administrateur").strip()
    role = str(closure.get("Role") or "").strip()
    closed_at = format_activity_timestamp(closure.get("DateCloture"))
    actor = f"{closed_by} ({role})" if role else closed_by
    closed_at_text = f" le {closed_at}" if closed_at else ""
    return (
        f"Journée clôturée - {target_date.strftime('%d/%m/%Y')}. "
        f"Clôturée par {actor}{closed_at_text}. "
        f"Les enregistrements, modifications et suppressions de {module_label} sont verrouillés."
    )


class DateField(ttk.Frame):
    def __init__(self, parent: tk.Misc, initial: str | None = None, *, allow_future: bool = False) -> None:
        super().__init__(parent)
        self.allow_future = allow_future
        self.var = tk.StringVar(value=initial or today_iso())
        self.entry = ttk.Entry(self, textvariable=self.var, width=14)
        self.entry.grid(row=0, column=0, sticky="ew")
        self.pick_button = ttk.Button(self, text="Choisir", command=self.open_picker)
        self.pick_button.grid(row=0, column=1, padx=(6, 0))
        self.button = ttk.Button(self, text="Aujourd'hui", command=self.set_today)
        self.button.grid(row=0, column=2, padx=(6, 0))
        self.columnconfigure(0, weight=1)
        self._callbacks: list[Callable[[], None]] = []
        self.entry.bind("<FocusOut>", lambda _event: self._notify())
        self.entry.bind("<Return>", lambda _event: self._notify())

    def bind_change(self, callback: Callable[[], None]) -> None:
        self._callbacks.append(callback)

    def _notify(self) -> None:
        for callback in self._callbacks:
            callback()

    def set_today(self) -> None:
        self.var.set(today_iso())
        self._notify()

    def open_picker(self) -> None:
        try:
            selected_date = self.get_date()
        except ValueError:
            selected_date = date.today()

        picker = tk.Toplevel(self)
        picker.title("Choisir une date")
        picker.resizable(False, False)
        picker.transient(self.winfo_toplevel())
        picker.grab_set()
        apply_window_icon(picker)

        year_var = tk.IntVar(value=selected_date.year)
        month_var = tk.IntVar(value=selected_date.month)
        header = ttk.Frame(picker, padding=10)
        header.pack(fill="x")
        ttk.Spinbox(
            header,
            from_=2000,
            to=2100 if self.allow_future else date.today().year,
            textvariable=year_var,
            width=7,
        ).grid(row=0, column=0, padx=4)
        ttk.Combobox(
            header,
            textvariable=month_var,
            values=list(range(1, 13)),
            state="readonly",
            width=5,
        ).grid(row=0, column=1, padx=4)
        days_frame = ttk.Frame(picker, padding=(10, 0, 10, 10))
        days_frame.pack()

        def select_day(day: int) -> None:
            self.var.set(date(int(year_var.get()), int(month_var.get()), day).strftime("%Y-%m-%d"))
            self._notify()
            picker.destroy()

        def render_days(*_args: Any) -> None:
            for child in days_frame.winfo_children():
                child.destroy()
            for column, label in enumerate(("Lun", "Mar", "Mer", "Jeu", "Ven", "Sam", "Dim")):
                ttk.Label(days_frame, text=label, anchor="center").grid(row=0, column=column, padx=2, pady=2)
            month_days = calendar.monthcalendar(int(year_var.get()), int(month_var.get()))
            for row_index, week in enumerate(month_days, start=1):
                for column, day_number in enumerate(week):
                    if day_number == 0:
                        ttk.Label(days_frame, text="").grid(row=row_index, column=column, padx=2, pady=2)
                        continue
                    candidate_date = date(int(year_var.get()), int(month_var.get()), day_number)
                    day_button = ttk.Button(
                        days_frame,
                        text=str(day_number),
                        width=4,
                        command=lambda value=day_number: select_day(value),
                    )
                    day_button.grid(row=row_index, column=column, padx=2, pady=2)
                    if not self.allow_future and candidate_date > date.today():
                        day_button.state(["disabled"])

        year_var.trace_add("write", render_days)
        month_var.trace_add("write", render_days)
        render_days()
        center_window(picker)

    def get_date(self) -> date:
        selected = parse_date(self.var.get())
        if not self.allow_future and selected > date.today():
            raise ValueError("Une date future ne peut pas être utilisée pour cet enregistrement.")
        return selected

    def set_date(self, value: date | str) -> None:
        if isinstance(value, date):
            self.var.set(value.strftime("%Y-%m-%d"))
        else:
            self.var.set(value)

    def get(self) -> str:
        return self.var.get()

    def set_enabled(self, enabled: bool) -> None:
        state = "normal" if enabled else "disabled"
        self.entry.configure(state=state)
        self.pick_button.state(["!disabled"] if enabled else ["disabled"])
        self.button.state(["!disabled"] if enabled else ["disabled"])


class DataTable(ttk.Frame):
    _TOUCH_SCROLL_THRESHOLD = 8
    _TOUCH_SCROLL_PIXELS_PER_UNIT = 18

    def __init__(self, parent: tk.Misc, height: int = 12) -> None:
        super().__init__(parent)
        self.tree = ttk.Treeview(self, show="headings", height=height, selectmode="browse")
        y_scroll = ttk.Scrollbar(self, orient="vertical", command=self.tree.yview)
        x_scroll = ttk.Scrollbar(self, orient="horizontal", command=self.tree.xview)
        self.tree.configure(yscrollcommand=y_scroll.set, xscrollcommand=x_scroll.set)
        self.tree.grid(row=0, column=0, sticky="nsew")
        y_scroll.grid(row=0, column=1, sticky="ns")
        x_scroll.grid(row=1, column=0, sticky="ew")
        self.columnconfigure(0, weight=1)
        self.rowconfigure(0, weight=1)
        self.rows_by_item: dict[str, dict[str, Any]] = {}
        self._touch_scroll_active = False
        self._touch_scroll_dragging = False
        self._touch_start_x_root = 0
        self._touch_start_y_root = 0
        self._touch_last_x_root = 0
        self._touch_last_y_root = 0
        self._touch_x_remainder = 0
        self._touch_y_remainder = 0
        self.tree.bind("<MouseWheel>", self._on_mousewheel, add="+")
        self.tree.bind("<Shift-MouseWheel>", self._on_shift_mousewheel, add="+")
        self.tree.bind("<ButtonPress-1>", self._on_touch_press, add="+")
        self.tree.bind("<B1-Motion>", self._on_touch_motion, add="+")
        self.tree.bind("<ButtonRelease-1>", self._on_touch_release, add="+")

    def set_data(
        self,
        rows: list[dict[str, Any]],
        columns: list[str],
        headings: dict[str, str] | None = None,
        hidden_columns: list[str] | None = None,
        formatters: dict[str, Callable[[Any], Any]] | None = None,
    ) -> None:
        headings = headings or {}
        hidden_columns = hidden_columns or []
        formatters = formatters or {}
        self.tree.delete(*self.tree.get_children())
        self.tree["columns"] = columns
        self.tree["displaycolumns"] = [col for col in columns if col not in hidden_columns]
        self.rows_by_item.clear()

        for column in columns:
            self.tree.heading(column, text=headings.get(column, column), anchor="w")
            self.tree.column(column, anchor="w", width=110, stretch=True)

        for index, row in enumerate(rows):
            item_id = f"row-{index}"
            values = []
            for column in columns:
                value = row.get(column, "")
                formatter = formatters.get(column)
                values.append(formatter(value) if formatter else value)
            self.tree.insert("", "end", iid=item_id, values=values)
            self.rows_by_item[item_id] = row

    def selected_row(self) -> dict[str, Any] | None:
        selection = self.tree.selection()
        if not selection:
            return None
        return self.rows_by_item.get(selection[0])

    def _normalize_wheel_units(self, delta: int) -> int:
        if delta == 0:
            return 0
        if delta % 120 == 0:
            return -1 * int(delta / 120)
        return -1 if delta > 0 else 1

    def _on_mousewheel(self, event: tk.Event[tk.Misc]) -> str | None:
        delta = int(getattr(event, "delta", 0) or 0)
        units = self._normalize_wheel_units(delta)
        if units == 0:
            return None
        self.tree.yview_scroll(units, "units")
        return "break"

    def _on_shift_mousewheel(self, event: tk.Event[tk.Misc]) -> str | None:
        delta = int(getattr(event, "delta", 0) or 0)
        units = self._normalize_wheel_units(delta)
        if units == 0:
            return None
        self.tree.xview_scroll(units, "units")
        return "break"

    def _on_touch_press(self, event: tk.Event[tk.Misc]) -> str | None:
        region = self.tree.identify_region(int(getattr(event, "x", 0)), int(getattr(event, "y", 0)))
        if region in {"heading", "separator"}:
            self._reset_touch_scroll()
            return None
        self._touch_scroll_active = True
        self._touch_scroll_dragging = False
        self._touch_start_x_root = int(getattr(event, "x_root", 0) or 0)
        self._touch_start_y_root = int(getattr(event, "y_root", 0) or 0)
        self._touch_last_x_root = self._touch_start_x_root
        self._touch_last_y_root = self._touch_start_y_root
        self._touch_x_remainder = 0
        self._touch_y_remainder = 0
        return None

    def _on_touch_motion(self, event: tk.Event[tk.Misc]) -> str | None:
        if not self._touch_scroll_active:
            return None
        current_x = int(getattr(event, "x_root", 0) or 0)
        current_y = int(getattr(event, "y_root", 0) or 0)
        total_dx = current_x - self._touch_start_x_root
        total_dy = current_y - self._touch_start_y_root
        if not self._touch_scroll_dragging:
            if max(abs(total_dx), abs(total_dy)) < self._TOUCH_SCROLL_THRESHOLD:
                return None
            self._touch_scroll_dragging = True

        dx = current_x - self._touch_last_x_root
        dy = current_y - self._touch_last_y_root
        self._touch_last_x_root = current_x
        self._touch_last_y_root = current_y
        self._scroll_from_touch_delta(dx, dy)
        return "break"

    def _on_touch_release(self, _event: tk.Event[tk.Misc]) -> str | None:
        was_dragging = self._touch_scroll_dragging
        self._reset_touch_scroll()
        return "break" if was_dragging else None

    def _reset_touch_scroll(self) -> None:
        self._touch_scroll_active = False
        self._touch_scroll_dragging = False
        self._touch_x_remainder = 0
        self._touch_y_remainder = 0

    def _scroll_from_touch_delta(self, dx: int, dy: int) -> None:
        self._touch_y_remainder += dy
        y_units = int(self._touch_y_remainder / self._TOUCH_SCROLL_PIXELS_PER_UNIT)
        if y_units:
            self.tree.yview_scroll(-y_units, "units")
            self._touch_y_remainder -= y_units * self._TOUCH_SCROLL_PIXELS_PER_UNIT

        self._touch_x_remainder += dx
        x_units = int(self._touch_x_remainder / self._TOUCH_SCROLL_PIXELS_PER_UNIT)
        if x_units:
            self.tree.xview_scroll(-x_units, "units")
            self._touch_x_remainder -= x_units * self._TOUCH_SCROLL_PIXELS_PER_UNIT


class ScrollableContent(ttk.Frame):
    _mousewheel_bindings_ready = False
    _touch_bindings_ready = False
    _active_touch_owner: "ScrollableContent | None" = None
    _TOUCH_SCROLL_THRESHOLD = 8
    _TOUCH_SCROLL_BLOCKED_CLASSES = {
        "Button",
        "Checkbutton",
        "Combobox",
        "Entry",
        "Listbox",
        "Radiobutton",
        "Scale",
        "Scrollbar",
        "Spinbox",
        "TButton",
        "TCheckbutton",
        "TCombobox",
        "TEntry",
        "Treeview",
        "TRadiobutton",
        "TScale",
        "TScrollbar",
        "TSpinbox",
        "Text",
    }

    def __init__(
        self,
        parent: tk.Misc,
        padding: int | tuple[int, int, int, int] = 0,
        background: str | None = None,
    ) -> None:
        super().__init__(parent)
        canvas_background = background
        if canvas_background is None:
            try:
                canvas_background = str(parent.cget("bg"))
            except tk.TclError:
                canvas_background = "#eef3f8"

        self.canvas = tk.Canvas(
            self,
            highlightthickness=0,
            borderwidth=0,
            background=canvas_background,
        )
        self.vertical_scrollbar = ttk.Scrollbar(self, orient="vertical", command=self.canvas.yview)
        self.horizontal_scrollbar = ttk.Scrollbar(self, orient="horizontal", command=self.canvas.xview)
        self.canvas.configure(
            yscrollcommand=self._sync_vertical_scrollbar,
            xscrollcommand=self._sync_horizontal_scrollbar,
        )

        self.canvas.grid(row=0, column=0, sticky="nsew")
        self.vertical_scrollbar.grid(row=0, column=1, sticky="ns")
        self.horizontal_scrollbar.grid(row=1, column=0, sticky="ew")
        self.columnconfigure(0, weight=1)
        self.rowconfigure(0, weight=1)

        self.content = ttk.Frame(self.canvas, padding=padding)
        self._content_window = self.canvas.create_window((0, 0), window=self.content, anchor="nw")
        self._touch_scroll_active = False
        self._touch_scroll_dragging = False
        self._touch_start_x_root = 0
        self._touch_start_y_root = 0
        setattr(self, "_scrollable_owner", self)
        setattr(self.canvas, "_scrollable_owner", self)
        setattr(self.content, "_scrollable_owner", self)

        self.content.bind("<Configure>", self._on_content_configure)
        self.canvas.bind("<Configure>", self._on_canvas_configure)
        self._install_global_mousewheel_bindings()
        self.after_idle(self._refresh_scroll_region)

    def _install_global_mousewheel_bindings(self) -> None:
        root = self.winfo_toplevel()
        if not ScrollableContent._mousewheel_bindings_ready:
            root.bind_all("<MouseWheel>", ScrollableContent._dispatch_mousewheel, add="+")
            root.bind_all("<Shift-MouseWheel>", ScrollableContent._dispatch_shift_mousewheel, add="+")
            ScrollableContent._mousewheel_bindings_ready = True
        if not ScrollableContent._touch_bindings_ready:
            root.bind_all("<ButtonPress-1>", ScrollableContent._dispatch_touch_press, add="+")
            root.bind_all("<B1-Motion>", ScrollableContent._dispatch_touch_motion, add="+")
            root.bind_all("<ButtonRelease-1>", ScrollableContent._dispatch_touch_release, add="+")
            ScrollableContent._touch_bindings_ready = True

    def _on_content_configure(self, _event: tk.Event[tk.Misc]) -> None:
        self._refresh_scroll_region()

    def _on_canvas_configure(self, event: tk.Event[tk.Misc]) -> None:
        requested_width = self.content.winfo_reqwidth()
        target_width = event.width if requested_width <= event.width else requested_width
        self.canvas.itemconfigure(self._content_window, width=target_width)
        self._refresh_scroll_region()

    def _refresh_scroll_region(self) -> None:
        self.canvas.update_idletasks()
        bbox = self.canvas.bbox(self._content_window)
        if bbox is not None:
            self.canvas.configure(scrollregion=bbox)

    def _sync_vertical_scrollbar(self, first: str, last: str) -> None:
        self.vertical_scrollbar.set(first, last)
        if float(first) <= 0.0 and float(last) >= 1.0:
            self.vertical_scrollbar.grid_remove()
        else:
            self.vertical_scrollbar.grid()

    def _sync_horizontal_scrollbar(self, first: str, last: str) -> None:
        self.horizontal_scrollbar.set(first, last)
        if float(first) <= 0.0 and float(last) >= 1.0:
            self.horizontal_scrollbar.grid_remove()
        else:
            self.horizontal_scrollbar.grid()

    @staticmethod
    def _dispatch_mousewheel(event: tk.Event[tk.Misc]) -> str | None:
        owner = ScrollableContent._resolve_owner_from_event(event)
        if owner is None:
            return None
        return owner._on_mousewheel(event)

    @staticmethod
    def _dispatch_shift_mousewheel(event: tk.Event[tk.Misc]) -> str | None:
        owner = ScrollableContent._resolve_owner_from_event(event)
        if owner is None:
            return None
        return owner._on_shift_mousewheel(event)

    @staticmethod
    def _dispatch_touch_press(event: tk.Event[tk.Misc]) -> str | None:
        owner = ScrollableContent._resolve_owner_from_event(event)
        if owner is None or not owner._can_start_touch_scroll(event):
            ScrollableContent._active_touch_owner = None
            return None
        ScrollableContent._active_touch_owner = owner
        owner._begin_touch_scroll(event)
        return None

    @staticmethod
    def _dispatch_touch_motion(event: tk.Event[tk.Misc]) -> str | None:
        owner = ScrollableContent._active_touch_owner
        if owner is None:
            return None
        return owner._on_touch_motion(event)

    @staticmethod
    def _dispatch_touch_release(_event: tk.Event[tk.Misc]) -> str | None:
        owner = ScrollableContent._active_touch_owner
        ScrollableContent._active_touch_owner = None
        if owner is None:
            return None
        return owner._on_touch_release()

    @staticmethod
    def _resolve_owner_from_event(event: tk.Event[tk.Misc]) -> "ScrollableContent | None":
        widget = getattr(event, "widget", None)
        if widget is None:
            return None
        try:
            current: tk.Misc | None = widget.winfo_containing(event.x_root, event.y_root)
        except tk.TclError:
            current = widget
        while current is not None:
            owner = getattr(current, "_scrollable_owner", None)
            if isinstance(owner, ScrollableContent):
                return owner
            try:
                parent_name = current.winfo_parent()
            except tk.TclError:
                return None
            if not parent_name:
                return None
            try:
                current = current.nametowidget(parent_name)
            except KeyError:
                return None
        return None

    def _normalize_wheel_units(self, delta: int) -> int:
        if delta == 0:
            return 0
        if delta % 120 == 0:
            return -1 * int(delta / 120)
        return -1 if delta > 0 else 1

    def _on_mousewheel(self, event: tk.Event[tk.Misc]) -> str | None:
        if not self.vertical_scrollbar.winfo_ismapped():
            return None
        delta = int(getattr(event, "delta", 0) or 0)
        units = self._normalize_wheel_units(delta)
        if units == 0:
            return None
        self.canvas.yview_scroll(units, "units")
        return "break"

    def _on_shift_mousewheel(self, event: tk.Event[tk.Misc]) -> str | None:
        if not self.horizontal_scrollbar.winfo_ismapped():
            return None
        delta = int(getattr(event, "delta", 0) or 0)
        units = self._normalize_wheel_units(delta)
        if units == 0:
            return None
        self.canvas.xview_scroll(units, "units")
        return "break"

    def _can_start_touch_scroll(self, event: tk.Event[tk.Misc]) -> bool:
        if not self.vertical_scrollbar.winfo_ismapped() and not self.horizontal_scrollbar.winfo_ismapped():
            return False
        widget = getattr(event, "widget", None)
        if widget is None:
            return False
        return not self._is_interactive_touch_widget(widget)

    def _is_interactive_touch_widget(self, widget: tk.Misc) -> bool:
        current: tk.Misc | None = widget
        while current is not None:
            owner = getattr(current, "_scrollable_owner", None)
            if isinstance(owner, ScrollableContent):
                return False
            try:
                widget_class = current.winfo_class()
            except tk.TclError:
                return False
            if widget_class in self._TOUCH_SCROLL_BLOCKED_CLASSES:
                return True
            try:
                parent_name = current.winfo_parent()
            except tk.TclError:
                return False
            if not parent_name:
                return False
            try:
                current = current.nametowidget(parent_name)
            except KeyError:
                return False
        return False

    def _begin_touch_scroll(self, event: tk.Event[tk.Misc]) -> None:
        self._touch_scroll_active = True
        self._touch_scroll_dragging = False
        self._touch_start_x_root = int(getattr(event, "x_root", 0) or 0)
        self._touch_start_y_root = int(getattr(event, "y_root", 0) or 0)
        self.canvas.scan_mark(*self._event_canvas_coordinates(event))

    def _on_touch_motion(self, event: tk.Event[tk.Misc]) -> str | None:
        if not self._touch_scroll_active:
            return None
        current_x = int(getattr(event, "x_root", 0) or 0)
        current_y = int(getattr(event, "y_root", 0) or 0)
        dx = current_x - self._touch_start_x_root
        dy = current_y - self._touch_start_y_root
        if not self._touch_scroll_dragging:
            if max(abs(dx), abs(dy)) < self._TOUCH_SCROLL_THRESHOLD:
                return None
            self._touch_scroll_dragging = True
        self.canvas.scan_dragto(*self._event_canvas_coordinates(event), gain=1)
        return "break"

    def _on_touch_release(self) -> str | None:
        was_dragging = self._touch_scroll_dragging
        self._touch_scroll_active = False
        self._touch_scroll_dragging = False
        return "break" if was_dragging else None

    def _event_canvas_coordinates(self, event: tk.Event[tk.Misc]) -> tuple[int, int]:
        x_root = int(getattr(event, "x_root", 0) or 0)
        y_root = int(getattr(event, "y_root", 0) or 0)
        return x_root - self.canvas.winfo_rootx(), y_root - self.canvas.winfo_rooty()


class FirstRunSetupWindow(ttk.Frame):
    def __init__(self, root: tk.Tk, on_complete: Callable[[], None]) -> None:
        super().__init__(root, padding=20)
        self.root = root
        self.on_complete = on_complete
        self.full_name_var = tk.StringVar()
        self.email_var = tk.StringVar()
        self.identifiant_var = tk.StringVar()
        self.password_var = tk.StringVar()
        self.confirm_var = tk.StringVar()
        self.message_var = tk.StringVar()
        self.pack(fill="both", expand=True)
        self.build_ui()

    def build_ui(self) -> None:
        card = ttk.LabelFrame(self, text="Première configuration", style="Card.TLabelframe", padding=20)
        card.pack(anchor="n", fill="x", pady=(10, 0))
        logo = create_logo_widget(card, 90)
        if logo is not None:
            logo.grid(row=0, column=0, columnspan=2, pady=(0, 8))
        ttk.Label(card, text="Créer l'administrateur", style="Header.TLabel").grid(
            row=1, column=0, columnspan=2, pady=(0, 8)
        )
        ttk.Label(
            card,
            text=(
                "Ce compte sera le premier administrateur. Il pourra configurer les utilisateurs, "
                "les accès, les sauvegardes et le serveur."
            ),
            wraplength=560,
            justify="center",
        ).grid(row=2, column=0, columnspan=2, pady=(0, 16))

        fields = (
            ("Nom complet", self.full_name_var, ""),
            ("Adresse e-mail", self.email_var, ""),
            ("Identifiant", self.identifiant_var, ""),
            ("Mot de passe", self.password_var, "*"),
            ("Confirmation", self.confirm_var, "*"),
        )
        first_entry: ttk.Entry | None = None
        for index, (label, variable, mask) in enumerate(fields, start=3):
            ttk.Label(card, text=label).grid(row=index, column=0, sticky="w", pady=6)
            entry = ttk.Entry(card, textvariable=variable, show=mask, width=38)
            entry.grid(row=index, column=1, sticky="ew", pady=6)
            if first_entry is None:
                first_entry = entry

        ttk.Label(
            card,
            textvariable=self.message_var,
            foreground=DANGER_COLOR,
            wraplength=520,
            justify="center",
        ).grid(row=8, column=0, columnspan=2, sticky="ew", pady=(10, 0))
        ttk.Button(
            card,
            text="Terminer la configuration",
            style="Primary.TButton",
            command=self.save,
        ).grid(row=9, column=0, columnspan=2, pady=(16, 0))
        card.columnconfigure(1, weight=1)
        if first_entry is not None:
            first_entry.focus()

    def save(self) -> None:
        password = self.password_var.get()
        if password != self.confirm_var.get():
            self.message_var.set("La confirmation ne correspond pas au mot de passe.")
            return
        try:
            DatabaseHelper.create_initial_admin(
                self.full_name_var.get(),
                self.identifiant_var.get(),
                self.email_var.get(),
                password,
            )
        except Exception as exc:
            self.message_var.set(str(exc))
            return
        self.destroy()
        self.on_complete()


class LoginWindow(ttk.Frame):
    def __init__(self, root: tk.Tk, post_update_notice: SessionNotice | None = None) -> None:
        super().__init__(root, padding=(18, 8, 18, 18))
        self.root = root
        self.post_update_notice = post_update_notice
        self.notice_label: ttk.Label | None = None
        self.watermark_label: ttk.Label | None = None
        self.discovery_queue: Queue[tuple[str, Any, bool]] = Queue()
        self.discovery_in_progress = False
        self.discovered_servers: list[DiscoveredServerInfo] = []
        self.public_server_checked = False
        self.public_server_settings: ConnectionSettings | None = None
        self.public_server_required = False
        self.public_server_label = "Serveur Internet"
        self.public_server_error = ""
        self.pack(fill="both", expand=True)
        self.root.protocol("WM_DELETE_WINDOW", self.on_quit)
        self.build_ui()
        self.after(300, self.auto_configure_connection)

    def build_ui(self) -> None:
        card = ttk.LabelFrame(self, text="Connexion", style="Card.TLabelframe", padding=18)
        card.pack(anchor="n", pady=(6, 0))
        self.watermark_label = create_logo_widget(card, 210, opacity=40)
        if self.watermark_label is not None:
            self.watermark_label.place(relx=0.5, rely=0.53, anchor="center")
            self.watermark_label.lower()

        ttk.Label(card, text=APP_NAME, style="Header.TLabel").grid(
            row=1, column=0, columnspan=2, pady=(0, 18)
        )

        ttk.Label(card, text=f"Version {APP_VERSION}", foreground=MUTED_TEXT_COLOR).grid(
            row=2, column=0, columnspan=2, pady=(0, 12)
        )

        self.connection_status_var = tk.StringVar(value=DatabaseHelper.get_connection_status_text())
        ttk.Label(
            card,
            textvariable=self.connection_status_var,
            foreground=SUCCESS_COLOR,
            wraplength=360,
            justify="center",
        ).grid(row=3, column=0, columnspan=2, pady=(0, 12))

        row_index = 4
        if self.post_update_notice is not None and self.post_update_notice.remaining_ms() > 0:
            self.notice_label = ttk.Label(
                card,
                text=self.post_update_notice.message,
                foreground=self.post_update_notice.foreground,
                justify="center",
                wraplength=360,
            )
            self.notice_label.grid(row=row_index, column=0, columnspan=2, pady=(0, 10))
            self.after(self.post_update_notice.remaining_ms(), self.hide_notice)
            row_index += 1

        ttk.Label(card, text="Identifiant ou e-mail").grid(row=row_index, column=0, sticky="w", pady=6)
        self.user_var = tk.StringVar()
        self.user_entry = ttk.Entry(card, textvariable=self.user_var, width=30)
        self.user_entry.grid(row=row_index, column=1, sticky="ew", pady=6)
        row_index += 1

        ttk.Label(card, text="Mot de passe").grid(row=row_index, column=0, sticky="w", pady=6)
        self.password_var = tk.StringVar()
        self.show_password_var = tk.BooleanVar(value=False)
        password_row = ttk.Frame(card)
        password_row.grid(row=row_index, column=1, sticky="ew", pady=6)
        password_row.columnconfigure(0, weight=1)
        self.password_entry = ttk.Entry(password_row, textvariable=self.password_var, width=30, show="*")
        self.password_entry.grid(row=0, column=0, sticky="ew")
        ttk.Checkbutton(
            password_row,
            text="Afficher",
            variable=self.show_password_var,
            command=self.toggle_password_visibility,
        ).grid(row=0, column=1, padx=(8, 0))
        row_index += 1

        button_row = ttk.Frame(card)
        button_row.grid(row=row_index, column=0, columnspan=2, pady=(14, 0))
        ttk.Button(button_row, text="Connexion", style="Primary.TButton", command=self.login).grid(
            row=0, column=0, columnspan=2, padx=6, pady=(0, 8), sticky="ew"
        )
        ttk.Button(button_row, text="Quitter", command=self.on_quit).grid(row=1, column=0, padx=6, pady=4, sticky="ew")
        ttk.Button(button_row, text="À propos", command=self.open_about).grid(row=1, column=1, padx=6, pady=4, sticky="ew")
        ttk.Button(button_row, text="Paramètres réseau", command=self.open_connection_settings).grid(
            row=2, column=0, padx=6, pady=4, sticky="ew"
        )
        ttk.Button(button_row, text="Détecter le serveur", command=self.detect_server_now).grid(
            row=2, column=1, padx=6, pady=4, sticky="ew"
        )
        button_row.columnconfigure(0, weight=1)
        button_row.columnconfigure(1, weight=1)
        card.columnconfigure(1, weight=1)
        add_copyright_footer(self, wraplength=560).pack(side="bottom", fill="x", pady=(8, 0))
        self.user_entry.bind("<Return>", lambda _event: self.password_entry.focus())
        self.password_entry.bind("<Return>", lambda _event: self.login())
        self.user_entry.focus()

    def refresh_connection_status(self) -> None:
        self.connection_status_var.set(DatabaseHelper.get_connection_status_text())

    def open_connection_settings(self) -> None:
        dialog = ConnectionSettingsDialog(self)
        self.wait_window(dialog)
        self.refresh_connection_status()

    def open_about(self) -> None:
        AboutWindow(self)

    def toggle_password_visibility(self) -> None:
        self.password_entry.configure(show="" if self.show_password_var.get() else "*")

    def _apply_session_connection_settings(self, settings: ConnectionSettings) -> None:
        DatabaseHelper.apply_connection_settings(settings, persist=False)
        self.refresh_connection_status()

    def _build_remote_settings(self, server_url: str, api_token: str = "") -> ConnectionSettings:
        return ConnectionSettings(mode="remote", server_url=server_url, api_token=api_token)

    def _is_reachable_remote_settings(self, settings: ConnectionSettings) -> bool:
        if not settings.is_remote():
            return False
        try:
            RemoteDatabaseClient(
                settings.normalized_url(),
                api_token=settings.api_token,
                timeout_seconds=2,
            ).ping()
        except Exception:
            return False
        return True

    def _get_saved_remote_settings(self) -> ConnectionSettings | None:
        settings = load_connection_settings(DatabaseHelper.app_data_dir)
        if settings.is_remote():
            return settings

        settings = DatabaseHelper.get_connection_settings()
        if settings.is_remote():
            return settings
        return None

    def _get_public_server_settings(self, force_refresh: bool = False) -> ConnectionSettings | None:
        if self.public_server_checked and not force_refresh:
            return self.public_server_settings

        self.public_server_checked = True
        self.public_server_settings = None
        self.public_server_required = False
        self.public_server_label = "Serveur Internet"
        self.public_server_error = ""
        try:
            directory = fetch_public_server_directory()
        except Exception as exc:
            self.public_server_error = str(exc)
            return None

        self.public_server_required = bool(directory.required)
        self.public_server_label = directory.label
        self.public_server_settings = directory.to_connection_settings()
        return self.public_server_settings

    def _set_central_server_unreachable_notice(
        self,
        settings: ConnectionSettings | None = None,
        detail: str = "",
    ) -> None:
        target_settings = settings or self._get_saved_remote_settings() or self._get_public_server_settings()
        if target_settings is not None:
            self._apply_session_connection_settings(target_settings)

        server_url = target_settings.normalized_url() if target_settings is not None else ""
        suffix = f" ({server_url})" if server_url else ""
        detail_text = f" {detail.strip()}" if detail.strip() else ""
        self.connection_status_var.set(
            "Serveur central introuvable : vérifiez que le serveur principal est allumé, "
            f"ou que l'adresse Internet du serveur est disponible{suffix}.{detail_text}"
        )

    def _get_local_server_settings(self, start_service_if_needed: bool = False) -> ConnectionSettings | None:
        handle = get_embedded_server_status()
        if handle is not None:
            return self._build_remote_settings(handle.preferred_url, handle.api_token)

        host_settings = load_central_server_settings()
        service_status = get_windows_service_status()
        if (
            service_status.installed
            and not service_status.is_running
            and start_service_if_needed
            and is_running_as_administrator()
        ):
            try:
                install_or_update_windows_service(
                    host_settings,
                    source_data_dir=DatabaseHelper.app_data_dir,
                )
                start_windows_service()
                service_status = get_windows_service_status()
            except Exception:
                pass

        if not service_status.installed or not service_status.is_running:
            return None

        token = host_settings.normalized_token()
        for server_url in build_local_server_addresses(host_settings.normalized_port()):
            settings = self._build_remote_settings(server_url, token)
            if self._is_reachable_remote_settings(settings):
                return settings
        return None

    def _discover_remote_settings(self, use_cached: bool = True) -> ConnectionSettings | None:
        servers = self.discovered_servers if use_cached and self.discovered_servers else []
        if not servers:
            servers = discover_remote_servers(timeout_seconds=REMOTE_DISCOVERY_TIMEOUT_SECONDS)
            self.discovered_servers = servers
        if not servers:
            return None

        current_settings = DatabaseHelper.get_connection_settings()
        selected_server = servers[0]
        return self._build_remote_settings(
            selected_server.server_url,
            current_settings.api_token,
        )

    def auto_configure_connection(self) -> None:
        if APP_DEMO:
            self._apply_session_connection_settings(ConnectionSettings())
            self.connection_status_var.set("Mode démo local - données séparées de la version officielle")
            return

        saved_remote_settings = self._get_saved_remote_settings()

        local_server_settings = self._get_local_server_settings(start_service_if_needed=True)
        if local_server_settings is not None:
            self._apply_session_connection_settings(local_server_settings)
            self.connection_status_var.set(
                f"Serveur principal local prêt : {local_server_settings.normalized_url()}"
            )
            return

        if saved_remote_settings is not None and self._is_reachable_remote_settings(saved_remote_settings):
            self._apply_session_connection_settings(saved_remote_settings)
            return

        public_server_settings = self._get_public_server_settings()
        if public_server_settings is not None and self._is_reachable_remote_settings(public_server_settings):
            self._apply_session_connection_settings(public_server_settings)
            self.connection_status_var.set(
                f"Serveur Internet prêt : {self.public_server_label} - {public_server_settings.normalized_url()}"
            )
            return

        self.start_server_discovery(auto_apply=True)

    def detect_server_now(self) -> None:
        self.start_server_discovery(auto_apply=False)

    def start_server_discovery(self, auto_apply: bool) -> None:
        if self.discovery_in_progress:
            return

        self.discovery_in_progress = True
        self.connection_status_var.set("Recherche automatique du serveur central sur le réseau local...")

        def worker() -> None:
            try:
                servers = discover_remote_servers(timeout_seconds=REMOTE_DISCOVERY_TIMEOUT_SECONDS)
                self.discovery_queue.put(("ok", servers, auto_apply))
            except Exception as exc:
                self.discovery_queue.put(("error", [str(exc)], auto_apply))

        threading.Thread(target=worker, name="boulangerie-auto-discovery", daemon=True).start()
        self.after(200, self.poll_server_discovery_results)

    def poll_server_discovery_results(self) -> None:
        try:
            item = self.discovery_queue.get_nowait()
        except Empty:
            if self.discovery_in_progress:
                self.after(200, self.poll_server_discovery_results)
            return

        self.discovery_in_progress = False
        status = str(item[0])
        auto_apply = bool(item[2])

        if status == "error":
            saved_remote_settings = self._get_saved_remote_settings()
            if saved_remote_settings is not None:
                self._set_central_server_unreachable_notice(saved_remote_settings, str(item[1][0]))
            else:
                self.refresh_connection_status()
            if not auto_apply:
                messagebox.showwarning("Recherche automatique", str(item[1][0]))
            return

        servers = item[1]
        if not isinstance(servers, list):
            servers = []
        self.discovered_servers = servers

        if not servers:
            saved_remote_settings = self._get_saved_remote_settings()
            if saved_remote_settings is not None:
                self._set_central_server_unreachable_notice(saved_remote_settings)
            else:
                current_settings = DatabaseHelper.get_connection_settings()
                if not current_settings.is_remote():
                    self.refresh_connection_status()
                else:
                    self.refresh_connection_status()
            if not auto_apply:
                messagebox.showinfo(
                    "Recherche automatique",
                    "Aucun serveur central n'a été détecté automatiquement sur le réseau local.",
                )
            return

        selected_server = servers[0]
        settings = DatabaseHelper.get_connection_settings()
        updated_settings = ConnectionSettings(
            mode="remote",
            server_url=selected_server.server_url,
            api_token=settings.api_token,
        )
        self._apply_session_connection_settings(updated_settings)

        if auto_apply:
            self.connection_status_var.set(
                f"Serveur détecté automatiquement : {selected_server.server_name} - {selected_server.server_url}"
            )
            return

        extra = ""
        if len(servers) > 1:
            extra = f"\n\n{len(servers)} serveurs ont été détectés. Le premier a été présélectionné."
        token_line = "\nJeton requis." if selected_server.token_required else "\nAucun jeton requis."
        messagebox.showinfo(
            "Recherche automatique",
            (
                "Serveur central détecté automatiquement :\n"
                f"{selected_server.server_name}\n"
                f"{selected_server.server_url}"
                f"{token_line}"
                f"{extra}"
            ),
        )

    def _build_login_connection_plan(self) -> list[ConnectionSettings]:
        if APP_DEMO:
            return [ConnectionSettings()]

        plan: list[ConnectionSettings] = []
        seen: set[tuple[str, str, str]] = set()
        saved_remote_settings = self._get_saved_remote_settings()
        public_server_settings = self._get_public_server_settings()
        central_server_required = saved_remote_settings is not None or self.public_server_required

        def add_setting(setting: ConnectionSettings | None) -> None:
            if setting is None:
                return
            normalized = ConnectionSettings(
                mode=setting.normalized_mode(),
                server_url=setting.normalized_url(),
                api_token=setting.api_token.strip(),
            )
            key = (
                normalized.normalized_mode(),
                normalized.normalized_url(),
                normalized.api_token.strip(),
            )
            if key in seen:
                return
            seen.add(key)
            plan.append(normalized)

        add_setting(self._get_local_server_settings(start_service_if_needed=True))
        add_setting(saved_remote_settings)
        add_setting(public_server_settings)
        add_setting(self._discover_remote_settings(use_cached=True))
        if APP_DEMO and not any(setting.is_remote() for setting in plan) and not central_server_required:
            add_setting(ConnectionSettings())
        return plan

    def _try_login_with_settings(
        self,
        settings: ConnectionSettings,
        identifiant: str,
        mot_de_passe: str,
        force_session: bool = False,
    ) -> tuple[AuthenticatedUser | None, str | None]:
        self._apply_session_connection_settings(settings)
        device_name = os.environ.get("COMPUTERNAME") or "Poste Windows"
        try:
            user = DatabaseHelper.find_user_for_login(
                identifiant,
                mot_de_passe,
                force_session,
                "Windows",
                device_name,
            )
            if user is not None and not DatabaseHelper.is_remote_mode():
                session_token = secrets.token_urlsafe(32)
                session_result = DatabaseHelper.open_active_session(
                    user.identifiant,
                    "Windows",
                    session_token,
                    device_name,
                    "",
                    force_session,
                )
                if not session_result.get("ok", False):
                    active_session = (
                        session_result.get("activeSession")
                        if isinstance(session_result.get("activeSession"), dict)
                        else {}
                    )
                    raise ActiveSessionConflictError(active_session)
                DatabaseHelper.set_current_session_context(user.identifiant, session_token)
        except ActiveSessionConflictError:
            raise
        except Exception as exc:
            return None, str(exc)
        return user, None

    def _confirm_replace_active_session(self, conflict: ActiveSessionConflictError) -> bool:
        active_session = conflict.active_session
        platform = str(active_session.get("Plateforme") or "un autre appareil")
        device_name = str(active_session.get("NomAppareil") or "").strip()
        connected_at = str(active_session.get("DateConnexion") or "").strip()
        details = f"Ce compte est deja connecte sur {platform}."
        if device_name:
            details += f"\nAppareil : {device_name}"
        if connected_at:
            details += f"\nConnecte depuis : {connected_at}"
        details += "\n\nVoulez-vous fermer cette session et vous connecter ici ?"
        return messagebox.askyesno("Session deja active", details)

    def _promote_admin_session_to_principal_server(
        self,
        identifiant: str,
        mot_de_passe: str,
        current_user: AuthenticatedUser,
    ) -> AuthenticatedUser:
        if current_user.role != "Admin" or DatabaseHelper.is_remote_mode():
            return current_user

        local_server_settings = self._get_local_server_settings(start_service_if_needed=True)
        if local_server_settings is None:
            return current_user

        remote_user, error_message = self._try_login_with_settings(
            local_server_settings,
            identifiant,
            mot_de_passe,
            force_session=True,
        )
        if error_message is not None or remote_user is None:
            self._apply_session_connection_settings(ConnectionSettings())
            return current_user
        return remote_user

    def login(self) -> None:
        identifiant = self.user_var.get().strip()
        mot_de_passe = self.password_var.get().strip()
        if not identifiant:
            messagebox.showwarning("Connexion", "Veuillez entrer un identifiant.")
            return
        if not mot_de_passe:
            messagebox.showwarning("Connexion", "Veuillez entrer un mot de passe.")
            return

        remote_errors: list[str] = []
        user: AuthenticatedUser | None = None
        connection_plan = self._build_login_connection_plan()
        central_server_required = self._get_saved_remote_settings() is not None or self.public_server_required

        if central_server_required and not any(settings.is_remote() for settings in connection_plan):
            self._set_central_server_unreachable_notice()
            messagebox.showerror(
                "Serveur central introuvable",
                (
                    "Impossible de joindre le serveur central.\n\n"
                    "L'application ne va pas basculer en mode local pour éviter de créer des données séparées.\n\n"
                    "Vérifiez que le serveur principal est allumé ou que l'adresse Internet du serveur est disponible."
                ),
            )
            return

        for settings in connection_plan:
            try:
                candidate_user, error_message = self._try_login_with_settings(settings, identifiant, mot_de_passe)
            except ActiveSessionConflictError as conflict:
                if not self._confirm_replace_active_session(conflict):
                    self.password_var.set("")
                    self.password_entry.focus()
                    return
                try:
                    candidate_user, error_message = self._try_login_with_settings(
                        settings,
                        identifiant,
                        mot_de_passe,
                        force_session=True,
                    )
                except ActiveSessionConflictError as retry_conflict:
                    messagebox.showerror("Session deja active", str(retry_conflict))
                    self.password_var.set("")
                    self.password_entry.focus()
                    return
            if error_message is not None:
                if settings.is_remote():
                    remote_errors.append(error_message)
                    continue
                messagebox.showerror("Connexion", error_message)
                return
            if candidate_user is None:
                continue
            user = self._promote_admin_session_to_principal_server(
                identifiant,
                mot_de_passe,
                candidate_user,
            )
            break

        if user is None:
            if remote_errors:
                self._set_central_server_unreachable_notice(detail=remote_errors[0])
                messagebox.showerror(
                    "Serveur central introuvable",
                    (
                        "Impossible de joindre le serveur central.\n\n"
                        "L'application ne va pas basculer en mode local pour éviter de créer des données séparées.\n\n"
                        f"Détail : {remote_errors[0]}"
                    ),
                )
            else:
                messagebox.showwarning("Connexion", "Identifiants incorrects.")
            self.password_var.set("")
            self.password_entry.focus()
            return

        self.user_var.set("")
        self.password_var.set("")
        try:
            DatabaseHelper.log_activity(
                user.identifiant,
                user.display_name,
                user.role,
                "Connexion",
                "Connexion réussie",
                f"Ouverture du tableau de bord en tant que {user.role}.",
            )
        except Exception:
            pass
        self.root.withdraw()
        dashboard = DashboardWindow(self.root, user, self.show_login, self.post_update_notice)
        if DatabaseHelper.is_using_default_password(user.identifiant):
            dashboard.after(250, dashboard.require_initial_password_change)
        self.root.wait_window(dashboard)

    def hide_notice(self) -> None:
        if self.notice_label is None:
            return
        self.notice_label.destroy()
        self.notice_label = None

    def show_login(self) -> None:
        self.root.deiconify()
        self.root.lift()

    def on_quit(self) -> None:
        if messagebox.askyesno("Confirmation", "Voulez-vous vraiment quitter l'application ?"):
            self.root.destroy()


class ConnectionSettingsDialog(tk.Toplevel):
    def __init__(self, parent: LoginWindow) -> None:
        super().__init__(parent)
        self.parent = parent
        self.title("Paramètres réseau")
        self.geometry("900x680")
        self.minsize(760, 460)
        self.configure(bg=MODULE_BACKGROUND)
        self.resizable(True, True)
        apply_window_icon(self)
        self.transient(parent)
        self.grab_set()
        self.protocol("WM_DELETE_WINDOW", self.close_window)

        settings = DatabaseHelper.get_connection_settings()
        host_settings = load_central_server_settings()
        self.mode_var = tk.StringVar(value=settings.mode)
        self.server_url_var = tk.StringVar(value=settings.server_url)
        preferred_token = settings.api_token or host_settings.normalized_token()
        self.api_token_var = tk.StringVar(value=preferred_token)
        self.message_var = tk.StringVar(value="")
        self.server_status_var = tk.StringVar(value="")
        self.windows_service_status_var = tk.StringVar(value="")
        self.server_button_var = tk.StringVar(value="Démarrer le serveur sur ce poste")
        self.message_box: ScrolledText | None = None

        self.build_ui()
        self.message_var.trace_add("write", self._sync_message_box)
        self._sync_message_box()
        self.refresh_server_status()
        self.refresh_windows_service_status()
        self.update_mode_fields()
        self.after(250, self.auto_discover_if_needed)
        fit_window_to_work_area(self, 900, 680, min_width=760, min_height=460)

    def build_ui(self) -> None:
        self.columnconfigure(0, weight=1)
        self.rowconfigure(0, weight=1)

        self.scrollable_content = ScrollableContent(self, padding=(10, 4, 10, 10), background=MODULE_BACKGROUND)
        self.scrollable_content.grid(row=0, column=0, sticky="nsew")
        frame = self.scrollable_content.content
        header = create_branded_header(frame, "Mode connecté", logo_size=SETTINGS_LOGO_SIZE, wraplength=620)
        setattr(self, "_header_logo", getattr(header, "_header_logo", None))
        ttk.Label(
            frame,
            text=(
                "Choisissez si ce poste travaille en local, ou s'il doit utiliser un serveur central. "
                "Le serveur central permet à plusieurs postes de partager les mêmes données en temps réel."
            ),
            wraplength=620,
            justify="center",
        ).pack(fill="x", pady=(0, 10))

        mode_frame = ttk.LabelFrame(frame, text="Mode de travail", style="Card.TLabelframe")
        mode_frame.pack(fill="x", pady=(0, 12))
        ttk.Radiobutton(
            mode_frame,
            text="Mode local",
            value="local",
            variable=self.mode_var,
            command=self.update_mode_fields,
        ).grid(row=0, column=0, sticky="w", pady=4)
        ttk.Radiobutton(
            mode_frame,
            text="Mode connecté au serveur central",
            value="remote",
            variable=self.mode_var,
            command=self.update_mode_fields,
        ).grid(row=1, column=0, sticky="w", pady=4)

        remote_frame = ttk.LabelFrame(frame, text="Serveur central", style="Card.TLabelframe")
        remote_frame.pack(fill="x", pady=(0, 12))
        ttk.Label(remote_frame, text="Adresse du serveur").grid(row=0, column=0, sticky="w", pady=6)
        self.server_url_entry = ttk.Entry(remote_frame, textvariable=self.server_url_var, width=48)
        self.server_url_entry.grid(row=0, column=1, sticky="ew", pady=6)
        ttk.Label(remote_frame, text="Jeton d'acces").grid(row=1, column=0, sticky="w", pady=6)
        self.api_token_entry = ttk.Entry(remote_frame, textvariable=self.api_token_var, width=48, show="*")
        self.api_token_entry.grid(row=1, column=1, sticky="ew", pady=6)

        remote_actions = ttk.Frame(remote_frame)
        remote_actions.grid(row=2, column=0, columnspan=2, pady=(12, 0))
        ttk.Button(remote_actions, text="Tester la connexion", command=self.test_connection).grid(
            row=0, column=0, padx=6
        )
        ttk.Button(
            remote_actions,
            text="Rechercher automatiquement",
            command=self.discover_servers_automatically,
        ).grid(row=0, column=1, padx=6)
        ttk.Button(remote_actions, text="Utiliser l'adresse locale du serveur", command=self.use_local_server_url).grid(
            row=0, column=2, padx=6
        )
        ttk.Button(remote_actions, text="Utiliser l'adresse Internet", command=self.use_public_server_url).grid(
            row=1, column=0, columnspan=3, pady=(8, 0)
        )
        remote_frame.columnconfigure(1, weight=1)

        server_frame = ttk.LabelFrame(frame, text="Serveur temporaire sur ce poste", style="Card.TLabelframe")
        server_frame.pack(fill="x", pady=(0, 12))
        ttk.Label(
            server_frame,
            text=(
                "Vous pouvez démarrer un serveur central temporaire directement sur ce poste. "
                "Ce mode reste pratique pour un test rapide, mais il faut laisser l'application ouverte. "
                "Si le service Windows tourne déjà sur ce poste, il faut l'arrêter d'abord car les deux modes ne peuvent pas utiliser le même port en même temps."
            ),
            wraplength=620,
            justify="center",
        ).pack(fill="x", pady=(0, 10))
        ttk.Label(
            server_frame,
            textvariable=self.server_status_var,
            foreground=SUCCESS_COLOR,
            wraplength=620,
            justify="center",
        ).pack(fill="x", pady=(0, 10))
        server_buttons = ttk.Frame(server_frame)
        server_buttons.pack()
        ttk.Button(server_buttons, textvariable=self.server_button_var, command=self.toggle_local_server).grid(
            row=0, column=0, padx=6
        )

        service_frame = ttk.LabelFrame(frame, text="Service Windows du serveur central", style="Card.TLabelframe")
        service_frame.pack(fill="x", pady=(0, 12))
        ttk.Label(
            service_frame,
            text=(
                "Mode recommandé pour le poste serveur : le service Windows démarre avec Windows "
                "et reste actif même si l'application est fermée. Une sauvegarde automatique "
                "est créée chaque jour dans le dossier central."
            ),
            wraplength=620,
            justify="center",
        ).pack(fill="x", pady=(0, 10))
        ttk.Label(
            service_frame,
            textvariable=self.windows_service_status_var,
            foreground=SUCCESS_COLOR,
            wraplength=620,
            justify="center",
        ).pack(fill="x", pady=(0, 10))
        service_buttons = ttk.Frame(service_frame)
        service_buttons.pack()
        ttk.Button(service_buttons, text="Installer / mettre à jour le service", command=self.install_windows_service).grid(
            row=0, column=0, padx=6, pady=4
        )
        ttk.Button(service_buttons, text="Démarrer le service", command=self.start_windows_service_from_ui).grid(
            row=0, column=1, padx=6, pady=4
        )
        ttk.Button(service_buttons, text="Arreter le service", command=self.stop_windows_service_from_ui).grid(
            row=0, column=2, padx=6, pady=4
        )
        ttk.Button(service_buttons, text="Désinstaller le service", command=self.remove_windows_service_from_ui).grid(
            row=0, column=3, padx=6, pady=4
        )

        footer = ttk.Frame(self, padding=(12, 8, 12, 12))
        footer.grid(row=1, column=0, sticky="ew")
        footer.columnconfigure(0, weight=1)
        self.fixed_footer = footer

        self.message_box = ScrolledText(
            footer,
            height=4,
            wrap="word",
            font=UI_FONT,
            fg=DANGER_COLOR,
            bg="#fff8f8",
            relief="solid",
            borderwidth=1,
            padx=10,
            pady=8,
        )
        self.message_box.grid(row=0, column=0, sticky="ew", pady=(0, 12))
        self.message_box.configure(state="disabled")
        button_row = ttk.Frame(footer)
        button_row.grid(row=1, column=0)
        ttk.Button(button_row, text="Enregistrer", style="Primary.TButton", command=self.save_settings).grid(
            row=0, column=0, padx=6
        )
        ttk.Button(button_row, text="Fermer", command=self.close_window).grid(row=0, column=1, padx=6)

    def _sync_message_box(self, *_args: Any) -> None:
        if self.message_box is None or not self.message_box.winfo_exists():
            return
        message = self.message_var.get().strip()
        self.message_box.configure(state="normal")
        self.message_box.delete("1.0", "end")
        if message:
            self.message_box.insert("1.0", message)
            self.message_box.yview_moveto(0)
        self.message_box.configure(state="disabled")

    def current_settings(self) -> ConnectionSettings:
        return ConnectionSettings(
            mode=self.mode_var.get(),
            server_url=self.server_url_var.get(),
            api_token=self.api_token_var.get(),
        )

    def current_server_host_settings(self) -> CentralServerSettings:
        existing_settings = load_central_server_settings()
        return CentralServerSettings(
            port=existing_settings.normalized_port(),
            api_token=self.api_token_var.get(),
            data_dir=str(existing_settings.normalized_data_dir()),
        )

    def ensure_admin_for_service_action(self) -> bool:
        if is_running_as_administrator():
            return True
        message = (
            "Cette action demande les droits administrateur Windows. "
            "Relancez l'application en tant qu'administrateur sur le poste serveur."
        )
        self.message_var.set(message)
        messagebox.showwarning("Service Windows", message)
        return False

    def update_mode_fields(self) -> None:
        remote_enabled = self.mode_var.get().strip().lower() == "remote"
        target_state = "!disabled" if remote_enabled else "disabled"
        self.server_url_entry.state([target_state])
        self.api_token_entry.state([target_state])

    def auto_discover_if_needed(self) -> None:
        if self.mode_var.get().strip().lower() == "remote" and not self.server_url_var.get().strip():
            if self.use_public_server_url(silent=True):
                return
            self.discover_servers_automatically(silent=True)

    def refresh_server_status(self) -> None:
        handle = get_embedded_server_status()
        if handle is None:
            self.server_status_var.set(
                f"Aucun serveur local n'est actif. Port recommande : {REMOTE_DEFAULT_PORT}."
            )
            self.server_button_var.set("Démarrer le serveur sur ce poste")
            return

        addresses = "\n".join(handle.urls)
        token_line = "Jeton : defini" if handle.api_token else "Jeton : aucun"
        self.server_status_var.set(
            "Serveur central actif sur ce poste.\n"
            f"{addresses}\n"
            f"{token_line}\n"
            "Laissez cette application ouverte pour garder le serveur disponible."
        )
        self.server_button_var.set("Arreter le serveur sur ce poste")

    def refresh_windows_service_status(self) -> None:
        service_status = get_windows_service_status()
        host_settings = load_central_server_settings()
        addresses = "\n".join(build_local_server_addresses(host_settings.normalized_port()))
        token_line = "Jeton : defini" if host_settings.normalized_token() else "Jeton : aucun"
        data_line = f"Dossier central : {host_settings.normalized_data_dir()}"
        backup_line = describe_latest_automatic_backup(host_settings.normalized_data_dir())

        if not service_status.installed:
            self.windows_service_status_var.set(
                f"{service_status.message}\n{data_line}\nPort : {host_settings.normalized_port()}\n{token_line}\n{backup_line}"
            )
            return

        details = [service_status.message]
        if addresses:
            details.append(addresses)
        details.append(data_line)
        details.append(token_line)
        details.append(backup_line)
        self.windows_service_status_var.set("\n".join(details))

    def use_local_server_url(self) -> None:
        handle = get_embedded_server_status()
        if handle is not None:
            self.server_url_var.set(handle.preferred_url)
            if handle.api_token and not self.api_token_var.get().strip():
                self.api_token_var.set(handle.api_token)
            self.message_var.set("L'adresse locale du serveur temporaire a été reportée dans le champ ci-dessus.")
            return

        service_status = get_windows_service_status()
        host_settings = load_central_server_settings()
        addresses = build_local_server_addresses(host_settings.normalized_port())
        if service_status.installed and addresses:
            self.server_url_var.set(addresses[0])
            if host_settings.normalized_token() and not self.api_token_var.get().strip():
                self.api_token_var.set(host_settings.normalized_token())
            if service_status.is_running:
                self.message_var.set("L'adresse locale du service Windows a été reportée dans le champ ci-dessus.")
            else:
                self.message_var.set(
                    "L'adresse du service Windows a été reportée. Pensez à démarrer le service avant de connecter les autres postes."
                )
            return

        self.message_var.set(
            "Demarrez d'abord le serveur temporaire ou le service Windows, ou saisissez l'adresse du serveur central."
        )

    def use_public_server_url(self, silent: bool = False) -> bool:
        try:
            directory = fetch_public_server_directory()
        except Exception as exc:
            if not silent:
                self.message_var.set(str(exc))
            return False

        settings = directory.to_connection_settings()
        if settings is None:
            if not silent:
                self.message_var.set(
                    "Aucune adresse Internet du serveur central n'est publiée pour le moment."
                )
            return False

        self.mode_var.set("remote")
        self.update_mode_fields()
        self.server_url_var.set(settings.normalized_url())
        if settings.api_token and not self.api_token_var.get().strip():
            self.api_token_var.set(settings.api_token)

        try:
            health = RemoteDatabaseClient(
                settings.normalized_url(),
                api_token=settings.api_token or self.api_token_var.get(),
                timeout_seconds=4,
            ).ping()
        except Exception as exc:
            self.message_var.set(
                f"Adresse Internet trouvée ({settings.normalized_url()}), mais le serveur ne répond pas : {exc}"
            )
            return False

        version = str(health.get("app_version", "") or "").strip()
        version_text = f" Version serveur : {version}." if version else ""
        message = (
            f"Adresse Internet appliquée : {directory.label} - {settings.normalized_url()}."
            f"{version_text}"
        )
        self.message_var.set(message)
        if not silent:
            messagebox.showinfo("Serveur Internet", message)
        return True

    def install_windows_service(self) -> None:
        if not self.ensure_admin_for_service_action():
            return
        if is_embedded_server_running():
            self.message_var.set(
                "Arrêtez d'abord le serveur temporaire avant d'installer ou mettre à jour le service Windows."
            )
            return
        try:
            message = install_or_update_windows_service(
                self.current_server_host_settings(),
                source_data_dir=DatabaseHelper.app_data_dir,
            )
        except Exception as exc:
            self.message_var.set(str(exc))
            return

        host_settings = load_central_server_settings()
        addresses = build_local_server_addresses(host_settings.normalized_port())
        if addresses and not self.server_url_var.get().strip():
            self.server_url_var.set(addresses[0])
        self.refresh_windows_service_status()
        self.message_var.set(message)

    def start_windows_service_from_ui(self) -> None:
        if not self.ensure_admin_for_service_action():
            return
        if is_embedded_server_running():
            self.message_var.set(
                "Arrêtez d'abord le serveur temporaire avant de démarrer le service Windows."
            )
            return
        try:
            service_status = get_windows_service_status()
            if service_status.installed and service_status.is_running:
                message = start_windows_service()
                self.refresh_windows_service_status()
                self.message_var.set(message)
                return
            install_or_update_windows_service(
                self.current_server_host_settings(),
                source_data_dir=DatabaseHelper.app_data_dir,
            )
            message = start_windows_service()
        except Exception as exc:
            self.message_var.set(str(exc))
            return

        self.refresh_windows_service_status()
        self.message_var.set(message)

    def stop_windows_service_from_ui(self) -> None:
        if not self.ensure_admin_for_service_action():
            return
        try:
            message = stop_windows_service()
        except Exception as exc:
            self.message_var.set(str(exc))
            return

        self.refresh_windows_service_status()
        self.message_var.set(message)

    def remove_windows_service_from_ui(self) -> None:
        if not self.ensure_admin_for_service_action():
            return
        if not messagebox.askyesno(
            "Service Windows",
            "Voulez-vous vraiment désinstaller le service Windows du serveur central ?",
        ):
            return

        try:
            service_status = get_windows_service_status()
            if service_status.is_running:
                stop_windows_service()
            message = remove_windows_service()
        except Exception as exc:
            self.message_var.set(str(exc))
            return

        self.refresh_windows_service_status()
        self.message_var.set(message)

    def test_connection(self) -> None:
        settings = self.current_settings()
        if not settings.is_remote():
            self.message_var.set("Activez d'abord le mode connecté puis saisissez une adresse serveur.")
            return

        try:
            health = RemoteDatabaseClient(
                settings.normalized_url(),
                api_token=settings.api_token,
            ).ping()
        except Exception as exc:
            self.message_var.set(str(exc))
            return

        server_port = health.get("server_port", REMOTE_DEFAULT_PORT)
        self.message_var.set(
            f"Connexion reussie avec le serveur central sur le port {server_port}."
        )

    def discover_servers_automatically(self, silent: bool = False) -> None:
        self.message_var.set("Recherche automatique des serveurs centraux en cours...")
        if self.use_public_server_url(silent=True):
            if not silent:
                messagebox.showinfo("Recherche automatique", self.message_var.get())
            return

        servers = discover_remote_servers(timeout_seconds=REMOTE_DISCOVERY_TIMEOUT_SECONDS)
        if not servers:
            self.message_var.set("Aucun serveur central n'a été détecté automatiquement sur le réseau local.")
            return

        selected_server = servers[0]
        self.mode_var.set("remote")
        self.update_mode_fields()
        self.server_url_var.set(selected_server.server_url)

        extra = ""
        if len(servers) > 1:
            extra = f" {len(servers)} serveurs ont été trouvés. Le premier a été présélectionné."

        token_hint = (
            " Ce serveur demande un jeton d'acces."
            if selected_server.token_required and not self.api_token_var.get().strip()
            else ""
        )
        message = (
            f"Serveur detecte : {selected_server.server_name} - {selected_server.server_url}."
            f"{token_hint}{extra}"
        )
        self.message_var.set(message)
        if not silent:
            messagebox.showinfo("Recherche automatique", message)

    def toggle_local_server(self) -> None:
        if is_embedded_server_running():
            stop_embedded_server()
            self.refresh_server_status()
            self.refresh_windows_service_status()
            self.message_var.set("Le serveur local a été arrêté.")
            return

        service_status = get_windows_service_status()
        if service_status.is_running:
            self.message_var.set(
                "Arrêtez d'abord le service Windows avant de démarrer un serveur temporaire sur ce poste. "
                "Le bouton démarre un serveur provisoire dans l'application elle-même, alors que le service Windows est le mode permanent recommandé pour le poste principal."
            )
            return

        host_settings = self.current_server_host_settings()
        try:
            save_central_server_settings(host_settings)
            prepare_central_server_data(DatabaseHelper.app_data_dir)
            ensure_windows_firewall_rules(host_settings.normalized_port())
            handle = start_embedded_server(
                port=host_settings.normalized_port(),
                api_token=host_settings.normalized_token(),
                data_dir=host_settings.normalized_data_dir(),
            )
        except Exception as exc:
            self.message_var.set(str(exc))
            return

        if not self.server_url_var.get().strip():
            self.server_url_var.set(handle.preferred_url)
        self.refresh_server_status()
        self.refresh_windows_service_status()
        self.message_var.set(
            "Le serveur local est démarré. Utilisez l'adresse affichée pour connecter les autres postes."
        )

    def save_settings(self) -> None:
        settings = self.current_settings()
        if settings.normalized_mode() == "remote" and not settings.normalized_url():
            self.message_var.set("Saisissez l'adresse du serveur central avant d'enregistrer le mode connecté.")
            return
        if settings.is_remote():
            try:
                RemoteDatabaseClient(
                    settings.normalized_url(),
                    api_token=settings.api_token,
                ).ping()
            except Exception as exc:
                self.message_var.set(str(exc))
                return

        try:
            DatabaseHelper.save_connection_settings(settings)
        except Exception as exc:
            self.message_var.set(str(exc))
            return

        self.parent.refresh_connection_status()
        if settings.is_remote():
            messagebox.showinfo(
                "Mode connecté",
                "Les paramêtres réseau ont été enregistrés. Les prochaines connexions utiliseront le serveur central.",
            )
        else:
            messagebox.showinfo(
                "Mode local",
                "Les paramêtres réseau ont été enregistrés. Ce poste utilise maintenant sa base locale.",
            )
        self.close_window()

    def close_window(self) -> None:
        self.destroy()


class DashboardMetricCard(tk.Frame):
    def __init__(self, parent: tk.Misc, accent: str) -> None:
        super().__init__(
            parent,
            bg=accent,
            bd=0,
            highlightthickness=0,
        )
        self.title_var = tk.StringVar(value="")
        self.value_var = tk.StringVar(value="")
        self.subtitle_var = tk.StringVar(value="")

        self.configure(padx=16, pady=14)
        tk.Label(
            self,
            textvariable=self.title_var,
            bg=accent,
            fg="#ffffff",
            font=(UI_FONT_FAMILY, 11, "bold"),
            anchor="w",
            justify="left",
        ).pack(fill="x")
        tk.Label(
            self,
            textvariable=self.value_var,
            bg=accent,
            fg="#ffffff",
            font=(UI_FONT_FAMILY, 24, "bold"),
            anchor="w",
            justify="left",
        ).pack(fill="x", pady=(6, 2))
        tk.Label(
            self,
            textvariable=self.subtitle_var,
            bg=accent,
            fg="#f5f5f5",
            font=(UI_FONT_FAMILY, 10),
            anchor="w",
            justify="left",
            wraplength=220,
        ).pack(fill="x")

    def update_card(self, title: str, value: str, subtitle: str) -> None:
        self.title_var.set(title)
        self.value_var.set(value)
        self.subtitle_var.set(subtitle)


class ActivityHistoryWindow(tk.Toplevel):
    def __init__(self, parent: DashboardWindow) -> None:
        super().__init__(parent)
        self.parent = parent
        self.live_refresh_after_id: str | None = None
        self.title("Historique des actions")
        self.geometry("1120x700")
        self.configure(bg=MODULE_BACKGROUND)
        self.resizable(True, True)
        apply_window_icon(self)
        self.protocol("WM_DELETE_WINDOW", self.close_window)
        self.transient(parent)
        self.grab_set()
        self.scrollable_content = ScrollableContent(self, padding=(10, 4, 10, 10), background=MODULE_BACKGROUND)
        self.scrollable_content.pack(fill="both", expand=True)
        shell = self.scrollable_content.content
        header = create_branded_header(shell, "Historique des actions", logo_size=FORM_LOGO_SIZE, wraplength=860)
        setattr(self, "_header_logo", getattr(header, "_header_logo", None))
        self.body = ttk.Frame(shell)
        self.body.pack(fill="both", expand=True)
        self.identifiant_filter_var = tk.StringVar()
        self.role_filter_var = tk.StringVar(value="Tous")
        self.message_var = tk.StringVar(value="")
        self.build_ui()
        self.refresh_logs()
        center_window(self)
        if self.parent.is_live_sync_enabled():
            self.schedule_live_refresh()

    def build_ui(self) -> None:
        container = self.body
        container.columnconfigure(0, weight=1)
        container.rowconfigure(1, weight=1)

        filters = ttk.LabelFrame(container, text="Filtres", style="Card.TLabelframe")
        filters.grid(row=0, column=0, sticky="ew", pady=(0, 12))
        ttk.Label(filters, text="Identifiant").grid(row=0, column=0, sticky="w", pady=6)
        ttk.Entry(filters, textvariable=self.identifiant_filter_var, width=24).grid(row=0, column=1, sticky="ew", pady=6)
        ttk.Label(filters, text="Rôle").grid(row=0, column=2, sticky="w", pady=6, padx=(12, 0))
        ttk.Combobox(
            filters,
            textvariable=self.role_filter_var,
            values=["Tous", *ROLES],
            state="readonly",
            width=24,
        ).grid(row=0, column=3, sticky="ew", pady=6)
        actions = ttk.Frame(filters)
        actions.grid(row=0, column=4, sticky="e", padx=(12, 0))
        ttk.Button(actions, text="Actualiser", command=self.refresh_logs).grid(row=0, column=0, padx=4)
        ttk.Button(actions, text="Fermer", command=self.close_window).grid(row=0, column=1, padx=4)
        filters.columnconfigure(1, weight=1)
        filters.columnconfigure(3, weight=1)

        table_frame = ttk.LabelFrame(container, text="Journal des actions", style="Card.TLabelframe")
        table_frame.grid(row=1, column=0, sticky="nsew")
        self.table = DataTable(table_frame, height=18)
        self.table.pack(fill="both", expand=True)

        ttk.Label(
            container,
            textvariable=self.message_var,
            foreground=MUTED_TEXT_COLOR,
            wraplength=900,
            justify="left",
        ).grid(row=2, column=0, sticky="ew", pady=(12, 0))

    def refresh_logs(self) -> None:
        role_filter = self.role_filter_var.get().strip()
        rows = DatabaseHelper.list_activity_logs(
            limit=400,
            identifiant=self.identifiant_filter_var.get().strip(),
            role="" if role_filter == "Tous" else role_filter,
        )
        self.table.set_data(
            rows,
            columns=["Id", "DateAction", "NomComplet", "Identifiant", "Role", "Module", "Action", "Details"],
            headings={
                "DateAction": "Date et heure",
                "NomComplet": "Nom complet",
                "Identifiant": "Identifiant",
                "Role": "Rôle",
                "Module": "Module",
                "Action": "Action",
                "Details": "Détails",
            },
            hidden_columns=["Id"],
            formatters={
                "DateAction": format_activity_timestamp,
                "Details": compact_multiline_text,
            },
        )
        self.table.tree.column("Details", width=340, stretch=True)
        self.message_var.set(f"{len(rows)} action(s) affichée(s).")

    def refresh_live_view(self) -> None:
        self.refresh_logs()

    def schedule_live_refresh(self) -> None:
        if self.live_refresh_after_id is not None:
            self.after_cancel(self.live_refresh_after_id)
        self.live_refresh_after_id = self.after(REMOTE_REFRESH_INTERVAL_MS, self.perform_live_refresh)

    def perform_live_refresh(self) -> None:
        self.live_refresh_after_id = None
        if not self.winfo_exists():
            return
        self.refresh_live_view()
        if self.parent.is_live_sync_enabled():
            self.schedule_live_refresh()

    def close_window(self) -> None:
        if self.live_refresh_after_id is not None:
            self.after_cancel(self.live_refresh_after_id)
            self.live_refresh_after_id = None
        self.destroy()


class DashboardWindow(tk.Toplevel):
    active_auto_lock_owner: "DashboardWindow | None" = None

    def __init__(
        self,
        root: tk.Tk,
        user: AuthenticatedUser,
        on_logout: Callable[[], None],
        post_update_notice: SessionNotice | None = None,
    ) -> None:
        super().__init__(root)
        self.root = root
        self.user = user
        self.on_logout_callback = on_logout
        self.post_update_notice = post_update_notice
        self.notice_label: ttk.Label | None = None
        self.update_result_queue: Queue[UpdateCheckResult] = Queue()
        self.update_check_running = False
        self.live_refresh_after_id: str | None = None
        self.summary_refresh_after_id: str | None = None
        self.auto_lock_after_id: str | None = None
        self.session_guard_after_id: str | None = None
        self.module_opening = False
        self.module_opening_overlay: tk.Toplevel | None = None
        self.critical_alerts_shown = False
        self.monthly_report_obligation: dict[str, Any] | None = None
        self.metric_cards: list[DashboardMetricCard] = []
        self.stock_alerts_var = tk.StringVar(value="Chargement des alertes de stock...")
        self.debt_alerts_var = tk.StringVar(value="Chargement des alertes de dettes...")
        self.recent_activity_var = tk.StringVar(value="Chargement de l'historique...")
        self.closure_status_var = tk.StringVar(value="Chargement du statut de clôture...")
        self.title(f"{APP_NAME} - Tableau de bord - v{APP_VERSION}")
        self.geometry("1180x760")
        self.minsize(980, 640)
        self.configure(bg=APP_BACKGROUND)
        self.resizable(True, True)
        apply_window_icon(self)
        self.protocol("WM_DELETE_WINDOW", self.on_close_app)
        self.scrollable_content = ScrollableContent(self, padding=(10, 4, 10, 10), background=APP_BACKGROUND)
        self.scrollable_content.pack(fill="both", expand=True)
        self.body = self.scrollable_content.content
        self.build_ui()
        maximize_window(self, 980, 640)
        self.request_refresh_summary(50)
        self.bind("<FocusIn>", lambda _event: self.request_refresh_summary(150))
        self.after(1000, self.start_startup_update_check)
        self.after(700, self.show_role_critical_alerts)
        self.after(1200, self.check_monthly_report_obligation)
        if self.is_live_sync_enabled():
            self.schedule_live_refresh()
        self.install_auto_lock()
        self.schedule_session_guard()

    def build_ui(self) -> None:
        container = self.body
        header = create_branded_header(
            container,
            f"Bienvenue, {self.user.display_name} ({self.user.role})",
            logo_size=DASHBOARD_LOGO_SIZE,
            wraplength=760,
        )
        setattr(self, "_header_logo", getattr(header, "_header_logo", None))

        ttk.Label(
            container,
            text=f"Version installée : {APP_VERSION}",
            foreground=MUTED_TEXT_COLOR,
        ).pack(anchor="center", pady=(0, 8))

        ttk.Label(
            container,
            text=DatabaseHelper.get_connection_status_text(),
            foreground=SUCCESS_COLOR,
            wraplength=680,
            justify="center",
        ).pack(anchor="center", pady=(0, 8))

        if self.post_update_notice is not None and self.post_update_notice.remaining_ms() > 0:
            self.notice_label = ttk.Label(
                container,
                text=self.post_update_notice.message,
                foreground=self.post_update_notice.foreground,
                justify="center",
                wraplength=540,
            )
            self.notice_label.pack(anchor="center", pady=(0, 14))
            self.after(self.post_update_notice.remaining_ms(), self.hide_notice)

        grid = ttk.Frame(container)
        grid.pack(fill="x")

        buttons = [
            ("Caisse", self.open_cash),
            ("Stock", self.open_stock),
            ("Production", self.open_production),
            ("Commandes", self.open_orders),
            ("Commissions", self.open_commissions),
            ("Travailleurs", self.open_workers_payroll),
        ]
        if self.user.role in FULL_VISIBILITY_ROLES:
            buttons.append(("Utilisateurs", self.open_users))

        self.module_buttons: dict[str, ttk.Button] = {}
        visible_buttons = [(label, callback) for label, callback in buttons if self.can_access(label, show_warning=False)]
        for index, (label, callback) in enumerate(visible_buttons):
            button = ttk.Button(grid, text=label, command=deferred_ui_command(self, callback))
            button.grid(row=index // 2, column=index % 2, padx=8, pady=8, sticky="ew")
            self.module_buttons[label] = button

        grid.columnconfigure(0, weight=1)
        grid.columnconfigure(1, weight=1)

        self.summary_var = tk.StringVar(value="Chargement des statistiques...")
        summary_frame = ttk.LabelFrame(container, text="Résumé", style="Card.TLabelframe")
        summary_frame.pack(fill="x", pady=18)
        ttk.Label(summary_frame, textvariable=self.summary_var, justify="center").pack(fill="x")

        visual_frame = ttk.LabelFrame(container, text="Indicateurs clés", style="Card.TLabelframe")
        visual_frame.pack(fill="x", pady=(0, 18))
        cards_grid = ttk.Frame(visual_frame)
        cards_grid.pack(fill="x")
        self.metric_cards = []
        metric_colors = (
            "#b22222",
            "#1f4e78",
            "#0a7d53",
            "#6b3fa0",
            "#b36b00",
            "#6d4c41",
            "#00796b",
            "#455a64",
        )
        for index, color in enumerate(metric_colors):
            card = DashboardMetricCard(cards_grid, color)
            card.grid(row=index // 4, column=index % 4, sticky="nsew", padx=6, pady=4)
            cards_grid.columnconfigure(index % 4, weight=1)
            self.metric_cards.append(card)

        stock_alert_roles = {"Admin", "Directeur Général", "Gestionnaire de stock"}
        debt_alert_roles = {"Admin", "Directeur Général", "Caissier", "Gestionnaire des commandes"}
        if self.user.role in stock_alert_roles | debt_alert_roles:
            alerts_frame = ttk.LabelFrame(container, text="Alertes prioritaires", style="Card.TLabelframe")
            alerts_frame.pack(fill="x", pady=(0, 18))
        if self.user.role in stock_alert_roles:
            stock_box = ttk.Frame(alerts_frame)
            stock_box.pack(fill="x", pady=(0, 10))
            ttk.Label(stock_box, text="Stock faible", foreground=DANGER_COLOR).pack(anchor="w")
            ttk.Label(stock_box, textvariable=self.stock_alerts_var, justify="left", wraplength=760).pack(fill="x")
        if self.user.role in debt_alert_roles:
            debt_box = ttk.Frame(alerts_frame)
            debt_box.pack(fill="x")
            ttk.Label(debt_box, text="Dettes en attente", foreground=DANGER_COLOR).pack(anchor="w")
            ttk.Label(debt_box, textvariable=self.debt_alerts_var, justify="left", wraplength=760).pack(fill="x")

        if self.user.role in FULL_VISIBILITY_ROLES:
            admin_frame = ttk.LabelFrame(container, text="Historique des actions", style="Card.TLabelframe")
            admin_frame.pack(fill="x", pady=(0, 18))
            ttk.Label(
                admin_frame,
                textvariable=self.recent_activity_var,
                justify="left",
                wraplength=760,
            ).pack(fill="x", pady=(0, 10))
            ttk.Button(
                admin_frame,
                text="Ouvrir l'historique complet",
                command=deferred_ui_command(self, self.open_activity_history),
            ).pack(anchor="center")

            closure_frame = ttk.LabelFrame(container, text="Clôture journalière", style="Card.TLabelframe")
            closure_frame.pack(fill="x", pady=(0, 18))
            ttk.Label(
                closure_frame,
                text=(
                    "Clôturez une journée pour figer les écritures, générer un rapport signé "
                    "et créer automatiquement une sauvegarde de sécurité."
                ),
                wraplength=760,
                justify="center",
            ).pack(fill="x", pady=(0, 10))
            closure_date_row = ttk.Frame(closure_frame)
            closure_date_row.pack(anchor="center", pady=(0, 10))
            ttk.Label(closure_date_row, text="Date à clôturer").grid(row=0, column=0, sticky="w", padx=(0, 8))
            self.closure_date_field = DateField(closure_date_row, today_iso())
            self.closure_date_field.grid(row=0, column=1, sticky="ew")
            self.closure_date_field.bind_change(self.refresh_closure_status)
            closure_buttons = ttk.Frame(closure_frame)
            closure_buttons.pack(anchor="center", pady=(0, 10))
            self.close_day_button = ttk.Button(
                closure_buttons,
                text="Clôturer la journée",
                command=deferred_ui_command(self, self.close_selected_day),
            )
            self.close_day_button.grid(row=0, column=0, padx=6, pady=4)
            self.reopen_day_button = ttk.Button(
                closure_buttons,
                text="Réouvrir la journée",
                command=deferred_ui_command(self, self.reopen_selected_day),
            )
            self.reopen_day_button.grid(row=0, column=1, padx=6, pady=4)
            if self.user.role != "Admin":
                self.reopen_day_button.state(["disabled"])
            ttk.Button(
                closure_buttons,
                text="Historique des clôtures",
                command=deferred_ui_command(self, self.open_closure_history),
            ).grid(row=0, column=2, padx=6, pady=4)
            ttk.Label(
                closure_frame,
                textvariable=self.closure_status_var,
                wraplength=760,
                justify="left",
            ).pack(fill="x")

        self.security_message_var = tk.StringVar(value="")
        security_frame = ttk.LabelFrame(container, text="Sécurité du compte", style="Card.TLabelframe")
        security_frame.pack(fill="x", pady=(0, 18))
        self.security_label = ttk.Label(
            security_frame,
            textvariable=self.security_message_var,
            wraplength=640,
            justify="center",
        )
        self.security_label.pack(fill="x", pady=(0, 12))
        ttk.Button(
            security_frame,
            text="Changer mon mot de passe",
            command=deferred_ui_command(self, self.open_change_password),
        ).pack(anchor="center")
        self.refresh_security_notice()

        reports_frame = ttk.LabelFrame(container, text="Rapports PDF et Excel", style="Card.TLabelframe")
        reports_frame.pack(fill="x", pady=(0, 18))
        ttk.Label(
            reports_frame,
            text=(
                "Générez un rapport journalier au format PDF ou Excel. Le contenu sera automatiquement "
                "limité aux modules autorisés pour le profil connecté."
            ),
            wraplength=640,
            justify="center",
        ).pack(fill="x", pady=(0, 12))
        report_buttons = ttk.Frame(reports_frame)
        report_buttons.pack(anchor="center")
        ttk.Button(report_buttons, text="Générer un rapport PDF", command=deferred_ui_command(self, self.open_pdf_report)).grid(
            row=0, column=0, padx=6, pady=4
        )
        ttk.Button(report_buttons, text="Générer un rapport Excel", command=deferred_ui_command(self, self.open_excel_report)).grid(
            row=0, column=1, padx=6, pady=4
        )
        ttk.Button(report_buttons, text="Ouvrir le dossier des rapports", command=deferred_ui_command(self, self.open_reports_folder)).grid(
            row=0, column=2, padx=6, pady=4
        )

        if self.user.role in FULL_VISIBILITY_ROLES:
            maintenance_frame = ttk.LabelFrame(container, text="Sauvegarde et restauration", style="Card.TLabelframe")
            maintenance_frame.pack(fill="x", pady=(0, 18))
            ttk.Label(
                maintenance_frame,
                text=self.get_maintenance_text(),
                wraplength=640,
                justify="center",
            ).pack(fill="x", pady=(0, 12))

            maintenance_buttons = ttk.Frame(maintenance_frame)
            maintenance_buttons.pack(anchor="center")
            self.backup_button = ttk.Button(
                maintenance_buttons,
                text="Sauvegarder la base",
                command=deferred_ui_command(self, self.backup_database),
            )
            self.backup_button.grid(row=0, column=0, padx=6, pady=4)
            self.restore_button = ttk.Button(
                maintenance_buttons,
                text="Restaurer une sauvegarde",
                command=deferred_ui_command(self, self.restore_database),
            )
            self.restore_button.grid(row=0, column=1, padx=6, pady=4)
            self.backup_folder_button = ttk.Button(
                maintenance_buttons,
                text="Ouvrir le dossier des sauvegardes",
                command=deferred_ui_command(self, self.open_backups_folder),
            )
            self.backup_folder_button.grid(row=0, column=2, padx=6, pady=4)
            self.reset_database_button = ttk.Button(
                maintenance_buttons,
                text="Réinitialiser la base",
                command=deferred_ui_command(self, self.reset_database),
            )
            self.reset_database_button.grid(row=0, column=3, padx=6, pady=4)
            if self.user.role != "Admin":
                self.backup_button.state(["disabled"])
                self.restore_button.state(["disabled"])
                self.reset_database_button.state(["disabled"])

        actions = ttk.Frame(container)
        actions.pack(anchor="center", pady=(8, 0))
        ttk.Button(actions, text="À propos", command=self.open_about).grid(row=0, column=0, padx=8, pady=4)
        ttk.Button(actions, text="Déconnexion", command=self.logout).grid(row=0, column=1, padx=8, pady=4)
        ttk.Button(actions, text="Quitter", command=self.on_close_app).grid(row=0, column=2, padx=8, pady=4)
        add_copyright_footer(container, wraplength=900).pack(fill="x", pady=(14, 0))

        self.apply_permissions()

    def install_auto_lock(self) -> None:
        DashboardWindow.active_auto_lock_owner = self
        for sequence in AUTO_LOCK_EVENT_SEQUENCES:
            self.bind_all(sequence, self.reset_auto_lock_timer, add="+")
        self.reset_auto_lock_timer()

    def reset_auto_lock_timer(self, _event: tk.Event | None = None) -> None:
        if DashboardWindow.active_auto_lock_owner is not self:
            return
        try:
            if not self.winfo_exists():
                return
        except tk.TclError:
            return
        if self.auto_lock_after_id is not None:
            try:
                self.after_cancel(self.auto_lock_after_id)
            except tk.TclError:
                pass
        self.auto_lock_after_id = self.after(AUTO_LOCK_TIMEOUT_MS, self.lock_due_to_inactivity)

    def cancel_dashboard_timers(self) -> None:
        for attribute_name in (
            "summary_refresh_after_id",
            "live_refresh_after_id",
            "auto_lock_after_id",
            "session_guard_after_id",
        ):
            after_id = getattr(self, attribute_name, None)
            if after_id is not None:
                try:
                    self.after_cancel(after_id)
                except tk.TclError:
                    pass
                setattr(self, attribute_name, None)
        if DashboardWindow.active_auto_lock_owner is self:
            DashboardWindow.active_auto_lock_owner = None

    def lock_due_to_inactivity(self) -> None:
        if DashboardWindow.active_auto_lock_owner is not self:
            return
        self.auto_lock_after_id = None
        try:
            if not self.winfo_exists():
                return
        except tk.TclError:
            return
        messagebox.showinfo(
            "Verrouillage automatique",
            "L'application a été verrouillée après 10 minutes d'inactivité. Veuillez vous reconnecter pour continuer.",
            parent=self,
        )
        self.cancel_dashboard_timers()
        DatabaseHelper.close_current_session()
        self.destroy()
        self.on_logout_callback()

    def schedule_session_guard(self) -> None:
        if self.session_guard_after_id is not None:
            try:
                self.after_cancel(self.session_guard_after_id)
            except tk.TclError:
                pass
        self.session_guard_after_id = self.after(15000, self.perform_session_guard)

    def perform_session_guard(self) -> None:
        self.session_guard_after_id = None
        try:
            if not self.winfo_exists():
                return
        except tk.TclError:
            return
        if not DatabaseHelper.validate_current_session():
            messagebox.showinfo(
                "Session fermee",
                "Cette session a ete fermee parce que ce compte s'est connecte ailleurs.",
                parent=self,
            )
            self.cancel_dashboard_timers()
            DatabaseHelper.close_current_session()
            self.destroy()
            self.on_logout_callback()
            return
        self.schedule_session_guard()

    def is_live_sync_enabled(self) -> bool:
        return DatabaseHelper.is_remote_mode() or is_embedded_server_running()

    def schedule_live_refresh(self) -> None:
        if self.live_refresh_after_id is not None:
            self.after_cancel(self.live_refresh_after_id)
        self.live_refresh_after_id = self.after(REMOTE_REFRESH_INTERVAL_MS, self.perform_live_refresh)

    def perform_live_refresh(self) -> None:
        self.live_refresh_after_id = None
        if not self.winfo_exists():
            return
        self.refresh_summary()
        self.refresh_security_notice()
        if self.is_live_sync_enabled():
            self.schedule_live_refresh()

    def request_refresh_summary(self, delay_ms: int = 50) -> None:
        if not self.winfo_exists():
            return
        if self.summary_refresh_after_id is not None:
            try:
                self.after_cancel(self.summary_refresh_after_id)
            except tk.TclError:
                pass
        self.summary_refresh_after_id = self.after(delay_ms, self._run_requested_summary_refresh)

    def _run_requested_summary_refresh(self) -> None:
        self.summary_refresh_after_id = None
        if not self.winfo_exists():
            return
        self.refresh_summary()
        self.refresh_security_notice()

    def get_maintenance_text(self) -> str:
        if DatabaseHelper.is_remote_mode():
            return (
                "En mode connecté, les sauvegardes et restaurations de l'admin sont executees "
                "directement sur le serveur central pour protéger la base partagée."
            )
        return "Sauvegardez la base dans le dossier local de l'application, puis restaurez une sauvegarde si besoin."

    def hide_notice(self) -> None:
        if self.notice_label is None:
            return
        self.notice_label.destroy()
        self.notice_label = None

    def apply_permissions(self) -> None:
        backup_folder_button = getattr(self, "backup_folder_button", None)
        if backup_folder_button is None:
            return
        if DatabaseHelper.is_remote_mode():
            backup_folder_button.configure(text="Voir les sauvegardes du serveur")
        else:
            backup_folder_button.configure(text="Ouvrir le dossier des sauvegardes")

    def refresh_summary(self) -> None:
        try:
            summary = self.build_dashboard_summary()
        except Exception as exc:
            summary = "Statistiques indisponibles pour le moment."
        self.summary_var.set(summary)
        for refresher in (
            self.refresh_metric_cards,
            self.refresh_alerts,
            self.refresh_recent_activity,
            self.refresh_closure_status,
        ):
            try:
                refresher()
            except Exception:
                continue

    def build_dashboard_summary(self) -> str:
        role = self.user.role
        if role == "Gestionnaire de stock":
            return self.build_stock_summary()
        if role == "Chargé de la production":
            return self.build_production_summary()
        if role == "Gestionnaire des commandes":
            return self.build_orders_and_commissions_summary(include_cash=False)
        if role == "Caissier":
            return self.build_orders_and_commissions_summary(include_cash=True)
        return self.build_admin_summary()

    def build_admin_summary(self) -> str:
        today = date.today()
        month_start = today.replace(day=1)
        orders_summary = DatabaseHelper.get_orders_summary_for_period(month_start, today)
        outstanding_orders = DatabaseHelper.get_global_orders_summary()
        production_summary = DatabaseHelper.get_production_summary_for_period(month_start, today)
        payroll_summary = DatabaseHelper.get_workers_payroll_summary(month_start, today)
        stock_journal = DatabaseHelper.get_stock_journal(today)
        stock_line = "Journal stock du jour indisponible."
        if stock_journal:
            stock_line = (
                "Stock du jour | "
                f"Ouverture farine : {format_number(float(stock_journal.get('FarineOuverture', 0) or 0))} | "
                f"Clôture farine : {format_number(float(stock_journal.get('FarineCloture', 0) or 0))}"
            )
        return (
            f"Indicateurs de {today.strftime('%m/%Y')} | Utilisateurs : {DatabaseHelper.count_users()} | "
            f"Approvisionnements : {DatabaseHelper.count_stock_supplies_for_period(month_start, today)} | "
            f"Sorties stock : {DatabaseHelper.count_stock_exits_for_period(month_start, today)}\n"
            f"Commandes : {int(orders_summary.get('NombreCommandes', 0) or 0)} | "
            f"Total bacs : {int(orders_summary.get('TotalBacs', 0) or 0)} | "
            f"Montant attendu : {format_fc(float(orders_summary.get('MontantAttendu', 0) or 0))}\n"
            f"Production : {int(production_summary.get('TotalBacsProduits', 0) or 0)} bacs produits | "
            f"Écart avec commandes : {int(production_summary.get('EcartCommandes', 0) or 0)}\n"
            f"Caisse du mois : {format_fc(DatabaseHelper.get_cash_total_for_period(month_start, today))} | "
            f"Commissions non payées : {format_fc(DatabaseHelper.get_total_commissions())} | "
            f"Paies du mois : {format_fc(float(payroll_summary.get('TotalNet', 0) or 0))}\n"
            f"Dettes non payées : {format_fc(float(outstanding_orders.get('TotalDettes', 0) or 0))} | "
            f"Commandes avec dette : {DatabaseHelper.count_orders_with_debt()}\n"
            f"{stock_line}"
        )

    def build_stock_summary(self) -> str:
        today = date.today()
        stock_journal = DatabaseHelper.get_stock_journal(today)
        stock_exits = DatabaseHelper.list_stock_exits_by_date(today)
        stock_supplies = DatabaseHelper.list_stock_supplies_by_date(today)
        if not stock_journal:
            return (
                f"Stock du jour - {today.strftime('%d/%m/%Y')}\n"
                "Aucun journal de stock n'est disponible pour aujourd'hui."
            )
        return (
            f"Stock du jour - {today.strftime('%d/%m/%Y')}\n"
            f"Approvisionnements : {len(stock_supplies)} | Sorties du jour : {len(stock_exits)}\n"
            f"Ouverture | Farine : {format_number(float(stock_journal.get('FarineOuverture', 0) or 0))} | "
            f"Levure : {format_number(float(stock_journal.get('LevureOuverture', 0) or 0))} | "
            f"Sel : {format_number(float(stock_journal.get('SelOuverture', 0) or 0))} | "
            f"Huile : {format_number(float(stock_journal.get('HuileOuverture', 0) or 0))}\n"
            f"Clôture | Farine : {format_number(float(stock_journal.get('FarineCloture', 0) or 0))} | "
            f"Levure : {format_number(float(stock_journal.get('LevureCloture', 0) or 0))} | "
            f"Sel : {format_number(float(stock_journal.get('SelCloture', 0) or 0))} | "
            f"Huile : {format_number(float(stock_journal.get('HuileCloture', 0) or 0))}"
        )

    def build_production_summary(self) -> str:
        today = date.today()
        summary = DatabaseHelper.get_production_summary_for_period(today.replace(day=1), today)
        return (
            f"Production du mois {today.strftime('%m/%Y')}\n"
            f"Commandés : {int(summary.get('TotalBacsCommandes', 0) or 0)} bacs | "
            f"Produits : {int(summary.get('TotalBacsProduits', 0) or 0)} bacs | "
            f"Écart : {int(summary.get('EcartCommandes', 0) or 0)}\n"
            f"Livrés aux dépositaires : {int(summary.get('TotalBacsLivresDepositaires', 0) or 0)} | "
            f"Livrés aux mamans : {int(summary.get('TotalBacsLivresMamans', 0) or 0)}\n"
            f"Restants : {int(summary.get('TotalBacsRestants', 0) or 0)} | "
            f"Foutus : {int(summary.get('TotalBacsFoutus', 0) or 0)} | "
            f"Couverture : {format_number(float(summary.get('TauxCouverture', 0) or 0))} %"
        )

    def build_orders_and_commissions_summary(self, include_cash: bool) -> str:
        today = date.today()
        month_start = today.replace(day=1)
        orders_summary = DatabaseHelper.get_orders_summary_for_period(month_start, today)
        outstanding_orders = DatabaseHelper.get_global_orders_summary()
        lines = [
            f"Commandes et commissions - {today.strftime('%m/%Y')}",
            (
                f"Nombre de commandes : {int(orders_summary.get('NombreCommandes', 0) or 0)} | "
                f"Commandes avec dette : {int(outstanding_orders.get('NombreAvecDette', 0) or 0)}"
            ),
            (
                f"Total bacs : {int(orders_summary.get('TotalBacs', 0) or 0)} | "
                f"Montant attendu : {format_fc(float(orders_summary.get('MontantAttendu', 0) or 0))}"
            ),
            (
                f"Montant reçu : {format_fc(float(orders_summary.get('MontantRecu', 0) or 0))} | "
                f"Dettes non payées : {format_fc(float(outstanding_orders.get('TotalDettes', 0) or 0))}"
            ),
            f"Avances clients disponibles : {format_fc(float(outstanding_orders.get('AvancesDisponibles', 0) or 0))}",
            f"Commissions non payées : {format_fc(DatabaseHelper.get_total_commissions())}",
        ]
        if include_cash:
            cash_today = DatabaseHelper.get_cash_for_date(date.today())
            expenses_today = float(cash_today.get("MontantTotalDepenses", 0) or 0)
            payroll_summary = DatabaseHelper.get_workers_payroll_summary(month_start, today)
            lines.append(
                f"Dépenses du jour : {format_fc(expenses_today)} | Caisse du mois : "
                f"{format_fc(DatabaseHelper.get_cash_total_for_period(month_start, today))}"
            )
            lines.append(
                "Travailleurs : "
                f"{int(payroll_summary.get('TravailleursActifs', 0) or 0)} actif(s) | "
                f"Paies : {format_fc(float(payroll_summary.get('TotalNet', 0) or 0))}"
            )
        return "\n".join(lines)

    def refresh_metric_cards(self) -> None:
        cards = self.build_metric_cards_data()
        for index, card in enumerate(self.metric_cards):
            if index >= len(cards):
                card.update_card("", "", "")
                card.grid_remove()
                continue
            title, value, subtitle = cards[index]
            card.update_card(title, value, subtitle)
            card.grid()

    def build_metric_cards_data(self) -> list[tuple[str, str, str]]:
        today = date.today()
        month_start = today.replace(day=1)
        month_label = today.strftime("%m/%Y")
        orders_summary = DatabaseHelper.get_orders_summary_for_period(month_start, today)
        outstanding_orders = DatabaseHelper.get_global_orders_summary()
        orders_summary["TotalDettes"] = outstanding_orders.get("TotalDettes", 0)
        orders_summary["NombreAvecDette"] = outstanding_orders.get("NombreAvecDette", 0)
        orders_summary["AvancesDisponibles"] = outstanding_orders.get("AvancesDisponibles", 0)
        debt_alerts = DatabaseHelper.get_debt_alerts(limit=5)
        commission_total = DatabaseHelper.get_total_commissions()
        cash_total = DatabaseHelper.get_cash_total_for_period(month_start, today)
        production_month = DatabaseHelper.get_production_summary_for_period(month_start, today)
        payroll_summary = DatabaseHelper.get_workers_payroll_summary(month_start, today)
        cash_rows = DatabaseHelper.list_cash_balance_by_period(month_start, today)
        paid_debts_month = sum(float(row.get("DettesPayeesAujourdHui", 0) or 0) for row in cash_rows)

        if self.user.role == "Gestionnaire de stock":
            configuration = DatabaseHelper.get_stock_configuration()
            summary = DatabaseHelper.get_stock_summary()
            return [
                ("Farine restante", format_number(float(summary.get("FarineRestante", 0) or 0)), f"Seuil : {format_number(float(configuration.get('FarineAlerteMin', 0) or 0))}"),
                ("Levure restante", format_number(float(summary.get("LevureRestante", 0) or 0)), f"Seuil : {format_number(float(configuration.get('LevureAlerteMin', 0) or 0))}"),
                ("Sel restant", format_number(float(summary.get("SelRestant", 0) or 0)), f"Seuil : {format_number(float(configuration.get('SelAlerteMin', 0) or 0))}"),
                ("Huile restante", format_number(float(summary.get("HuileRestante", 0) or 0)), f"Seuil : {format_number(float(configuration.get('HuileAlerteMin', 0) or 0))}"),
            ]
        if self.user.role == "Gestionnaire des commandes":
            return [
                ("Commandes du mois", str(int(orders_summary.get("NombreCommandes", 0) or 0)), month_label),
                ("Bacs du mois", str(int(orders_summary.get("TotalBacs", 0) or 0)), month_label),
                ("Avances clients", format_fc(float(orders_summary.get("AvancesDisponibles", 0) or 0)), "Solde à reporter"),
                ("Commissions non payées", format_fc(commission_total), "Solde cumulé"),
            ]
        if self.user.role == "Chargé de la production":
            return [
                ("Bacs commandés ce mois", str(int(production_month.get("TotalBacsCommandes", 0) or 0)), month_label),
                ("Bacs produits ce mois", str(int(production_month.get("TotalBacsProduits", 0) or 0)), f"Écart : {int(production_month.get('EcartCommandes', 0) or 0)}"),
                ("Bacs restants ce mois", str(int(production_month.get("TotalBacsRestants", 0) or 0)), month_label),
                ("Bacs foutus ce mois", str(int(production_month.get("TotalBacsFoutus", 0) or 0)), f"Couverture : {format_number(float(production_month.get('TauxCouverture', 0) or 0))} %"),
            ]
        if self.user.role == "Caissier":
            return [
                ("Montant reçu ce mois", format_fc(float(orders_summary.get("MontantRecu", 0) or 0)), month_label),
                ("Dettes payées ce mois", format_fc(paid_debts_month), month_label),
                ("Caisse du mois", format_fc(cash_total), "Entrées moins dépenses"),
                ("Dettes ouvertes", format_fc(float(orders_summary.get("TotalDettes", 0) or 0)), f"{len(debt_alerts)} client(s) prioritaire(s)"),
                ("Avances clients", format_fc(float(orders_summary.get("AvancesDisponibles", 0) or 0)), "Montants à reporter"),
                (
                    "Travailleurs",
                    str(int(payroll_summary.get("TravailleursActifs", 0) or 0)),
                    f"Paies du mois : {format_fc(float(payroll_summary.get('TotalNet', 0) or 0))}",
                ),
            ]
        stock_summary = DatabaseHelper.get_stock_summary()
        return [
            ("Stock", format_number(float(stock_summary.get("FarineRestante", 0) or 0)), "Farine restante"),
            ("Approvisionnements du mois", str(DatabaseHelper.count_stock_supplies_for_period(month_start, today)), month_label),
            ("Commandes du mois", str(int(orders_summary.get("NombreCommandes", 0) or 0)), f"{int(orders_summary.get('TotalBacs', 0) or 0)} bacs"),
            ("Production du mois", str(int(production_month.get("TotalBacsProduits", 0) or 0)), f"Écart : {int(production_month.get('EcartCommandes', 0) or 0)} bacs"),
            ("Caisse du mois", format_fc(cash_total), month_label),
            ("Commissions non payées", format_fc(commission_total), "Solde cumulé"),
            ("Dettes ouvertes", format_fc(float(orders_summary.get("TotalDettes", 0) or 0)), f"{len(debt_alerts)} alerte(s) prioritaires"),
            (
                "Travailleurs",
                str(int(payroll_summary.get("TravailleursActifs", 0) or 0)),
                f"Paies du mois : {format_fc(float(payroll_summary.get('TotalNet', 0) or 0))}",
            ),
        ]

    def refresh_alerts(self) -> None:
        try:
            stock_alerts = DatabaseHelper.get_low_stock_alerts()
            debt_alerts = DatabaseHelper.get_debt_alerts(limit=5)
        except Exception:
            self.stock_alerts_var.set("Alertes indisponibles pour le moment.")
            self.debt_alerts_var.set("Alertes indisponibles pour le moment.")
            return

        if stock_alerts:
            lines = []
            for row in stock_alerts:
                lines.append(
                    f"{row['Article']} : restant {format_number(float(row['StockRestant']))} {row['Unite']} | seuil {format_number(float(row['SeuilAlerte']))}"
                )
            self.stock_alerts_var.set("\n".join(lines))
        else:
            self.stock_alerts_var.set("Aucun article n'est en dessous du seuil d'alerte.")

        if debt_alerts:
            lines = []
            for row in debt_alerts:
                lines.append(
                    f"{row['Client']} : {format_fc(float(row['DetteTotale'] or 0))} | {int(row['NombreCommandes'] or 0)} commande(s) | dernière : {row['DerniereCommande']}"
                )
            self.debt_alerts_var.set("\n".join(lines))
        else:
            self.debt_alerts_var.set("Aucune dette en attente pour le moment.")

    def show_role_critical_alerts(self) -> None:
        if self.critical_alerts_shown or not self.winfo_exists():
            return
        self.critical_alerts_shown = True
        messages: list[str] = []
        try:
            if self.user.role in {"Admin", "Directeur Général", "Gestionnaire de stock"}:
                stock_alerts = DatabaseHelper.get_low_stock_alerts()
                if stock_alerts:
                    lines = ["Stock critique :"]
                    for row in stock_alerts[:5]:
                        lines.append(
                            f"- {row['Article']} : restant {format_number(float(row['StockRestant']))} {row['Unite']}"
                        )
                    messages.append("\n".join(lines))
            if self.user.role in {"Admin", "Directeur Général", "Caissier", "Gestionnaire des commandes"}:
                debt_alerts = DatabaseHelper.get_debt_alerts(limit=5)
                if debt_alerts:
                    lines = ["Dettes critiques :"]
                    for row in debt_alerts:
                        lines.append(f"- {row['Client']} : {format_fc(float(row['DetteTotale'] or 0))}")
                    messages.append("\n".join(lines))
        except Exception:
            return
        if not messages:
            return
        messagebox.showwarning(
            "Alertes critiques",
            "\n\n".join(messages) + "\n\nCes alertes restent visibles sur le tableau de bord.",
            parent=self,
        )

    def refresh_recent_activity(self) -> None:
        if self.user.role not in FULL_VISIBILITY_ROLES:
            return
        try:
            rows = DatabaseHelper.get_recent_activity_summary(limit=5)
        except Exception:
            self.recent_activity_var.set("Historique indisponible pour le moment.")
            return
        if not rows:
            self.recent_activity_var.set("Aucune action enregistrée pour le moment.")
            return
        lines = []
        for row in rows:
            lines.append(
                f"{format_activity_timestamp(row.get('DateAction'))} | {row.get('NomComplet')} | {row.get('Module')} | {row.get('Action')}"
            )
        self.recent_activity_var.set("\n".join(lines))

    def refresh_closure_status(self) -> None:
        if self.user.role not in FULL_VISIBILITY_ROLES:
            return
        date_field = getattr(self, "closure_date_field", None)
        if date_field is None:
            return
        try:
            target_date = date_field.get_date()
        except ValueError as exc:
            self.closure_status_var.set(str(exc))
            return

        try:
            closure = DatabaseHelper.get_day_closure(target_date)
        except Exception:
            self.closure_status_var.set("Statut de clôture indisponible pour le moment.")
            return

        if not closure:
            self.closure_status_var.set(
                f"Journée du {target_date.strftime('%d/%m/%Y')} ouverte. "
                "Vous pouvez encore modifier les écritures."
            )
            return

        lines = [
            f"Statut : {closure.get('StatutAffichage', 'Clôturée')}",
            (
                f"Clôturée le {format_activity_timestamp(closure.get('DateCloture'))} "
                f"par {closure.get('NomComplet') or closure.get('Identifiant')}"
            ),
        ]
        report_path = str(closure.get("CheminRapport", "") or "").strip()
        backup_path = str(closure.get("CheminSauvegarde", "") or "").strip()
        if report_path:
            lines.append(f"Rapport : {report_path}")
        if backup_path:
            lines.append(f"Sauvegarde : {backup_path}")
        if bool(closure.get("EstReouverte", False)):
            reopen_actor = closure.get("ReouvertParNomComplet") or closure.get("ReouvertParIdentifiant") or "Admin"
            lines.append(
                f"Réouverte le {format_activity_timestamp(closure.get('DateReouverture'))} par {reopen_actor}"
            )
            reopen_reason = str(closure.get("MotifReouverture", "") or "").strip()
            if reopen_reason:
                lines.append(f"Motif : {reopen_reason}")
        self.closure_status_var.set("\n".join(lines))

    def close_selected_day(self) -> None:
        if self.user.role not in CLOSURE_ROLES:
            messagebox.showwarning("Clôture journalière", "Accès non autorisé.")
            return
        date_field = getattr(self, "closure_date_field", None)
        if date_field is None:
            return
        try:
            target_date = date_field.get_date()
        except ValueError as exc:
            messagebox.showwarning("Clôture journalière", str(exc))
            return

        if not messagebox.askyesno(
            "Clôture journalière",
            (
                f"Voulez-vous clôturer la journée du {target_date.strftime('%d/%m/%Y')} ?\n\n"
                "Cette opération va figer les écritures, générer un rapport signé "
                "et créer automatiquement une sauvegarde de sécurité."
            ),
        ):
            return

        try:
            closure = DatabaseHelper.close_day(
                target_date,
                self.user.identifiant,
                self.user.display_name,
                self.user.role,
            )
        except ValueError as exc:
            messagebox.showwarning("Clôture journalière", str(exc))
            return
        except Exception as exc:
            messagebox.showerror("Clôture journalière", str(exc))
            return

        self.refresh_summary()
        report_path = str(closure.get("CheminRapport", "") or "").strip()
        backup_path = str(closure.get("CheminSauvegarde", "") or "").strip()
        message = [f"La journée du {target_date.strftime('%d/%m/%Y')} a été clôturée avec succès."]
        if report_path:
            message.append(f"Rapport : {report_path}")
        if backup_path:
            message.append(f"Sauvegarde : {backup_path}")
        message.append("")
        message.append("Voulez-vous ouvrir le rapport de clôture ?")
        if messagebox.askyesno("Clôture journalière", "\n".join(message)):
            try:
                open_file(report_path)
            except Exception as exc:
                messagebox.showerror("Clôture journalière", str(exc))

    def reopen_selected_day(self) -> None:
        if self.user.role != "Admin":
            messagebox.showwarning("Clôture journalière", "Accès non autorisé.")
            return
        date_field = getattr(self, "closure_date_field", None)
        if date_field is None:
            return
        try:
            target_date = date_field.get_date()
        except ValueError as exc:
            messagebox.showwarning("Clôture journalière", str(exc))
            return

        reason = simpledialog.askstring(
            "Réouverture d'une journée",
            f"Motif de réouverture pour le {target_date.strftime('%d/%m/%Y')} :",
            parent=self,
        )
        if reason is None:
            return

        try:
            DatabaseHelper.reopen_day(
                target_date,
                self.user.identifiant,
                self.user.display_name,
                self.user.role,
                reason,
            )
        except ValueError as exc:
            messagebox.showwarning("Clôture journalière", str(exc))
            return
        except Exception as exc:
            messagebox.showerror("Clôture journalière", str(exc))
            return

        self.refresh_summary()
        messagebox.showinfo(
            "Clôture journalière",
            f"La journée du {target_date.strftime('%d/%m/%Y')} a été réouverte.",
        )

    def open_closure_history(self) -> None:
        if self.user.role not in FULL_VISIBILITY_ROLES:
            messagebox.showwarning("Accès refusé", "Accès non autorisé.")
            return
        window = DayClosuresWindow(self)
        self.wait_window(window)
        self.refresh_summary()

    def refresh_security_notice(self) -> None:
        if DatabaseHelper.is_using_default_password(self.user.identifiant):
            self.security_message_var.set(
                "Attention : ce compte utilise encore le mot de passe par défaut. "
                "Changez-le maintenant pour mieux protéger l'application."
            )
            self.security_label.configure(foreground=DANGER_COLOR)
            return

        self.security_message_var.set(
            "Vous pouvez changer votre mot de passe à tout moment depuis ce tableau de bord."
        )
        self.security_label.configure(foreground=SUCCESS_COLOR)

    def check_monthly_report_obligation(self, *, silent: bool = False) -> bool:
        try:
            obligation = DatabaseHelper.get_monthly_report_obligation(self.user.role)
        except Exception as exc:
            if not silent:
                messagebox.showwarning("Rapport mensuel", str(exc), parent=self)
            return False

        self.monthly_report_obligation = obligation if bool(obligation.get("Required")) else None
        if self.monthly_report_obligation is None:
            return False

        if not silent:
            month_label = str(obligation.get("MonthLabel") or obligation.get("YearMonth") or "")
            messagebox.showwarning(
                "Rapport mensuel obligatoire",
                (
                    f"Le rapport mensuel de {month_label} doit être généré.\n\n"
                    "À partir du 8 du mois, l'impression/génération du rapport mensuel du mois précédent "
                    "devient obligatoire. Les grands modules resteront bloqués jusqu'à la génération du rapport."
                ),
                parent=self,
            )
            self.open_pdf_report(required_monthly=True)
        return True

    def enforce_monthly_report_obligation(self) -> bool:
        if self.check_monthly_report_obligation(silent=True):
            month_label = str(self.monthly_report_obligation.get("MonthLabel") or "") if self.monthly_report_obligation else ""
            messagebox.showwarning(
                "Rapport mensuel obligatoire",
                (
                    f"Veuillez générer le rapport mensuel de {month_label} avant de continuer.\n\n"
                    "La fenêtre des rapports PDF va s'ouvrir en mode mensuel."
                ),
                parent=self,
            )
            self.open_pdf_report(required_monthly=True)
            return True
        return False

    def start_startup_update_check(self) -> None:
        if self.update_check_running:
            return
        self.update_check_running = UpdateChecker.run_startup_check_async(self.update_result_queue)
        if self.update_check_running:
            self.after(300, self.poll_update_results)

    def poll_update_results(self) -> None:
        if not self.winfo_exists():
            return

        try:
            result = self.update_result_queue.get_nowait()
        except Empty:
            self.after(300, self.poll_update_results)
            return

        self.update_check_running = False
        if result.status == "update_available" and result.update_info is not None:
            self.show_update_dialog(result)

    def backup_database(self) -> None:
        if self.user.role != "Admin":
            messagebox.showwarning("Sauvegarde", "Accès non autorisé.")
            return
        try:
            backup_path = DatabaseHelper.backup_database()
        except Exception as exc:
            messagebox.showerror("Sauvegarde", str(exc))
            return
        log_user_action(self, "Sauvegarde", "Sauvegarde créée", str(backup_path))

        if DatabaseHelper.is_remote_mode():
            prompt = (
                "Une sauvegarde a été créée sur le serveur central.\n\n"
                f"Fichier : {backup_path}\n\n"
                "Voulez-vous voir les sauvegardes du serveur ?"
            )
        else:
            prompt = (
                "La sauvegarde a été créée avec succès.\n\n"
                f"Fichier : {backup_path}\n\n"
                "Voulez-vous ouvrir le dossier des sauvegardes ?"
            )

        open_folder = messagebox.askyesno("Sauvegarde terminée", prompt)
        if open_folder:
            self.open_backups_folder()

    def restore_database(self) -> None:
        if self.user.role != "Admin":
            messagebox.showwarning("Restauration", "Accès non autorisé.")
            return
        if DatabaseHelper.is_remote_mode():
            selected_backup = self.choose_remote_backup_for_restore()
            if selected_backup is None:
                return
            file_path = str(selected_backup)
        else:
            file_path = filedialog.askopenfilename(
                title="Choisir une sauvegarde",
                initialdir=str(DatabaseHelper.backups_dir),
                filetypes=[
                    ("Bases SQLite", "*.db *.sqlite *.sqlite3 *.bak"),
                    ("Tous les fichiers", "*.*"),
                ],
            )
        if not file_path:
            return

        warning_text = (
            "La restauration va remplacer les données actuelles.\n"
            "Une sauvegarde de sécurité sera créée automatiquement avant la restauration.\n\n"
            "Voulez-vous continuer ?"
        )
        if DatabaseHelper.is_remote_mode():
            warning_text = (
                "La restauration va remplacer les données du serveur central.\n"
                "Une sauvegarde de sécurité sera créée automatiquement avant la restauration.\n\n"
                "Tous les postes devront ensuite se reconnecter.\n\n"
                "Voulez-vous continuer ?"
            )
        if not messagebox.askyesno(
            "Restaurer une sauvegarde",
            warning_text,
        ):
            return

        try:
            safety_backup, _ = DatabaseHelper.restore_database(file_path)
        except Exception as exc:
            messagebox.showerror("Restauration", str(exc))
            return

        details = f"Sauvegarde restaurée depuis : {file_path}"
        if safety_backup is not None:
            details += f"\nSauvegarde de sécurité créée ici : {safety_backup}"

        if DatabaseHelper.is_remote_mode():
            details += "\n\nL'application va se fermer pour forcer une nouvelle connexion au serveur central."
        else:
            details += "\n\nL'application va se fermer pour recharger les nouvelles données."
        log_user_action(self, "Sauvegarde", "Restauration effectuée", details)
        messagebox.showinfo("Restauration terminée", details)
        self.root.destroy()

    def reset_database(self) -> None:
        if self.user.role != "Admin":
            messagebox.showwarning("Réinitialisation", "Accès non autorisé.")
            return

        if DatabaseHelper.is_remote_mode():
            warning_text = (
                "Cette action va remettre à zéro la base du serveur central : commandes, caisse, stock, "
                "production, travailleurs, utilisateurs, rapports internes et historique.\n\n"
                "Une sauvegarde de sécurité sera créée automatiquement avant la réinitialisation.\n\n"
                "Tous les postes et la version web devront ensuite recréer le premier Admin et se reconnecter.\n\n"
                "Voulez-vous continuer ?"
            )
        else:
            warning_text = (
                "Cette action va remettre à zéro la base de ce poste : commandes, caisse, stock, production, "
                "travailleurs, utilisateurs, rapports internes et historique.\n\n"
                "Une sauvegarde de sécurité sera créée automatiquement avant la réinitialisation.\n\n"
                "L'application redemandera la création du premier Admin au prochain démarrage.\n\n"
                "Voulez-vous continuer ?"
            )

        if not messagebox.askyesno("Réinitialiser la base", warning_text, parent=self):
            return

        confirmation = simpledialog.askstring(
            "Confirmation",
            "Tapez REINITIALISER pour confirmer la remise à zéro complète.",
            parent=self,
        )
        if confirmation != "REINITIALISER":
            messagebox.showinfo("Réinitialisation annulée", "La base n'a pas été modifiée.", parent=self)
            return

        try:
            safety_backup = DatabaseHelper.reset_database_to_empty()
        except Exception as exc:
            messagebox.showerror("Réinitialisation impossible", str(exc), parent=self)
            return

        details = "La base a été remise à zéro."
        if safety_backup is not None:
            details += f"\n\nSauvegarde de sécurité : {safety_backup}"
        details += "\n\nL'application va se fermer. Relancez-la pour créer le premier administrateur."
        messagebox.showinfo("Réinitialisation terminée", details, parent=self)
        self.root.destroy()

    def open_backups_folder(self) -> None:
        if DatabaseHelper.is_remote_mode():
            self.show_server_backups_browser()
            return
        open_folder(DatabaseHelper.backups_dir)

    def show_server_backups_browser(self) -> None:
        browser = ServerBackupsWindow(self, selection_mode=False)
        self.wait_window(browser)

    def choose_remote_backup_for_restore(self) -> Path | None:
        browser = ServerBackupsWindow(self, selection_mode=True)
        self.wait_window(browser)
        return browser.selected_backup_path

    def open_reports_folder(self) -> None:
        open_folder(DatabaseHelper.get_reports_dir_for_user(self.user.identifiant))

    def open_activity_history(self) -> None:
        if self.user.role not in FULL_VISIBILITY_ROLES:
            messagebox.showwarning("Accès refusé", "Accès non autorisé.")
            return
        window = ActivityHistoryWindow(self)
        self.wait_window(window)
        self.refresh_summary()

    def open_pdf_report(self, required_monthly: bool = False) -> None:
        window = PdfReportWindow(self, required_monthly=required_monthly)
        self.wait_window(window)
        self.check_monthly_report_obligation(silent=True)

    def open_excel_report(self) -> None:
        window = ExcelReportWindow(self)
        self.wait_window(window)

    def show_update_dialog(self, result: UpdateCheckResult) -> None:
        update_info = result.update_info
        if update_info is None:
            return
        message = (
            "Une nouvelle version de l'application est disponible.\n\n"
            f"Version installée : {APP_VERSION}\n"
            f"Nouvelle version : {update_info.version}"
        )

        if update_info.published_at:
            message += f"\nDate de publication : {update_info.published_at}"

        if update_info.notes:
            message += f"\n\nNotes :\n{update_info.notes}"

        if result.mandatory:
            message += (
                "\n\nCette mise à jour est maintenant obligatoire. "
                f"Elle est disponible depuis {result.days_since_available} jour(s), "
                f"et le délai autorisé est de {result.mandatory_after_days} jours.\n\n"
                "Le lien de téléchargement va s'ouvrir. Installez la nouvelle version pour continuer."
            )
            messagebox.showwarning("Mise à jour obligatoire", message)
            webbrowser.open(update_info.download_url)
            self.cancel_dashboard_timers()
            DatabaseHelper.close_current_session()
            self.root.destroy()
            return

        remaining_days = max(result.mandatory_after_days - result.days_since_available, 0)
        if result.first_seen_at:
            message += (
                f"\n\nCette version deviendra obligatoire dans {remaining_days} jour(s) "
                "si elle n'est pas installée."
            )

        message += "\n\nVoulez-vous ouvrir le lien de téléchargement ?"

        if messagebox.askyesno("Mise à jour disponible", message):
            webbrowser.open(update_info.download_url)

    def can_access(self, module_name: str, *, show_warning: bool = True) -> bool:
        allowed = ROLE_MODULE_ACCESS.get(self.user.role, set())
        if module_name not in allowed:
            if show_warning:
                messagebox.showwarning("Accès refusé", "Accès non autorisé.")
            return False
        return True

    def is_module_read_only(self, module_name: str) -> bool:
        return module_name in ROLE_READ_ONLY_MODULES.get(self.user.role, set())

    def show_module_opening_overlay(self, module_label: str) -> None:
        self.destroy_module_opening_overlay()
        overlay = tk.Toplevel(self)
        overlay.overrideredirect(True)
        overlay.configure(bg=SURFACE_BACKGROUND)
        overlay.resizable(False, False)
        frame = ttk.Frame(overlay, padding=(24, 18, 24, 18))
        frame.pack(fill="both", expand=True)
        ttk.Label(
            frame,
            text=f"Ouverture de {module_label}...",
            font=(UI_FONT_FAMILY, 15, "bold"),
            foreground=PRIMARY_COLOR,
            justify="center",
        ).pack(fill="x")
        ttk.Label(
            frame,
            text="Préparation de la fenêtre, un instant.",
            foreground=MUTED_TEXT_COLOR,
            justify="center",
        ).pack(fill="x", pady=(8, 0))

        overlay.update_idletasks()
        width = max(overlay.winfo_reqwidth(), 380)
        height = max(overlay.winfo_reqheight(), 112)
        work_x, work_y, work_width, work_height = get_work_area_geometry(self)
        x = work_x + max((work_width - width) // 2, 0)
        y = work_y + max((work_height - height) // 2, 0)
        overlay.geometry(f"{width}x{height}+{x}+{y}")
        try:
            overlay.attributes("-topmost", True)
        except tk.TclError:
            pass
        overlay.lift()
        overlay.update()
        self.module_opening_overlay = overlay

    def destroy_module_opening_overlay(self) -> None:
        overlay = self.module_opening_overlay
        self.module_opening_overlay = None
        if overlay is not None and overlay.winfo_exists():
            overlay.destroy()

    def open_large_module(self, window_factory: Callable[[DashboardWindow], BaseModuleWindow], module_label: str) -> None:
        if self.module_opening:
            return
        if self.enforce_monthly_report_obligation():
            return
        self.module_opening = True
        self.configure(cursor="watch")
        self.show_module_opening_overlay(module_label)
        self.after(10, lambda: self._open_large_module_now(window_factory))

    def _open_large_module_now(self, window_factory: Callable[[DashboardWindow], BaseModuleWindow]) -> None:
        window: BaseModuleWindow | None = None
        try:
            window = window_factory(self)
            window.update_idletasks()
            window.lift()
            self.destroy_module_opening_overlay()
            self.withdraw()
            self.wait_window(window)
        except Exception as exc:
            self.destroy_module_opening_overlay()
            messagebox.showerror("Ouverture du module", str(exc), parent=self)
        finally:
            self.module_opening = False
            self.configure(cursor="")
            if self.winfo_exists():
                restore_maximized_window(self, 980, 640)
                self.after(120, lambda: restore_maximized_window(self, 980, 640))
                self.request_refresh_summary(50)

    def open_cash(self) -> None:
        if not self.can_access("Caisse"):
            return
        self.open_large_module(CashWindow, "la caisse")

    def open_stock(self) -> None:
        if not self.can_access("Stock"):
            return
        self.open_large_module(StockWindow, "le stock")

    def open_production(self) -> None:
        if not self.can_access("Production"):
            return
        self.open_large_module(ProductionWindow, "la production")

    def open_orders(self) -> None:
        if not self.can_access("Commandes"):
            return
        self.open_large_module(OrdersWindow, "les commandes")

    def open_commissions(self) -> None:
        if not self.can_access("Commissions"):
            return
        self.open_large_module(CommissionsWindow, "les commissions")

    def open_workers_payroll(self) -> None:
        if not self.can_access("Travailleurs"):
            return
        self.open_large_module(WorkersPayrollWindow, "les travailleurs et paies")

    def open_users(self) -> None:
        if self.user.role not in FULL_VISIBILITY_ROLES:
            messagebox.showwarning("Accès refusé", "Accès non autorisé.")
            return
        self.open_large_module(UsersWindow, "les utilisateurs")

    def logout(self) -> None:
        if not messagebox.askyesno("Confirmation", "Voulez-vous vraiment vous déconnecter ?"):
            return
        self.cancel_dashboard_timers()
        DatabaseHelper.close_current_session()
        self.destroy()
        self.on_logout_callback()

    def open_change_password(self) -> None:
        window = ChangePasswordWindow(self, self.user.identifiant, self.refresh_security_notice)
        self.wait_window(window)
        self.refresh_security_notice()

    def require_initial_password_change(self) -> None:
        messagebox.showwarning(
            "Sécurité obligatoire",
            "Le mot de passe initial doit être remplacé avant de continuer.",
            parent=self,
        )
        self.open_change_password()
        if DatabaseHelper.is_using_default_password(self.user.identifiant):
            messagebox.showerror(
                "Sécurité obligatoire",
                "Le changement de mot de passe n'a pas été effectué. La session va être fermée.",
                parent=self,
            )
            self.cancel_dashboard_timers()
            DatabaseHelper.close_current_session()
            self.destroy()
            self.on_logout_callback()

    def open_about(self) -> None:
        AboutWindow(self)

    def on_close_app(self) -> None:
        if not messagebox.askyesno("Confirmation", "Voulez-vous vraiment quitter l'application ?"):
            return
        self.cancel_dashboard_timers()
        DatabaseHelper.close_current_session()
        self.root.destroy()


class BaseModuleWindow(tk.Toplevel):
    DIRECTOR_DISABLED_BUTTON_PREFIXES = (
        "Enregistrer",
        "Modifier",
        "Supprimer",
        "Nouveau",
        "Nouvelle",
        "Ajouter",
        "Approvisionner",
        "Paramètres",
        "Restaurer",
        "Sauvegarder",
    )

    def __init__(
        self,
        parent: DashboardWindow,
        title: str,
        geometry: str,
        *,
        start_maximized: bool = True,
        min_width: int = 760,
        min_height: int = 520,
    ) -> None:
        super().__init__(parent)
        self.parent = parent
        self.live_refresh_after_id: str | None = None
        self.header_title = title
        self.title(title)
        self.geometry(geometry)
        self.configure(bg=MODULE_BACKGROUND)
        self.resizable(True, True)
        apply_window_icon(self)
        self.protocol("WM_DELETE_WINDOW", self.close_window)
        if not start_maximized:
            self.transient(parent)
            self.grab_set()
        self.scrollable_content = ScrollableContent(self, padding=(10, 4, 10, 10), background=MODULE_BACKGROUND)
        self.scrollable_content.pack(fill="both", expand=True)
        shell = self.scrollable_content.content
        header = create_branded_header(shell, title, logo_size=FORM_LOGO_SIZE, wraplength=860)
        setattr(self, "_header_logo", getattr(header, "_header_logo", None))
        self.body = ttk.Frame(shell)
        self.body.pack(fill="both", expand=True)
        add_copyright_footer(shell, wraplength=900).pack(fill="x", pady=(10, 0))
        if start_maximized:
            maximize_window(self, min_width, min_height)
        else:
            center_window(self)
        if self.parent.is_live_sync_enabled():
            self.schedule_live_refresh()
        self.after_idle(self.apply_director_read_only_mode)

    def apply_director_read_only_mode(self) -> None:
        if self.parent.user.role != "Directeur Général" or not self.winfo_exists():
            return

        def visit(widget: tk.Misc) -> None:
            for child in widget.winfo_children():
                try:
                    text = str(child.cget("text") or "").strip()
                except tk.TclError:
                    text = ""
                if text.startswith(self.DIRECTOR_DISABLED_BUTTON_PREFIXES):
                    try:
                        child.state(["disabled"])
                    except (AttributeError, tk.TclError):
                        try:
                            child.configure(state="disabled")
                        except tk.TclError:
                            pass
                visit(child)

        visit(self.body)

    def close_window(self) -> None:
        if self.live_refresh_after_id is not None:
            self.after_cancel(self.live_refresh_after_id)
            self.live_refresh_after_id = None
        self.destroy()

    def schedule_live_refresh(self) -> None:
        if self.live_refresh_after_id is not None:
            self.after_cancel(self.live_refresh_after_id)
        self.live_refresh_after_id = self.after(REMOTE_REFRESH_INTERVAL_MS, self.perform_live_refresh)

    def perform_live_refresh(self) -> None:
        self.live_refresh_after_id = None
        if not self.winfo_exists():
            return
        if not self.should_pause_live_refresh():
            try:
                self.refresh_live_view()
            except Exception:
                pass
        if self.parent.is_live_sync_enabled():
            self.schedule_live_refresh()

    def should_pause_live_refresh(self) -> bool:
        if bool(getattr(self, "edit_mode", False)):
            return True
        widget = self.focus_get()
        if widget is None:
            return False
        return str(widget.winfo_class()) in {
            "Entry",
            "TEntry",
            "Text",
            "TCombobox",
            "Combobox",
            "Spinbox",
            "TSpinbox",
            "Treeview",
        }

    def refresh_live_view(self) -> None:
        return

    def is_read_only_module(self, module_name: str) -> bool:
        return self.parent.is_module_read_only(module_name)

    def ensure_module_writable(self, module_name: str, title: str | None = None) -> bool:
        if not self.is_read_only_module(module_name):
            return True
        messagebox.showwarning(
            title or module_name,
            "Ce module est en lecture seule pour votre profil.",
            parent=self,
        )
        return False

    def hide_read_only_buttons(self, module_name: str, buttons: list[tk.Misc]) -> None:
        if not self.is_read_only_module(module_name):
            return
        if self.parent.user.role == "Directeur Général":
            for button in buttons:
                try:
                    button.state(["disabled"])
                except AttributeError:
                    button.configure(state="disabled")
            return
        for button in buttons:
            try:
                button.grid_remove()
            except tk.TclError:
                try:
                    button.pack_forget()
                except tk.TclError:
                    pass

    def create_day_lock_notice(
        self,
        parent: tk.Misc,
        module_label: str,
        *,
        before: tk.Misc | None = None,
        wraplength: int = 980,
    ) -> None:
        self.day_lock_module_label = module_label
        self.day_lock_notice_before = before
        self.day_lock_notice_var = tk.StringVar(value="")
        self.day_lock_notice_label = ttk.Label(
            parent,
            textvariable=self.day_lock_notice_var,
            style="DayLock.TLabel",
            justify="left",
            wraplength=wraplength,
        )
        self.day_lock_write_buttons: list[Any] = []
        self.day_lock_date_field: DateField | None = None

    def configure_day_lock_controls(self, date_field: DateField, write_buttons: list[Any]) -> None:
        self.day_lock_date_field = date_field
        self.day_lock_write_buttons = write_buttons
        date_field.bind_change(self.refresh_day_lock_state)
        self.refresh_day_lock_state()

    def set_day_lock_write_buttons_enabled(self, enabled: bool) -> None:
        if self.parent.user.role == "Directeur Général":
            enabled = False
        for button in getattr(self, "day_lock_write_buttons", []):
            try:
                button.state(["!disabled"] if enabled else ["disabled"])
            except AttributeError:
                button.configure(state="normal" if enabled else "disabled")

    def refresh_day_lock_state(self) -> bool:
        date_field = getattr(self, "day_lock_date_field", None)
        notice_label = getattr(self, "day_lock_notice_label", None)
        notice_var = getattr(self, "day_lock_notice_var", None)
        if date_field is None or notice_label is None or notice_var is None:
            return False
        try:
            target_date = date_field.get_date()
            closure = DatabaseHelper.get_day_closure(target_date)
        except Exception:
            notice_var.set("")
            if notice_label.winfo_ismapped():
                notice_label.pack_forget()
            self.set_day_lock_write_buttons_enabled(True)
            return False

        locked = bool(closure) and not bool(closure.get("EstReouverte", False))
        if locked:
            notice_var.set(
                build_day_lock_notice(
                    target_date,
                    closure,
                    str(getattr(self, "day_lock_module_label", "ce module")),
                )
            )
            if not notice_label.winfo_ismapped():
                pack_options: dict[str, Any] = {"fill": "x", "pady": (0, 10)}
                before = getattr(self, "day_lock_notice_before", None)
                if before is not None and before.winfo_exists():
                    pack_options["before"] = before
                notice_label.pack(**pack_options)
            self.set_day_lock_write_buttons_enabled(False)
            return True

        notice_var.set("")
        if notice_label.winfo_ismapped():
            notice_label.pack_forget()
        self.set_day_lock_write_buttons_enabled(True)
        return False


class DayClosuresWindow(BaseModuleWindow):
    def __init__(self, parent: DashboardWindow) -> None:
        super().__init__(parent, "Historique des clôtures journalières", "1160x620", start_maximized=False)
        self.message_var = tk.StringVar(value="Chargement des clôtures...")
        self.table = DataTable(self.body, height=12)
        self.build_ui()
        self.refresh_closures()

    def build_ui(self) -> None:
        container = self.body
        container.columnconfigure(0, weight=1)
        container.rowconfigure(1, weight=1)

        ttk.Label(
            container,
            text=(
                "Consultez les journées clôturées, les réouvertures effectuées, "
                "ainsi que les chemins du rapport signé et de la sauvegarde automatique."
            ),
            wraplength=820,
            justify="left",
        ).grid(row=0, column=0, sticky="ew", pady=(0, 12))

        self.table.grid(row=1, column=0, sticky="nsew")
        self.table.tree.bind("<Double-1>", lambda _event: self.open_selected_report())

        ttk.Label(
            container,
            textvariable=self.message_var,
            wraplength=820,
            justify="left",
            foreground=MUTED_TEXT_COLOR,
        ).grid(row=2, column=0, sticky="ew", pady=(12, 10))

        actions = ttk.Frame(container)
        actions.grid(row=3, column=0, sticky="e")
        ttk.Button(actions, text="Actualiser", command=self.refresh_closures).grid(row=0, column=0, padx=(0, 8))
        ttk.Button(actions, text="Ouvrir le rapport", command=self.open_selected_report).grid(
            row=0, column=1, padx=(0, 8)
        )
        ttk.Button(actions, text="Ouvrir le dossier de sauvegarde", command=self.open_selected_backup_folder).grid(
            row=0, column=2, padx=(0, 8)
        )
        ttk.Button(actions, text="Copier les chemins", command=self.copy_selected_paths).grid(
            row=0, column=3, padx=(0, 8)
        )
        ttk.Button(actions, text="Fermer", command=self.close_window).grid(row=0, column=4)

    def refresh_closures(self) -> None:
        try:
            rows = DatabaseHelper.list_day_closures(limit=240)
        except Exception as exc:
            self.message_var.set(f"Impossible de charger l'historique des clôtures : {exc}")
            self.table.set_data([], ["DateJour", "StatutAffichage", "DateCloture"])
            return

        self.table.set_data(
            rows,
            columns=[
                "Id",
                "DateJour",
                "StatutAffichage",
                "DateCloture",
                "NomComplet",
                "Role",
                "DateReouverture",
                "ReouvertParNomComplet",
                "MotifReouverture",
                "CheminRapport",
                "CheminSauvegarde",
            ],
            headings={
                "DateJour": "Jour",
                "StatutAffichage": "Statut",
                "DateCloture": "Date de clôture",
                "NomComplet": "Clôturée par",
                "Role": "Rôle",
                "DateReouverture": "Date de réouverture",
                "ReouvertParNomComplet": "Réouverte par",
                "MotifReouverture": "Motif",
                "CheminRapport": "Rapport",
                "CheminSauvegarde": "Sauvegarde",
            },
            hidden_columns=["Id", "CheminRapport", "CheminSauvegarde"],
            formatters={
                "DateJour": lambda value: format_activity_timestamp(f"{value}T00:00:00")[:10]
                if value
                else "",
                "DateCloture": format_activity_timestamp,
                "DateReouverture": format_activity_timestamp,
            },
        )
        if rows:
            self.message_var.set(f"{len(rows)} journée(s) de clôture enregistrée(s).")
        else:
            self.message_var.set("Aucune clôture n'a encore été enregistrée.")

    def refresh_live_view(self) -> None:
        self.refresh_closures()

    def selected_closure(self) -> dict[str, Any] | None:
        row = self.table.selected_row()
        if row is None:
            messagebox.showwarning("Clôtures", "Veuillez sélectionner une journée dans la grille.")
            return None
        return row

    def open_selected_report(self) -> None:
        row = self.selected_closure()
        if row is None:
            return
        report_path = str(row.get("CheminRapport", "") or "").strip()
        if not report_path:
            messagebox.showwarning("Clôtures", "Aucun rapport n'est associé à cette clôture.")
            return
        if not Path(report_path).exists():
            messagebox.showwarning("Clôtures", "Le fichier de rapport est introuvable.")
            return
        open_file(report_path)

    def open_selected_backup_folder(self) -> None:
        row = self.selected_closure()
        if row is None:
            return
        backup_path = str(row.get("CheminSauvegarde", "") or "").strip()
        if not backup_path:
            messagebox.showwarning("Clôtures", "Aucune sauvegarde n'est associée à cette clôture.")
            return
        backup_file = Path(backup_path)
        target_folder = backup_file.parent if backup_file.parent else DatabaseHelper.backups_dir
        open_folder(target_folder)

    def copy_selected_paths(self) -> None:
        row = self.selected_closure()
        if row is None:
            return
        report_path = str(row.get("CheminRapport", "") or "").strip()
        backup_path = str(row.get("CheminSauvegarde", "") or "").strip()
        payload = f"Rapport : {report_path}\nSauvegarde : {backup_path}".strip()
        self.clipboard_clear()
        self.clipboard_append(payload)
        self.message_var.set("Les chemins du rapport et de la sauvegarde ont été copiés dans le presse-papiers.")


class ServerBackupsWindow(BaseModuleWindow):
    def __init__(self, parent: DashboardWindow, selection_mode: bool) -> None:
        title = "Choisir une sauvegarde du serveur" if selection_mode else "Sauvegardes du serveur central"
        super().__init__(parent, title, "980x560", start_maximized=False)
        self.selection_mode = selection_mode
        self.selected_backup_path: Path | None = None
        self.server_directory_var = tk.StringVar(value="Chargement...")
        self.message_var = tk.StringVar(value="")
        self.table: DataTable | None = None
        self.build_ui()
        self.refresh_backups()

    def build_ui(self) -> None:
        container = self.body
        container.columnconfigure(0, weight=1)
        ttk.Label(
            container,
            text=(
                "Les sauvegardes ci-dessous sont stockées sur le serveur central. "
                "Vous pouvez en consulter la liste ou en choisir une pour la restauration."
            ),
            wraplength=780,
            justify="left",
        ).grid(row=0, column=0, sticky="ew", pady=(0, 12))

        location_frame = ttk.LabelFrame(container, text="Emplacement serveur", style="Card.TLabelframe")
        location_frame.grid(row=1, column=0, sticky="ew", pady=(0, 12))
        location_frame.columnconfigure(0, weight=1)
        ttk.Label(
            location_frame,
            textvariable=self.server_directory_var,
            wraplength=760,
            justify="left",
        ).grid(row=0, column=0, sticky="ew", padx=(0, 8))
        ttk.Button(location_frame, text="Copier le chemin", command=self.copy_server_directory_path).grid(
            row=0, column=1, sticky="e"
        )

        self.table = DataTable(container, height=10)
        self.table.grid(row=2, column=0, sticky="nsew")
        container.rowconfigure(2, weight=1)
        self.table.tree.bind("<Double-1>", self.handle_double_click)

        ttk.Label(
            container,
            textvariable=self.message_var,
            foreground=MUTED_TEXT_COLOR,
            justify="left",
            wraplength=780,
        ).grid(row=3, column=0, sticky="ew", pady=(12, 8))

        actions = ttk.Frame(container)
        actions.grid(row=4, column=0, sticky="e")
        ttk.Button(actions, text="Actualiser", command=self.refresh_backups).grid(row=0, column=0, padx=(0, 8))
        ttk.Button(actions, text="Copier le chemin selectionne", command=self.copy_selected_path).grid(
            row=0, column=1, padx=(0, 8)
        )
        if self.selection_mode:
            ttk.Button(actions, text="Utiliser cette sauvegarde", command=self.confirm_selection).grid(
                row=0, column=2, padx=(0, 8)
            )
        ttk.Button(actions, text="Fermer", command=self.close_window).grid(row=0, column=3)

    def refresh_backups(self) -> None:
        if self.table is None:
            return
        try:
            backup_dir = DatabaseHelper.get_backups_directory()
            rows = DatabaseHelper.list_backup_files()
        except Exception as exc:
            self.server_directory_var.set("Emplacement indisponible.")
            self.message_var.set(f"Impossible de lire les sauvegardes du serveur : {exc}")
            self.table.set_data([], ["NomFichier", "DateModification", "TailleOctets", "CheminComplet"])
            return

        self.server_directory_var.set(str(backup_dir))
        if rows:
            self.message_var.set(
                f"{len(rows)} sauvegarde(s) disponible(s) sur le serveur central."
            )
        else:
            self.message_var.set("Aucune sauvegarde n'est disponible pour le moment sur le serveur central.")
        self.table.set_data(
            rows,
            ["NomFichier", "DateModification", "TailleOctets", "CheminComplet"],
            headings={
                "NomFichier": "Fichier",
                "DateModification": "Derniere modification",
                "TailleOctets": "Taille",
                "CheminComplet": "Chemin complet",
            },
            hidden_columns=["CheminComplet"],
            formatters={
                "DateModification": lambda value: value.strftime("%d/%m/%Y %H:%M")
                if isinstance(value, datetime)
                else str(value),
                "TailleOctets": lambda value: format_file_size(int(value or 0)),
            },
        )

    def handle_double_click(self, _event: tk.Event[tk.Misc]) -> None:
        if self.selection_mode:
            self.confirm_selection()
        else:
            self.copy_selected_path()

    def copy_server_directory_path(self) -> None:
        path_text = self.server_directory_var.get().strip()
        if not path_text or path_text == "Chargement..." or path_text == "Emplacement indisponible.":
            messagebox.showinfo("Sauvegardes", "Le chemin du serveur n'est pas encore disponible.")
            return
        self.clipboard_clear()
        self.clipboard_append(path_text)
        self.message_var.set("Le chemin du dossier de sauvegarde du serveur a été copié.")

    def copy_selected_path(self) -> None:
        if self.table is None:
            return
        row = self.table.selected_row()
        if not row:
            messagebox.showinfo("Sauvegardes", "Selectionnez d'abord une sauvegarde dans la liste.")
            return
        path_value = row.get("CheminComplet")
        if not path_value:
            messagebox.showinfo("Sauvegardes", "Le chemin de cette sauvegarde est indisponible.")
            return
        self.clipboard_clear()
        self.clipboard_append(str(path_value))
        self.message_var.set("Le chemin de la sauvegarde sélectionnée a été copié.")

    def confirm_selection(self) -> None:
        if self.table is None:
            return
        row = self.table.selected_row()
        if not row:
            messagebox.showinfo("Restauration", "Selectionnez d'abord une sauvegarde du serveur.")
            return
        path_value = row.get("CheminComplet")
        if not path_value:
            messagebox.showerror("Restauration", "Le chemin de la sauvegarde sélectionnée est indisponible.")
            return
        self.selected_backup_path = Path(path_value)
        self.close_window()


class PdfReportWindow(BaseModuleWindow):
    def __init__(self, parent: DashboardWindow, *, required_monthly: bool = False) -> None:
        super().__init__(parent, "Rapports PDF", "760x560", start_maximized=False)
        self.identifiant = parent.user.identifiant
        self.role = parent.user.role
        self.reports_dir = DatabaseHelper.get_reports_dir_for_user(self.identifiant)
        self.report_mode_var = tk.StringVar(value="daily")
        self.required_monthly = required_monthly
        self.message_var = tk.StringVar(value="")
        self.build_ui()

    def build_ui(self) -> None:
        container = self.body

        intro = ttk.LabelFrame(container, text="Impression", style="Card.TLabelframe")
        intro.pack(fill="x", pady=(0, 14))
        ttk.Label(
            intro,
            text=(
                "Choisissez une date de référence puis générez un document PDF prêt à imprimer. "
                "En mode mensuel, seul le mois et l'année de cette date seront utilisés. "
                "En mode période, vous définissez une date de début et une date de fin. "
                f"{get_report_scope_description(self.role)}"
            ),
            wraplength=560,
            justify="center",
        ).pack(fill="x")
        ttk.Label(
            intro,
            text=f"Profil du rapport : {get_report_scope_label(self.role)}",
            foreground=SUCCESS_COLOR,
            justify="center",
        ).pack(fill="x", pady=(8, 0))

        form = ttk.LabelFrame(container, text="Paramètres du rapport", style="Card.TLabelframe")
        form.pack(fill="x")

        ttk.Label(form, text="Type de rapport").grid(row=0, column=0, sticky="w", pady=6)
        mode_row = ttk.Frame(form)
        mode_row.grid(row=0, column=1, sticky="w", pady=6)
        ttk.Radiobutton(mode_row, text="Journalier", value="daily", variable=self.report_mode_var).grid(row=0, column=0, padx=(0, 10))
        ttk.Radiobutton(mode_row, text="Mensuel", value="monthly", variable=self.report_mode_var).grid(row=0, column=1)
        ttk.Radiobutton(mode_row, text="Période", value="period", variable=self.report_mode_var).grid(row=0, column=2, padx=(10, 0))

        if self.role in {"Admin", "Directeur Général", "Caissier"}:
            ttk.Radiobutton(mode_row, text="Caisse hebdo", value="cash_weekly", variable=self.report_mode_var).grid(row=1, column=0, padx=(0, 10), pady=(6, 0))
            ttk.Radiobutton(mode_row, text="Bilan caisse mensuel", value="cash_monthly", variable=self.report_mode_var).grid(row=1, column=1, columnspan=2, sticky="w", pady=(6, 0))

        ttk.Label(form, text="Date de début / référence").grid(row=1, column=0, sticky="w", pady=6)
        self.date_field = DateField(form)
        self.date_field.grid(row=1, column=1, sticky="ew", pady=6)
        ttk.Label(form, text="Date de fin").grid(row=2, column=0, sticky="w", pady=6)
        self.end_date_field = DateField(form)
        self.end_date_field.grid(row=2, column=1, sticky="ew", pady=6)
        ttk.Label(
            form,
            text=(
                "Journalier : la date de début est utilisée seule. "
                "Mensuel : le mois de la date de début est utilisé. "
                "Période : toutes les données entre la date de début et la date de fin sont regroupées."
            ),
            foreground=MUTED_TEXT_COLOR,
            wraplength=520,
            justify="left",
        ).grid(row=3, column=0, columnspan=2, sticky="w", pady=(0, 6))

        actions = ttk.Frame(form)
        actions.grid(row=5, column=0, columnspan=2, pady=(14, 0))
        ttk.Button(actions, text="Générer le PDF", style="Primary.TButton", command=self.generate_report).grid(
            row=0, column=0, padx=6
        )
        ttk.Button(actions, text="Ouvrir le dossier des rapports", command=self.open_reports_folder).grid(
            row=0, column=1, padx=6
        )
        ttk.Button(actions, text="Fermer", command=self.close_window).grid(row=0, column=2, padx=6)

        form.columnconfigure(1, weight=1)
        self.report_mode_var.trace_add("write", self._on_report_mode_change)
        if self.required_monthly:
            previous_month = date.today().replace(day=1) - timedelta(days=1)
            self.report_mode_var.set("monthly")
            self.date_field.set_date(previous_month.strftime("%Y-%m-%d"))
            self.message_var.set(
                "Rapport mensuel obligatoire : générez le PDF du mois précédent pour continuer."
            )
        self._on_report_mode_change()

        ttk.Label(
            container,
            textvariable=self.message_var,
            foreground=DANGER_COLOR,
            wraplength=520,
            justify="center",
        ).pack(fill="x", pady=(12, 0))

    def _on_report_mode_change(self, *_args: Any) -> None:
        period_mode = self.report_mode_var.get().strip().lower() == "period"
        self.end_date_field.set_enabled(period_mode)
        if not period_mode:
            self.end_date_field.set_date(self.date_field.get())

    def generate_report(self) -> None:
        try:
            target_date = self.date_field.get_date()
            end_date = self.end_date_field.get_date()
        except Exception as exc:
            self.message_var.set(str(exc))
            return

        self.reports_dir.mkdir(parents=True, exist_ok=True)
        mode = self.report_mode_var.get().strip().lower()
        if mode == "cash_weekly":
            week_start, week_end = cash_week_bounds(target_date)
            suggested_name = f"bilan-caisse-hebdomadaire-{week_start.strftime('%Y%m%d')}-{week_end.strftime('%Y%m%d')}.pdf"
        elif mode == "cash_monthly":
            month_start, _month_end = cash_month_bounds(target_date)
            suggested_name = f"bilan-caisse-mensuel-{month_start.strftime('%Y%m')}.pdf"
        elif mode == "monthly":
            suggested_name = f"rapport-mensuel-{target_date.strftime('%Y%m')}.pdf"
        elif mode == "period":
            suggested_name = f"rapport-periode-{target_date.strftime('%Y%m%d')}-{end_date.strftime('%Y%m%d')}.pdf"
        else:
            suggested_name = f"rapport-journalier-{target_date.strftime('%Y%m%d')}.pdf"
        suggested_path = self.reports_dir / suggested_name
        destination = filedialog.asksaveasfilename(
            title="Enregistrer le rapport PDF",
            initialdir=str(self.reports_dir),
            initialfile=suggested_path.name,
            defaultextension=".pdf",
            filetypes=[("Fichiers PDF", "*.pdf")],
        )
        if not destination:
            return

        try:
            if mode == "cash_weekly":
                week_start, week_end = cash_week_bounds(target_date)
                report_path = create_cash_balance_pdf_report(
                    week_start,
                    week_end,
                    destination,
                    role=self.role,
                    generated_by=self.parent.user.display_name,
                    generated_role=self.role,
                    title="BILAN HEBDOMADAIRE DE CAISSE",
                )
            elif mode == "cash_monthly":
                month_start, month_end = cash_month_bounds(target_date)
                report_path = create_cash_balance_pdf_report(
                    month_start,
                    month_end,
                    destination,
                    role=self.role,
                    generated_by=self.parent.user.display_name,
                    generated_role=self.role,
                    title="BALANCE MENSUELLE DE CAISSE",
                )
            elif mode == "monthly":
                report_path = create_monthly_pdf_report(
                    target_date,
                    destination,
                    role=self.role,
                    generated_by=self.parent.user.display_name,
                    generated_role=self.role,
                )
            elif mode == "period":
                report_path = create_period_pdf_report(
                    target_date,
                    end_date,
                    destination,
                    role=self.role,
                    generated_by=self.parent.user.display_name,
                    generated_role=self.role,
                )
            else:
                report_path = create_daily_pdf_report(
                    target_date,
                    destination,
                    role=self.role,
                    generated_by=self.parent.user.display_name,
                    generated_role=self.role,
                )
        except ReportGenerationError as exc:
            self.message_var.set(str(exc))
            return
        except Exception as exc:
            self.message_var.set(f"Generation impossible : {exc}")
            return

        self.message_var.set(f"Rapport créé : {report_path}")
        if mode in {"monthly", "cash_monthly"}:
            report_reference_date = month_start if mode == "cash_monthly" else target_date
            try:
                DatabaseHelper.record_monthly_report_generation(
                    report_reference_date.strftime("%Y-%m"),
                    mode,
                    "PDF",
                    self.parent.user.identifiant,
                    self.parent.user.display_name,
                    self.role,
                    str(report_path),
                )
                self.parent.monthly_report_obligation = None
            except Exception as exc:
                self.message_var.set(f"Rapport créé, mais suivi mensuel non enregistré : {exc}")
        log_user_action(
            self,
            "Rapports PDF",
            "Rapport généré",
            f"Mode : {mode} | Fichier : {report_path.name}",
        )
        try:
            open_file(report_path)
        except Exception as exc:
            self.message_var.set(f"Rapport créé, mais ouverture automatique impossible : {exc}")

    def open_reports_folder(self) -> None:
        open_folder(self.reports_dir)


class ExcelReportWindow(BaseModuleWindow):
    def __init__(self, parent: DashboardWindow) -> None:
        super().__init__(parent, "Rapports Excel", "760x560", start_maximized=False)
        self.identifiant = parent.user.identifiant
        self.role = parent.user.role
        self.reports_dir = DatabaseHelper.get_reports_dir_for_user(self.identifiant)
        self.report_mode_var = tk.StringVar(value="daily")
        self.message_var = tk.StringVar(value="")
        self.build_ui()

    def build_ui(self) -> None:
        container = self.body

        intro = ttk.LabelFrame(container, text="Export Excel", style="Card.TLabelframe")
        intro.pack(fill="x", pady=(0, 14))
        ttk.Label(
            intro,
            text=(
                "Choisissez une date de référence puis générez un classeur Excel prêt à partager ou à retravailler. "
                "En mode mensuel, seul le mois et l'année de cette date seront utilisés. "
                "En mode période, vous définissez une date de début et une date de fin. "
                f"{get_report_scope_description(self.role)}"
            ),
            wraplength=560,
            justify="center",
        ).pack(fill="x")
        ttk.Label(
            intro,
            text=f"Profil du rapport : {get_report_scope_label(self.role)}",
            foreground=SUCCESS_COLOR,
            justify="center",
        ).pack(fill="x", pady=(8, 0))

        form = ttk.LabelFrame(container, text="Paramètres du rapport", style="Card.TLabelframe")
        form.pack(fill="x")

        ttk.Label(form, text="Type de rapport").grid(row=0, column=0, sticky="w", pady=6)
        mode_row = ttk.Frame(form)
        mode_row.grid(row=0, column=1, sticky="w", pady=6)
        ttk.Radiobutton(mode_row, text="Journalier", value="daily", variable=self.report_mode_var).grid(row=0, column=0, padx=(0, 10))
        ttk.Radiobutton(mode_row, text="Mensuel", value="monthly", variable=self.report_mode_var).grid(row=0, column=1)
        ttk.Radiobutton(mode_row, text="Période", value="period", variable=self.report_mode_var).grid(row=0, column=2, padx=(10, 0))

        if self.role in {"Admin", "Directeur Général", "Caissier"}:
            ttk.Radiobutton(mode_row, text="Caisse hebdo", value="cash_weekly", variable=self.report_mode_var).grid(row=1, column=0, padx=(0, 10), pady=(6, 0))
            ttk.Radiobutton(mode_row, text="Bilan caisse mensuel", value="cash_monthly", variable=self.report_mode_var).grid(row=1, column=1, columnspan=2, sticky="w", pady=(6, 0))

        ttk.Label(form, text="Date de début / référence").grid(row=1, column=0, sticky="w", pady=6)
        self.date_field = DateField(form)
        self.date_field.grid(row=1, column=1, sticky="ew", pady=6)
        ttk.Label(form, text="Date de fin").grid(row=2, column=0, sticky="w", pady=6)
        self.end_date_field = DateField(form)
        self.end_date_field.grid(row=2, column=1, sticky="ew", pady=6)
        ttk.Label(
            form,
            text=(
                "Journalier : la date de début est utilisée seule. "
                "Mensuel : le mois de la date de début est utilisé. "
                "Période : toutes les données entre la date de début et la date de fin sont regroupées."
            ),
            foreground=MUTED_TEXT_COLOR,
            wraplength=520,
            justify="left",
        ).grid(row=3, column=0, columnspan=2, sticky="w", pady=(0, 6))

        actions = ttk.Frame(form)
        actions.grid(row=5, column=0, columnspan=2, pady=(14, 0))
        ttk.Button(
            actions,
            text="Générer le fichier Excel",
            style="Primary.TButton",
            command=self.generate_report,
        ).grid(row=0, column=0, padx=6)
        ttk.Button(actions, text="Ouvrir le dossier des rapports", command=self.open_reports_folder).grid(
            row=0, column=1, padx=6
        )
        ttk.Button(actions, text="Fermer", command=self.close_window).grid(row=0, column=2, padx=6)

        form.columnconfigure(1, weight=1)
        self.report_mode_var.trace_add("write", self._on_report_mode_change)
        self._on_report_mode_change()

        ttk.Label(
            container,
            textvariable=self.message_var,
            foreground=DANGER_COLOR,
            wraplength=520,
            justify="center",
        ).pack(fill="x", pady=(12, 0))

    def _on_report_mode_change(self, *_args: Any) -> None:
        period_mode = self.report_mode_var.get().strip().lower() == "period"
        self.end_date_field.set_enabled(period_mode)
        if not period_mode:
            self.end_date_field.set_date(self.date_field.get())

    def generate_report(self) -> None:
        try:
            target_date = self.date_field.get_date()
            end_date = self.end_date_field.get_date()
        except Exception as exc:
            self.message_var.set(str(exc))
            return

        self.reports_dir.mkdir(parents=True, exist_ok=True)
        mode = self.report_mode_var.get().strip().lower()
        if mode == "cash_weekly":
            week_start, week_end = cash_week_bounds(target_date)
            suggested_name = f"bilan-caisse-hebdomadaire-{week_start.strftime('%Y%m%d')}-{week_end.strftime('%Y%m%d')}.xlsx"
        elif mode == "cash_monthly":
            month_start, _month_end = cash_month_bounds(target_date)
            suggested_name = f"bilan-caisse-mensuel-{month_start.strftime('%Y%m')}.xlsx"
        elif mode == "monthly":
            suggested_name = f"rapport-excel-mensuel-{target_date.strftime('%Y%m')}.xlsx"
        elif mode == "period":
            suggested_name = (
                f"rapport-excel-periode-{target_date.strftime('%Y%m%d')}-{end_date.strftime('%Y%m%d')}.xlsx"
            )
        else:
            suggested_name = f"rapport-excel-journalier-{target_date.strftime('%Y%m%d')}.xlsx"
        suggested_path = self.reports_dir / suggested_name
        destination = filedialog.asksaveasfilename(
            title="Enregistrer le rapport Excel",
            initialdir=str(self.reports_dir),
            initialfile=suggested_path.name,
            defaultextension=".xlsx",
            filetypes=[("Classeur Excel", "*.xlsx")],
        )
        if not destination:
            return

        try:
            if mode == "cash_weekly":
                week_start, week_end = cash_week_bounds(target_date)
                report_path = create_cash_balance_excel_report(
                    week_start,
                    week_end,
                    destination,
                    role=self.role,
                    generated_by=self.parent.user.display_name,
                    generated_role=self.role,
                    title="BILAN HEBDOMADAIRE DE CAISSE",
                )
            elif mode == "cash_monthly":
                month_start, month_end = cash_month_bounds(target_date)
                report_path = create_cash_balance_excel_report(
                    month_start,
                    month_end,
                    destination,
                    role=self.role,
                    generated_by=self.parent.user.display_name,
                    generated_role=self.role,
                    title="BALANCE MENSUELLE DE CAISSE",
                )
            elif mode == "monthly":
                report_path = create_monthly_excel_report(
                    target_date,
                    destination,
                    role=self.role,
                    generated_by=self.parent.user.display_name,
                    generated_role=self.role,
                )
            elif mode == "period":
                report_path = create_period_excel_report(
                    target_date,
                    end_date,
                    destination,
                    role=self.role,
                    generated_by=self.parent.user.display_name,
                    generated_role=self.role,
                )
            else:
                report_path = create_daily_excel_report(
                    target_date,
                    destination,
                    role=self.role,
                    generated_by=self.parent.user.display_name,
                    generated_role=self.role,
                )
        except ReportGenerationError as exc:
            self.message_var.set(str(exc))
            return
        except Exception as exc:
            self.message_var.set(f"Génération impossible : {exc}")
            return

        self.message_var.set(f"Rapport créé : {report_path}")
        if mode in {"monthly", "cash_monthly"}:
            report_reference_date = month_start if mode == "cash_monthly" else target_date
            try:
                DatabaseHelper.record_monthly_report_generation(
                    report_reference_date.strftime("%Y-%m"),
                    mode,
                    "EXCEL",
                    self.parent.user.identifiant,
                    self.parent.user.display_name,
                    self.role,
                    str(report_path),
                )
                self.parent.monthly_report_obligation = None
            except Exception as exc:
                self.message_var.set(f"Rapport créé, mais suivi mensuel non enregistré : {exc}")
        log_user_action(
            self,
            "Rapports Excel",
            "Rapport généré",
            f"Mode : {mode} | Fichier : {report_path.name}",
        )
        try:
            open_file(report_path)
        except Exception as exc:
            self.message_var.set(f"Rapport créé, mais ouverture automatique impossible : {exc}")

    def open_reports_folder(self) -> None:
        open_folder(self.reports_dir)


class ChangePasswordWindow(BaseModuleWindow):
    def __init__(
        self,
        parent: DashboardWindow,
        identifiant: str,
        on_password_changed: Callable[[], None] | None = None,
    ) -> None:
        super().__init__(parent, "Sécurité du compte", "620x470", start_maximized=False)
        self.identifiant = identifiant
        self.on_password_changed = on_password_changed
        self.current_password_var = tk.StringVar()
        self.new_password_var = tk.StringVar()
        self.confirm_password_var = tk.StringVar()
        self.message_var = tk.StringVar(value="")
        self.build_ui()

    def build_ui(self) -> None:
        container = self.body

        description = ttk.LabelFrame(container, text="Protection du compte", style="Card.TLabelframe")
        description.pack(fill="x", pady=(0, 14))

        if DatabaseHelper.is_using_default_password(self.identifiant):
            description_text = (
                "Ce compte utilise encore le mot de passe par défaut. "
                "Choisissez-en un nouveau des maintenant."
            )
            description_color = DANGER_COLOR
        else:
            description_text = (
                "Saisissez votre mot de passe actuel, puis choisissez un nouveau mot de passe "
                "fort : 12 caracteres minimum, 14 pour Admin/DG, avec majuscule, minuscule, chiffre et symbole."
            )
            description_color = SUCCESS_COLOR

        ttk.Label(
            description,
            text=description_text,
            foreground=description_color,
            wraplength=420,
            justify="center",
        ).pack(fill="x")

        form = ttk.LabelFrame(container, text="Mot de passe", style="Card.TLabelframe")
        form.pack(fill="x")

        ttk.Label(form, text="Mot de passe actuel").grid(row=0, column=0, sticky="w", pady=6)
        self.current_entry = ttk.Entry(form, textvariable=self.current_password_var, show="*", width=34)
        self.current_entry.grid(row=0, column=1, sticky="ew", pady=6)

        ttk.Label(form, text="Nouveau mot de passe").grid(row=1, column=0, sticky="w", pady=6)
        self.new_entry = ttk.Entry(form, textvariable=self.new_password_var, show="*", width=34)
        self.new_entry.grid(row=1, column=1, sticky="ew", pady=6)

        ttk.Label(form, text="Confirmation").grid(row=2, column=0, sticky="w", pady=6)
        self.confirm_entry = ttk.Entry(form, textvariable=self.confirm_password_var, show="*", width=34)
        self.confirm_entry.grid(row=2, column=1, sticky="ew", pady=6)

        buttons = ttk.Frame(form)
        buttons.grid(row=3, column=0, columnspan=2, pady=(14, 0))
        ttk.Button(buttons, text="Enregistrer", style="Primary.TButton", command=self.save_password).grid(
            row=0, column=0, padx=6
        )
        ttk.Button(buttons, text="Fermer", command=self.close_window).grid(row=0, column=1, padx=6)

        form.columnconfigure(1, weight=1)

        ttk.Label(
            container,
            textvariable=self.message_var,
            foreground=DANGER_COLOR,
            wraplength=440,
            justify="center",
        ).pack(fill="x", pady=(12, 0))

        self.current_entry.focus()
        self.current_entry.bind("<Return>", lambda _event: self.new_entry.focus())
        self.new_entry.bind("<Return>", lambda _event: self.confirm_entry.focus())
        self.confirm_entry.bind("<Return>", lambda _event: self.save_password())

    def save_password(self) -> None:
        if self.parent.user.role == "Directeur Général":
            messagebox.showwarning(
                "Sécurité",
                "Ce compte est en lecture seule. Le mot de passe doit être géré par un administrateur.",
                parent=self,
            )
            return
        current_password = self.current_password_var.get()
        new_password = self.new_password_var.get()
        confirm_password = self.confirm_password_var.get()

        if not confirm_password.strip():
            self.message_var.set("Veuillez confirmer le nouveau mot de passe.")
            self.confirm_entry.focus()
            return
        if new_password != confirm_password:
            self.message_var.set("La confirmation ne correspond pas au nouveau mot de passe.")
            self.confirm_password_var.set("")
            self.confirm_entry.focus()
            return

        try:
            DatabaseHelper.change_user_password(self.identifiant, current_password, new_password)
        except Exception as exc:
            self.message_var.set(str(exc))
            self.current_password_var.set("")
            self.current_entry.focus()
            return

        self.message_var.set("")
        log_user_action(self, "Sécurité", "Mot de passe modifié", "Changement du mot de passe du compte connecté.")
        messagebox.showinfo("Sécurité", "Le mot de passe a été modifié avec succès.")
        if self.on_password_changed is not None:
            self.on_password_changed()
        self.destroy()


class UsersWindow(BaseModuleWindow):
    def __init__(self, parent: DashboardWindow) -> None:
        super().__init__(parent, "Gestion des utilisateurs", "1060x700")
        self.edit_mode = False
        self.original_identifiant = ""
        self.build_ui()
        self.after_idle(self.refresh_users)

    def build_ui(self) -> None:
        container = self.body

        top = ttk.Frame(container)
        top.pack(fill="x")
        form = ttk.LabelFrame(top, text="Utilisateur", style="Card.TLabelframe")
        form.pack(side="left", fill="y", padx=(0, 12))

        ttk.Label(form, text="Nom complet").grid(row=0, column=0, sticky="w", pady=6)
        self.name_var = tk.StringVar()
        self.name_entry = ttk.Entry(form, textvariable=self.name_var, width=34)
        self.name_entry.grid(row=0, column=1, sticky="ew", pady=6)

        ttk.Label(form, text="Identifiant").grid(row=1, column=0, sticky="w", pady=6)
        self.identifiant_var = tk.StringVar()
        self.identifiant_entry = ttk.Entry(form, textvariable=self.identifiant_var, width=34)
        self.identifiant_entry.grid(row=1, column=1, sticky="ew", pady=6)

        ttk.Label(form, text="Adresse e-mail (facultative)").grid(row=2, column=0, sticky="w", pady=6)
        self.email_var = tk.StringVar()
        ttk.Entry(form, textvariable=self.email_var, width=34).grid(row=2, column=1, sticky="ew", pady=6)

        ttk.Label(form, text="Mot de passe").grid(row=3, column=0, sticky="w", pady=6)
        self.password_var = tk.StringVar()
        self.show_password_var = tk.BooleanVar(value=False)
        password_row = ttk.Frame(form)
        password_row.grid(row=3, column=1, sticky="ew", pady=6)
        self.password_entry = ttk.Entry(password_row, textvariable=self.password_var, show="*", width=26)
        self.password_entry.grid(row=0, column=0, sticky="ew")
        ttk.Checkbutton(
            password_row,
            text="Afficher",
            variable=self.show_password_var,
            command=self.toggle_password_visibility,
        ).grid(row=0, column=1, padx=(8, 0), sticky="w")
        password_row.columnconfigure(0, weight=1)

        ttk.Label(form, text="Rôle").grid(row=4, column=0, sticky="w", pady=6)
        self.role_var = tk.StringVar(value=ROLES[0])
        self.role_combo = ttk.Combobox(form, textvariable=self.role_var, values=ROLES, state="readonly", width=31)
        self.role_combo.grid(row=4, column=1, sticky="ew", pady=6)

        button_bar = ttk.Frame(form)
        button_bar.grid(row=5, column=0, columnspan=2, pady=(14, 0))
        ttk.Button(button_bar, text="Enregistrer", command=self.save_user).grid(row=0, column=0, padx=4, pady=4)
        ttk.Button(button_bar, text="Modifier", command=self.load_user_for_edit).grid(row=0, column=1, padx=4, pady=4)
        ttk.Button(button_bar, text="Supprimer", command=self.delete_user).grid(row=0, column=2, padx=4, pady=4)
        ttk.Button(button_bar, text="Rechercher", command=self.search_user).grid(row=1, column=0, padx=4, pady=4)
        ttk.Button(button_bar, text="Tout afficher", command=self.refresh_users).grid(row=1, column=1, padx=4, pady=4)
        ttk.Button(button_bar, text="Fermer", command=self.close_window).grid(row=1, column=2, padx=4, pady=4)

        form.columnconfigure(1, weight=1)

        self.message_var = tk.StringVar(value="")
        ttk.Label(form, textvariable=self.message_var, foreground=DANGER_COLOR, wraplength=320).grid(
            row=6, column=0, columnspan=2, sticky="ew", pady=(12, 0)
        )

        table_frame = ttk.LabelFrame(top, text="Liste", style="Card.TLabelframe")
        table_frame.pack(side="left", fill="both", expand=True)
        self.table = DataTable(table_frame, height=18)
        self.table.pack(fill="both", expand=True)

    def refresh_users(self) -> None:
        rows = DatabaseHelper.list_users()
        self.table.set_data(
            rows,
            columns=["Id", "NomComplet", "Identifiant", "Email", "MotDePasse", "Role"],
            headings={
                "NomComplet": "Nom complet",
                "Identifiant": "Identifiant",
                "Email": "Adresse e-mail",
                "MotDePasse": "Mot de passe",
                "Role": "Rôle",
            },
            hidden_columns=["Id"],
        )
        self.message_var.set("Liste des utilisateurs affichée.")

    def toggle_password_visibility(self) -> None:
        self.password_entry.configure(show="" if self.show_password_var.get() else "*")

    def refresh_live_view(self) -> None:
        self.refresh_users()

    def search_user(self) -> None:
        identifiant = self.identifiant_var.get().strip()
        if not identifiant:
            messagebox.showwarning("Utilisateurs", "Veuillez saisir un identifiant.")
            return
        rows = DatabaseHelper.search_users_by_identifiant(identifiant)
        self.table.set_data(
            rows,
            columns=["Id", "NomComplet", "Identifiant", "Email", "MotDePasse", "Role"],
            headings={
                "NomComplet": "Nom complet",
                "Identifiant": "Identifiant",
                "Email": "Adresse e-mail",
                "MotDePasse": "Mot de passe",
                "Role": "Rôle",
            },
            hidden_columns=["Id"],
        )
        self.message_var.set("Recherche terminée." if rows else "Aucun utilisateur trouvé.")

    def save_user(self) -> None:
        if not self.ensure_module_writable("Utilisateurs"):
            return
        name = self.name_var.get().strip()
        identifiant = self.identifiant_var.get().strip()
        email = self.email_var.get().strip()
        password = self.password_var.get().strip()
        role = self.role_var.get().strip()

        if not name or not identifiant or not role:
            messagebox.showwarning(
                "Utilisateurs",
                "Veuillez saisir le nom complet, l'identifiant et le rÃ´le. "
                "Si l'e-mail est vide, une adresse @boulangerie-lomoto.com sera crÃ©Ã©e.",
            )
            return
        if not self.edit_mode and not password:
            messagebox.showwarning("Utilisateurs", "Veuillez saisir un mot de passe.")
            return

        try:
            if self.edit_mode:
                updated = DatabaseHelper.update_user(self.original_identifiant, name, password, role, email)
                message = "Utilisateur modifié avec succès." if updated else "Aucune modification effectuée."
                if updated:
                    log_user_action(
                        self,
                        "Utilisateurs",
                        "Utilisateur modifié",
                        f"{self.original_identifiant} -> rôle {role}",
                    )
            else:
                DatabaseHelper.add_user(name, identifiant, password, role, email)
                message = "Utilisateur ajouté avec succès."
                log_user_action(self, "Utilisateurs", "Utilisateur ajouté", f"{identifiant} | rôle {role}")
            message += process_email_notifications_for_ui()
            self.reset_form()
            self.refresh_users()
            self.message_var.set(message)
        except Exception as exc:
            self.message_var.set(str(exc))

    def load_user_for_edit(self) -> None:
        row = self.table.selected_row()
        if row is None:
            messagebox.showwarning("Utilisateurs", "Veuillez d'abord sélectionner un utilisateur.")
            return
        user = DatabaseHelper.get_user_for_admin_edit(str(row["Identifiant"]))
        if not user:
            messagebox.showwarning("Utilisateurs", "Utilisateur introuvable.")
            return
        self.name_var.set(str(user.get("NomComplet", "")))
        self.identifiant_var.set(str(user.get("Identifiant", "")))
        self.email_var.set(str(user.get("Email", "")))
        self.password_var.set("")
        self.show_password_var.set(False)
        self.toggle_password_visibility()
        self.role_var.set(str(user.get("Role", "")))
        self.original_identifiant = str(user.get("Identifiant", ""))
        self.edit_mode = True
        self.identifiant_entry.state(["disabled"])
        self.message_var.set(
            "Le mot de passe actuel n'est jamais affiché. Laissez le champ vide pour le conserver, "
            "ou saisissez un mot de passe fort conforme au rôle."
        )

    def delete_user(self) -> None:
        if not self.ensure_module_writable("Utilisateurs"):
            return
        identifiant = self.identifiant_var.get().strip()
        if not identifiant:
            messagebox.showwarning("Utilisateurs", "Veuillez saisir l'identifiant à supprimer.")
            return
        if not messagebox.askyesno("Confirmation", "Voulez-vous vraiment supprimer cet utilisateur ?"):
            return

        try:
            role = DatabaseHelper.get_user_role(identifiant)
            if role == "Admin" and DatabaseHelper.count_admins() <= 1:
                self.message_var.set("Impossible de supprimer le dernier administrateur.")
                return
            deleted = DatabaseHelper.delete_user(identifiant)
            if deleted:
                log_user_action(self, "Utilisateurs", "Utilisateur supprimé", identifiant)
                self.reset_form()
                self.refresh_users()
                self.message_var.set("Utilisateur supprimé avec succès.")
            else:
                self.message_var.set("Aucun utilisateur trouvé avec cet identifiant.")
        except Exception as exc:
            self.message_var.set(str(exc))

    def reset_form(self) -> None:
        self.name_var.set("")
        self.identifiant_var.set("")
        self.email_var.set("")
        self.password_var.set("")
        self.show_password_var.set(False)
        self.toggle_password_visibility()
        self.role_var.set(ROLES[0])
        self.edit_mode = False
        self.original_identifiant = ""
        self.identifiant_entry.state(["!disabled"])
        self.name_entry.focus()


class WorkersPayrollWindow(BaseModuleWindow):
    def __init__(self, parent: DashboardWindow) -> None:
        super().__init__(parent, "Travailleurs et paies", "1180x780")
        self.worker_edit_id = 0
        self.payroll_edit_id = 0
        self.worker_options: dict[str, int] = {}
        self.build_ui()
        self.after_idle(self.refresh_all)

    def build_ui(self) -> None:
        container = self.body
        container.columnconfigure(0, weight=1)
        container.rowconfigure(2, weight=1)

        top_bar = ttk.Frame(container)
        top_bar.grid(row=0, column=0, sticky="ew", pady=(0, 12))
        top_bar.columnconfigure(0, weight=1)
        self.summary_var = tk.StringVar(value="Chargement du résumé...")
        ttk.Label(
            top_bar,
            textvariable=self.summary_var,
            foreground=ACCENT_DARK_COLOR,
            justify="left",
            wraplength=900,
        ).grid(row=0, column=0, sticky="ew")
        ttk.Button(top_bar, text="Fermer", style="Primary.TButton", command=self.close_window).grid(
            row=0, column=1, sticky="e", padx=(12, 0)
        )

        forms = ttk.Frame(container)
        forms.grid(row=1, column=0, sticky="ew", pady=(0, 12))
        forms.columnconfigure(0, weight=1)
        forms.columnconfigure(1, weight=1)

        worker_form = ttk.LabelFrame(forms, text="Fiche travailleur", style="Card.TLabelframe")
        worker_form.grid(row=0, column=0, sticky="nsew", padx=(0, 8))
        worker_form.columnconfigure(1, weight=1)

        self.worker_name_var = tk.StringVar()
        self.worker_function_var = tk.StringVar()
        self.worker_phone_var = tk.StringVar()
        self.worker_email_var = tk.StringVar()
        self.worker_address_var = tk.StringVar()
        self.worker_salary_var = tk.StringVar(value="0")
        self.worker_status_var = tk.StringVar(value="Actif")
        self.worker_observations_var = tk.StringVar()

        ttk.Label(worker_form, text="Nom complet").grid(row=0, column=0, sticky="w", pady=5)
        ttk.Entry(worker_form, textvariable=self.worker_name_var, width=34).grid(row=0, column=1, sticky="ew", pady=5)
        ttk.Label(worker_form, text="Fonction").grid(row=1, column=0, sticky="w", pady=5)
        ttk.Entry(worker_form, textvariable=self.worker_function_var).grid(row=1, column=1, sticky="ew", pady=5)
        ttk.Label(worker_form, text="Téléphone").grid(row=2, column=0, sticky="w", pady=5)
        ttk.Entry(worker_form, textvariable=self.worker_phone_var).grid(row=2, column=1, sticky="ew", pady=5)
        ttk.Label(worker_form, text="Adresse e-mail").grid(row=3, column=0, sticky="w", pady=5)
        ttk.Entry(worker_form, textvariable=self.worker_email_var).grid(row=3, column=1, sticky="ew", pady=5)
        ttk.Label(worker_form, text="Adresse").grid(row=4, column=0, sticky="w", pady=5)
        ttk.Entry(worker_form, textvariable=self.worker_address_var).grid(row=4, column=1, sticky="ew", pady=5)
        ttk.Label(worker_form, text="Date d'embauche").grid(row=5, column=0, sticky="w", pady=5)
        self.hire_date_field = DateField(worker_form, today_iso())
        self.hire_date_field.grid(row=5, column=1, sticky="ew", pady=5)
        ttk.Label(worker_form, text="Salaire mensuel").grid(row=6, column=0, sticky="w", pady=5)
        ttk.Entry(worker_form, textvariable=self.worker_salary_var).grid(row=6, column=1, sticky="ew", pady=5)
        ttk.Label(worker_form, text="Statut").grid(row=7, column=0, sticky="w", pady=5)
        ttk.Combobox(
            worker_form,
            textvariable=self.worker_status_var,
            values=["Actif", "Suspendu", "Inactif"],
            state="readonly",
        ).grid(row=7, column=1, sticky="ew", pady=5)
        ttk.Label(worker_form, text="Observations").grid(row=8, column=0, sticky="w", pady=5)
        ttk.Entry(worker_form, textvariable=self.worker_observations_var).grid(row=8, column=1, sticky="ew", pady=5)

        worker_buttons = ttk.Frame(worker_form)
        worker_buttons.grid(row=9, column=0, columnspan=2, pady=(12, 0))
        ttk.Button(worker_buttons, text="Enregistrer", command=self.save_worker).grid(row=0, column=0, padx=4, pady=4)
        ttk.Button(worker_buttons, text="Modifier", command=self.load_worker_for_edit).grid(row=0, column=1, padx=4, pady=4)
        ttk.Button(worker_buttons, text="Supprimer / désactiver", command=self.delete_worker).grid(
            row=0, column=2, padx=4, pady=4
        )
        ttk.Button(worker_buttons, text="Nouveau", command=self.reset_worker_form).grid(row=1, column=0, padx=4, pady=4)

        payroll_form = ttk.LabelFrame(forms, text="Paie du travailleur", style="Card.TLabelframe")
        payroll_form.grid(row=0, column=1, sticky="nsew", padx=(8, 0))
        payroll_form.columnconfigure(1, weight=1)

        self.payroll_worker_var = tk.StringVar()
        self.payroll_period_var = tk.StringVar(value=date.today().strftime("%m/%Y"))
        self.payroll_gross_var = tk.StringVar(value="0")
        self.payroll_bonus_var = tk.StringVar(value="0")
        self.payroll_advance_var = tk.StringVar(value="0")
        self.payroll_withholding_var = tk.StringVar(value="0")
        self.payroll_net_var = tk.StringVar(value="0 FC")
        self.payroll_mode_var = tk.StringVar(value="Espèces")
        self.payroll_status_var = tk.StringVar(value="Préparée")
        self.payroll_observations_var = tk.StringVar()

        ttk.Label(payroll_form, text="Travailleur").grid(row=0, column=0, sticky="w", pady=5)
        self.payroll_worker_combo = ttk.Combobox(
            payroll_form,
            textvariable=self.payroll_worker_var,
            values=[],
            state="readonly",
        )
        self.payroll_worker_combo.grid(row=0, column=1, sticky="ew", pady=5)
        ttk.Label(payroll_form, text="Date de paie").grid(row=1, column=0, sticky="w", pady=5)
        self.payroll_date_field = DateField(payroll_form, today_iso())
        self.payroll_date_field.grid(row=1, column=1, sticky="ew", pady=5)
        ttk.Label(payroll_form, text="Période").grid(row=2, column=0, sticky="w", pady=5)
        ttk.Entry(payroll_form, textvariable=self.payroll_period_var).grid(row=2, column=1, sticky="ew", pady=5)
        ttk.Label(payroll_form, text="Montant brut").grid(row=3, column=0, sticky="w", pady=5)
        ttk.Entry(payroll_form, textvariable=self.payroll_gross_var).grid(row=3, column=1, sticky="ew", pady=5)
        ttk.Label(payroll_form, text="Prime").grid(row=4, column=0, sticky="w", pady=5)
        ttk.Entry(payroll_form, textvariable=self.payroll_bonus_var).grid(row=4, column=1, sticky="ew", pady=5)
        ttk.Label(payroll_form, text="Avance").grid(row=5, column=0, sticky="w", pady=5)
        ttk.Entry(payroll_form, textvariable=self.payroll_advance_var).grid(row=5, column=1, sticky="ew", pady=5)
        ttk.Label(payroll_form, text="Retenue").grid(row=6, column=0, sticky="w", pady=5)
        ttk.Entry(payroll_form, textvariable=self.payroll_withholding_var).grid(row=6, column=1, sticky="ew", pady=5)
        ttk.Label(payroll_form, text="Net à payer").grid(row=7, column=0, sticky="w", pady=5)
        ttk.Label(payroll_form, textvariable=self.payroll_net_var, foreground=DANGER_COLOR).grid(
            row=7, column=1, sticky="w", pady=5
        )
        ttk.Label(payroll_form, text="Mode paiement").grid(row=8, column=0, sticky="w", pady=5)
        ttk.Combobox(
            payroll_form,
            textvariable=self.payroll_mode_var,
            values=["Espèces", "Mobile money", "Virement", "Autre"],
            state="readonly",
        ).grid(row=8, column=1, sticky="ew", pady=5)
        ttk.Label(payroll_form, text="Statut").grid(row=9, column=0, sticky="w", pady=5)
        ttk.Combobox(
            payroll_form,
            textvariable=self.payroll_status_var,
            values=["Préparée", "Validée", "Payée", "En attente", "Avance seulement"],
            state="readonly",
        ).grid(row=9, column=1, sticky="ew", pady=5)
        ttk.Label(payroll_form, text="Observations").grid(row=10, column=0, sticky="w", pady=5)
        ttk.Entry(payroll_form, textvariable=self.payroll_observations_var).grid(row=10, column=1, sticky="ew", pady=5)

        payroll_buttons = ttk.Frame(payroll_form)
        payroll_buttons.grid(row=11, column=0, columnspan=2, pady=(12, 0))
        ttk.Button(payroll_buttons, text="Enregistrer", command=self.save_payroll).grid(row=0, column=0, padx=4, pady=4)
        ttk.Button(payroll_buttons, text="Modifier", command=self.load_payroll_for_edit).grid(row=0, column=1, padx=4, pady=4)
        ttk.Button(payroll_buttons, text="Supprimer", command=self.delete_payroll).grid(row=0, column=2, padx=4, pady=4)
        ttk.Button(payroll_buttons, text="Nouvelle paie", command=self.reset_payroll_form).grid(row=1, column=0, padx=4, pady=4)

        for var in (
            self.payroll_gross_var,
            self.payroll_bonus_var,
            self.payroll_advance_var,
            self.payroll_withholding_var,
        ):
            var.trace_add("write", lambda *_args: self.update_payroll_net_preview())

        tables = ttk.PanedWindow(container, orient="horizontal")
        tables.grid(row=2, column=0, sticky="nsew")
        workers_frame = ttk.LabelFrame(tables, text="Liste des travailleurs", style="Card.TLabelframe")
        payrolls_frame = ttk.LabelFrame(tables, text="Historique des paies", style="Card.TLabelframe")
        tables.add(workers_frame, weight=1)
        tables.add(payrolls_frame, weight=1)

        self.workers_table = DataTable(workers_frame, height=16)
        self.workers_table.pack(fill="both", expand=True)
        self.workers_table.tree.bind("<Double-1>", lambda _event: self.load_worker_for_edit())
        self.payrolls_table = DataTable(payrolls_frame, height=16)
        self.payrolls_table.pack(fill="both", expand=True)
        self.payrolls_table.tree.bind("<Double-1>", lambda _event: self.load_payroll_for_edit())

        self.message_var = tk.StringVar(value="")
        ttk.Label(container, textvariable=self.message_var, foreground=DANGER_COLOR, wraplength=980).grid(
            row=3, column=0, sticky="ew", pady=(12, 0)
        )
        actions = ttk.Frame(container)
        actions.grid(row=4, column=0, sticky="e", pady=(12, 0))
        ttk.Button(actions, text="Fermer", style="Primary.TButton", command=self.close_window).grid(row=0, column=0)

    def refresh_live_view(self) -> None:
        self.refresh_all()

    def refresh_all(self) -> None:
        self.refresh_workers()
        self.refresh_payrolls()
        self.refresh_summary()

    def refresh_workers(self) -> None:
        rows = DatabaseHelper.list_workers(include_inactive=True)
        self.workers_table.set_data(
            rows,
            columns=[
                "Id",
                "NomComplet",
                "Fonction",
                "Telephone",
                "Email",
                "DateEmbauche",
                "Anciennete",
                "SalaireMensuel",
                "Statut",
                "TotalPaye",
                "DernierePaie",
            ],
            headings={
                "NomComplet": "Nom complet",
                "Fonction": "Fonction",
                "Telephone": "Téléphone",
                "Email": "Adresse e-mail",
                "DateEmbauche": "Embauche",
                "Anciennete": "Ancienneté",
                "SalaireMensuel": "Salaire mensuel",
                "Statut": "Statut",
                "TotalPaye": "Total payé",
                "DernierePaie": "Dernière paie",
            },
            hidden_columns=["Id"],
            formatters={
                "SalaireMensuel": lambda value: format_fc(float(value or 0)),
                "TotalPaye": lambda value: format_fc(float(value or 0)),
            },
        )
        self.worker_options = {
            f"{row['Id']} - {row['NomComplet']}": int(row["Id"])
            for row in rows
            if str(row.get("Statut", "")) == "Actif"
        }
        self.payroll_worker_combo.configure(values=list(self.worker_options.keys()))
        if not self.payroll_worker_var.get() and self.worker_options:
            self.payroll_worker_var.set(next(iter(self.worker_options)))

    def refresh_payrolls(self) -> None:
        rows = DatabaseHelper.list_payrolls()
        self.payrolls_table.set_data(
            rows,
            columns=[
                "Id",
                "TravailleurId",
                "DatePaie",
                "Periode",
                "NomComplet",
                "Fonction",
                "MontantBrut",
                "Prime",
                "Avance",
                "Retenue",
                "MontantNet",
                "ModePaiement",
                "Statut",
            ],
            headings={
                "DatePaie": "Date",
                "Periode": "Période",
                "NomComplet": "Travailleur",
                "Fonction": "Fonction",
                "MontantBrut": "Brut",
                "Prime": "Prime",
                "Avance": "Avance",
                "Retenue": "Retenue",
                "MontantNet": "Net",
                "ModePaiement": "Mode",
                "Statut": "Statut",
            },
            hidden_columns=["Id", "TravailleurId"],
            formatters={
                "MontantBrut": lambda value: format_fc(float(value or 0)),
                "Prime": lambda value: format_fc(float(value or 0)),
                "Avance": lambda value: format_fc(float(value or 0)),
                "Retenue": lambda value: format_fc(float(value or 0)),
                "MontantNet": lambda value: format_fc(float(value or 0)),
            },
        )

    def refresh_summary(self) -> None:
        summary = DatabaseHelper.get_workers_payroll_summary()
        self.summary_var.set(
            "Travailleurs : "
            f"{int(summary.get('NombreTravailleurs', 0) or 0)} | "
            f"Actifs : {int(summary.get('TravailleursActifs', 0) or 0)} | "
            f"Masse salariale mensuelle : {format_fc(float(summary.get('MasseSalarialeMensuelle', 0) or 0))} | "
            f"Total net payé : {format_fc(float(summary.get('TotalNet', 0) or 0))}"
        )

    def selected_worker_id_for_payroll(self) -> int:
        label = self.payroll_worker_var.get().strip()
        return int(self.worker_options.get(label, 0))

    def update_payroll_net_preview(self) -> None:
        try:
            gross = parse_optional_float(self.payroll_gross_var.get())
            bonus = parse_optional_float(self.payroll_bonus_var.get())
            advance = parse_optional_float(self.payroll_advance_var.get())
            withholding = parse_optional_float(self.payroll_withholding_var.get())
            self.payroll_net_var.set(format_fc(gross + bonus - advance - withholding))
        except Exception:
            self.payroll_net_var.set("Calcul impossible")

    def save_worker(self) -> None:
        if not self.ensure_module_writable("Travailleurs"):
            return
        try:
            salary = parse_optional_float(self.worker_salary_var.get())
            if self.worker_edit_id:
                updated = DatabaseHelper.update_worker(
                    self.worker_edit_id,
                    self.worker_name_var.get(),
                    self.worker_function_var.get(),
                    self.worker_phone_var.get(),
                    self.worker_email_var.get(),
                    self.worker_address_var.get(),
                    self.hire_date_field.get_date(),
                    salary,
                    self.worker_status_var.get(),
                    self.worker_observations_var.get(),
                )
                message = "Travailleur modifié avec succès." if updated else "Aucune modification effectuée."
                action = "Travailleur modifié"
            else:
                worker_id = DatabaseHelper.add_worker(
                    self.worker_name_var.get(),
                    self.worker_function_var.get(),
                    self.worker_phone_var.get(),
                    self.worker_email_var.get(),
                    self.worker_address_var.get(),
                    self.hire_date_field.get_date(),
                    salary,
                    self.worker_status_var.get(),
                    self.worker_observations_var.get(),
                )
                message = "Travailleur ajouté avec succès."
                action = "Travailleur ajouté"
                self.worker_edit_id = worker_id
            log_user_action(self, "Travailleurs", action, self.worker_name_var.get().strip())
            self.reset_worker_form()
            self.refresh_all()
            self.message_var.set(message)
        except Exception as exc:
            self.message_var.set(str(exc))

    def load_worker_for_edit(self) -> None:
        row = self.workers_table.selected_row()
        if row is None:
            messagebox.showwarning("Travailleurs", "Veuillez sélectionner un travailleur.")
            return
        self.worker_edit_id = int(row["Id"])
        self.worker_name_var.set(str(row.get("NomComplet", "")))
        self.worker_function_var.set(str(row.get("Fonction", "")))
        self.worker_phone_var.set(str(row.get("Telephone", "")))
        self.worker_email_var.set(str(row.get("Email", "")))
        self.worker_address_var.set(str(row.get("Adresse", "")))
        self.hire_date_field.set_date(str(row.get("DateEmbauche", today_iso()) or today_iso()))
        self.worker_salary_var.set(format_number(float(row.get("SalaireMensuel", 0) or 0)))
        self.worker_status_var.set(str(row.get("Statut", "Actif") or "Actif"))
        self.worker_observations_var.set(str(row.get("Observations", "")))
        self.set_payroll_worker(int(row["Id"]))
        self.message_var.set("Travailleur chargé. Modifiez les informations puis enregistrez.")

    def delete_worker(self) -> None:
        if not self.ensure_module_writable("Travailleurs"):
            return
        row = self.workers_table.selected_row()
        if row is None:
            messagebox.showwarning("Travailleurs", "Veuillez sélectionner un travailleur.")
            return
        if not messagebox.askyesno(
            "Travailleurs",
            "Voulez-vous vraiment supprimer ce travailleur ?\n\n"
            "S'il possède déjà un historique de paie, il sera plutôt marqué comme inactif pour conserver les traces.",
        ):
            return
        try:
            deleted = DatabaseHelper.delete_worker(int(row["Id"]))
            if deleted:
                log_user_action(self, "Travailleurs", "Travailleur supprimé ou désactivé", str(row.get("NomComplet", "")))
                self.reset_worker_form()
                self.reset_payroll_form()
                self.refresh_all()
                self.message_var.set("Travailleur supprimé ou désactivé avec succès.")
            else:
                self.message_var.set("Aucun travailleur supprimé.")
        except Exception as exc:
            self.message_var.set(str(exc))

    def reset_worker_form(self) -> None:
        self.worker_edit_id = 0
        self.worker_name_var.set("")
        self.worker_function_var.set("")
        self.worker_phone_var.set("")
        self.worker_email_var.set("")
        self.worker_address_var.set("")
        self.hire_date_field.set_date(today_iso())
        self.worker_salary_var.set("0")
        self.worker_status_var.set("Actif")
        self.worker_observations_var.set("")

    def set_payroll_worker(self, worker_id: int) -> None:
        for label, current_id in self.worker_options.items():
            if current_id == worker_id:
                self.payroll_worker_var.set(label)
                return

    def save_payroll(self) -> None:
        if not self.ensure_module_writable("Travailleurs", "Paies"):
            return
        try:
            worker_id = self.selected_worker_id_for_payroll()
            gross = parse_optional_float(self.payroll_gross_var.get())
            bonus = parse_optional_float(self.payroll_bonus_var.get())
            advance = parse_optional_float(self.payroll_advance_var.get())
            withholding = parse_optional_float(self.payroll_withholding_var.get())
            if self.payroll_edit_id:
                updated = DatabaseHelper.update_payroll(
                    self.payroll_edit_id,
                    worker_id,
                    self.payroll_date_field.get_date(),
                    self.payroll_period_var.get(),
                    gross,
                    bonus,
                    advance,
                    withholding,
                    self.payroll_mode_var.get(),
                    self.payroll_status_var.get(),
                    self.payroll_observations_var.get(),
                )
                message = "Paie modifiée avec succès." if updated else "Aucune modification effectuée."
                action = "Paie modifiée"
            else:
                DatabaseHelper.add_payroll(
                    worker_id,
                    self.payroll_date_field.get_date(),
                    self.payroll_period_var.get(),
                    gross,
                    bonus,
                    advance,
                    withholding,
                    self.payroll_mode_var.get(),
                    self.payroll_status_var.get(),
                    self.payroll_observations_var.get(),
                )
                message = "Paie enregistrée avec succès."
                action = "Paie enregistrée"
            log_user_action(self, "Travailleurs", action, self.payroll_worker_var.get())
            message += process_email_notifications_for_ui()
            self.reset_payroll_form()
            self.refresh_all()
            self.message_var.set(message)
        except Exception as exc:
            self.message_var.set(str(exc))

    def load_payroll_for_edit(self) -> None:
        row = self.payrolls_table.selected_row()
        if row is None:
            messagebox.showwarning("Paies", "Veuillez sélectionner une paie.")
            return
        self.payroll_edit_id = int(row["Id"])
        self.set_payroll_worker(int(row["TravailleurId"]))
        self.payroll_date_field.set_date(str(row.get("DatePaie", today_iso()) or today_iso()))
        self.payroll_period_var.set(str(row.get("Periode", "")))
        self.payroll_gross_var.set(format_number(float(row.get("MontantBrut", 0) or 0)))
        self.payroll_bonus_var.set(format_number(float(row.get("Prime", 0) or 0)))
        self.payroll_advance_var.set(format_number(float(row.get("Avance", 0) or 0)))
        self.payroll_withholding_var.set(format_number(float(row.get("Retenue", 0) or 0)))
        self.payroll_mode_var.set(str(row.get("ModePaiement", "Espèces") or "Espèces"))
        self.payroll_status_var.set(str(row.get("Statut", "Payée") or "Payée"))
        self.payroll_observations_var.set(str(row.get("Observations", "")))
        self.update_payroll_net_preview()
        self.message_var.set("Paie chargée. Modifiez les informations puis enregistrez.")

    def delete_payroll(self) -> None:
        if not self.ensure_module_writable("Travailleurs", "Paies"):
            return
        row = self.payrolls_table.selected_row()
        if row is None:
            messagebox.showwarning("Paies", "Veuillez sélectionner une paie.")
            return
        if not messagebox.askyesno("Paies", "Voulez-vous vraiment supprimer cette paie ?"):
            return
        try:
            deleted = DatabaseHelper.delete_payroll(int(row["Id"]))
            if deleted:
                log_user_action(self, "Travailleurs", "Paie supprimée", str(row.get("NomComplet", "")))
                self.reset_payroll_form()
                self.refresh_all()
                self.message_var.set("Paie supprimée avec succès.")
            else:
                self.message_var.set("Aucune paie supprimée.")
        except Exception as exc:
            self.message_var.set(str(exc))

    def reset_payroll_form(self) -> None:
        self.payroll_edit_id = 0
        if self.worker_options:
            self.payroll_worker_var.set(next(iter(self.worker_options)))
        else:
            self.payroll_worker_var.set("")
        self.payroll_date_field.set_date(today_iso())
        self.payroll_period_var.set(date.today().strftime("%m/%Y"))
        self.payroll_gross_var.set("0")
        self.payroll_bonus_var.set("0")
        self.payroll_advance_var.set("0")
        self.payroll_withholding_var.set("0")
        self.payroll_mode_var.set("Espèces")
        self.payroll_status_var.set("Préparée")
        self.payroll_observations_var.set("")
        self.update_payroll_net_preview()


class StockWindow(BaseModuleWindow):
    def __init__(self, parent: DashboardWindow) -> None:
        super().__init__(parent, "Gestion du stock", "1160x780")
        self.edit_mode = False
        self.selected_exit_id = 0
        self.first_open_of_day = False
        self.closing_message_shown = False
        self.build_ui()
        self.opening_var.set("Chargement du stock du jour...")
        self.closing_var.set("")
        self.after_idle(self.finish_initial_load)

    def finish_initial_load(self) -> None:
        if self.is_read_only_module("Stock"):
            self.first_open_of_day = False
        else:
            self.first_open_of_day = DatabaseHelper.initialize_stock_day(date.today())
        self.refresh_data()
        if self.first_open_of_day:
            self.show_opening_message()

    def build_ui(self) -> None:
        container = self.body

        info_frame = ttk.LabelFrame(container, text="Stock du jour", style="Card.TLabelframe")
        info_frame.pack(fill="x", pady=(0, 12))
        self.opening_var = tk.StringVar()
        self.closing_var = tk.StringVar()
        ttk.Label(info_frame, textvariable=self.opening_var).pack(anchor="w", pady=3)
        ttk.Label(info_frame, textvariable=self.closing_var, foreground="#7a0000").pack(anchor="w", pady=3)

        content = ttk.Frame(container)
        content.pack(fill="both", expand=True)
        self.create_day_lock_notice(container, "la gestion du stock", before=content)

        form = ttk.LabelFrame(content, text="Sortie de stock", style="Card.TLabelframe")
        form.pack(side="left", fill="y", padx=(0, 12))

        ttk.Label(form, text="Date").grid(row=0, column=0, sticky="w", pady=6)
        self.date_field = DateField(form)
        self.date_field.grid(row=0, column=1, sticky="ew", pady=6)

        self.sacs_var = tk.StringVar()
        self.paquets_var = tk.StringVar()
        self.sel_var = tk.StringVar()
        self.huile_var = tk.StringVar()

        self._make_entry(form, "Farine (sacs)", self.sacs_var, 1)
        self._make_entry(form, "Levure (paquets)", self.paquets_var, 2)
        self._make_entry(form, "Sel (kg)", self.sel_var, 3)
        self._make_entry(form, "Huile (litres)", self.huile_var, 4)

        button_bar = ttk.Frame(form)
        button_bar.grid(row=5, column=0, columnspan=2, pady=(14, 0))
        self.save_button = ttk.Button(button_bar, text="Enregistrer", command=self.save_exit)
        self.save_button.grid(row=0, column=0, padx=4, pady=4)
        self.edit_button = ttk.Button(button_bar, text="Modifier", command=self.load_selected_exit)
        self.edit_button.grid(row=0, column=1, padx=4, pady=4)
        self.delete_button = ttk.Button(button_bar, text="Supprimer", command=self.delete_exit)
        self.delete_button.grid(row=0, column=2, padx=4, pady=4)
        ttk.Button(button_bar, text="Paramètres", command=self.edit_stock_parameters).grid(
            row=1, column=0, padx=4, pady=4
        )
        ttk.Button(button_bar, text="Approvisionner", command=self.open_stock_supply_window).grid(
            row=1, column=1, padx=4, pady=4
        )
        ttk.Button(button_bar, text="Fermer", command=self.close_window).grid(row=1, column=2, padx=4, pady=4)

        form.columnconfigure(1, weight=1)

        table_frame = ttk.LabelFrame(content, text="Historique des sorties", style="Card.TLabelframe")
        table_frame.pack(side="left", fill="both", expand=True)
        self.table = DataTable(table_frame, height=18)
        self.table.pack(fill="both", expand=True)
        self.configure_day_lock_controls(
            self.date_field,
            [self.save_button, self.edit_button, self.delete_button],
        )

    def _make_entry(self, parent: ttk.LabelFrame, label: str, variable: tk.StringVar, row: int) -> None:
        ttk.Label(parent, text=label).grid(row=row, column=0, sticky="w", pady=6)
        ttk.Entry(parent, textvariable=variable, width=20).grid(row=row, column=1, sticky="ew", pady=6)

    def refresh_live_view(self) -> None:
        self.refresh_data()

    def refresh_data(self) -> None:
        if not self.is_read_only_module("Stock"):
            DatabaseHelper.update_stock_closing(date.today())
        journal = DatabaseHelper.get_stock_journal(date.today())
        if journal:
            self.opening_var.set(
                "Ouverture du jour | "
                f"Farine : {format_number(float(journal['FarineOuverture']))} sacs | "
                f"Levure : {format_number(float(journal['LevureOuverture']))} paquets | "
                f"Sel : {format_number(float(journal['SelOuverture']))} kg | "
                f"Huile : {format_number(float(journal['HuileOuverture']))} litres"
            )
            self.closing_var.set(
                "Clôture courante | "
                f"Farine : {format_number(float(journal['FarineCloture']))} sacs | "
                f"Levure : {format_number(float(journal['LevureCloture']))} paquets | "
                f"Sel : {format_number(float(journal['SelCloture']))} kg | "
                f"Huile : {format_number(float(journal['HuileCloture']))} litres"
            )
        rows = DatabaseHelper.list_stock_exits()
        self.table.set_data(
            rows,
            columns=["Id", "DateSortie", "SacsUtilises", "PaquetsUtilises", "KgSelUtilises", "LitresHuileUtilises"],
            headings={
                "DateSortie": "Date",
                "SacsUtilises": "Farine",
                "PaquetsUtilises": "Levure",
                "KgSelUtilises": "Sel",
                "LitresHuileUtilises": "Huile",
            },
            hidden_columns=["Id"],
            formatters={
                "SacsUtilises": lambda value: format_number(float(value)),
                "PaquetsUtilises": lambda value: format_number(float(value)),
                "KgSelUtilises": lambda value: format_number(float(value)),
                "LitresHuileUtilises": lambda value: format_number(float(value)),
            },
        )
        self.refresh_day_lock_state()

    def show_opening_message(self) -> None:
        journal = DatabaseHelper.get_stock_journal(date.today())
        if not journal:
            return
        messagebox.showinfo(
            "Ouverture du jour",
            "Stock d'ouverture du jour :\n"
            f"Farine : {format_number(float(journal['FarineOuverture']))} sacs\n"
            f"Levure : {format_number(float(journal['LevureOuverture']))} paquets\n"
            f"Sel : {format_number(float(journal['SelOuverture']))} kg\n"
            f"Huile : {format_number(float(journal['HuileOuverture']))} litres",
        )

    def validate_exit(self) -> tuple[date, float, float, float, float] | None:
        try:
            target_date = self.date_field.get_date()
            sacs = parse_float(self.sacs_var.get(), "Farine")
            paquets = parse_float(self.paquets_var.get(), "Levure")
            sel = parse_float(self.sel_var.get(), "Sel")
            huile = parse_float(self.huile_var.get(), "Huile")
        except Exception as exc:
            messagebox.showwarning("Stock", str(exc))
            return None

        if min(sacs, paquets, sel, huile) < 0:
            messagebox.showwarning("Stock", "Les quantités ne peuvent pas être négatives.")
            return None
        if sacs == 0 and paquets == 0 and sel == 0 and huile == 0:
            messagebox.showwarning("Stock", "Veuillez saisir au moins une quantité supérieure à zéro.")
            return None

        summary = DatabaseHelper.get_stock_summary(self.selected_exit_id if self.edit_mode else 0)
        if not summary:
            messagebox.showwarning("Stock", "Impossible de vérifier le stock disponible.")
            return None

        remaining = {
            "Farine": float(summary["FarineRestante"]),
            "Levure": float(summary["LevureRestante"]),
            "Sel": float(summary["SelRestant"]),
            "Huile": float(summary["HuileRestante"]),
        }
        requested = {
            "Farine": sacs,
            "Levure": paquets,
            "Sel": sel,
            "Huile": huile,
        }
        for label, value in requested.items():
            if value > remaining[label]:
                messagebox.showwarning(
                    "Stock",
                    f"La quantité de {label.lower()} dépasse le stock disponible.",
                )
                return None

        return target_date, sacs, paquets, sel, huile

    def save_exit(self) -> None:
        if not self.ensure_module_writable("Stock"):
            return
        validated = self.validate_exit()
        if validated is None:
            return
        target_date, sacs, paquets, sel, huile = validated
        try:
            if self.edit_mode:
                updated = DatabaseHelper.update_stock_exit(
                    self.selected_exit_id, target_date, sacs, paquets, sel, huile
                )
                if updated:
                    log_user_action(
                        self,
                        "Stock",
                        "Sortie de stock modifiée",
                        f"{target_date.strftime('%d/%m/%Y')} | Farine {format_number(sacs)} | Levure {format_number(paquets)} | Sel {format_number(sel)} | Huile {format_number(huile)}",
                    )
                    messagebox.showinfo("Stock", "La sortie de stock a été modifiée avec succès.")
                else:
                    messagebox.showwarning("Stock", "Aucune modification n'a été enregistrée.")
            else:
                DatabaseHelper.add_stock_exit(target_date, sacs, paquets, sel, huile)
                log_user_action(
                    self,
                    "Stock",
                    "Sortie de stock ajoutée",
                    f"{target_date.strftime('%d/%m/%Y')} | Farine {format_number(sacs)} | Levure {format_number(paquets)} | Sel {format_number(sel)} | Huile {format_number(huile)}",
                )
                messagebox.showinfo("Stock", "La sortie de stock a été enregistrée avec succès.")
            self.reset_form()
            self.refresh_data()
        except ValueError as exc:
            messagebox.showwarning("Stock", str(exc))
        except Exception as exc:
            messagebox.showerror("Stock", str(exc))

    def load_selected_exit(self) -> None:
        row = self.table.selected_row()
        if row is None:
            messagebox.showwarning("Stock", "Veuillez sélectionner une sortie dans la grille.")
            return
        self.selected_exit_id = int(row["Id"])
        self.edit_mode = True
        self.date_field.set_date(str(row["DateSortie"]))
        self.sacs_var.set(format_number(float(row["SacsUtilises"])))
        self.paquets_var.set(format_number(float(row["PaquetsUtilises"])))
        self.sel_var.set(format_number(float(row["KgSelUtilises"])))
        self.huile_var.set(format_number(float(row["LitresHuileUtilises"])))
        self.refresh_day_lock_state()
        messagebox.showinfo("Stock", "La sortie a été chargée. Modifiez-la puis enregistrez.")

    def delete_exit(self) -> None:
        if not self.ensure_module_writable("Stock"):
            return
        row = self.table.selected_row()
        if row is None:
            messagebox.showwarning("Stock", "Veuillez sélectionner une sortie dans la grille.")
            return
        if not messagebox.askyesno("Confirmation", "Voulez-vous vraiment supprimer cette sortie ?"):
            return
        try:
            deleted = DatabaseHelper.delete_stock_exit(int(row["Id"]))
            if deleted:
                log_user_action(
                    self,
                    "Stock",
                    "Sortie de stock supprimée",
                    f"Id {row['Id']} | Date {row['DateSortie']}",
                )
                messagebox.showinfo("Stock", "La sortie de stock a été supprimée avec succès.")
                self.reset_form()
                self.refresh_data()
            else:
                messagebox.showwarning("Stock", "Aucune sortie n'a été supprimée.")
        except ValueError as exc:
            messagebox.showwarning("Stock", str(exc))
        except Exception as exc:
            messagebox.showerror("Stock", str(exc))

    def edit_stock_parameters(self) -> None:
        if not self.ensure_module_writable("Stock"):
            return
        current = DatabaseHelper.get_stock_configuration()
        if not current:
            messagebox.showwarning("Stock", "Impossible de charger la configuration du stock.")
            return

        dialog = tk.Toplevel(self)
        dialog.geometry("560x420")
        dialog.title("Paramètres du stock")
        dialog.configure(bg=MODULE_BACKGROUND)
        dialog.resizable(True, True)
        apply_window_icon(dialog)
        frame = ttk.Frame(dialog, padding=16)
        frame.pack(fill="both", expand=True)
        logo_label = create_logo_widget(frame, STOCK_DIALOG_LOGO_SIZE)
        if logo_label is not None:
            logo_label.grid(row=0, column=0, columnspan=2, sticky="w", pady=(0, 10))

        variables = {
            "Farine": tk.StringVar(value=format_number(float(current["FarineInitial"]))),
            "Levure": tk.StringVar(value=format_number(float(current["LevureInitial"]))),
            "Sel": tk.StringVar(value=format_number(float(current["SelInitial"]))),
            "Huile": tk.StringVar(value=format_number(float(current["HuileInitial"]))),
        }
        threshold_variables = {
            "Farine": tk.StringVar(value=format_number(float(current.get("FarineAlerteMin", 20) or 0))),
            "Levure": tk.StringVar(value=format_number(float(current.get("LevureAlerteMin", 16) or 0))),
            "Sel": tk.StringVar(value=format_number(float(current.get("SelAlerteMin", 10) or 0))),
            "Huile": tk.StringVar(value=format_number(float(current.get("HuileAlerteMin", 12) or 0))),
        }

        for index, (label, variable) in enumerate(variables.items()):
            row_index = index + 1
            ttk.Label(frame, text=f"{label} initial").grid(row=row_index, column=0, sticky="w", pady=6)
            ttk.Entry(frame, textvariable=variable, width=20).grid(row=row_index, column=1, sticky="ew", pady=6)
            ttk.Label(frame, text=f"Seuil d'alerte {label.lower()}").grid(row=row_index, column=2, sticky="w", padx=(12, 0), pady=6)
            ttk.Entry(frame, textvariable=threshold_variables[label], width=18).grid(row=row_index, column=3, sticky="ew", pady=6)

        def save() -> None:
            try:
                farine = parse_float(variables["Farine"].get(), "Farine initiale")
                levure = parse_float(variables["Levure"].get(), "Levure initiale")
                sel = parse_float(variables["Sel"].get(), "Sel initial")
                huile = parse_float(variables["Huile"].get(), "Huile initiale")
                farine_alert = parse_float(threshold_variables["Farine"].get(), "Seuil d'alerte farine")
                levure_alert = parse_float(threshold_variables["Levure"].get(), "Seuil d'alerte levure")
                sel_alert = parse_float(threshold_variables["Sel"].get(), "Seuil d'alerte sel")
                huile_alert = parse_float(threshold_variables["Huile"].get(), "Seuil d'alerte huile")
                if min(farine, levure, sel, huile, farine_alert, levure_alert, sel_alert, huile_alert) < 0:
                    raise ValueError("Les valeurs initiales ne peuvent pas être négatives.")
                DatabaseHelper.update_stock_configuration(
                    farine,
                    levure,
                    sel,
                    huile,
                    farine_alert,
                    levure_alert,
                    sel_alert,
                    huile_alert,
                )
                log_user_action(
                    self,
                    "Stock",
                    "Configuration du stock modifiée",
                    (
                        f"Initiaux | Farine {format_number(farine)}, Levure {format_number(levure)}, "
                        f"Sel {format_number(sel)}, Huile {format_number(huile)} | "
                        f"Seuils | Farine {format_number(farine_alert)}, Levure {format_number(levure_alert)}, "
                        f"Sel {format_number(sel_alert)}, Huile {format_number(huile_alert)}"
                    ),
                )
                dialog.destroy()
                self.refresh_data()
                messagebox.showinfo("Stock", "Le stock initial a été mis à jour avec succès.")
            except Exception as exc:
                messagebox.showwarning("Stock", str(exc))

        actions = ttk.Frame(frame)
        actions.grid(row=5, column=0, columnspan=4, pady=(12, 0))
        ttk.Button(actions, text="Enregistrer", command=save).grid(row=0, column=0, padx=6)
        ttk.Button(actions, text="Annuler", command=dialog.destroy).grid(row=0, column=1, padx=6)
        frame.columnconfigure(1, weight=1)
        frame.columnconfigure(3, weight=1)
        center_window(dialog)

    def open_stock_supply_window(self) -> None:
        if not self.ensure_module_writable("Stock"):
            return
        dialog = StockSupplyDialog(self)
        self.wait_window(dialog)
        self.refresh_data()

    def reset_form(self) -> None:
        self.date_field.set_date(today_iso())
        self.sacs_var.set("")
        self.paquets_var.set("")
        self.sel_var.set("")
        self.huile_var.set("")
        self.edit_mode = False
        self.selected_exit_id = 0
        self.refresh_day_lock_state()

    def close_window(self) -> None:
        if not self.is_read_only_module("Stock") and not self.closing_message_shown:
            DatabaseHelper.update_stock_closing(date.today())
            journal = DatabaseHelper.get_stock_journal(date.today())
            if journal:
                self.closing_message_shown = True
                messagebox.showinfo(
                    "Clôture du jour",
                    "Stock de clôture du jour :\n"
                    f"Farine : {format_number(float(journal['FarineCloture']))} sacs\n"
                    f"Levure : {format_number(float(journal['LevureCloture']))} paquets\n"
                    f"Sel : {format_number(float(journal['SelCloture']))} kg\n"
                    f"Huile : {format_number(float(journal['HuileCloture']))} litres",
                )
        super().close_window()


class StockSupplyDialog(tk.Toplevel):
    def __init__(self, parent: StockWindow) -> None:
        super().__init__(parent)
        self.parent_window = parent
        self.selected_supply_id = 0
        self.edit_mode = False
        self.title("Approvisionnement du stock")
        self.geometry("980x680")
        self.minsize(860, 560)
        self.configure(bg=MODULE_BACKGROUND)
        self.resizable(True, True)
        self.transient(parent)
        self.grab_set()
        apply_window_icon(self)
        self.protocol("WM_DELETE_WINDOW", self.close_dialog)
        self.build_ui()
        self.refresh_table()
        center_window(self)

    def build_ui(self) -> None:
        container = ttk.Frame(self, padding=16)
        container.pack(fill="both", expand=True)
        header = create_branded_header(
            container,
            "Approvisionnement du stock",
            logo_size=STOCK_DIALOG_LOGO_SIZE,
            wraplength=760,
        )
        setattr(self, "_header_logo", getattr(header, "_header_logo", None))

        content = ttk.Frame(container)
        content.pack(fill="both", expand=True, pady=(8, 0))

        form = ttk.LabelFrame(content, text="Nouvel approvisionnement", style="Card.TLabelframe")
        form.pack(side="left", fill="y", padx=(0, 12))

        ttk.Label(form, text="Date").grid(row=0, column=0, sticky="w", pady=6)
        self.date_field = DateField(form)
        self.date_field.grid(row=0, column=1, sticky="ew", pady=6)

        self.sacs_var = tk.StringVar()
        self.paquets_var = tk.StringVar()
        self.sel_var = tk.StringVar()
        self.huile_var = tk.StringVar()

        self._make_entry(form, "Farine ajoutée (sacs)", self.sacs_var, 1)
        self._make_entry(form, "Levure ajoutée (paquets)", self.paquets_var, 2)
        self._make_entry(form, "Sel ajouté (kg)", self.sel_var, 3)
        self._make_entry(form, "Huile ajoutée (litres)", self.huile_var, 4)

        ttk.Label(form, text="Observations").grid(row=5, column=0, sticky="nw", pady=6)
        self.observations_text = ScrolledText(form, width=30, height=5)
        self.observations_text.configure(font=UI_FONT)
        self.observations_text.grid(row=5, column=1, sticky="ew", pady=6)

        actions = ttk.Frame(form)
        actions.grid(row=6, column=0, columnspan=2, pady=(14, 0))
        self.save_button = ttk.Button(actions, text="Enregistrer", command=self.save_supply)
        self.save_button.grid(row=0, column=0, padx=4, pady=4)
        ttk.Button(actions, text="Modifier", command=self.load_selected_supply).grid(row=0, column=1, padx=4, pady=4)
        ttk.Button(actions, text="Supprimer", command=self.delete_supply).grid(row=0, column=2, padx=4, pady=4)
        ttk.Button(actions, text="Nouveau", command=self.reset_form).grid(row=1, column=0, padx=4, pady=4)
        ttk.Button(actions, text="Fermer", command=self.close_dialog).grid(row=1, column=1, padx=4, pady=4)

        form.columnconfigure(1, weight=1)

        table_frame = ttk.LabelFrame(content, text="Historique des approvisionnements", style="Card.TLabelframe")
        table_frame.pack(side="left", fill="both", expand=True)
        self.table = DataTable(table_frame, height=18)
        self.table.pack(fill="both", expand=True)

    def _make_entry(self, parent: ttk.LabelFrame, label: str, variable: tk.StringVar, row: int) -> None:
        ttk.Label(parent, text=label).grid(row=row, column=0, sticky="w", pady=6)
        ttk.Entry(parent, textvariable=variable, width=20).grid(row=row, column=1, sticky="ew", pady=6)

    def validate_supply(self) -> tuple[date, float, float, float, float, str] | None:
        try:
            target_date = self.date_field.get_date()
            sacs = parse_optional_float(self.sacs_var.get())
            paquets = parse_optional_float(self.paquets_var.get())
            sel = parse_optional_float(self.sel_var.get())
            huile = parse_optional_float(self.huile_var.get())
        except Exception as exc:
            messagebox.showwarning("Approvisionnement", str(exc), parent=self)
            return None
        observations = self.observations_text.get("1.0", "end").strip()
        return target_date, sacs, paquets, sel, huile, observations

    def save_supply(self) -> None:
        validated = self.validate_supply()
        if validated is None:
            return
        target_date, sacs, paquets, sel, huile, observations = validated
        try:
            if self.edit_mode:
                updated = DatabaseHelper.update_stock_supply(
                    self.selected_supply_id,
                    target_date,
                    sacs,
                    paquets,
                    sel,
                    huile,
                    observations,
                )
                if updated:
                    action = "Approvisionnement modifié"
                else:
                    messagebox.showwarning("Approvisionnement", "Aucune modification n'a été enregistrée.", parent=self)
                    return
            else:
                DatabaseHelper.add_stock_supply(target_date, sacs, paquets, sel, huile, observations)
                action = "Approvisionnement ajouté"
            DatabaseHelper.update_stock_closing(target_date)
            log_user_action(
                self.parent_window,
                "Stock",
                action,
                (
                    f"{target_date.strftime('%d/%m/%Y')} | Farine {format_number(sacs)} | "
                    f"Levure {format_number(paquets)} | Sel {format_number(sel)} | Huile {format_number(huile)}"
                ),
            )
            self.reset_form()
            self.refresh_table()
            self.parent_window.refresh_data()
            messagebox.showinfo("Approvisionnement", "L'approvisionnement a été enregistré avec succès.", parent=self)
        except ValueError as exc:
            messagebox.showwarning("Approvisionnement", str(exc), parent=self)
        except Exception as exc:
            messagebox.showerror("Approvisionnement", str(exc), parent=self)

    def refresh_table(self) -> None:
        rows = DatabaseHelper.list_stock_supplies()
        self.table.set_data(
            rows,
            columns=[
                "Id",
                "DateApprovisionnement",
                "SacsAjoutes",
                "PaquetsAjoutes",
                "KgSelAjoutes",
                "LitresHuileAjoutes",
                "Observations",
            ],
            headings={
                "DateApprovisionnement": "Date",
                "SacsAjoutes": "Farine",
                "PaquetsAjoutes": "Levure",
                "KgSelAjoutes": "Sel",
                "LitresHuileAjoutes": "Huile",
                "Observations": "Observations",
            },
            hidden_columns=["Id"],
            formatters={
                "SacsAjoutes": lambda value: format_number(float(value)),
                "PaquetsAjoutes": lambda value: format_number(float(value)),
                "KgSelAjoutes": lambda value: format_number(float(value)),
                "LitresHuileAjoutes": lambda value: format_number(float(value)),
                "Observations": compact_multiline_text,
            },
        )

    def load_selected_supply(self) -> None:
        row = self.selected_order_row()
        if row is None:
            messagebox.showwarning("Approvisionnement", "Veuillez sélectionner un approvisionnement.", parent=self)
            return
        self.selected_supply_id = int(row["Id"])
        self.edit_mode = True
        self.date_field.set_date(str(row["DateApprovisionnement"]))
        self.sacs_var.set(format_number(float(row["SacsAjoutes"])))
        self.paquets_var.set(format_number(float(row["PaquetsAjoutes"])))
        self.sel_var.set(format_number(float(row["KgSelAjoutes"])))
        self.huile_var.set(format_number(float(row["LitresHuileAjoutes"])))
        self.observations_text.delete("1.0", "end")
        self.observations_text.insert("1.0", str(row.get("Observations", "") or ""))
        messagebox.showinfo("Approvisionnement", "L'approvisionnement a été chargé. Modifiez-le puis enregistrez.", parent=self)

    def delete_supply(self) -> None:
        row = self.selected_order_row()
        if row is None:
            messagebox.showwarning("Approvisionnement", "Veuillez sélectionner un approvisionnement.", parent=self)
            return
        if not messagebox.askyesno("Confirmation", "Voulez-vous vraiment supprimer cet approvisionnement ?", parent=self):
            return
        try:
            deleted = DatabaseHelper.delete_stock_supply(int(row["Id"]))
            if deleted:
                log_user_action(
                    self.parent_window,
                    "Stock",
                    "Approvisionnement supprimé",
                    f"Id {row['Id']} | Date {row['DateApprovisionnement']}",
                )
                DatabaseHelper.update_stock_closing(date.today())
                self.reset_form()
                self.refresh_table()
                self.parent_window.refresh_data()
                messagebox.showinfo("Approvisionnement", "L'approvisionnement a été supprimé avec succès.", parent=self)
            else:
                messagebox.showwarning("Approvisionnement", "Aucun approvisionnement n'a été supprimé.", parent=self)
        except ValueError as exc:
            messagebox.showwarning("Approvisionnement", str(exc), parent=self)
        except Exception as exc:
            messagebox.showerror("Approvisionnement", str(exc), parent=self)

    def reset_form(self) -> None:
        self.selected_supply_id = 0
        self.edit_mode = False
        self.date_field.set_date(today_iso())
        self.sacs_var.set("")
        self.paquets_var.set("")
        self.sel_var.set("")
        self.huile_var.set("")
        self.observations_text.delete("1.0", "end")

    def close_dialog(self) -> None:
        try:
            self.grab_release()
        except tk.TclError:
            pass
        self.destroy()


class PrevisionWindow(BaseModuleWindow):
    def __init__(self, parent: DashboardWindow) -> None:
        super().__init__(parent, "Gestion des prévisions", "1320x860")
        self.selected_prevision_id = 0
        self.edit_mode = False
        self.show_all_dates = False
        self.active_prevision_table: DataTable | None = None
        self.build_ui()
        self.reset_form()
        self.summary_var.set("Chargement des prévisions...")
        self.after_idle(self.refresh_previsions)

    def build_ui(self) -> None:
        container = self.body

        content = ttk.Frame(container)
        content.pack(fill="both", expand=True)
        self.create_day_lock_notice(container, "la prévision", before=content)

        form = ttk.LabelFrame(content, text="Prévision de production", style="Card.TLabelframe")
        form.pack(side="left", fill="y", padx=(0, 12))

        ttk.Label(form, text="Date prévue").grid(row=0, column=0, sticky="w", pady=6)
        self.date_field = DateField(form, tomorrow_iso(), allow_future=True)
        self.date_field.grid(row=0, column=1, sticky="ew", pady=6)
        self.date_field.bind_change(self._on_date_change)

        self.location_var = tk.StringVar(value=PREVISION_LOCATIONS[0])
        self.client_var = tk.StringVar()
        self.status_var = tk.StringVar(value=DEPOSITARY_STATUS)
        self.square_1500_var = tk.StringVar(value="0")
        self.square_1000_var = tk.StringVar(value="0")
        self.baguette_500_var = tk.StringVar(value="0")
        self.baguette_1000_var = tk.StringVar(value="0")
        self.line_total_var = tk.StringVar(value="0 article | 0 FC")

        ttk.Label(form, text="Localisation").grid(row=1, column=0, sticky="w", pady=6)
        self.location_combo = ttk.Combobox(
            form,
            textvariable=self.location_var,
            values=PREVISION_LOCATIONS,
            state="readonly",
            width=24,
        )
        self.location_combo.grid(row=1, column=1, sticky="ew", pady=6)

        ttk.Label(form, text="Nom du client").grid(row=2, column=0, sticky="w", pady=6)
        ttk.Entry(form, textvariable=self.client_var, width=28).grid(row=2, column=1, sticky="ew", pady=6)

        ttk.Label(form, text="Statut").grid(row=3, column=0, sticky="w", pady=6)
        self.status_combo = ttk.Combobox(
            form,
            textvariable=self.status_var,
            values=PREVISION_STATUSES,
            state="readonly",
            width=20,
        )
        self.status_combo.grid(row=3, column=1, sticky="ew", pady=6)

        ttk.Label(form, text="Commande", foreground=PRIMARY_DARK_COLOR).grid(
            row=4, column=0, columnspan=2, sticky="w", pady=(14, 6)
        )

        ttk.Label(form, text="Carré 1.500 FC").grid(row=5, column=0, sticky="w", pady=6)
        ttk.Spinbox(form, from_=0, to=100000, textvariable=self.square_1500_var, width=12).grid(
            row=5, column=1, sticky="w", pady=6
        )

        ttk.Label(form, text="Carré 1.000 FC").grid(row=6, column=0, sticky="w", pady=6)
        ttk.Spinbox(form, from_=0, to=100000, textvariable=self.square_1000_var, width=12).grid(
            row=6, column=1, sticky="w", pady=6
        )

        ttk.Label(form, text="Bgtte 500 FC").grid(row=7, column=0, sticky="w", pady=6)
        ttk.Spinbox(form, from_=0, to=100000, textvariable=self.baguette_500_var, width=12).grid(
            row=7, column=1, sticky="w", pady=6
        )

        ttk.Label(form, text="Bgtte 1.000 FC").grid(row=8, column=0, sticky="w", pady=6)
        ttk.Spinbox(form, from_=0, to=100000, textvariable=self.baguette_1000_var, width=12).grid(
            row=8, column=1, sticky="w", pady=6
        )

        self._make_label_value(form, "Total ligne", self.line_total_var, 9, SUCCESS_COLOR)

        actions = ttk.Frame(form)
        actions.grid(row=10, column=0, columnspan=2, pady=(14, 0))
        self.save_button = ttk.Button(actions, text="Enregistrer", command=self.save_prevision)
        self.save_button.grid(row=0, column=0, padx=4, pady=4)
        self.edit_button = ttk.Button(actions, text="Modifier", command=self.load_prevision_for_edit)
        self.edit_button.grid(row=0, column=1, padx=4, pady=4)
        self.delete_button = ttk.Button(actions, text="Supprimer", command=self.delete_prevision)
        self.delete_button.grid(row=0, column=2, padx=4, pady=4)
        ttk.Button(actions, text="Tout afficher", command=self.show_all).grid(row=1, column=0, padx=4, pady=4)
        ttk.Button(actions, text="Imprimer les fiches", command=self.export_prevision_excel).grid(
            row=1, column=1, padx=4, pady=4
        )
        ttk.Button(actions, text="Fermer", command=self.close_window).grid(row=1, column=2, padx=4, pady=4)

        self.summary_var = tk.StringVar()
        ttk.Label(form, textvariable=self.summary_var, wraplength=390, justify="left").grid(
            row=11, column=0, columnspan=2, sticky="ew", pady=(14, 0)
        )

        grids_frame = ttk.Frame(content)
        grids_frame.pack(side="left", fill="both", expand=True)
        grids_frame.columnconfigure(0, weight=1)
        grids_frame.columnconfigure(1, weight=1)
        grids_frame.rowconfigure(0, weight=3)
        grids_frame.rowconfigure(1, weight=2)

        depositary_frame = ttk.LabelFrame(
            grids_frame,
            text="FICHE DE COMMANDE DES DEPOSITAIRES",
            style="Card.TLabelframe",
        )
        depositary_frame.grid(row=0, column=0, sticky="nsew", padx=(0, 8), pady=(0, 8))
        self.depositary_table = DataTable(depositary_frame, height=16)
        self.depositary_table.pack(fill="both", expand=True)

        mama_frame = ttk.LabelFrame(
            grids_frame,
            text="FICHE DE COMMANDE DES MAMANS",
            style="Card.TLabelframe",
        )
        mama_frame.grid(row=0, column=1, sticky="nsew", padx=(8, 0), pady=(0, 8))
        self.mama_table = DataTable(mama_frame, height=16)
        self.mama_table.pack(fill="both", expand=True)

        bottom_frame = ttk.LabelFrame(grids_frame, text="Résumé de la fiche Mamans", style="Card.TLabelframe")
        bottom_frame.grid(row=1, column=0, columnspan=2, sticky="nsew")
        self.production_summary_table = DataTable(bottom_frame, height=8)
        self.production_summary_table.pack(fill="both", expand=True)

        for variable in (
            self.square_1500_var,
            self.square_1000_var,
            self.baguette_500_var,
            self.baguette_1000_var,
        ):
            variable.trace_add("write", lambda *_args: self.calculate_line_total())
        self.status_var.trace_add("write", lambda *_args: self._on_status_change())
        self.depositary_table.tree.bind("<<TreeviewSelect>>", lambda _event: self._activate_table(self.depositary_table))
        self.mama_table.tree.bind("<<TreeviewSelect>>", lambda _event: self._activate_table(self.mama_table))

        form.columnconfigure(1, weight=1)
        self.configure_day_lock_controls(
            self.date_field,
            [self.save_button, self.edit_button, self.delete_button],
        )
        self.hide_read_only_buttons("Commandes", [self.save_button, self.edit_button, self.delete_button])
        self._on_status_change()

    def _make_label_value(
        self,
        parent: ttk.LabelFrame,
        label: str,
        variable: tk.StringVar,
        row: int,
        foreground: str,
    ) -> None:
        ttk.Label(parent, text=label).grid(row=row, column=0, sticky="w", pady=6)
        ttk.Label(parent, textvariable=variable, foreground=foreground).grid(row=row, column=1, sticky="w", pady=6)

    def _parse_quantity(self, value: str, field_name: str) -> int:
        text = value.strip().replace(" ", "").replace(",", ".")
        if not text:
            return 0
        try:
            number = int(float(text))
        except ValueError as exc:
            raise ValueError(f"Le champ « {field_name} » doit être numérique.") from exc
        if number < 0:
            raise ValueError(f"Le champ « {field_name} » ne peut pas être négatif.")
        return number

    def _on_date_change(self) -> None:
        self.show_all_dates = False
        self.refresh_previsions()

    def _on_status_change(self) -> None:
        if self.status_var.get().strip() == "Maman":
            self.location_combo.configure(state="disabled")
            return
        self.location_combo.configure(state="readonly")
        if not self.location_var.get().strip():
            self.location_var.set(PREVISION_LOCATIONS[0])

    def calculate_line_total(self) -> None:
        try:
            square_1500 = self._parse_quantity(self.square_1500_var.get(), "Carré 1.500 FC")
            square_1000 = self._parse_quantity(self.square_1000_var.get(), "Carré 1.000 FC")
            baguette_500 = self._parse_quantity(self.baguette_500_var.get(), "Bgtte 500 FC")
            baguette_1000 = self._parse_quantity(self.baguette_1000_var.get(), "Bgtte 1.000 FC")
        except ValueError:
            self.line_total_var.set("Quantités invalides")
            return
        total_articles = square_1500 + square_1000 + baguette_500 + baguette_1000
        total_amount = (square_1500 * 1500) + (square_1000 * 1000) + (baguette_500 * 500) + (baguette_1000 * 1000)
        article_label = "article" if total_articles <= 1 else "articles"
        self.line_total_var.set(f"{total_articles} {article_label} | {format_fc(total_amount)}")

    def validate_prevision(self) -> tuple[date, str, str, str, int, int, int, int] | None:
        try:
            target_date = self.date_field.get_date()
            localisation = self.location_var.get().strip()
            client = self.client_var.get().strip()
            status = self.status_var.get().strip()
            square_1500 = self._parse_quantity(self.square_1500_var.get(), "Carré 1.500 FC")
            square_1000 = self._parse_quantity(self.square_1000_var.get(), "Carré 1.000 FC")
            baguette_500 = self._parse_quantity(self.baguette_500_var.get(), "Bgtte 500 FC")
            baguette_1000 = self._parse_quantity(self.baguette_1000_var.get(), "Bgtte 1.000 FC")
        except Exception as exc:
            messagebox.showwarning("Prévision", str(exc))
            return None
        if status == "Maman":
            localisation = ""
        elif not localisation:
            messagebox.showwarning("Prévision", "Veuillez renseigner la localisation.")
            return None
        if not client:
            messagebox.showwarning("Prévision", "Veuillez renseigner le nom du client.")
            return None
        if status not in PREVISION_STATUSES:
            messagebox.showwarning("Prévision", "Le statut doit être Dépositaire ou Maman.")
            return None
        if square_1500 + square_1000 + baguette_500 + baguette_1000 <= 0:
            messagebox.showwarning("Prévision", "Veuillez saisir au moins une quantité dans la commande.")
            return None
        return target_date, localisation, client, status, square_1500, square_1000, baguette_500, baguette_1000

    def save_prevision(self) -> None:
        validated = self.validate_prevision()
        if validated is None:
            return
        target_date, localisation, client, status, square_1500, square_1000, baguette_500, baguette_1000 = validated

        try:
            if self.edit_mode and self.selected_prevision_id > 0:
                DatabaseHelper.update_prevision_order(
                    self.selected_prevision_id,
                    target_date,
                    localisation,
                    client,
                    status,
                    square_1500,
                    square_1000,
                    baguette_500,
                    baguette_1000,
                )
                action = "Prévision modifiée"
            else:
                DatabaseHelper.add_prevision_order(
                    target_date,
                    localisation,
                    client,
                    status,
                    square_1500,
                    square_1000,
                    baguette_500,
                    baguette_1000,
                )
                action = "Prévision enregistrée"
            log_user_action(
                self,
                "Prévision",
                action,
                (
                    f"{target_date.strftime('%d/%m/%Y')} | {localisation} | {client} | {status} | "
                    f"Carré 1.500 FC : {square_1500} | Carré 1.000 FC : {square_1000} | "
                    f"Bgtte 500 FC : {baguette_500} | Bgtte 1.000 FC : {baguette_1000}"
                ),
            )
            self.reset_form()
            self.refresh_previsions()
            messagebox.showinfo("Prévision", "La prévision a été enregistrée avec succès.")
        except ValueError as exc:
            messagebox.showwarning("Prévision", str(exc))
        except Exception as exc:
            messagebox.showerror("Prévision", str(exc))

    def refresh_previsions(self) -> None:
        try:
            target_date = self.date_field.get_date()
        except ValueError:
            target_date = date.today() + timedelta(days=1)
        rows = DatabaseHelper.list_previsions() if self.show_all_dates else DatabaseHelper.list_previsions_by_date(target_date)
        depositary_rows = [row for row in rows if str(row.get("Statut") or "").strip() == DEPOSITARY_STATUS]
        mama_rows = [row for row in rows if str(row.get("Statut") or "").strip() == "Maman"]

        common_headings = {
            "DatePrevision": "Date prévue",
            "Carre1500": "Carré 1.500 FC",
            "Carre1000": "Carré 1.000 FC",
            "Baguette500": "Bgtte 500 FC",
            "Baguette1000": "Bgtte 1.000 FC",
            "TotalArticles": "Total",
            "MontantPrevu": "Montant prévu",
        }
        common_formatters = {
            "DatePrevision": self._format_grid_date,
            "MontantPrevu": lambda value: format_fc(float(value or 0)),
        }
        self.depositary_table.set_data(
            self._decorate_depositary_rows(depositary_rows),
            columns=[
                "RowKind",
                "Id",
                "DatePrevision",
                "Localisation",
                "Client",
                "Carre1500",
                "Carre1000",
                "Baguette500",
                "Baguette1000",
                "TotalArticles",
                "MontantPrevu",
            ],
            headings=common_headings,
            hidden_columns=["RowKind", "Id"],
            formatters=common_formatters,
        )
        self.mama_table.set_data(
            self._decorate_mama_rows(mama_rows),
            columns=[
                "RowKind",
                "Id",
                "DatePrevision",
                "Client",
                "Carre1500",
                "Carre1000",
                "Baguette500",
                "Baguette1000",
                "TotalArticles",
                "MontantPrevu",
            ],
            headings=common_headings,
            hidden_columns=["RowKind", "Id"],
            formatters=common_formatters,
        )
        self._configure_prevision_table_widths()
        self.update_summary()
        self.refresh_day_lock_state()

    def _format_grid_date(self, value: Any) -> str:
        text = str(value or "")
        try:
            return datetime.strptime(text, "%Y-%m-%d").strftime("%d/%m/%Y")
        except ValueError:
            return text

    def _sum_rows(self, rows: list[dict[str, Any]], key: str) -> int:
        total = 0
        for row in rows:
            try:
                total += int(float(row.get(key, 0) or 0))
            except (TypeError, ValueError):
                continue
        return total

    def _sum_amount(self, rows: list[dict[str, Any]]) -> float:
        total = 0.0
        for row in rows:
            try:
                total += float(row.get("MontantPrevu", 0) or 0)
            except (TypeError, ValueError):
                continue
        return total

    def _make_total_row(self, label: str, rows: list[dict[str, Any]], kind: str = "subtotal") -> dict[str, Any]:
        return {
            "RowKind": kind,
            "Id": "",
            "DatePrevision": "",
            "Localisation": label,
            "Client": "",
            "Carre1500": self._sum_rows(rows, "Carre1500"),
            "Carre1000": self._sum_rows(rows, "Carre1000"),
            "Baguette500": self._sum_rows(rows, "Baguette500"),
            "Baguette1000": self._sum_rows(rows, "Baguette1000"),
            "TotalArticles": self._sum_rows(rows, "TotalArticles"),
            "MontantPrevu": self._sum_amount(rows),
        }

    def _decorate_depositary_rows(self, rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
        decorated: list[dict[str, Any]] = []
        rows_by_location = {location: [] for location in PREVISION_LOCATIONS}
        extra_rows: list[dict[str, Any]] = []
        for row in rows:
            location = str(row.get("Localisation") or "").strip()
            if location in rows_by_location:
                rows_by_location[location].append({**row, "RowKind": "detail"})
            else:
                extra_rows.append({**row, "RowKind": "detail"})
        if extra_rows:
            rows_by_location["Autres"] = extra_rows

        for location, location_rows in rows_by_location.items():
            if not location_rows:
                continue
            decorated.append(
                {
                    "RowKind": "section",
                    "Id": "",
                    "DatePrevision": "",
                    "Localisation": location.upper(),
                    "Client": "",
                }
            )
            decorated.extend(location_rows)
            decorated.append(self._make_total_row(f"Total {location}", location_rows))
        if rows:
            decorated.append(self._make_total_row("TOTAL GÉNÉRAL DÉPOSITAIRES", rows, "total"))
        return decorated

    def _decorate_mama_rows(self, rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
        decorated = [{**row, "RowKind": "detail"} for row in rows]
        if rows:
            total_row = self._make_total_row("TOTAL MAMANS", rows, "total")
            total_row["Client"] = total_row["Localisation"]
            decorated.append(total_row)
        return decorated

    def _configure_prevision_table_widths(self) -> None:
        for table in (self.depositary_table, self.mama_table):
            for column_name, width in {
                "DatePrevision": 105,
                "Localisation": 165,
                "Client": 190,
                "Carre1500": 110,
                "Carre1000": 110,
                "Baguette500": 110,
                "Baguette1000": 115,
                "TotalArticles": 85,
                "MontantPrevu": 120,
            }.items():
                try:
                    table.tree.column(column_name, width=width, stretch=True)
                except tk.TclError:
                    continue

    def _activate_table(self, active_table: DataTable) -> None:
        self.active_prevision_table = active_table
        for table in (self.depositary_table, self.mama_table):
            if table is active_table:
                continue
            table.tree.selection_remove(table.tree.selection())

    def selected_prevision_row(self) -> dict[str, Any] | None:
        table_order: list[DataTable] = []
        if self.active_prevision_table is not None:
            table_order.append(self.active_prevision_table)
        for table in (self.depositary_table, self.mama_table):
            if table not in table_order:
                table_order.append(table)
        for table in table_order:
            row = table.selected_row()
            if row is not None:
                return row
        return None

    def update_summary(self) -> None:
        if self.show_all_dates:
            summary = DatabaseHelper.get_global_prevision_summary()
            self.summary_var.set(
                "Prévisions globales\n"
                f"Jours préparés : {int(summary.get('JoursPrevision', 0) or 0)} | "
                f"Clients : {int(summary.get('NombreClients', 0) or 0)}\n"
                f"Dépositaires : {int(summary.get('TotalDepositaires', 0) or 0)} | "
                f"Mamans : {int(summary.get('TotalMamans', 0) or 0)}\n"
                f"Total bacs : {int(summary.get('TotalArticlesPrevus', 0) or 0)} | "
                f"Sacs à produire : {format_number(float(summary.get('NombreSacsAProduire', 0) or 0))}"
            )
            self.update_bottom_summary(summary)
            return

        try:
            target_date = self.date_field.get_date()
        except ValueError:
            target_date = date.today() + timedelta(days=1)
        summary = DatabaseHelper.get_prevision_summary_for_date(target_date)
        self.summary_var.set(
            f"Prévision du {target_date.strftime('%d/%m/%Y')}\n"
            f"Clients : {int(summary.get('NombreClients', 0) or 0)} | "
            f"Dépositaires : {int(summary.get('NombreDepositaires', 0) or 0)} | "
            f"Mamans : {int(summary.get('NombreMamans', 0) or 0)}\n"
            f"Total bacs : {int(summary.get('TotalArticlesPrevus', 0) or 0)}\n"
            f"Carré 1.500 FC : {int(summary.get('TotalCarre1500', 0) or 0)} | "
            f"Carré 1.000 FC : {int(summary.get('TotalCarre1000', 0) or 0)} | "
            f"Bgtte 500 FC : {int(summary.get('TotalBaguette500', 0) or 0)} | "
            f"Bgtte 1.000 FC : {int(summary.get('TotalBaguette1000', 0) or 0)}\n"
            f"Sacs à produire : {format_number(float(summary.get('NombreSacsAProduire', 0) or 0))} | "
            f"Montant prévu : {format_fc(float(summary.get('MontantPrevu', 0) or 0))}"
        )
        self.update_bottom_summary(summary)

    def update_bottom_summary(self, summary: dict[str, Any]) -> None:
        total_depositaries = int(summary.get("TotalDepositaires", 0) or 0)
        total_mamas = int(summary.get("TotalMamans", 0) or 0)
        total_general = int(summary.get("TotalArticlesPrevus", 0) or 0)
        rows = [
            {"Libelle": "Total général", "Depots": total_depositaries, "Mamans": total_mamas, "Total": total_general},
            {
                "Libelle": "Nombre de sacs à produire",
                "Depots": "",
                "Mamans": "",
                "Total": format_number(float(summary.get("NombreSacsAProduire", 0) or 0)),
            },
            {"Libelle": "Nbre sacs produits", "Depots": "", "Mamans": "", "Total": ""},
            {"Libelle": "Bacs livrés", "Depots": "", "Mamans": "", "Total": ""},
            {"Libelle": "Bacs restants", "Depots": "", "Mamans": "", "Total": ""},
            {"Libelle": "Foutus", "Depots": "", "Mamans": "", "Total": ""},
            {"Libelle": "Baraka", "Depots": "", "Mamans": "", "Total": ""},
            {"Libelle": "Police", "Depots": "", "Mamans": "", "Total": ""},
        ]
        self.production_summary_table.set_data(
            rows,
            columns=["Libelle", "Depots", "Mamans", "Total"],
            headings={"Libelle": "Rubrique", "Depots": "Dépôts", "Mamans": "Mamans", "Total": "Total"},
        )

    def load_prevision_for_edit(self) -> None:
        row = self.selected_prevision_row()
        if row is None or row.get("RowKind") != "detail":
            messagebox.showwarning("Prévision", "Veuillez sélectionner une ligne client dans une des grilles.")
            return
        self.selected_prevision_id = int(row["Id"])
        self.edit_mode = True
        self.date_field.set_date(str(row["DatePrevision"]))
        self.location_var.set(str(row.get("Localisation", "") or PREVISION_LOCATIONS[0]))
        self.client_var.set(str(row.get("Client", "") or ""))
        self.status_var.set(str(row.get("Statut", "") or DEPOSITARY_STATUS))
        self.square_1500_var.set(str(int(row.get("Carre1500", 0) or 0)))
        self.square_1000_var.set(str(int(row.get("Carre1000", 0) or 0)))
        self.baguette_500_var.set(str(int(row.get("Baguette500", 0) or 0)))
        self.baguette_1000_var.set(str(int(row.get("Baguette1000", 0) or 0)))
        self.show_all_dates = False
        self.calculate_line_total()
        self._on_status_change()
        self.refresh_day_lock_state()
        messagebox.showinfo("Prévision", "La prévision a été chargée. Modifiez-la puis enregistrez.")

    def delete_prevision(self) -> None:
        row = self.selected_prevision_row()
        if row is None or row.get("RowKind") != "detail":
            messagebox.showwarning("Prévision", "Veuillez sélectionner une ligne client dans une des grilles.")
            return
        if not messagebox.askyesno("Confirmation", "Voulez-vous vraiment supprimer cette prévision ?"):
            return
        try:
            deleted = DatabaseHelper.delete_prevision_day(int(row["Id"]))
            if deleted:
                log_user_action(
                    self,
                    "Prévision",
                    "Prévision supprimée",
                    f"Id {row['Id']} | Date {row['DatePrevision']}",
                )
                self.reset_form()
                self.refresh_previsions()
                messagebox.showinfo("Prévision", "La prévision a été supprimée avec succès.")
            else:
                messagebox.showwarning("Prévision", "Aucune prévision n'a été supprimée.")
        except ValueError as exc:
            messagebox.showwarning("Prévision", str(exc))
        except Exception as exc:
            messagebox.showerror("Prévision", str(exc))

    def export_prevision_excel(self) -> None:
        try:
            target_date = self.date_field.get_date()
        except ValueError as exc:
            messagebox.showwarning("Prévision", str(exc))
            return
        try:
            reports_dir = DatabaseHelper.get_reports_dir_for_user(self.parent.user.identifiant)
            timestamp = datetime.now().strftime("%H%M%S")
            output_path = reports_dir / f"fiches-prevision-production-{target_date.strftime('%Y%m%d')}-{timestamp}.xlsx"
            created_path = create_prevision_excel_workbook(target_date, output_path)
            log_user_action(
                self,
                "Prévision",
                "Fiches de prévision générées",
                f"{target_date.strftime('%d/%m/%Y')} | {created_path}",
            )
            open_file(created_path)
        except Exception as exc:
            messagebox.showerror("Prévision", str(exc))

    def show_all(self) -> None:
        self.show_all_dates = True
        self.refresh_previsions()

    def refresh_live_view(self) -> None:
        self.refresh_previsions()

    def reset_form(self) -> None:
        self.selected_prevision_id = 0
        self.edit_mode = False
        self.show_all_dates = False
        self.active_prevision_table = None
        self.date_field.set_date(tomorrow_iso())
        self.location_var.set(PREVISION_LOCATIONS[0])
        self.client_var.set("")
        self.status_var.set(DEPOSITARY_STATUS)
        self.square_1500_var.set("0")
        self.square_1000_var.set("0")
        self.baguette_500_var.set("0")
        self.baguette_1000_var.set("0")
        self.calculate_line_total()
        self._on_status_change()
        self.refresh_day_lock_state()


class ProductionWindow(BaseModuleWindow):
    def __init__(self, parent: DashboardWindow) -> None:
        super().__init__(parent, "Gestion de la production", "1320x860")
        self.selected_production_id = 0
        self.edit_mode = False
        self.show_all_dates = False
        self.build_ui()
        self.reset_form()
        self.summary_var.set("Chargement de la production...")
        self.after_idle(self.refresh_production)

    def build_ui(self) -> None:
        container = self.body

        content = ttk.Frame(container)
        content.pack(fill="both", expand=True)
        self.create_day_lock_notice(container, "la production", before=content)

        form = ttk.LabelFrame(content, text="Production journalière", style="Card.TLabelframe")
        form.pack(side="left", fill="y", padx=(0, 12))

        ttk.Label(form, text="Date").grid(row=0, column=0, sticky="w", pady=6)
        self.date_field = DateField(form)
        self.date_field.grid(row=0, column=1, sticky="ew", pady=6)
        self.date_field.bind_change(self._on_date_change)

        self.ordered_trays_var = tk.StringVar(value="0")
        self.available_trays_var = tk.StringVar(value="0")
        self.gap_var = tk.StringVar(value="0")
        self.coverage_var = tk.StringVar(value="0 %")
        self.total_produced_var = tk.StringVar(value="0")
        self.sacks_used_var = tk.StringVar(value="0")
        self.delivered_depositaries_var = tk.StringVar(value="0")
        self.delivered_mamas_var = tk.StringVar(value="0")
        self.given_trays_var = tk.StringVar(value="0")
        self.sample_trays_var = tk.StringVar(value="0")
        self.remaining_trays_var = tk.StringVar(value="0")
        self.wasted_trays_var = tk.StringVar(value="0")

        ttk.Label(form, text="Bacs commandés").grid(row=1, column=0, sticky="w", pady=6)
        ttk.Spinbox(form, from_=0, to=100000, textvariable=self.ordered_trays_var, width=12).grid(
            row=1, column=1, sticky="w", pady=6
        )

        ttk.Label(form, text="Bacs livrés dépositaires").grid(row=2, column=0, sticky="w", pady=6)
        ttk.Spinbox(form, from_=0, to=100000, textvariable=self.delivered_depositaries_var, width=12).grid(
            row=2, column=1, sticky="w", pady=6
        )

        ttk.Label(form, text="Bacs livrés mamans").grid(row=3, column=0, sticky="w", pady=6)
        ttk.Spinbox(form, from_=0, to=100000, textvariable=self.delivered_mamas_var, width=12).grid(
            row=3, column=1, sticky="w", pady=6
        )

        ttk.Label(form, text="Bacs donnés").grid(row=4, column=0, sticky="w", pady=6)
        ttk.Spinbox(form, from_=0, to=100000, textvariable=self.given_trays_var, width=12).grid(
            row=4, column=1, sticky="w", pady=6
        )

        ttk.Label(form, text="Échantillons (Agent commercial)").grid(row=5, column=0, sticky="w", pady=6)
        ttk.Spinbox(form, from_=0, to=100000, textvariable=self.sample_trays_var, width=12).grid(
            row=5, column=1, sticky="w", pady=6
        )

        ttk.Label(form, text="Bacs restants / disponibles").grid(row=6, column=0, sticky="w", pady=6)
        ttk.Spinbox(form, from_=0, to=100000, textvariable=self.remaining_trays_var, width=12).grid(
            row=6, column=1, sticky="w", pady=6
        )

        ttk.Label(form, text="Bacs foutus").grid(row=7, column=0, sticky="w", pady=6)
        ttk.Spinbox(form, from_=0, to=100000, textvariable=self.wasted_trays_var, width=12).grid(
            row=7, column=1, sticky="w", pady=6
        )

        self._make_label_value(form, "Total bacs produits", self.total_produced_var, 8, SUCCESS_COLOR)
        self._make_label_value(form, "Bacs disponibles", self.available_trays_var, 9, SUCCESS_COLOR)
        ttk.Label(form, text="Écart avec commandes").grid(row=10, column=0, sticky="w", pady=6)
        self.gap_label = ttk.Label(form, textvariable=self.gap_var, foreground=PRIMARY_DARK_COLOR)
        self.gap_label.grid(row=10, column=1, sticky="w", pady=6)
        self._make_label_value(form, "Taux de couverture", self.coverage_var, 11, ACCENT_DARK_COLOR)
        ttk.Label(form, text="Nombre de sacs utilisés").grid(row=12, column=0, sticky="w", pady=6)
        self.sacks_used_entry = ttk.Entry(form, textvariable=self.sacks_used_var, width=12)
        self.sacks_used_entry.grid(row=12, column=1, sticky="w", pady=6)

        ttk.Label(form, text="Observations").grid(row=13, column=0, sticky="nw", pady=6)
        self.observations_text = ScrolledText(form, width=34, height=7)
        self.observations_text.configure(font=UI_FONT)
        self.observations_text.grid(row=13, column=1, sticky="ew", pady=6)

        actions = ttk.Frame(form)
        actions.grid(row=14, column=0, columnspan=2, pady=(14, 0))
        self.save_button = ttk.Button(actions, text="Enregistrer", command=self.save_production)
        self.save_button.grid(row=0, column=0, padx=4, pady=4)
        self.edit_button = ttk.Button(actions, text="Modifier", command=self.load_production_for_edit)
        self.edit_button.grid(row=0, column=1, padx=4, pady=4)
        self.delete_button = ttk.Button(actions, text="Supprimer", command=self.delete_production)
        self.delete_button.grid(row=0, column=2, padx=4, pady=4)
        ttk.Button(actions, text="Tout afficher", command=self.show_all).grid(row=1, column=0, padx=4, pady=4)
        ttk.Button(actions, text="Fermer", command=self.close_window).grid(row=1, column=1, padx=4, pady=4)

        self.summary_var = tk.StringVar()
        ttk.Label(form, textvariable=self.summary_var, wraplength=390, justify="left").grid(
            row=15, column=0, columnspan=2, sticky="ew", pady=(14, 0)
        )

        table_frame = ttk.LabelFrame(content, text="Historique de production", style="Card.TLabelframe")
        table_frame.pack(side="left", fill="both", expand=True)
        self.table = DataTable(table_frame, height=22)
        self.table.pack(fill="both", expand=True)

        for variable in (
            self.ordered_trays_var,
            self.delivered_depositaries_var,
            self.delivered_mamas_var,
            self.given_trays_var,
            self.sample_trays_var,
            self.remaining_trays_var,
            self.wasted_trays_var,
        ):
            variable.trace_add("write", lambda *_args: self.calculate_current_totals())

        form.columnconfigure(1, weight=1)
        self.configure_day_lock_controls(
            self.date_field,
            [self.save_button, self.edit_button, self.delete_button],
        )
        self.hide_read_only_buttons("Production", [self.save_button, self.edit_button, self.delete_button])

    def _make_label_value(
        self,
        parent: ttk.LabelFrame,
        label: str,
        variable: tk.StringVar,
        row: int,
        foreground: str,
    ) -> None:
        ttk.Label(parent, text=label).grid(row=row, column=0, sticky="w", pady=6)
        ttk.Label(parent, textvariable=variable, foreground=foreground).grid(row=row, column=1, sticky="w", pady=6)

    def _parse_tray_count(self, value: str, field_name: str) -> int:
        text = value.strip().replace(" ", "").replace(",", ".")
        if not text:
            return 0
        try:
            number = int(float(text))
        except ValueError as exc:
            raise ValueError(f"Le champ « {field_name} » doit être numérique.") from exc
        if number < 0:
            raise ValueError(f"Le champ « {field_name} » ne peut pas être négatif.")
        return number

    def _on_date_change(self) -> None:
        self.show_all_dates = False
        self.load_day_summary()
        self.refresh_production()

    def calculate_current_totals(self) -> None:
        try:
            delivered_depositaries = self._parse_tray_count(
                self.delivered_depositaries_var.get(),
                "Bacs livrés dépositaires",
            )
            delivered_mamas = self._parse_tray_count(self.delivered_mamas_var.get(), "Bacs livrés mamans")
            given = self._parse_tray_count(self.given_trays_var.get(), "Bacs donnés")
            samples = self._parse_tray_count(self.sample_trays_var.get(), "Échantillons")
            remaining = self._parse_tray_count(self.remaining_trays_var.get(), "Bacs restants")
            wasted = self._parse_tray_count(self.wasted_trays_var.get(), "Bacs foutus")
        except ValueError:
            delivered_depositaries = delivered_mamas = given = samples = remaining = wasted = 0
        try:
            ordered = self._parse_tray_count(self.ordered_trays_var.get(), "Bacs commandés")
        except ValueError:
            ordered = 0
        produced = delivered_depositaries + delivered_mamas + given + samples + remaining + wasted
        gap = produced - ordered
        coverage = round((produced * 100.0 / ordered), 2) if ordered > 0 else 0.0
        self.total_produced_var.set(str(produced))
        self.available_trays_var.set(str(remaining))
        self.gap_var.set(str(gap))
        self.coverage_var.set(f"{format_number(coverage)} %")
        self.gap_label.configure(foreground=DANGER_COLOR if gap < 0 else SUCCESS_COLOR)

    def load_day_summary(self) -> None:
        try:
            target_date = self.date_field.get_date()
        except ValueError:
            target_date = date.today()
        summary = DatabaseHelper.get_production_summary_for_date(target_date)
        self.ordered_trays_var.set(str(int(summary.get("NombreBacsCommandes", 0) or 0)))
        if not self.edit_mode and int(summary.get("Id", 0) or 0) > 0:
            self.selected_production_id = int(summary.get("Id", 0) or 0)
            self.delivered_depositaries_var.set(str(int(summary.get("NombreBacsLivresDepositaires", 0) or 0)))
            self.delivered_mamas_var.set(str(int(summary.get("NombreBacsLivresMamans", 0) or 0)))
            self.given_trays_var.set(str(int(summary.get("NombreBacsDonnes", 0) or 0)))
            self.sample_trays_var.set(str(int(summary.get("NombreEchantillons", 0) or 0)))
            self.remaining_trays_var.set(str(int(summary.get("NombreBacsRestants", 0) or 0)))
            self.wasted_trays_var.set(str(int(summary.get("NombreBacsFoutus", 0) or 0)))
            self.sacks_used_var.set(format_number(float(summary.get("NombreSacsUtilises", 0) or 0)))
            self.observations_text.delete("1.0", "end")
            self.observations_text.insert("1.0", str(summary.get("Observations", "") or ""))
        elif not self.edit_mode:
            self.selected_production_id = 0
            self.delivered_depositaries_var.set("0")
            self.delivered_mamas_var.set("0")
            self.given_trays_var.set("0")
            self.sample_trays_var.set("0")
            self.remaining_trays_var.set("0")
            self.wasted_trays_var.set("0")
            self.sacks_used_var.set("0")
            self.observations_text.delete("1.0", "end")
        self.calculate_current_totals()

    def validate_production(self) -> tuple[date, int, int, int, int, int, int, int, float, str] | None:
        try:
            target_date = self.date_field.get_date()
            ordered = self._parse_tray_count(self.ordered_trays_var.get(), "Bacs commandés")
            delivered_depositaries = self._parse_tray_count(
                self.delivered_depositaries_var.get(),
                "Bacs livrés dépositaires",
            )
            delivered_mamas = self._parse_tray_count(self.delivered_mamas_var.get(), "Bacs livrés mamans")
            given = self._parse_tray_count(self.given_trays_var.get(), "Bacs donnés")
            samples = self._parse_tray_count(self.sample_trays_var.get(), "Échantillons")
            remaining = self._parse_tray_count(self.remaining_trays_var.get(), "Bacs restants")
            wasted = self._parse_tray_count(self.wasted_trays_var.get(), "Bacs foutus")
            sacks_used = parse_float(self.sacks_used_var.get(), "Nombre de sacs utilisés")
            if sacks_used < 0:
                raise ValueError("Le nombre de sacs utilisés ne peut pas être négatif.")
        except Exception as exc:
            messagebox.showwarning("Production", str(exc))
            return None

        observations = self.observations_text.get("1.0", "end").strip()
        return target_date, ordered, delivered_depositaries, delivered_mamas, given, samples, remaining, wasted, sacks_used, observations

    def save_production(self) -> None:
        if self.is_read_only_module("Production"):
            messagebox.showwarning("Production", "Ce module est en lecture seule pour votre profil.")
            return
        validated = self.validate_production()
        if validated is None:
            return
        target_date, ordered, delivered_depositaries, delivered_mamas, given, samples, remaining, wasted, sacks_used, observations = validated

        try:
            DatabaseHelper.save_production_day(
                target_date,
                ordered,
                delivered_depositaries,
                delivered_mamas,
                given,
                samples,
                remaining,
                wasted,
                sacks_used,
                observations,
            )
            log_user_action(
                self,
                "Production",
                "Production enregistrée",
                (
                    f"{target_date.strftime('%d/%m/%Y')} | Dépositaires {delivered_depositaries} | "
                    f"Mamans {delivered_mamas} | Donnés {given} | Échantillons {samples} | "
                    f"Restants {remaining} | Foutus {wasted}"
                ),
            )
            self.reset_form()
            self.refresh_production()
            messagebox.showinfo("Production", "La production a été enregistrée avec succès.")
        except ValueError as exc:
            messagebox.showwarning("Production", str(exc))
        except Exception as exc:
            messagebox.showerror("Production", str(exc))

    def refresh_production(self) -> None:
        try:
            target_date = self.date_field.get_date()
        except ValueError:
            target_date = date.today()
        rows = DatabaseHelper.list_productions() if self.show_all_dates else DatabaseHelper.list_productions_by_date(target_date)
        self.table.set_data(
            rows,
            columns=[
                "Id",
                "DateProduction",
                "NombreBacsCommandes",
                "NombreBacsLivresDepositaires",
                "NombreBacsLivresMamans",
                "NombreBacsDonnes",
                "NombreEchantillons",
                "NombreBacsRestants",
                "NombreBacsFoutus",
                "NombreBacsProduits",
                "NombreSacsUtilises",
                "EcartCommandes",
                "TauxCouverture",
                "Observations",
            ],
            headings={
                "DateProduction": "Date",
                "NombreBacsCommandes": "Commandés",
                "NombreBacsLivresDepositaires": "Livrés dépositaires",
                "NombreBacsLivresMamans": "Livrés mamans",
                "NombreBacsDonnes": "Donnés",
                "NombreEchantillons": "Échantillons",
                "NombreBacsRestants": "Restants",
                "NombreBacsFoutus": "Foutus",
                "NombreBacsProduits": "Produits",
                "NombreSacsUtilises": "Sacs utilisés",
                "EcartCommandes": "Écart",
                "TauxCouverture": "Couverture",
                "Observations": "Observations",
            },
            hidden_columns=["Id"],
            formatters={
                "TauxCouverture": lambda value: f"{format_number(float(value or 0))} %",
                "Observations": compact_multiline_text,
            },
        )
        self.update_summary(len(rows))
        self.refresh_day_lock_state()

    def update_summary(self, row_count: int | None = None) -> None:
        if self.show_all_dates:
            summary = DatabaseHelper.get_global_production_summary()
            self.summary_var.set(
                "Production globale\n"
                f"Jours saisis : {int(summary.get('JoursProduction', 0) or 0)} | "
                f"Bacs produits : {int(summary.get('TotalBacsProduits', 0) or 0)}\n"
                f"Bacs restants : {int(summary.get('TotalBacsRestants', 0) or 0)} | "
                f"Sacs utilisés : {format_number(float(summary.get('TotalSacsUtilises', 0) or 0))} | "
                f"Écart : {int(summary.get('EcartCommandes', 0) or 0)}"
            )
            return

        try:
            target_date = self.date_field.get_date()
        except ValueError:
            target_date = date.today()
        summary = DatabaseHelper.get_production_summary_for_date(target_date)
        self.summary_var.set(
            f"Production du {target_date.strftime('%d/%m/%Y')}\n"
            f"Commandés : {int(summary.get('NombreBacsCommandes', 0) or 0)} | "
            f"Produits : {int(summary.get('NombreBacsProduits', 0) or 0)} | "
            f"Restants : {int(summary.get('NombreBacsRestants', 0) or 0)}\n"
            f"Livrés dépositaires : {int(summary.get('NombreBacsLivresDepositaires', 0) or 0)} | "
            f"Livrés mamans : {int(summary.get('NombreBacsLivresMamans', 0) or 0)} | "
            f"Écart : {int(summary.get('EcartCommandes', 0) or 0)} | "
            f"Sacs utilisés : {format_number(float(summary.get('NombreSacsUtilises', 0) or 0))}"
        )

    def load_production_for_edit(self) -> None:
        if self.is_read_only_module("Production"):
            messagebox.showwarning("Production", "Ce module est en lecture seule pour votre profil.")
            return
        row = self.selected_order_row()
        if row is None:
            messagebox.showwarning("Production", "Veuillez sélectionner une production dans la grille.")
            return
        self.selected_production_id = int(row["Id"])
        self.edit_mode = True
        self.date_field.set_date(str(row["DateProduction"]))
        self.ordered_trays_var.set(str(int(row.get("NombreBacsCommandes", 0) or 0)))
        self.delivered_depositaries_var.set(str(int(row.get("NombreBacsLivresDepositaires", 0) or 0)))
        self.delivered_mamas_var.set(str(int(row.get("NombreBacsLivresMamans", 0) or 0)))
        self.given_trays_var.set(str(int(row.get("NombreBacsDonnes", 0) or 0)))
        self.sample_trays_var.set(str(int(row.get("NombreEchantillons", 0) or 0)))
        self.remaining_trays_var.set(str(int(row.get("NombreBacsRestants", 0) or 0)))
        self.wasted_trays_var.set(str(int(row.get("NombreBacsFoutus", 0) or 0)))
        self.sacks_used_var.set(format_number(float(row.get("NombreSacsUtilises", 0) or 0)))
        self.observations_text.delete("1.0", "end")
        self.observations_text.insert("1.0", str(row.get("Observations", "") or ""))
        self.show_all_dates = False
        self.calculate_current_totals()
        self.refresh_day_lock_state()
        messagebox.showinfo("Production", "La production a été chargée. Modifiez-la puis enregistrez.")

    def delete_production(self) -> None:
        if self.is_read_only_module("Production"):
            messagebox.showwarning("Production", "Ce module est en lecture seule pour votre profil.")
            return
        row = self.table.selected_row()
        if row is None:
            messagebox.showwarning("Production", "Veuillez sélectionner une production dans la grille.")
            return
        if not messagebox.askyesno("Confirmation", "Voulez-vous vraiment supprimer cette production ?"):
            return
        try:
            deleted = DatabaseHelper.delete_production_day(int(row["Id"]))
            if deleted:
                log_user_action(
                    self,
                    "Production",
                    "Production supprimée",
                    f"Id {row['Id']} | Date {row['DateProduction']}",
                )
                self.reset_form()
                self.refresh_production()
                messagebox.showinfo("Production", "La production a été supprimée avec succès.")
            else:
                messagebox.showwarning("Production", "Aucune production n'a été supprimée.")
        except ValueError as exc:
            messagebox.showwarning("Production", str(exc))
        except Exception as exc:
            messagebox.showerror("Production", str(exc))

    def show_all(self) -> None:
        self.show_all_dates = True
        self.refresh_production()

    def refresh_live_view(self) -> None:
        self.load_day_summary()
        self.refresh_production()

    def reset_form(self) -> None:
        self.selected_production_id = 0
        self.edit_mode = False
        self.show_all_dates = False
        self.date_field.set_date(today_iso())
        self.delivered_depositaries_var.set("0")
        self.delivered_mamas_var.set("0")
        self.given_trays_var.set("0")
        self.sample_trays_var.set("0")
        self.remaining_trays_var.set("0")
        self.wasted_trays_var.set("0")
        self.observations_text.delete("1.0", "end")
        self.load_day_summary()
        self.refresh_day_lock_state()


class OrdersWindow(BaseModuleWindow):
    def __init__(self, parent: DashboardWindow) -> None:
        super().__init__(parent, "Gestion des commandes", "1240x840")
        self.edit_mode = False
        self.selected_order_id = 0
        self.show_all_dates = False
        self.loaded_amount_due_rate: float | None = None
        self.available_advance = 0.0
        self._clearing_order_selection = False
        self.build_ui()
        self.reset_form()
        self.summary_var.set("Chargement des commandes...")
        self.after_idle(self.refresh_orders)

    def build_ui(self) -> None:
        container = self.body

        content = ttk.Frame(container)
        content.pack(fill="both", expand=True)
        self.create_day_lock_notice(container, "les commandes", before=content)

        form = ttk.LabelFrame(content, text="Commande", style="Card.TLabelframe")
        form.pack(side="left", fill="y", padx=(0, 12))

        ttk.Label(form, text="Date").grid(row=0, column=0, sticky="w", pady=6)
        self.date_field = DateField(form)
        self.date_field.grid(row=0, column=1, sticky="ew", pady=6)
        self.date_field.bind_change(self._on_date_change)

        ttk.Label(form, text="Client").grid(row=1, column=0, sticky="w", pady=6)
        self.client_var = tk.StringVar()
        self.client_entry = ttk.Entry(form, textvariable=self.client_var, width=28)
        self.client_entry.grid(row=1, column=1, sticky="ew", pady=6)
        self.client_entry.bind("<FocusOut>", lambda _event: self.refresh_client_advance())

        ttk.Label(form, text="Statut").grid(row=2, column=0, sticky="w", pady=6)
        self.status_var = tk.StringVar(value=ORDER_STATUSES[0])
        self.status_combo = ttk.Combobox(
            form,
            textvariable=self.status_var,
            values=ORDER_STATUSES,
            state="readonly",
            width=25,
        )
        self.status_combo.grid(row=2, column=1, sticky="ew", pady=6)

        ttk.Label(form, text="Nombre de bacs").grid(row=3, column=0, sticky="w", pady=6)
        self.trays_var = tk.StringVar(value="1")
        ttk.Spinbox(form, from_=1, to=100000, textvariable=self.trays_var, width=10).grid(
            row=3, column=1, sticky="w", pady=6
        )

        ttk.Label(form, text="Montant à percevoir").grid(row=4, column=0, sticky="w", pady=6)
        self.amount_due_var = tk.StringVar(value=format_fc(0))
        ttk.Label(form, textvariable=self.amount_due_var, foreground="#7a0000").grid(
            row=4, column=1, sticky="w", pady=6
        )

        ttk.Label(form, text="Montant reçu").grid(row=5, column=0, sticky="w", pady=6)
        self.amount_received_var = tk.StringVar(value="0")
        ttk.Entry(form, textvariable=self.amount_received_var, width=28).grid(row=5, column=1, sticky="ew", pady=6)

        ttk.Label(form, text="Avance disponible").grid(row=6, column=0, sticky="w", pady=6)
        self.advance_available_var = tk.StringVar(value=format_fc(0))
        ttk.Label(form, textvariable=self.advance_available_var, foreground=PRIMARY_DARK_COLOR).grid(
            row=6, column=1, sticky="w", pady=6
        )

        ttk.Label(form, text="Avance utilisée").grid(row=7, column=0, sticky="w", pady=6)
        self.advance_used_var = tk.StringVar(value=format_fc(0))
        ttk.Label(form, textvariable=self.advance_used_var, foreground=PRIMARY_DARK_COLOR).grid(
            row=7, column=1, sticky="w", pady=6
        )

        ttk.Label(form, text="Nouvelle avance").grid(row=8, column=0, sticky="w", pady=6)
        self.advance_generated_var = tk.StringVar(value=format_fc(0))
        ttk.Label(form, textvariable=self.advance_generated_var, foreground=SUCCESS_COLOR).grid(
            row=8, column=1, sticky="w", pady=6
        )

        ttk.Label(form, text="Dette").grid(row=9, column=0, sticky="w", pady=6)
        self.debt_var = tk.StringVar(value=format_fc(0))
        self.debt_label = ttk.Label(form, textvariable=self.debt_var, foreground=SUCCESS_COLOR)
        self.debt_label.grid(row=9, column=1, sticky="w", pady=6)

        actions = ttk.Frame(form)
        actions.grid(row=10, column=0, columnspan=2, pady=(14, 0))
        self.save_button = ttk.Button(actions, text="Enregistrer", command=self.save_order)
        self.save_button.grid(row=0, column=0, padx=4, pady=4)
        self.edit_button = ttk.Button(actions, text="Modifier", command=self.load_order_for_edit)
        self.edit_button.grid(row=0, column=1, padx=4, pady=4)
        self.delete_button = ttk.Button(actions, text="Supprimer", command=self.delete_order)
        self.delete_button.grid(row=0, column=2, padx=4, pady=4)
        ttk.Button(actions, text="Tout afficher", command=self.show_all).grid(row=1, column=0, padx=4, pady=4)
        ttk.Button(actions, text="Fermer", command=self.close_window).grid(row=1, column=1, padx=4, pady=4)

        self.summary_var = tk.StringVar()
        ttk.Label(form, textvariable=self.summary_var, wraplength=360, justify="left").grid(
            row=11, column=0, columnspan=2, sticky="ew", pady=(14, 0)
        )

        tables_container = ttk.Frame(content)
        tables_container.pack(side="left", fill="both", expand=True)

        depositary_frame = ttk.LabelFrame(
            tables_container,
            text="Commandes des dépositaires",
            style="Card.TLabelframe",
        )
        depositary_frame.pack(fill="both", expand=True, pady=(0, 8))
        self.depositary_table = DataTable(depositary_frame, height=10)
        self.depositary_table.pack(fill="both", expand=True)

        customer_frame = ttk.LabelFrame(
            tables_container,
            text="Commandes des mamans et vente cash",
            style="Card.TLabelframe",
        )
        customer_frame.pack(fill="both", expand=True)
        self.customer_table = DataTable(customer_frame, height=10)
        self.customer_table.pack(fill="both", expand=True)
        self.table = self.customer_table
        self.depositary_table.tree.bind(
            "<<TreeviewSelect>>",
            lambda _event: self.clear_other_order_table_selection(self.depositary_table),
            add="+",
        )
        self.customer_table.tree.bind(
            "<<TreeviewSelect>>",
            lambda _event: self.clear_other_order_table_selection(self.customer_table),
            add="+",
        )

        self.status_combo.bind("<<ComboboxSelected>>", self._on_status_change)
        self.amount_received_var.trace_add("write", lambda *_args: self.recalculate_amounts())
        self.trays_var.trace_add("write", lambda *_args: self.recalculate_amounts())
        form.columnconfigure(1, weight=1)
        self.configure_day_lock_controls(
            self.date_field,
            [self.save_button, self.edit_button, self.delete_button],
        )

    def clear_other_order_table_selection(self, source_table: DataTable) -> None:
        if self._clearing_order_selection:
            return
        self._clearing_order_selection = True
        try:
            other_table = self.customer_table if source_table is self.depositary_table else self.depositary_table
            other_table.tree.selection_remove(other_table.tree.selection())
        finally:
            self._clearing_order_selection = False

    def selected_order_row(self) -> dict[str, Any] | None:
        return self.depositary_table.selected_row() or self.customer_table.selected_row()

    def set_orders_table_data(self, table: DataTable, rows: list[dict[str, Any]]) -> None:
        table.set_data(
            rows,
            columns=[
                "Id",
                "DateCommande",
                "Client",
                "Statut",
                "NombreBacs",
                "MontantAPercevoir",
                "MontantRecu",
                "AvanceUtilisee",
                "AvanceGeneree",
                "SoldeAvance",
                "DetteInitiale",
                "DettePayee",
                "Dette",
                "StatutDette",
            ],
            headings={
                "DateCommande": "Date",
                "NombreBacs": "Bacs",
                "MontantAPercevoir": "À percevoir",
                "MontantRecu": "Reçu",
                "AvanceUtilisee": "Avance utilisée",
                "AvanceGeneree": "Nouvelle avance",
                "SoldeAvance": "Solde avance",
                "DetteInitiale": "Dette initiale",
                "DettePayee": "Dette payée",
                "Dette": "Dette restante",
                "StatutDette": "Statut dette",
            },
            hidden_columns=["Id"],
            formatters={
                "Statut": normalize_status_label,
                "NombreBacs": lambda value: f"{int(value)}",
                "MontantAPercevoir": lambda value: format_fc(float(value)),
                "MontantRecu": lambda value: format_fc(float(value)),
                "AvanceUtilisee": lambda value: format_fc(float(value)),
                "AvanceGeneree": lambda value: format_fc(float(value)),
                "SoldeAvance": lambda value: format_fc(float(value)),
                "DetteInitiale": lambda value: format_fc(float(value)),
                "DettePayee": lambda value: format_fc(float(value)),
                "Dette": lambda value: format_fc(float(value)),
            },
        )

    def _on_date_change(self) -> None:
        self.show_all_dates = False
        self.refresh_client_advance()
        self.refresh_orders()

    def _on_status_change(self, _event: object | None = None) -> None:
        if normalize_status_form_label(self.status_var.get()) != DEPOSITARY_STATUS:
            self.loaded_amount_due_rate = None
        self.recalculate_amounts()

    def get_status_rate(self, status: str) -> float:
        normalized_status = normalize_status_form_label(status)
        if normalized_status == DEPOSITARY_STATUS and self.loaded_amount_due_rate is not None:
            return float(self.loaded_amount_due_rate)
        return float(ORDER_STATUS_RATES.get(normalized_status, 0))

    def refresh_client_advance(self) -> None:
        client = self.client_var.get().strip()
        if not client:
            self.available_advance = 0.0
        else:
            try:
                self.available_advance = DatabaseHelper.get_client_advance_balance(
                    client,
                    self.date_field.get_date(),
                    self.selected_order_id if self.edit_mode else 0,
                )
            except Exception:
                self.available_advance = 0.0
        self.recalculate_amounts()

    def recalculate_amounts(self) -> None:
        try:
            trays = int(float(self.trays_var.get() or "0"))
        except ValueError:
            trays = 0
        amount_due = trays * self.get_status_rate(self.status_var.get())
        try:
            amount_received = parse_optional_float(self.amount_received_var.get())
        except ValueError:
            amount_received = 0
        advance_used = min(self.available_advance, amount_due)
        cash_needed = max(amount_due - advance_used, 0.0)
        debt = max(cash_needed - amount_received, 0.0)
        advance_generated = max(amount_received - cash_needed, 0.0)
        self.amount_due_var.set(format_fc(amount_due))
        self.advance_available_var.set(format_fc(self.available_advance))
        self.advance_used_var.set(format_fc(advance_used))
        self.advance_generated_var.set(format_fc(advance_generated))
        self.debt_var.set(format_fc(debt))
        self.debt_label.configure(foreground=DANGER_COLOR if debt > 0 else SUCCESS_COLOR)

    def validate_order(self) -> tuple[date, str, str, int, float, float, float] | None:
        try:
            target_date = self.date_field.get_date()
        except Exception as exc:
            messagebox.showwarning("Commandes", str(exc))
            return None

        client = self.client_var.get().strip()
        if not client:
            messagebox.showwarning("Commandes", "Veuillez saisir le nom du client.")
            return None
        try:
            self.available_advance = DatabaseHelper.get_client_advance_balance(
                client,
                target_date,
                self.selected_order_id if self.edit_mode else 0,
            )
        except Exception as exc:
            messagebox.showwarning("Commandes", str(exc))
            return None
        status = normalize_status_form_label(self.status_var.get().strip())
        if not status:
            messagebox.showwarning("Commandes", "Veuillez choisir un statut.")
            return None

        try:
            trays = int(float(self.trays_var.get()))
        except ValueError:
            messagebox.showwarning("Commandes", "Le nombre de bacs doit être numérique.")
            return None
        if trays <= 0:
            messagebox.showwarning("Commandes", "Le nombre de bacs doit être supérieur à zéro.")
            return None

        try:
            amount_received = parse_optional_float(self.amount_received_var.get())
        except ValueError:
            messagebox.showwarning("Commandes", "Le montant reçu doit être numérique.")
            return None
        if amount_received < 0:
            messagebox.showwarning("Commandes", "Le montant reçu ne peut pas être négatif.")
            return None

        amount_due = trays * self.get_status_rate(status)
        advance_used = min(self.available_advance, amount_due)
        debt = max(amount_due - advance_used - amount_received, 0.0)
        return target_date, client, status, trays, amount_due, amount_received, debt

    def handle_duplicate_order(
        self,
        target_date: date,
        client: str,
        status: str,
        trays: int,
        amount_due: float,
        amount_received: float,
        debt: float,
    ) -> bool:
        if self.edit_mode:
            existing_id = DatabaseHelper.find_existing_order(target_date, client, self.selected_order_id)
            if existing_id > 0:
                messagebox.showwarning(
                    "Commandes",
                    "Une autre commande existe déjà pour ce client à cette date.",
                )
                return False
            return True

        existing_id = DatabaseHelper.find_existing_order(target_date, client)
        if existing_id == 0:
            similar_order = DatabaseHelper.find_similar_order(target_date, client)
            if similar_order is None:
                return True
            existing_client = str(similar_order.get("Client", ""))
            choice = messagebox.askyesnocancel(
                "Client similaire détecté",
                (
                    f"Il y a déjà une commande enregistrée au nom de : {existing_client}.\n\n"
                    "Oui : charger cette commande pour la modifier.\n"
                    "Non : continuer parce qu'il s'agit d'un client différent.\n"
                    "Annuler : revenir au formulaire."
                ),
            )
            if choice is None:
                return False
            if choice:
                self.load_order_row_for_edit(similar_order)
                return False
            return True

        if not messagebox.askyesno(
            "Commande déjà existante",
            "Une commande existe déjà pour ce client à cette date.\n"
            "Voulez-vous la mettre à jour au lieu d'en créer une nouvelle ?",
        ):
            return False

        updated = DatabaseHelper.update_order(
            existing_id,
            target_date,
            client,
            status,
            trays,
            amount_due,
            amount_received,
            debt,
        )
        if updated:
            log_user_action(
                self,
                "Commandes",
                "Commande dupliquée mise à jour",
                f"{client} | {target_date.strftime('%d/%m/%Y')} | Dette {format_fc(debt)}",
            )
            messagebox.showinfo("Commandes", "La commande existante a été modifiée avec succès.")
            self.reset_form()
            self.refresh_orders()
        else:
            messagebox.showwarning("Commandes", "La commande existante n'a pas pu être modifiée.")
        return False

    def save_order(self) -> None:
        if self.is_read_only_module("Commandes"):
            messagebox.showwarning("Commandes", "Ce module est en lecture seule pour votre profil.")
            return
        validated = self.validate_order()
        if validated is None:
            return
        target_date, client, status, trays, amount_due, amount_received, debt = validated

        try:
            if not self.handle_duplicate_order(
                target_date, client, status, trays, amount_due, amount_received, debt
            ):
                return
            if self.edit_mode:
                updated = DatabaseHelper.update_order(
                    self.selected_order_id,
                    target_date,
                    client,
                    status,
                    trays,
                    amount_due,
                    amount_received,
                    debt,
                )
                if updated:
                    log_user_action(
                        self,
                        "Commandes",
                        "Commande modifiée",
                        f"{client} | {target_date.strftime('%d/%m/%Y')} | {trays} bacs | Dette {format_fc(debt)}",
                    )
                    messagebox.showinfo("Commandes", "La commande a été modifiée avec succès.")
                else:
                    messagebox.showwarning("Commandes", "Aucune commande n'a été modifiée.")
            else:
                DatabaseHelper.add_order(
                    target_date,
                    client,
                    status,
                    trays,
                    amount_due,
                    amount_received,
                    debt,
                )
                log_user_action(
                    self,
                    "Commandes",
                    "Commande ajoutée",
                    f"{client} | {target_date.strftime('%d/%m/%Y')} | {trays} bacs | Dette {format_fc(debt)}",
                )
                messagebox.showinfo("Commandes", "La commande a été enregistrée avec succès.")
            self.reset_form()
            self.refresh_orders()
        except ValueError as exc:
            messagebox.showwarning("Commandes", str(exc))
        except Exception as exc:
            messagebox.showerror("Commandes", str(exc))

    def show_all(self) -> None:
        self.show_all_dates = True
        self.refresh_orders()

    def refresh_live_view(self) -> None:
        self.refresh_orders()

    def refresh_orders(self) -> None:
        try:
            target_date = self.date_field.get_date()
        except ValueError:
            target_date = date.today()
        rows = DatabaseHelper.list_orders() if self.show_all_dates else DatabaseHelper.list_orders_by_date(target_date)
        depositary_rows = [row for row in rows if is_depositary_status(row.get("Statut"))]
        customer_rows = [row for row in rows if not is_depositary_status(row.get("Statut"))]
        self.set_orders_table_data(self.depositary_table, depositary_rows)
        self.set_orders_table_data(self.customer_table, customer_rows)
        self.update_summary(rows)
        self.refresh_day_lock_state()
        return
        self.table.set_data(
            rows,
            columns=[
                "Id",
                "DateCommande",
                "Client",
                "Statut",
                "NombreBacs",
                "MontantAPercevoir",
                "MontantRecu",
                "DetteInitiale",
                "DettePayee",
                "Dette",
                "StatutDette",
            ],
            headings={
                "DateCommande": "Date",
                "NombreBacs": "Bacs",
                "MontantAPercevoir": "À percevoir",
                "MontantRecu": "Reçu",
                "DetteInitiale": "Dette initiale",
                "DettePayee": "Dette payée",
                "Dette": "Dette restante",
                "StatutDette": "Statut dette",
            },
            hidden_columns=["Id"],
            formatters={
                "Statut": normalize_status_label,
                "NombreBacs": lambda value: f"{int(value)}",
                "MontantAPercevoir": lambda value: format_fc(float(value)),
                "MontantRecu": lambda value: format_fc(float(value)),
                "DetteInitiale": lambda value: format_fc(float(value)),
                "DettePayee": lambda value: format_fc(float(value)),
                "Dette": lambda value: format_fc(float(value)),
            },
        )
        self.update_summary(rows)
        self.refresh_day_lock_state()

    def update_summary(self, rows: list[dict[str, Any]]) -> None:
        if self.show_all_dates:
            summary = DatabaseHelper.get_global_orders_summary()
            text = (
                "Affichage : toutes les dates\n"
                f"Nombre de commandes : {len(rows)} | Commandes avec dette : {int(summary.get('NombreAvecDette', 0))}\n"
                f"Total bacs : {int(summary.get('TotalBacs', 0))}\n"
                f"Montant attendu : {format_fc(float(summary.get('MontantAttendu', 0)))} | "
                f"Montant reçu : {format_fc(float(summary.get('MontantRecu', 0)))} | "
                f"Dettes : {format_fc(float(summary.get('TotalDettes', 0)))}\n"
                f"Avances disponibles : {format_fc(float(summary.get('AvancesDisponibles', 0)))}"
            )
        else:
            try:
                target_date = self.date_field.get_date()
            except ValueError:
                target_date = date.today()
            total_bacs = sum(int(row["NombreBacs"]) for row in rows)
            total_due = sum(float(row["MontantAPercevoir"]) for row in rows)
            total_received = sum(float(row["MontantRecu"]) for row in rows)
            advances_used = sum(float(row.get("AvanceUtilisee", 0) or 0) for row in rows)
            advances_generated = sum(float(row.get("AvanceGeneree", 0) or 0) for row in rows)
            total_debt = sum(float(row["Dette"]) for row in rows)
            with_debt = sum(1 for row in rows if float(row["Dette"]) > 0)
            text = (
                f"Date : {target_date.strftime('%d/%m/%Y')}\n"
                f"Nombre de commandes : {len(rows)} | Commandes avec dette : {with_debt}\n"
                f"Total bacs : {total_bacs}\n"
                f"Montant attendu : {format_fc(total_due)} | "
                f"Montant reçu : {format_fc(total_received)} | "
                f"Dettes : {format_fc(total_debt)}\n"
                f"Avances utilisées : {format_fc(advances_used)} | "
                f"Nouvelles avances : {format_fc(advances_generated)}"
            )
        self.summary_var.set(text)

    def load_order_row_for_edit(self, row: dict[str, Any]) -> None:
        self.selected_order_id = int(row["Id"])
        self.edit_mode = True
        self.date_field.set_date(str(row["DateCommande"]))
        self.client_var.set(str(row["Client"]))
        self.status_var.set(normalize_status_form_label(row["Statut"]))
        self.trays_var.set(str(int(row["NombreBacs"])))
        self.amount_received_var.set(format_number(float(row["MontantRecu"])))
        self.available_advance = DatabaseHelper.get_client_advance_balance(
            str(row["Client"]),
            str(row["DateCommande"]),
            self.selected_order_id,
        )
        if is_legacy_depositary_6000_status(row["Statut"]) and int(row["NombreBacs"]) > 0:
            self.loaded_amount_due_rate = float(row["MontantAPercevoir"]) / int(row["NombreBacs"])
        elif normalize_status_form_label(row["Statut"]) == DEPOSITARY_STATUS and int(row["NombreBacs"]) > 0:
            self.loaded_amount_due_rate = float(row["MontantAPercevoir"]) / int(row["NombreBacs"])
        else:
            self.loaded_amount_due_rate = None
        self.recalculate_amounts()
        self.refresh_day_lock_state()
        messagebox.showinfo("Commandes", "La commande a été chargée. Modifiez-la puis enregistrez.")

    def load_order_for_edit(self) -> None:
        if self.is_read_only_module("Commandes"):
            messagebox.showwarning("Commandes", "Ce module est en lecture seule pour votre profil.")
            return
        row = self.table.selected_row()
        if row is None:
            messagebox.showwarning("Commandes", "Veuillez sélectionner une commande dans la grille.")
            return
        self.selected_order_id = int(row["Id"])
        self.edit_mode = True
        self.date_field.set_date(str(row["DateCommande"]))
        self.client_var.set(str(row["Client"]))
        self.status_var.set(normalize_status_form_label(row["Statut"]))
        self.trays_var.set(str(int(row["NombreBacs"])))
        self.amount_received_var.set(format_number(float(row["MontantRecu"])))
        if is_legacy_depositary_6000_status(row["Statut"]) and int(row["NombreBacs"]) > 0:
            self.loaded_amount_due_rate = float(row["MontantAPercevoir"]) / int(row["NombreBacs"])
        elif normalize_status_form_label(row["Statut"]) == DEPOSITARY_STATUS and int(row["NombreBacs"]) > 0:
            self.loaded_amount_due_rate = float(row["MontantAPercevoir"]) / int(row["NombreBacs"])
        else:
            self.loaded_amount_due_rate = None
        self.recalculate_amounts()
        self.refresh_day_lock_state()
        messagebox.showinfo("Commandes", "La commande a été chargée. Modifiez-la puis enregistrez.")

    def load_order_for_edit(self) -> None:
        if self.is_read_only_module("Commandes"):
            messagebox.showwarning("Commandes", "Ce module est en lecture seule pour votre profil.")
            return
        row = self.selected_order_row()
        if row is None:
            messagebox.showwarning("Commandes", "Veuillez sélectionner une commande dans la grille.")
            return
        self.load_order_row_for_edit(row)

    def delete_order(self) -> None:
        if self.is_read_only_module("Commandes"):
            messagebox.showwarning("Commandes", "Ce module est en lecture seule pour votre profil.")
            return
        row = self.table.selected_row()
        if row is None:
            messagebox.showwarning("Commandes", "Veuillez sélectionner une commande dans la grille.")
            return
        if not messagebox.askyesno("Confirmation", "Voulez-vous vraiment supprimer cette commande ?"):
            return
        try:
            deleted = DatabaseHelper.delete_order(int(row["Id"]))
            if deleted:
                log_user_action(
                    self,
                    "Commandes",
                    "Commande supprimée",
                    f"Id {row['Id']} | Client {row['Client']} | Date {row['DateCommande']}",
                )
                messagebox.showinfo("Commandes", "La commande a été supprimée avec succès.")
                self.reset_form()
                self.refresh_orders()
            else:
                messagebox.showwarning("Commandes", "Aucune commande n'a été supprimée.")
        except ValueError as exc:
            messagebox.showwarning("Commandes", str(exc))
        except Exception as exc:
            messagebox.showerror("Commandes", str(exc))

    def delete_order(self) -> None:
        if self.is_read_only_module("Commandes"):
            messagebox.showwarning("Commandes", "Ce module est en lecture seule pour votre profil.")
            return
        row = self.selected_order_row()
        if row is None:
            messagebox.showwarning("Commandes", "Veuillez sélectionner une commande dans la grille.")
            return
        if not messagebox.askyesno("Confirmation", "Voulez-vous vraiment supprimer cette commande ?"):
            return
        try:
            deleted = DatabaseHelper.delete_order(int(row["Id"]))
            if deleted:
                log_user_action(
                    self,
                    "Commandes",
                    "Commande supprimée",
                    f"Id {row['Id']} | Client {row['Client']} | Date {row['DateCommande']}",
                )
                messagebox.showinfo("Commandes", "La commande a été supprimée avec succès.")
                self.reset_form()
                self.refresh_orders()
            else:
                messagebox.showwarning("Commandes", "Aucune commande n'a été supprimée.")
        except ValueError as exc:
            messagebox.showwarning("Commandes", str(exc))
        except Exception as exc:
            messagebox.showerror("Commandes", str(exc))

    def reset_form(self) -> None:
        self.date_field.set_date(today_iso())
        self.client_var.set("")
        self.status_var.set(ORDER_STATUSES[0])
        self.trays_var.set("1")
        self.amount_received_var.set("0")
        self.edit_mode = False
        self.selected_order_id = 0
        self.loaded_amount_due_rate = None
        self.show_all_dates = False
        self.available_advance = 0.0
        self.recalculate_amounts()
        self.refresh_day_lock_state()


class CashWindow(BaseModuleWindow):
    def __init__(self, parent: DashboardWindow) -> None:
        super().__init__(parent, "Gestion de la caisse", "1280x900")
        self.show_all_dates = False
        self.selected_cash_id = 0
        self.trays_today = 0.0
        self.expected_today = 0.0
        self.received_today = 0.0
        self.debts_today = 0.0
        self.accumulated_debts_before_payment = 0.0
        self.remaining_accumulated_debts = 0.0
        self.total_entries_today = 0.0
        self.build_ui()
        self.total_trays_var.set("...")
        self.expected_var.set("Chargement...")
        self.received_var.set("Chargement...")
        self.debts_var.set("Chargement...")
        self.accumulated_debts_var.set("Chargement...")
        self.remaining_accumulated_debts_var.set("Chargement...")
        self.accumulated_debts_status_var.set("Chargement...")
        self.total_entries_var.set("Chargement...")
        self.balance_var.set("Chargement...")
        self.summary_var.set("Chargement de la caisse...")
        self.after_idle(self.finish_initial_load)

    def finish_initial_load(self) -> None:
        self.reset_form()
        self.refresh_data()

    def build_ui(self) -> None:
        container = self.body

        content = ttk.Frame(container)
        content.pack(fill="both", expand=True)
        self.create_day_lock_notice(container, "la caisse", before=content)

        form = ttk.LabelFrame(content, text="Fiche journalière", style="Card.TLabelframe")
        form.pack(side="left", fill="y", padx=(0, 12))

        ttk.Label(form, text="Date").grid(row=0, column=0, sticky="w", pady=6)
        self.date_field = DateField(form)
        self.date_field.grid(row=0, column=1, sticky="ew", pady=6)
        self.date_field.bind_change(self._on_date_change)

        self.total_trays_var = tk.StringVar()
        self.expected_var = tk.StringVar()
        self.received_var = tk.StringVar()
        self.debts_var = tk.StringVar()
        self.accumulated_debts_var = tk.StringVar()
        self.remaining_accumulated_debts_var = tk.StringVar()
        self.accumulated_debts_status_var = tk.StringVar()
        self.paid_debts_var = tk.StringVar(value="0")
        self.total_entries_var = tk.StringVar()
        self.balance_var = tk.StringVar()

        self._make_label_value(form, "Nombre total de bacs", self.total_trays_var, 1)
        self._make_label_value(form, "Montant attendu", self.expected_var, 2, "#7a0000")
        self._make_label_value(form, "Montant reçu", self.received_var, 3, SUCCESS_COLOR)
        self._make_label_value(form, "Dettes du jour", self.debts_var, 4, DANGER_COLOR)
        self._make_label_value(form, "Total dettes accumulées", self.accumulated_debts_var, 5, DANGER_COLOR)

        ttk.Label(form, text="Dettes payées aujourd'hui").grid(row=6, column=0, sticky="w", pady=6)
        ttk.Entry(form, textvariable=self.paid_debts_var, width=28).grid(row=6, column=1, sticky="ew", pady=6)

        ttk.Label(form, text="Ceux qui ont payé leurs dettes").grid(row=7, column=0, sticky="nw", pady=6)
        self.paid_debts_details_text = ScrolledText(form, width=28, height=6)
        self.paid_debts_details_text.configure(font=UI_FONT)
        self.paid_debts_details_text.grid(row=7, column=1, sticky="ew", pady=6)

        self._make_label_value(form, "Dettes accumulées restantes", self.remaining_accumulated_debts_var, 8, DANGER_COLOR)
        self._make_label_value(form, "Statut dettes accumulées", self.accumulated_debts_status_var, 9, "#1f4e79")
        self._make_label_value(form, "Total des entrées", self.total_entries_var, 10, "#1f4e79")

        ttk.Label(form, text="Montant total des dépenses").grid(row=11, column=0, sticky="w", pady=6)
        self.expenses_var = tk.StringVar(value="0")
        ttk.Entry(form, textvariable=self.expenses_var, width=28).grid(row=11, column=1, sticky="ew", pady=6)

        ttk.Label(form, text="Dépenses effectuées").grid(row=12, column=0, sticky="nw", pady=6)
        self.expenses_text = ScrolledText(form, width=28, height=7)
        self.expenses_text.configure(font=UI_FONT)
        self.expenses_text.grid(row=12, column=1, sticky="ew", pady=6)

        self._make_label_value(form, "Solde", self.balance_var, 13, PRIMARY_DARK_COLOR)

        actions = ttk.Frame(form)
        actions.grid(row=14, column=0, columnspan=2, pady=(14, 0))
        self.save_button = ttk.Button(actions, text="Enregistrer", command=self.save_cash)
        self.save_button.grid(row=0, column=0, padx=4, pady=4)
        self.edit_button = ttk.Button(actions, text="Modifier", command=self.load_cash_for_edit)
        self.edit_button.grid(row=0, column=1, padx=4, pady=4)
        self.delete_button = ttk.Button(actions, text="Supprimer", command=self.delete_cash)
        self.delete_button.grid(row=0, column=2, padx=4, pady=4)
        ttk.Button(actions, text="Tout afficher", command=self.show_all).grid(row=1, column=0, padx=4, pady=4)
        ttk.Button(actions, text="Fermer", command=self.close_window).grid(row=1, column=1, padx=4, pady=4)

        self.summary_var = tk.StringVar()
        ttk.Label(form, textvariable=self.summary_var, wraplength=420, justify="left").grid(
            row=15, column=0, columnspan=2, sticky="ew", pady=(14, 0)
        )

        table_frame = ttk.LabelFrame(content, text="Historique de caisse", style="Card.TLabelframe")
        table_frame.pack(side="left", fill="both", expand=True)
        self.table = DataTable(table_frame, height=22)
        self.table.pack(fill="both", expand=True)

        self.paid_debts_var.trace_add("write", lambda *_args: self.calculate_balance())
        self.expenses_var.trace_add("write", lambda *_args: self.calculate_balance())
        form.columnconfigure(1, weight=1)
        self.configure_day_lock_controls(
            self.date_field,
            [self.save_button, self.edit_button, self.delete_button],
        )

    def _make_label_value(
        self,
        parent: ttk.LabelFrame,
        label: str,
        variable: tk.StringVar,
        row: int,
        foreground: str = "#000000",
    ) -> None:
        ttk.Label(parent, text=label).grid(row=row, column=0, sticky="w", pady=6)
        ttk.Label(parent, textvariable=variable, foreground=foreground).grid(row=row, column=1, sticky="w", pady=6)

    def refresh_paid_debts_details_message(self, paid_debts: float) -> None:
        current_text = self.paid_debts_details_text.get("1.0", "end").strip()
        should_show_message = paid_debts <= 0 and self.accumulated_debts_before_payment <= 0
        if should_show_message and current_text in {"", NO_DEBT_PAYMENT_MESSAGE}:
            self.paid_debts_details_text.delete("1.0", "end")
            self.paid_debts_details_text.insert("1.0", NO_DEBT_PAYMENT_MESSAGE)
        elif not should_show_message and current_text == NO_DEBT_PAYMENT_MESSAGE:
            self.paid_debts_details_text.delete("1.0", "end")

    def _on_date_change(self) -> None:
        self.show_all_dates = False
        self.refresh_data()

    def reset_form(self) -> None:
        self.selected_cash_id = 0
        self.date_field.set_date(today_iso())
        self.expenses_var.set("0")
        self.paid_debts_details_text.delete("1.0", "end")
        self.expenses_text.delete("1.0", "end")
        self.show_all_dates = False
        self.load_day_summary()
        self.refresh_day_lock_state()

    def load_day_summary(self) -> None:
        try:
            target_date = self.date_field.get_date()
        except ValueError:
            target_date = date.today()

        summary = DatabaseHelper.get_orders_summary_for_date(target_date)
        self.trays_today = float(summary.get("NombreTotalBacs", 0) or 0)
        self.expected_today = float(summary.get("MontantAttendu", 0) or 0)
        self.received_today = float(summary.get("MontantRecu", 0) or 0)
        self.debts_today = float(summary.get("TotalDettes", 0) or 0)
        accumulated = DatabaseHelper.get_accumulated_debt_totals_for_date(target_date)
        self.accumulated_debts_before_payment = float(
            accumulated.get("DettesAccumuleesAvantPaiement", 0) or 0
        )

        self.total_trays_var.set(f"{int(self.trays_today)}")
        self.expected_var.set(format_fc(self.expected_today))
        self.received_var.set(format_fc(self.received_today))
        self.debts_var.set(format_fc(self.debts_today))
        self.accumulated_debts_var.set(format_fc(self.accumulated_debts_before_payment))

        cash = DatabaseHelper.get_cash_for_date(target_date)
        if cash:
            self.selected_cash_id = int(cash["Id"])
            self.paid_debts_var.set(format_number(float(cash.get("DettesPayeesAujourdHui", 0) or 0)))
            self.paid_debts_details_text.delete("1.0", "end")
            self.paid_debts_details_text.insert("1.0", str(cash.get("DettesPayeesDetails", "")))
            self.expenses_var.set(format_number(float(cash["MontantTotalDepenses"])))
            self.expenses_text.delete("1.0", "end")
            self.expenses_text.insert("1.0", str(cash["DepensesEffectuees"]))
        else:
            self.selected_cash_id = 0
            self.paid_debts_var.set("0")
            self.paid_debts_details_text.delete("1.0", "end")
            self.expenses_var.set("0")
            self.expenses_text.delete("1.0", "end")

        self.calculate_balance()

    def calculate_balance(self) -> None:
        try:
            paid_debts = parse_optional_float(self.paid_debts_var.get())
        except ValueError:
            paid_debts = 0
        try:
            expenses = parse_optional_float(self.expenses_var.get())
        except ValueError:
            expenses = 0
        self.remaining_accumulated_debts = max(self.accumulated_debts_before_payment - paid_debts, 0.0)
        if self.accumulated_debts_before_payment <= 0:
            debt_status = "Aucune dette accumulée"
        elif self.remaining_accumulated_debts <= 0:
            debt_status = "Payées"
        elif paid_debts > 0:
            debt_status = "Partiellement payées"
        else:
            debt_status = "En attente"
        self.total_entries_today = self.received_today + paid_debts
        balance = self.total_entries_today - expenses
        self.remaining_accumulated_debts_var.set(format_fc(self.remaining_accumulated_debts))
        self.accumulated_debts_status_var.set(debt_status)
        self.total_entries_var.set(format_fc(self.total_entries_today))
        self.balance_var.set(format_fc(balance))
        self.refresh_paid_debts_details_message(paid_debts)
        self.update_summary()

    def update_summary(self, row_count: int | None = None) -> None:
        if row_count is None:
            row_count = len(self.table.tree.get_children())
        total_global = DatabaseHelper.get_total_cash()
        try:
            target_date = self.date_field.get_date()
        except ValueError:
            target_date = date.today()
        try:
            paid_debts = parse_optional_float(self.paid_debts_var.get())
        except ValueError:
            paid_debts = 0
        try:
            expenses = parse_optional_float(self.expenses_var.get())
        except ValueError:
            expenses = 0
        entries_today = self.received_today + paid_debts
        balance = entries_today - expenses

        if self.show_all_dates:
            summary = DatabaseHelper.get_global_orders_summary()
            paid_debts_total = sum(float(row.get("DettesPayeesAujourdHui", 0) or 0) for row in self.table.rows_by_item.values())
            entries_total = sum(float(row.get("TotalEntrees", 0) or 0) for row in self.table.rows_by_item.values())
            accumulated_remaining = sum(float(row.get("DettesAccumuleesRestantes", 0) or 0) for row in self.table.rows_by_item.values())
            text = (
                "Affichage : toutes les dates\n"
                f"Fiches caisse : {row_count}\n"
                f"Total bacs : {int(summary.get('TotalBacs', 0))} | "
                f"Attendu : {format_fc(float(summary.get('MontantAttendu', 0)))} | "
                f"Reçu : {format_fc(float(summary.get('MontantRecu', 0)))}\n"
                f"Dettes payées : {format_fc(paid_debts_total)} | Entrées : {format_fc(entries_total)}\n"
                f"Dettes du jour : {format_fc(float(summary.get('TotalDettes', 0)))} | "
                f"Restant accumulé : {format_fc(accumulated_remaining)} | "
                f"Solde global : {format_fc(total_global)}"
            )
        else:
            text = (
                f"Jour : {target_date.strftime('%d/%m/%Y')} | Bacs : {int(self.trays_today)}\n"
                f"Fiches caisse : {row_count} | Reçu : {format_fc(self.received_today)} | "
                f"Dettes payées : {format_fc(paid_debts)}\n"
                f"Entrées : {format_fc(entries_today)} | "
                f"Solde du jour : {format_fc(balance)}\n"
                f"Dettes du jour : {format_fc(self.debts_today)} | "
                f"Dettes accumulées restantes : {format_fc(self.remaining_accumulated_debts)} | "
                f"Total global : {format_fc(total_global)}"
            )
        self.summary_var.set(text)

    def refresh_data(self) -> None:
        self.load_day_summary()
        try:
            target_date = self.date_field.get_date()
        except ValueError:
            target_date = date.today()
        rows = DatabaseHelper.list_cash_days() if self.show_all_dates else DatabaseHelper.list_cash_days_by_date(target_date)
        self.table.set_data(
            rows,
            columns=[
                "Id",
                "DateCaisse",
                "NombreTotalBacs",
                "MontantAttendu",
                "MontantRecu",
                "TotalDettes",
                "TotalDettesAccumulees",
                "DettesPayeesAujourdHui",
                "DettesAccumuleesRestantes",
                "StatutDettesAccumulees",
                "TotalEntrees",
                "MontantTotalDepenses",
                "Solde",
                "DepensesEffectuees",
                "DettesPayeesDetails",
            ],
            headings={
                "DateCaisse": "Date",
                "NombreTotalBacs": "Bacs",
                "MontantAttendu": "Attendu",
                "MontantRecu": "Reçu",
                "TotalDettes": "Dettes du jour",
                "TotalDettesAccumulees": "Dettes accumulées",
                "DettesPayeesAujourdHui": "Dettes payées",
                "DettesAccumuleesRestantes": "Dettes restantes",
                "StatutDettesAccumulees": "Statut dettes",
                "TotalEntrees": "Entrées",
                "MontantTotalDepenses": "Dépenses",
                "DepensesEffectuees": "Détails des dépenses",
                "DettesPayeesDetails": "Ceux qui ont payé",
            },
            hidden_columns=["Id"],
            formatters={
                "NombreTotalBacs": lambda value: f"{int(value)}",
                "MontantAttendu": lambda value: format_fc(float(value)),
                "MontantRecu": lambda value: format_fc(float(value)),
                "TotalDettes": lambda value: format_fc(float(value)),
                "TotalDettesAccumulees": lambda value: format_fc(float(value)),
                "DettesPayeesAujourdHui": lambda value: format_fc(float(value)),
                "DettesAccumuleesRestantes": lambda value: format_fc(float(value)),
                "TotalEntrees": lambda value: format_fc(float(value)),
                "MontantTotalDepenses": lambda value: format_fc(float(value)),
                "Solde": lambda value: format_fc(float(value)),
                "DepensesEffectuees": compact_multiline_text,
                "DettesPayeesDetails": compact_multiline_text,
            },
        )
        self.table.tree.column("DepensesEffectuees", width=260, stretch=True)
        self.table.tree.column("DettesPayeesDetails", width=280, stretch=True)
        self.table.tree.column("TotalDettesAccumulees", width=150, stretch=True)
        self.table.tree.column("DettesAccumuleesRestantes", width=150, stretch=True)
        self.table.tree.column("StatutDettesAccumulees", width=160, stretch=True)
        self.update_summary(len(rows))
        self.refresh_day_lock_state()

    def refresh_live_view(self) -> None:
        self.refresh_data()

    def show_all(self) -> None:
        self.show_all_dates = True
        self.refresh_data()

    def save_cash(self) -> None:
        if not self.ensure_module_writable("Caisse"):
            return
        try:
            target_date = self.date_field.get_date()
            paid_debts = parse_optional_float(self.paid_debts_var.get())
            expenses = parse_optional_float(self.expenses_var.get())
        except Exception as exc:
            messagebox.showwarning("Caisse", str(exc))
            return

        details = self.expenses_text.get("1.0", "end").strip()
        paid_debts_details = self.paid_debts_details_text.get("1.0", "end").strip()
        if paid_debts_details == NO_DEBT_PAYMENT_MESSAGE:
            paid_debts_details = ""
        if expenses > 0 and not details:
            messagebox.showwarning(
                "Caisse",
                "Veuillez décrire les dépenses effectuées avant d'enregistrer la caisse.",
            )
            return
        if paid_debts > 0 and not paid_debts_details:
            messagebox.showwarning(
                "Caisse",
                "Veuillez renseigner la liste des personnes qui ont payé leurs dettes avant d'enregistrer la caisse.",
            )
            return
        if paid_debts > self.accumulated_debts_before_payment:
            messagebox.showwarning(
                "Caisse",
                (
                    "Le montant des dettes payées aujourd'hui dépasse les dettes accumulées des jours précédents.\n\n"
                    f"Dettes accumulées disponibles : {format_fc(self.accumulated_debts_before_payment)}"
                ),
            )
            return

        try:
            DatabaseHelper.save_cash_day(target_date, expenses, details, paid_debts, paid_debts_details)
            log_user_action(
                self,
                "Caisse",
                "Fiche de caisse enregistrée",
                f"{target_date.strftime('%d/%m/%Y')} | Dépenses {format_fc(expenses)} | Dettes payées {format_fc(paid_debts)}",
            )
            messagebox.showinfo("Caisse", "La fiche de caisse a été enregistrée avec succès.")
            self.refresh_data()
        except ValueError as exc:
            messagebox.showwarning("Caisse", str(exc))
        except Exception as exc:
            messagebox.showerror("Caisse", str(exc))

    def load_cash_for_edit(self) -> None:
        row = self.table.selected_row()
        if row is None:
            messagebox.showwarning("Caisse", "Veuillez sélectionner une fiche dans la grille.")
            return
        self.selected_cash_id = int(row["Id"])
        self.date_field.set_date(str(row["DateCaisse"]))
        self.expenses_var.set(format_number(float(row["MontantTotalDepenses"])))
        self.paid_debts_var.set(format_number(float(row.get("DettesPayeesAujourdHui", 0) or 0)))
        self.paid_debts_details_text.delete("1.0", "end")
        self.paid_debts_details_text.insert("1.0", str(row.get("DettesPayeesDetails", "")))
        self.expenses_text.delete("1.0", "end")
        self.expenses_text.insert("1.0", str(row["DepensesEffectuees"]))
        self.calculate_balance()
        self.refresh_day_lock_state()
        messagebox.showinfo("Caisse", "La fiche de caisse a été chargée.")

    def delete_cash(self) -> None:
        if not self.ensure_module_writable("Caisse"):
            return
        row = self.table.selected_row()
        if row is None:
            messagebox.showwarning("Caisse", "Veuillez sélectionner une fiche dans la grille.")
            return
        if not messagebox.askyesno("Confirmation", "Voulez-vous vraiment supprimer cette fiche de caisse ?"):
            return
        try:
            deleted = DatabaseHelper.delete_cash_day(int(row["Id"]))
            if deleted:
                log_user_action(
                    self,
                    "Caisse",
                    "Fiche de caisse supprimée",
                    f"Id {row['Id']} | Date {row['DateCaisse']}",
                )
                messagebox.showinfo("Caisse", "La fiche de caisse a été supprimée avec succès.")
                self.reset_form()
                self.refresh_data()
            else:
                messagebox.showwarning("Caisse", "Aucune fiche de caisse n'a été supprimée.")
        except ValueError as exc:
            messagebox.showwarning("Caisse", str(exc))
        except Exception as exc:
            messagebox.showerror("Caisse", str(exc))


class CommissionsWindow(BaseModuleWindow):
    def __init__(self, parent: DashboardWindow) -> None:
        super().__init__(parent, "Gestion des commissions", "1260x840")
        self.selected_commission_id = 0
        self.edit_mode = False
        self.show_all_dates = False
        self.current_status = ""
        self.current_trays = 0
        self.current_paid = 0.0
        self.current_commission = 0.0
        self.current_debt = 0.0
        self.current_net = 0.0
        self.all_rows: list[dict[str, Any]] = []
        self.build_ui()
        self.summary_var.set("Chargement des commissions...")
        self.after_idle(self.finish_initial_load)

    def finish_initial_load(self) -> None:
        self.reset_form()
        self.refresh_commissions()

    def build_ui(self) -> None:
        container = self.body

        content = ttk.Frame(container)
        content.pack(fill="both", expand=True)
        self.create_day_lock_notice(container, "les commissions", before=content)

        form = ttk.LabelFrame(content, text="Commission automatique", style="Card.TLabelframe")
        form.pack(side="left", fill="y", padx=(0, 12))
        ttk.Label(
            form,
            text=(
                "Les commissions sont calculées automatiquement à partir des commandes. "
                "Pour corriger une commission, modifiez la commande correspondante."
            ),
            wraplength=360,
            justify="left",
            foreground=MUTED_TEXT_COLOR,
        ).grid(row=0, column=0, columnspan=2, sticky="ew", pady=(0, 10))

        ttk.Label(form, text="Date").grid(row=1, column=0, sticky="w", pady=6)
        self.date_field = DateField(form)
        self.date_field.grid(row=1, column=1, sticky="ew", pady=6)
        self.date_field.bind_change(self._on_date_change)

        ttk.Label(form, text="Nom").grid(row=2, column=0, sticky="w", pady=6)
        self.name_var = tk.StringVar()
        self.name_combo = ttk.Combobox(form, textvariable=self.name_var, state="readonly", width=28)
        self.name_combo.grid(row=2, column=1, sticky="ew", pady=6)
        self.name_combo.bind("<<ComboboxSelected>>", lambda _event: self.load_synthesis())

        self.status_value = tk.StringVar()
        self.trays_value = tk.StringVar(value="0")
        self.amount_paid_value = tk.StringVar(value=format_fc(0))
        self.commissions_value = tk.StringVar(value=format_fc(0))
        self.debts_value = tk.StringVar(value=format_fc(0))
        self.net_value = tk.StringVar(value=format_fc(0))

        self._make_label_value(form, "Statut", self.status_value, 3, "#7a0000")
        self._make_label_value(form, "Nombre de bacs", self.trays_value, 4, PRIMARY_DARK_COLOR)
        self._make_label_value(form, "Montant payé", self.amount_paid_value, 5, SUCCESS_COLOR)
        self._make_label_value(form, "Commissions", self.commissions_value, 6, "#7a0000")
        self._make_label_value(form, "Dettes", self.debts_value, 7, DANGER_COLOR)
        self.net_label = ttk.Label(form, textvariable=self.net_value, foreground=PRIMARY_DARK_COLOR)
        ttk.Label(form, text="Net à payer").grid(row=8, column=0, sticky="w", pady=6)
        self.net_label.grid(row=8, column=1, sticky="w", pady=6)

        ttk.Label(form, text="Filtre de statut").grid(row=9, column=0, sticky="w", pady=6)
        self.filter_var = tk.StringVar(value=COMMISSION_FILTERS[0])
        self.filter_combo = ttk.Combobox(
            form,
            textvariable=self.filter_var,
            values=COMMISSION_FILTERS,
            state="readonly",
            width=28,
        )
        self.filter_combo.grid(row=9, column=1, sticky="ew", pady=6)
        self.filter_combo.bind("<<ComboboxSelected>>", lambda _event: self.apply_filter())

        actions = ttk.Frame(form)
        actions.grid(row=10, column=0, columnspan=2, pady=(14, 0))
        ttk.Button(actions, text="Actualiser", command=self.refresh_commissions).grid(row=0, column=0, padx=4, pady=4)
        ttk.Button(actions, text="Tout afficher", command=self.show_all).grid(row=0, column=1, padx=4, pady=4)
        ttk.Button(actions, text="Fermer", command=self.close_window).grid(row=0, column=2, padx=4, pady=4)

        self.summary_var = tk.StringVar()
        ttk.Label(form, textvariable=self.summary_var, wraplength=400, justify="left").grid(
            row=11, column=0, columnspan=2, sticky="ew", pady=(14, 0)
        )

        table_frame = ttk.LabelFrame(content, text="Historique des commissions", style="Card.TLabelframe")
        table_frame.pack(side="left", fill="both", expand=True)
        self.table = DataTable(table_frame, height=22)
        self.table.pack(fill="both", expand=True)

        form.columnconfigure(1, weight=1)
        self.configure_day_lock_controls(self.date_field, [])

    def _make_label_value(
        self,
        parent: ttk.LabelFrame,
        label: str,
        variable: tk.StringVar,
        row: int,
        foreground: str,
    ) -> None:
        ttk.Label(parent, text=label).grid(row=row, column=0, sticky="w", pady=6)
        ttk.Label(parent, textvariable=variable, foreground=foreground).grid(row=row, column=1, sticky="w", pady=6)

    def _on_date_change(self) -> None:
        self.show_all_dates = False
        self.load_names()
        self.refresh_commissions()

    def reset_synthesis(self) -> None:
        self.current_status = ""
        self.current_trays = 0
        self.current_paid = 0.0
        self.current_commission = 0.0
        self.current_debt = 0.0
        self.current_net = 0.0
        self.status_value.set("")
        self.trays_value.set("0")
        self.amount_paid_value.set(format_fc(0))
        self.commissions_value.set(format_fc(0))
        self.debts_value.set(format_fc(0))
        self.net_value.set(format_fc(0))
        self.net_label.configure(foreground=PRIMARY_DARK_COLOR)

    def reset_form(self) -> None:
        self.selected_commission_id = 0
        self.edit_mode = False
        self.show_all_dates = False
        self.date_field.set_date(today_iso())
        self.filter_var.set(COMMISSION_FILTERS[0])
        self.reset_synthesis()
        self.load_names()
        self.refresh_day_lock_state()

    def load_names(self) -> None:
        try:
            target_date = self.date_field.get_date()
        except ValueError:
            target_date = date.today()
        names = DatabaseHelper.list_clients_from_orders_by_date(target_date)
        self.name_combo["values"] = names
        if names:
            if self.name_var.get() in names:
                self.load_synthesis()
            else:
                self.name_var.set(names[0])
                self.load_synthesis()
        else:
            self.name_var.set("")
            self.reset_synthesis()

    def load_synthesis(self) -> None:
        self.reset_synthesis()
        name = self.name_var.get().strip()
        if not name:
            return
        try:
            target_date = self.date_field.get_date()
        except ValueError:
            return
        summary = DatabaseHelper.get_commission_synthesis_from_orders(target_date, name)
        if not summary:
            return

        self.current_status = normalize_status_form_label(summary.get("Statut", ""))
        self.current_trays = int(summary.get("NombreBacs", 0) or 0)
        self.current_paid = float(summary.get("MontantPaye", 0) or 0)
        self.current_commission = float(summary.get("Commissions", 0) or 0)
        self.current_debt = float(summary.get("Dettes", 0) or 0)
        self.current_net = float(summary.get("NetAPayer", 0) or 0)

        self.status_value.set(self.current_status)
        self.trays_value.set(str(self.current_trays))
        self.amount_paid_value.set(format_fc(self.current_paid))
        self.commissions_value.set(format_fc(self.current_commission))
        self.debts_value.set(format_fc(self.current_debt))
        self.net_value.set(format_fc(self.current_net))
        self.net_label.configure(foreground=DANGER_COLOR if self.current_net < 0 else PRIMARY_DARK_COLOR)
        self.refresh_day_lock_state()

    def refresh_commissions(self) -> None:
        try:
            target_date = self.date_field.get_date()
        except ValueError:
            target_date = date.today()
        self.all_rows = (
            DatabaseHelper.list_commissions()
            if self.show_all_dates
            else DatabaseHelper.list_commissions_by_date(target_date)
        )
        self.apply_filter()
        self.refresh_day_lock_state()

    def refresh_live_view(self) -> None:
        self.refresh_commissions()

    def apply_filter(self) -> None:
        filter_value = self.filter_var.get()
        rows = self.all_rows
        if filter_value == "Maman":
            rows = [row for row in rows if normalize_status_label(row["Statut"]) == "Maman"]
        elif filter_value == DEPOSITARY_STATUS:
            rows = [row for row in rows if is_depositary_status(row["Statut"])]
        elif filter_value == "Vente cash":
            rows = [row for row in rows if normalize_status_label(row["Statut"]) == "Vente cash"]

        self.table.set_data(
            rows,
            columns=[
                "Id",
                "DateCommission",
                "Nom",
                "Statut",
                "NombreBacs",
                "MontantPaye",
                "Commissions",
                "Dettes",
                "NetAPayer",
            ],
            headings={
                "DateCommission": "Date",
                "NombreBacs": "Bacs",
                "MontantPaye": "Montant payé",
                "Commissions": "Commissions",
                "Dettes": "Dettes",
                "NetAPayer": "Net à payer",
            },
            hidden_columns=["Id"],
            formatters={
                "Statut": normalize_status_label,
                "NombreBacs": lambda value: f"{int(value)}",
                "MontantPaye": lambda value: format_fc(float(value)),
                "Commissions": lambda value: format_fc(float(value)),
                "Dettes": lambda value: format_fc(float(value)),
                "NetAPayer": lambda value: format_fc(float(value)),
            },
        )
        self.update_summary(rows)

    def update_summary(self, rows: list[dict[str, Any]]) -> None:
        total_commissions = sum(float(row["Commissions"]) for row in rows)
        total_net = sum(float(row["NetAPayer"]) for row in rows)
        if self.show_all_dates:
            prefix = "Affichage : toutes les dates"
        else:
            try:
                target_date = self.date_field.get_date()
            except ValueError:
                target_date = date.today()
            prefix = f"Date : {target_date.strftime('%d/%m/%Y')}"
        self.summary_var.set(
            f"{prefix}\n"
            f"Filtre : {self.filter_var.get()}\n"
            f"Nombre de commissions : {len(rows)}\n"
            f"Total commissions : {format_fc(total_commissions)}\n"
            f"Total net à payer : {format_fc(total_net)}"
        )

    def show_all(self) -> None:
        self.show_all_dates = True
        self.refresh_commissions()

    def validate_commission(self) -> tuple[date, str] | None:
        try:
            target_date = self.date_field.get_date()
        except Exception as exc:
            messagebox.showwarning("Commissions", str(exc))
            return None
        name = self.name_var.get().strip()
        if not name:
            messagebox.showwarning("Commissions", "Veuillez choisir un nom provenant des commandes.")
            return None
        if not self.current_status:
            messagebox.showwarning(
                "Commissions",
                "Aucune synthèse de commande n'a été trouvée pour ce nom et cette date.",
            )
            return None
        if self.current_commission <= 0:
            messagebox.showwarning(
                "Commissions",
                "Ce client n'a pas de commissions. Il ne peut pas être enregistré.",
            )
            return None
        return target_date, name

    def handle_duplicate_commission(self, target_date: date, name: str) -> bool:
        if self.edit_mode:
            existing_id = DatabaseHelper.find_existing_commission(
                target_date, name, self.selected_commission_id
            )
            if existing_id > 0:
                messagebox.showwarning(
                    "Commissions",
                    "Une autre commission existe déjà pour ce nom à cette date.",
                )
                return False
            return True

        existing_id = DatabaseHelper.find_existing_commission(target_date, name)
        if existing_id == 0:
            return True

        if not messagebox.askyesno(
            "Commission déjà existante",
            "Une commission existe déjà pour ce nom à la date sélectionnée.\n"
            "Voulez-vous la mettre à jour au lieu d'en créer une nouvelle ?",
        ):
            return False

        updated = DatabaseHelper.update_commission(
            existing_id,
            target_date,
            name,
            self.current_status,
            self.current_trays,
            self.current_paid,
            self.current_commission,
            self.current_debt,
            self.current_net,
        )
        if updated:
            log_user_action(
                self,
                "Commissions",
                "Commission dupliquée mise à jour",
                f"{name} | {target_date.strftime('%d/%m/%Y')} | Net {format_fc(self.current_net)}",
            )
            messagebox.showinfo("Commissions", "La commission existante a été modifiée avec succès.")
            self.reset_form()
            self.refresh_commissions()
        else:
            messagebox.showwarning("Commissions", "La commission existante n'a pas pu être modifiée.")
        return False

    def save_commission(self) -> None:
        if not self.ensure_module_writable("Commissions"):
            return
        validated = self.validate_commission()
        if validated is None:
            return
        target_date, name = validated

        try:
            if not self.handle_duplicate_commission(target_date, name):
                return
            if self.edit_mode:
                updated = DatabaseHelper.update_commission(
                    self.selected_commission_id,
                    target_date,
                    name,
                    self.current_status,
                    self.current_trays,
                    self.current_paid,
                    self.current_commission,
                    self.current_debt,
                    self.current_net,
                )
                if updated:
                    log_user_action(
                        self,
                        "Commissions",
                        "Commission modifiée",
                        f"{name} | {target_date.strftime('%d/%m/%Y')} | Net {format_fc(self.current_net)}",
                    )
                    messagebox.showinfo("Commissions", "La commission a été modifiée avec succès.")
                else:
                    messagebox.showwarning("Commissions", "Aucune commission n'a été modifiée.")
            else:
                DatabaseHelper.add_commission(
                    target_date,
                    name,
                    self.current_status,
                    self.current_trays,
                    self.current_paid,
                    self.current_commission,
                    self.current_debt,
                    self.current_net,
                )
                log_user_action(
                    self,
                    "Commissions",
                    "Commission ajoutée",
                    f"{name} | {target_date.strftime('%d/%m/%Y')} | Net {format_fc(self.current_net)}",
                )
                messagebox.showinfo("Commissions", "La commission a été enregistrée avec succès.")
            self.reset_form()
            self.refresh_commissions()
        except ValueError as exc:
            messagebox.showwarning("Commissions", str(exc))
        except Exception as exc:
            messagebox.showerror("Commissions", str(exc))

    def load_commission_for_edit(self) -> None:
        row = self.table.selected_row()
        if row is None:
            messagebox.showwarning("Commissions", "Veuillez sélectionner une commission dans la grille.")
            return
        self.selected_commission_id = int(row["Id"])
        self.edit_mode = True
        self.date_field.set_date(str(row["DateCommission"]))
        name = str(row["Nom"])
        current_names = list(self.name_combo["values"])
        if name not in current_names:
            current_names.append(name)
            self.name_combo["values"] = current_names
        self.name_var.set(name)
        self.current_status = normalize_status_form_label(row["Statut"])
        self.current_trays = int(row["NombreBacs"])
        self.current_paid = float(row["MontantPaye"])
        self.current_commission = float(row["Commissions"])
        self.current_debt = float(row["Dettes"])
        self.current_net = float(row["NetAPayer"])
        self.status_value.set(self.current_status)
        self.trays_value.set(str(self.current_trays))
        self.amount_paid_value.set(format_fc(self.current_paid))
        self.commissions_value.set(format_fc(self.current_commission))
        self.debts_value.set(format_fc(self.current_debt))
        self.net_value.set(format_fc(self.current_net))
        self.net_label.configure(foreground=DANGER_COLOR if self.current_net < 0 else PRIMARY_DARK_COLOR)
        self.refresh_day_lock_state()
        messagebox.showinfo("Commissions", "La commission a été chargée. Modifiez-la puis enregistrez.")

    def delete_commission(self) -> None:
        if not self.ensure_module_writable("Commissions"):
            return
        row = self.table.selected_row()
        if row is None:
            messagebox.showwarning("Commissions", "Veuillez sélectionner une commission dans la grille.")
            return
        if not messagebox.askyesno("Confirmation", "Voulez-vous vraiment supprimer cette commission ?"):
            return
        try:
            deleted = DatabaseHelper.delete_commission(int(row["Id"]))
            if deleted:
                log_user_action(
                    self,
                    "Commissions",
                    "Commission supprimée",
                    f"Id {row['Id']} | Nom {row['Nom']} | Date {row['DateCommission']}",
                )
                messagebox.showinfo("Commissions", "La commission a été supprimée avec succès.")
                self.reset_form()
                self.refresh_commissions()
            else:
                messagebox.showwarning("Commissions", "Aucune commission n'a été supprimée.")
        except ValueError as exc:
            messagebox.showwarning("Commissions", str(exc))
        except Exception as exc:
            messagebox.showerror("Commissions", str(exc))
