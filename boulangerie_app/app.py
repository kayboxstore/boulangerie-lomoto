from __future__ import annotations

import os
import sys
import threading
from pathlib import Path
from queue import Empty, Queue
import tkinter as tk
import webbrowser
from datetime import date, datetime
from tkinter import filedialog, messagebox, ttk
from tkinter.scrolledtext import ScrolledText
from typing import Any, Callable

from PIL import Image, ImageTk

from .connected_mode import (
    ConnectionSettings,
    DiscoveredServerInfo,
    REMOTE_DEFAULT_PORT,
    REMOTE_DISCOVERY_TIMEOUT_SECONDS,
    REMOTE_REFRESH_INTERVAL_MS,
    RemoteDatabaseClient,
    discover_remote_servers,
)
from .connected_server import (
    get_embedded_server_status,
    is_embedded_server_running,
    start_embedded_server,
    stop_embedded_server,
)
from .database import AuthenticatedUser, DatabaseHelper
from .excel_reports import create_daily_excel_report
from .reports import (
    ReportGenerationError,
    create_daily_pdf_report,
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
from .version import APP_NAME, APP_VERSION

UI_FONT_FAMILY = "Poppins"
UI_FONT_SIZE = 11
UI_FONT = (UI_FONT_FAMILY, UI_FONT_SIZE)
APP_BACKGROUND = "#dfeaf4"
MODULE_BACKGROUND = "#eef3f8"
FORM_LOGO_SIZE = 68
DASHBOARD_LOGO_SIZE = 80
SETTINGS_LOGO_SIZE = 70
STOCK_DIALOG_LOGO_SIZE = 60

_BRAND_IMAGE_CACHE: dict[tuple[str, int, int], ImageTk.PhotoImage] = {}


ROLES = [
    "Admin",
    "Caissier",
    "Gestionnaire de stock",
    "Gestionnaire des commandes",
]


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


def run_app() -> None:
    if os.name == "nt" and not is_running_as_administrator():
        if relaunch_current_process_as_administrator():
            return
        return

    DatabaseHelper.initialize_database()
    post_update_notice = UpdateChecker.consume_post_update_notice()
    root = tk.Tk()
    root.title(f"{APP_NAME} - Connexion - v{APP_VERSION}")
    root.geometry("580x380")
    root.minsize(580, 380)
    root.configure(bg=APP_BACKGROUND)
    apply_window_icon(root)
    configure_styles()
    root.resizable(True, True)
    LoginWindow(root, post_update_notice)
    center_window(root)
    root.mainloop()


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
    style.configure("Card.TLabelframe", padding=8)
    style.configure("Card.TLabelframe.Label", font=(UI_FONT_FAMILY, UI_FONT_SIZE, "bold"))
    style.configure("Primary.TButton", padding=(12, 8))


def today_iso() -> str:
    return date.today().strftime("%Y-%m-%d")


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


def center_window(window: tk.Misc) -> None:
    window.update_idletasks()
    width, height = _measure_window_size(window)

    requested_width, requested_height = _measure_requested_content_size(window)
    required_width = requested_width + 24
    required_height = requested_height + 36
    max_width = max(int(window.winfo_screenwidth() * 0.96), 320)
    max_height = max(int(window.winfo_screenheight() * 0.92), 240)

    width = min(max(width, required_width), max_width)
    height = min(max(height, required_height), max_height)

    x = max((window.winfo_screenwidth() - width) // 2, 0)
    y = max((window.winfo_screenheight() - height) // 2, 0)
    window.geometry(f"{width}x{height}+{x}+{y}")
    if hasattr(window, "minsize"):
        window.minsize(width, height)


def maximize_window(window: tk.Misc, min_width: int = 760, min_height: int = 520) -> None:
    window.update_idletasks()
    requested_width, requested_height = _measure_requested_content_size(window)
    safe_min_width = max(min_width, min(requested_width + 24, window.winfo_screenwidth()))
    safe_min_height = max(min_height, min(requested_height + 36, window.winfo_screenheight()))
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

    window.geometry(f"{window.winfo_screenwidth()}x{window.winfo_screenheight()}+0+0")


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


class DateField(ttk.Frame):
    def __init__(self, parent: tk.Misc, initial: str | None = None) -> None:
        super().__init__(parent)
        self.var = tk.StringVar(value=initial or today_iso())
        self.entry = ttk.Entry(self, textvariable=self.var, width=14)
        self.entry.grid(row=0, column=0, sticky="ew")
        self.button = ttk.Button(self, text="Aujourd'hui", command=self.set_today)
        self.button.grid(row=0, column=1, padx=(6, 0))
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

    def get_date(self) -> date:
        return parse_date(self.var.get())

    def set_date(self, value: date | str) -> None:
        if isinstance(value, date):
            self.var.set(value.strftime("%Y-%m-%d"))
        else:
            self.var.set(value)

    def get(self) -> str:
        return self.var.get()


class DataTable(ttk.Frame):
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
        self.tree.bind("<MouseWheel>", self._on_mousewheel, add="+")
        self.tree.bind("<Shift-MouseWheel>", self._on_shift_mousewheel, add="+")

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


class ScrollableContent(ttk.Frame):
    _mousewheel_bindings_ready = False

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
        setattr(self, "_scrollable_owner", self)
        setattr(self.canvas, "_scrollable_owner", self)
        setattr(self.content, "_scrollable_owner", self)

        self.content.bind("<Configure>", self._on_content_configure)
        self.canvas.bind("<Configure>", self._on_canvas_configure)
        self._install_global_mousewheel_bindings()
        self.after_idle(self._refresh_scroll_region)

    def _install_global_mousewheel_bindings(self) -> None:
        if ScrollableContent._mousewheel_bindings_ready:
            return
        root = self.winfo_toplevel()
        root.bind_all("<MouseWheel>", ScrollableContent._dispatch_mousewheel, add="+")
        root.bind_all("<Shift-MouseWheel>", ScrollableContent._dispatch_shift_mousewheel, add="+")
        ScrollableContent._mousewheel_bindings_ready = True

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

        ttk.Label(card, text=f"Version {APP_VERSION}", foreground="#5a6570").grid(
            row=2, column=0, columnspan=2, pady=(0, 12)
        )

        self.connection_status_var = tk.StringVar(value=DatabaseHelper.get_connection_status_text())
        ttk.Label(
            card,
            textvariable=self.connection_status_var,
            foreground="#2f5d3a",
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

        ttk.Label(card, text="Identifiant").grid(row=row_index, column=0, sticky="w", pady=6)
        self.user_var = tk.StringVar()
        user_entry = ttk.Entry(card, textvariable=self.user_var, width=30)
        user_entry.grid(row=row_index, column=1, sticky="ew", pady=6)
        row_index += 1

        ttk.Label(card, text="Mot de passe").grid(row=row_index, column=0, sticky="w", pady=6)
        self.password_var = tk.StringVar()
        self.password_entry = ttk.Entry(card, textvariable=self.password_var, width=30, show="*")
        self.password_entry.grid(row=row_index, column=1, sticky="ew", pady=6)
        row_index += 1

        button_row = ttk.Frame(card)
        button_row.grid(row=row_index, column=0, columnspan=2, pady=(14, 0))
        ttk.Button(button_row, text="Connexion", style="Primary.TButton", command=self.login).grid(
            row=0, column=0, padx=6
        )
        ttk.Button(button_row, text="Quitter", command=self.on_quit).grid(row=0, column=1, padx=6)
        ttk.Button(button_row, text="Paramètres réseau", command=self.open_connection_settings).grid(
            row=0, column=2, padx=6
        )
        ttk.Button(button_row, text="Détecter le serveur", command=self.detect_server_now).grid(
            row=0, column=3, padx=6
        )
        card.columnconfigure(1, weight=1)
        user_entry.focus()
        user_entry.bind("<Return>", lambda _event: self.password_entry.focus())
        self.password_entry.bind("<Return>", lambda _event: self.login())

    def refresh_connection_status(self) -> None:
        self.connection_status_var.set(DatabaseHelper.get_connection_status_text())

    def open_connection_settings(self) -> None:
        dialog = ConnectionSettingsDialog(self)
        self.wait_window(dialog)
        self.refresh_connection_status()

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
        settings = DatabaseHelper.get_connection_settings()
        if settings.is_remote():
            return settings
        return None

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
        local_server_settings = self._get_local_server_settings(start_service_if_needed=True)
        if local_server_settings is not None:
            self._apply_session_connection_settings(local_server_settings)
            self.connection_status_var.set(
                f"Serveur principal local prêt : {local_server_settings.normalized_url()}"
            )
            return

        saved_remote_settings = self._get_saved_remote_settings()
        if saved_remote_settings is not None and self._is_reachable_remote_settings(saved_remote_settings):
            self._apply_session_connection_settings(saved_remote_settings)
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
            self.refresh_connection_status()
            if not auto_apply:
                messagebox.showwarning("Recherche automatique", str(item[1][0]))
            return

        servers = item[1]
        if not isinstance(servers, list):
            servers = []
        self.discovered_servers = servers

        if not servers:
            self._apply_session_connection_settings(ConnectionSettings())
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
        plan: list[ConnectionSettings] = []
        seen: set[tuple[str, str, str]] = set()

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
        add_setting(self._discover_remote_settings(use_cached=True))
        add_setting(self._get_saved_remote_settings())
        add_setting(ConnectionSettings())
        return plan

    def _try_login_with_settings(
        self,
        settings: ConnectionSettings,
        identifiant: str,
        mot_de_passe: str,
    ) -> tuple[AuthenticatedUser | None, str | None]:
        self._apply_session_connection_settings(settings)
        try:
            user = DatabaseHelper.find_user_for_login(identifiant, mot_de_passe)
        except Exception as exc:
            return None, str(exc)
        return user, None

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

        for settings in self._build_login_connection_plan():
            candidate_user, error_message = self._try_login_with_settings(settings, identifiant, mot_de_passe)
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
                messagebox.showerror("Connexion", remote_errors[0])
            else:
                messagebox.showwarning("Connexion", "Identifiants incorrects.")
            self.password_var.set("")
            self.password_entry.focus()
            return

        self.user_var.set("")
        self.password_var.set("")
        self.root.withdraw()
        dashboard = DashboardWindow(self.root, user, self.show_login, self.post_update_notice)
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
        self.geometry("900x760")
        self.minsize(820, 700)
        self.configure(bg=MODULE_BACKGROUND)
        self.resizable(True, True)
        apply_window_icon(self)
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
        maximize_window(self, 820, 700)

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
            foreground="#2f5d3a",
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
                "Mode recommande pour le poste serveur : le service Windows demarre avec Windows "
                "et reste actif meme si l'application est fermee."
            ),
            wraplength=620,
            justify="center",
        ).pack(fill="x", pady=(0, 10))
        ttk.Label(
            service_frame,
            textvariable=self.windows_service_status_var,
            foreground="#2f5d3a",
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
            fg="#8b0000",
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

        if not service_status.installed:
            self.windows_service_status_var.set(
                f"{service_status.message}\n{data_line}\nPort : {host_settings.normalized_port()}\n{token_line}"
            )
            return

        details = [service_status.message]
        if addresses:
            details.append(addresses)
        details.append(data_line)
        details.append(token_line)
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


class DashboardWindow(tk.Toplevel):
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
        self.refresh_summary()
        maximize_window(self, 980, 640)
        self.bind("<FocusIn>", lambda _event: self.refresh_summary())
        self.after(1000, self.start_weekly_update_check)
        if self.is_live_sync_enabled():
            self.schedule_live_refresh()

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
            text=f"Version installee : {APP_VERSION}",
            foreground="#5a6570",
        ).pack(anchor="center", pady=(0, 8))

        ttk.Label(
            container,
            text=DatabaseHelper.get_connection_status_text(),
            foreground="#2f5d3a",
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
            ("Commandes", self.open_orders),
            ("Commissions", self.open_commissions),
        ]
        for index, (label, callback) in enumerate(buttons):
            button = ttk.Button(grid, text=label, command=callback)
            button.grid(row=index // 2, column=index % 2, padx=8, pady=8, sticky="ew")
            setattr(self, f"{label.lower()}_button", button)

        self.users_button = ttk.Button(grid, text="Utilisateurs", command=self.open_users)
        self.users_button.grid(row=2, column=0, columnspan=2, padx=8, pady=(12, 8), sticky="ew")
        if self.user.role != "Admin":
            self.users_button.state(["disabled"])

        grid.columnconfigure(0, weight=1)
        grid.columnconfigure(1, weight=1)

        self.summary_var = tk.StringVar(value="Chargement des statistiques...")
        summary_frame = ttk.LabelFrame(container, text="Résumé", style="Card.TLabelframe")
        summary_frame.pack(fill="x", pady=18)
        ttk.Label(summary_frame, textvariable=self.summary_var, justify="center").pack(fill="x")

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
            command=self.open_change_password,
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
        ttk.Button(report_buttons, text="Générer un rapport PDF", command=self.open_pdf_report).grid(
            row=0, column=0, padx=6, pady=4
        )
        ttk.Button(report_buttons, text="Générer un rapport Excel", command=self.open_excel_report).grid(
            row=0, column=1, padx=6, pady=4
        )
        ttk.Button(report_buttons, text="Ouvrir le dossier des rapports", command=self.open_reports_folder).grid(
            row=0, column=2, padx=6, pady=4
        )

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
            command=self.backup_database,
        )
        self.backup_button.grid(row=0, column=0, padx=6, pady=4)
        self.restore_button = ttk.Button(
            maintenance_buttons,
            text="Restaurer une sauvegarde",
            command=self.restore_database,
        )
        self.restore_button.grid(row=0, column=1, padx=6, pady=4)
        self.backup_folder_button = ttk.Button(
            maintenance_buttons,
            text="Ouvrir le dossier des sauvegardes",
            command=self.open_backups_folder,
        )
        self.backup_folder_button.grid(row=0, column=2, padx=6, pady=4)

        actions = ttk.Frame(container)
        actions.pack(anchor="center", pady=(8, 0))
        ttk.Button(actions, text="Déconnexion", command=self.logout).grid(row=0, column=0, padx=8)
        ttk.Button(actions, text="Quitter", command=self.on_close_app).grid(row=0, column=1, padx=8)

        self.apply_permissions()

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
        self.backup_button.state(["!disabled"])
        self.restore_button.state(["!disabled"])
        self.backup_folder_button.state(["!disabled"])
        if DatabaseHelper.is_remote_mode():
            self.backup_folder_button.configure(text="Voir les sauvegardes du serveur")
        else:
            self.backup_folder_button.configure(text="Ouvrir le dossier des sauvegardes")

        if self.user.role == "Admin":
            return
        allowed = {
            "Caissier": {"Caisse"},
            "Gestionnaire de stock": {"Stock"},
            "Gestionnaire des commandes": {"Commandes", "Commissions"},
        }.get(self.user.role, set())
        if "Caisse" not in allowed:
            self.caisse_button.state(["disabled"])
        if "Stock" not in allowed:
            self.stock_button.state(["disabled"])
        if "Commandes" not in allowed:
            self.commandes_button.state(["disabled"])
        if "Commissions" not in allowed:
            self.commissions_button.state(["disabled"])
        self.backup_button.state(["disabled"])
        self.restore_button.state(["disabled"])
        self.backup_folder_button.state(["disabled"])

    def refresh_summary(self) -> None:
        try:
            summary = self.build_dashboard_summary()
        except Exception:
            summary = "Statistiques indisponibles pour le moment."
        self.summary_var.set(summary)

    def build_dashboard_summary(self) -> str:
        role = self.user.role
        if role == "Gestionnaire de stock":
            return self.build_stock_summary()
        if role == "Gestionnaire des commandes":
            return self.build_orders_and_commissions_summary(include_cash=False)
        if role == "Caissier":
            return self.build_orders_and_commissions_summary(include_cash=True)
        return self.build_admin_summary()

    def build_admin_summary(self) -> str:
        orders_summary = DatabaseHelper.get_global_orders_summary()
        today = date.today()
        stock_journal = DatabaseHelper.get_stock_journal(today)
        stock_line = "Journal stock du jour indisponible."
        if stock_journal:
            stock_line = (
                "Stock du jour | "
                f"Ouverture farine : {format_number(float(stock_journal.get('FarineOuverture', 0) or 0))} | "
                f"Clôture farine : {format_number(float(stock_journal.get('FarineCloture', 0) or 0))}"
            )
        return (
            f"Utilisateurs : {DatabaseHelper.count_users()} | Sorties stock : {DatabaseHelper.count_stock_exits()} | "
            f"Commandes avec dette : {DatabaseHelper.count_orders_with_debt()}\n"
            f"Commandes : {int(orders_summary.get('NombreCommandes', 0) or 0)} | "
            f"Total bacs : {int(orders_summary.get('TotalBacs', 0) or 0)} | "
            f"Montant attendu : {format_fc(float(orders_summary.get('MontantAttendu', 0) or 0))}\n"
            f"Total caisse : {format_fc(DatabaseHelper.get_total_cash())} | "
            f"Total commissions : {format_fc(DatabaseHelper.get_total_commissions())}\n"
            f"{stock_line}"
        )

    def build_stock_summary(self) -> str:
        today = date.today()
        stock_journal = DatabaseHelper.get_stock_journal(today)
        stock_exits = DatabaseHelper.list_stock_exits_by_date(today)
        if not stock_journal:
            return (
                f"Stock du jour - {today.strftime('%d/%m/%Y')}\n"
                "Aucun journal de stock n'est disponible pour aujourd'hui."
            )
        return (
            f"Stock du jour - {today.strftime('%d/%m/%Y')}\n"
            f"Sorties du jour : {len(stock_exits)}\n"
            f"Ouverture | Farine : {format_number(float(stock_journal.get('FarineOuverture', 0) or 0))} | "
            f"Levure : {format_number(float(stock_journal.get('LevureOuverture', 0) or 0))} | "
            f"Sel : {format_number(float(stock_journal.get('SelOuverture', 0) or 0))} | "
            f"Huile : {format_number(float(stock_journal.get('HuileOuverture', 0) or 0))}\n"
            f"Clôture | Farine : {format_number(float(stock_journal.get('FarineCloture', 0) or 0))} | "
            f"Levure : {format_number(float(stock_journal.get('LevureCloture', 0) or 0))} | "
            f"Sel : {format_number(float(stock_journal.get('SelCloture', 0) or 0))} | "
            f"Huile : {format_number(float(stock_journal.get('HuileCloture', 0) or 0))}"
        )

    def build_orders_and_commissions_summary(self, include_cash: bool) -> str:
        orders_summary = DatabaseHelper.get_global_orders_summary()
        lines = [
            "Commandes et commissions",
            (
                f"Nombre de commandes : {int(orders_summary.get('NombreCommandes', 0) or 0)} | "
                f"Commandes avec dette : {int(orders_summary.get('NombreAvecDette', 0) or 0)}"
            ),
            (
                f"Total bacs : {int(orders_summary.get('TotalBacs', 0) or 0)} | "
                f"Montant attendu : {format_fc(float(orders_summary.get('MontantAttendu', 0) or 0))}"
            ),
            (
                f"Montant reçu : {format_fc(float(orders_summary.get('MontantRecu', 0) or 0))} | "
                f"Dettes : {format_fc(float(orders_summary.get('TotalDettes', 0) or 0))}"
            ),
            f"Total commissions : {format_fc(DatabaseHelper.get_total_commissions())}",
        ]
        if include_cash:
            cash_today = DatabaseHelper.get_cash_for_date(date.today())
            expenses_today = float(cash_today.get("MontantTotalDepenses", 0) or 0)
            lines.append(
                f"Dépenses du jour : {format_fc(expenses_today)} | Solde global : {format_fc(DatabaseHelper.get_total_cash())}"
            )
        return "\n".join(lines)

    def refresh_security_notice(self) -> None:
        if DatabaseHelper.is_using_default_password(self.user.identifiant):
            self.security_message_var.set(
                "Attention : ce compte utilise encore le mot de passe par défaut. "
                "Changez-le maintenant pour mieux protéger l'application."
            )
            self.security_label.configure(foreground="#8b0000")
            return

        self.security_message_var.set(
            "Vous pouvez changer votre mot de passe à tout moment depuis ce tableau de bord."
        )
        self.security_label.configure(foreground="#2f5d3a")

    def start_weekly_update_check(self) -> None:
        if self.update_check_running:
            return
        self.update_check_running = UpdateChecker.run_weekly_check_async(self.update_result_queue)
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
            self.show_update_dialog(result.update_info)

    def backup_database(self) -> None:
        try:
            backup_path = DatabaseHelper.backup_database()
        except Exception as exc:
            messagebox.showerror("Sauvegarde", str(exc))
            return

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
        messagebox.showinfo("Restauration terminée", details)
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

    def open_pdf_report(self) -> None:
        window = PdfReportWindow(self)
        self.wait_window(window)

    def open_excel_report(self) -> None:
        window = ExcelReportWindow(self)
        self.wait_window(window)

    def show_update_dialog(self, update_info: UpdateInfo) -> None:
        message = (
            "Une nouvelle version de l'application est disponible.\n\n"
            f"Version installee : {APP_VERSION}\n"
            f"Nouvelle version : {update_info.version}"
        )

        if update_info.published_at:
            message += f"\nDate de publication : {update_info.published_at}"

        if update_info.notes:
            message += f"\n\nNotes :\n{update_info.notes}"

        message += "\n\nVoulez-vous ouvrir le lien de téléchargement ?"

        if messagebox.askyesno("Mise à jour disponible", message):
            webbrowser.open(update_info.download_url)

    def can_access(self, module_name: str) -> bool:
        if self.user.role == "Admin":
            return True
        allowed = {
            "Caissier": {"Caisse"},
            "Gestionnaire de stock": {"Stock"},
            "Gestionnaire des commandes": {"Commandes", "Commissions"},
        }.get(self.user.role, set())
        if module_name not in allowed:
            messagebox.showwarning("Accès refusé", "Accès non autorisé.")
            return False
        return True

    def open_cash(self) -> None:
        if not self.can_access("Caisse"):
            return
        window = CashWindow(self)
        self.wait_window(window)
        self.refresh_summary()

    def open_stock(self) -> None:
        if not self.can_access("Stock"):
            return
        window = StockWindow(self)
        self.wait_window(window)
        self.refresh_summary()

    def open_orders(self) -> None:
        if not self.can_access("Commandes"):
            return
        window = OrdersWindow(self)
        self.wait_window(window)
        self.refresh_summary()

    def open_commissions(self) -> None:
        if not self.can_access("Commissions"):
            return
        window = CommissionsWindow(self)
        self.wait_window(window)
        self.refresh_summary()

    def open_users(self) -> None:
        if self.user.role != "Admin":
            messagebox.showwarning("Accès refusé", "Accès non autorisé.")
            return
        window = UsersWindow(self)
        self.wait_window(window)
        self.refresh_summary()

    def logout(self) -> None:
        if not messagebox.askyesno("Confirmation", "Voulez-vous vraiment vous déconnecter ?"):
            return
        self.destroy()
        self.on_logout_callback()

    def open_change_password(self) -> None:
        window = ChangePasswordWindow(self, self.user.identifiant, self.refresh_security_notice)
        self.wait_window(window)
        self.refresh_security_notice()

    def on_close_app(self) -> None:
        if not messagebox.askyesno("Confirmation", "Voulez-vous vraiment quitter l'application ?"):
            return
        if self.live_refresh_after_id is not None:
            self.after_cancel(self.live_refresh_after_id)
            self.live_refresh_after_id = None
        self.root.destroy()


class BaseModuleWindow(tk.Toplevel):
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
        self.scrollable_content = ScrollableContent(self, padding=(10, 4, 10, 10), background=MODULE_BACKGROUND)
        self.scrollable_content.pack(fill="both", expand=True)
        shell = self.scrollable_content.content
        header = create_branded_header(shell, title, logo_size=FORM_LOGO_SIZE, wraplength=860)
        setattr(self, "_header_logo", getattr(header, "_header_logo", None))
        self.body = ttk.Frame(shell)
        self.body.pack(fill="both", expand=True)
        if start_maximized:
            maximize_window(self, min_width, min_height)
        else:
            center_window(self)
        if self.parent.is_live_sync_enabled():
            self.schedule_live_refresh()

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
            foreground="#4b5563",
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
    def __init__(self, parent: DashboardWindow) -> None:
        super().__init__(parent, "Rapport PDF journalier", "700x420", start_maximized=False)
        self.identifiant = parent.user.identifiant
        self.role = parent.user.role
        self.reports_dir = DatabaseHelper.get_reports_dir_for_user(self.identifiant)
        self.open_after_generation_var = tk.BooleanVar(value=True)
        self.message_var = tk.StringVar(value="")
        self.build_ui()

    def build_ui(self) -> None:
        container = self.body

        intro = ttk.LabelFrame(container, text="Impression", style="Card.TLabelframe")
        intro.pack(fill="x", pady=(0, 14))
        ttk.Label(
            intro,
            text=(
                "Choisissez une date puis générez un document PDF prêt à imprimer. "
                f"{get_report_scope_description(self.role)}"
            ),
            wraplength=500,
            justify="center",
        ).pack(fill="x")
        ttk.Label(
            intro,
            text=f"Profil du rapport : {get_report_scope_label(self.role)}",
            foreground="#2f5d3a",
            justify="center",
        ).pack(fill="x", pady=(8, 0))

        form = ttk.LabelFrame(container, text="Paramètres du rapport", style="Card.TLabelframe")
        form.pack(fill="x")

        ttk.Label(form, text="Date du rapport").grid(row=0, column=0, sticky="w", pady=6)
        self.date_field = DateField(form)
        self.date_field.grid(row=0, column=1, sticky="ew", pady=6)

        ttk.Checkbutton(
            form,
            text="Proposer l'ouverture du PDF apres generation",
            variable=self.open_after_generation_var,
        ).grid(row=1, column=0, columnspan=2, sticky="w", pady=(6, 0))

        actions = ttk.Frame(form)
        actions.grid(row=2, column=0, columnspan=2, pady=(14, 0))
        ttk.Button(actions, text="Générer le PDF", style="Primary.TButton", command=self.generate_report).grid(
            row=0, column=0, padx=6
        )
        ttk.Button(actions, text="Ouvrir le dossier des rapports", command=self.open_reports_folder).grid(
            row=0, column=1, padx=6
        )
        ttk.Button(actions, text="Fermer", command=self.close_window).grid(row=0, column=2, padx=6)

        form.columnconfigure(1, weight=1)

        ttk.Label(
            container,
            textvariable=self.message_var,
            foreground="#8b0000",
            wraplength=520,
            justify="center",
        ).pack(fill="x", pady=(12, 0))

    def generate_report(self) -> None:
        try:
            target_date = self.date_field.get_date()
        except Exception as exc:
            self.message_var.set(str(exc))
            return

        self.reports_dir.mkdir(parents=True, exist_ok=True)
        suggested_path = self.reports_dir / f"rapport-journalier-{target_date.strftime('%Y%m%d')}.pdf"
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
            report_path = create_daily_pdf_report(target_date, destination, role=self.role)
        except ReportGenerationError as exc:
            self.message_var.set(str(exc))
            return
        except Exception as exc:
            self.message_var.set(f"Generation impossible : {exc}")
            return

        self.message_var.set(f"Rapport créé : {report_path}")
        message = f"Le rapport PDF a été créé avec succès.\n\nFichier : {report_path}"
        if self.open_after_generation_var.get():
            message += "\n\nVoulez-vous l'ouvrir maintenant ?"
            if messagebox.askyesno("Rapport PDF", message):
                open_file(report_path)
            return

        message += "\n\nVoulez-vous ouvrir le dossier qui contient ce rapport ?"
        if messagebox.askyesno("Rapport PDF", message):
            self.open_reports_folder()

    def open_reports_folder(self) -> None:
        open_folder(self.reports_dir)


class ExcelReportWindow(BaseModuleWindow):
    def __init__(self, parent: DashboardWindow) -> None:
        super().__init__(parent, "Rapport Excel journalier", "700x420", start_maximized=False)
        self.identifiant = parent.user.identifiant
        self.role = parent.user.role
        self.reports_dir = DatabaseHelper.get_reports_dir_for_user(self.identifiant)
        self.open_after_generation_var = tk.BooleanVar(value=True)
        self.message_var = tk.StringVar(value="")
        self.build_ui()

    def build_ui(self) -> None:
        container = self.body

        intro = ttk.LabelFrame(container, text="Export Excel", style="Card.TLabelframe")
        intro.pack(fill="x", pady=(0, 14))
        ttk.Label(
            intro,
            text=(
                "Choisissez une date puis générez un classeur Excel prêt à partager ou à retravailler. "
                f"{get_report_scope_description(self.role)}"
            ),
            wraplength=500,
            justify="center",
        ).pack(fill="x")
        ttk.Label(
            intro,
            text=f"Profil du rapport : {get_report_scope_label(self.role)}",
            foreground="#2f5d3a",
            justify="center",
        ).pack(fill="x", pady=(8, 0))

        form = ttk.LabelFrame(container, text="Paramètres du rapport", style="Card.TLabelframe")
        form.pack(fill="x")

        ttk.Label(form, text="Date du rapport").grid(row=0, column=0, sticky="w", pady=6)
        self.date_field = DateField(form)
        self.date_field.grid(row=0, column=1, sticky="ew", pady=6)

        ttk.Checkbutton(
            form,
            text="Proposer l'ouverture du fichier Excel après génération",
            variable=self.open_after_generation_var,
        ).grid(row=1, column=0, columnspan=2, sticky="w", pady=(6, 0))

        actions = ttk.Frame(form)
        actions.grid(row=2, column=0, columnspan=2, pady=(14, 0))
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

        ttk.Label(
            container,
            textvariable=self.message_var,
            foreground="#8b0000",
            wraplength=520,
            justify="center",
        ).pack(fill="x", pady=(12, 0))

    def generate_report(self) -> None:
        try:
            target_date = self.date_field.get_date()
        except Exception as exc:
            self.message_var.set(str(exc))
            return

        self.reports_dir.mkdir(parents=True, exist_ok=True)
        suggested_path = self.reports_dir / f"rapport-excel-journalier-{target_date.strftime('%Y%m%d')}.xlsx"
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
            report_path = create_daily_excel_report(target_date, destination, role=self.role)
        except ReportGenerationError as exc:
            self.message_var.set(str(exc))
            return
        except Exception as exc:
            self.message_var.set(f"Génération impossible : {exc}")
            return

        self.message_var.set(f"Rapport créé : {report_path}")
        message = f"Le rapport Excel a été créé avec succès.\n\nFichier : {report_path}"
        if self.open_after_generation_var.get():
            message += "\n\nVoulez-vous l'ouvrir maintenant ?"
            if messagebox.askyesno("Rapport Excel", message):
                open_file(report_path)
            return

        message += "\n\nVoulez-vous ouvrir le dossier qui contient ce rapport ?"
        if messagebox.askyesno("Rapport Excel", message):
            self.open_reports_folder()

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
            description_color = "#8b0000"
        else:
            description_text = (
                "Saisissez votre mot de passe actuel, puis choisissez un nouveau mot de passe "
                "d'au moins 6 caracteres."
            )
            description_color = "#2f5d3a"

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
            foreground="#8b0000",
            wraplength=440,
            justify="center",
        ).pack(fill="x", pady=(12, 0))

        self.current_entry.focus()
        self.current_entry.bind("<Return>", lambda _event: self.new_entry.focus())
        self.new_entry.bind("<Return>", lambda _event: self.confirm_entry.focus())
        self.confirm_entry.bind("<Return>", lambda _event: self.save_password())

    def save_password(self) -> None:
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
        self.refresh_users()

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

        ttk.Label(form, text="Mot de passe").grid(row=2, column=0, sticky="w", pady=6)
        self.password_var = tk.StringVar()
        self.show_password_var = tk.BooleanVar(value=False)
        password_row = ttk.Frame(form)
        password_row.grid(row=2, column=1, sticky="ew", pady=6)
        self.password_entry = ttk.Entry(password_row, textvariable=self.password_var, show="*", width=26)
        self.password_entry.grid(row=0, column=0, sticky="ew")
        ttk.Checkbutton(
            password_row,
            text="Afficher",
            variable=self.show_password_var,
            command=self.toggle_password_visibility,
        ).grid(row=0, column=1, padx=(8, 0), sticky="w")
        password_row.columnconfigure(0, weight=1)

        ttk.Label(form, text="Rôle").grid(row=3, column=0, sticky="w", pady=6)
        self.role_var = tk.StringVar(value=ROLES[0])
        self.role_combo = ttk.Combobox(form, textvariable=self.role_var, values=ROLES, state="readonly", width=31)
        self.role_combo.grid(row=3, column=1, sticky="ew", pady=6)

        button_bar = ttk.Frame(form)
        button_bar.grid(row=4, column=0, columnspan=2, pady=(14, 0))
        ttk.Button(button_bar, text="Enregistrer", command=self.save_user).grid(row=0, column=0, padx=4, pady=4)
        ttk.Button(button_bar, text="Modifier", command=self.load_user_for_edit).grid(row=0, column=1, padx=4, pady=4)
        ttk.Button(button_bar, text="Supprimer", command=self.delete_user).grid(row=0, column=2, padx=4, pady=4)
        ttk.Button(button_bar, text="Rechercher", command=self.search_user).grid(row=1, column=0, padx=4, pady=4)
        ttk.Button(button_bar, text="Tout afficher", command=self.refresh_users).grid(row=1, column=1, padx=4, pady=4)
        ttk.Button(button_bar, text="Fermer", command=self.close_window).grid(row=1, column=2, padx=4, pady=4)

        form.columnconfigure(1, weight=1)

        self.message_var = tk.StringVar(value="")
        ttk.Label(form, textvariable=self.message_var, foreground="#8b0000", wraplength=320).grid(
            row=5, column=0, columnspan=2, sticky="ew", pady=(12, 0)
        )

        table_frame = ttk.LabelFrame(top, text="Liste", style="Card.TLabelframe")
        table_frame.pack(side="left", fill="both", expand=True)
        self.table = DataTable(table_frame, height=18)
        self.table.pack(fill="both", expand=True)

    def refresh_users(self) -> None:
        rows = DatabaseHelper.list_users()
        self.table.set_data(
            rows,
            columns=["Id", "NomComplet", "Identifiant", "MotDePasse", "Role"],
            headings={
                "NomComplet": "Nom complet",
                "Identifiant": "Identifiant",
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
            columns=["Id", "NomComplet", "Identifiant", "MotDePasse", "Role"],
            headings={
                "NomComplet": "Nom complet",
                "Identifiant": "Identifiant",
                "MotDePasse": "Mot de passe",
                "Role": "Rôle",
            },
            hidden_columns=["Id"],
        )
        self.message_var.set("Recherche terminée." if rows else "Aucun utilisateur trouvé.")

    def save_user(self) -> None:
        name = self.name_var.get().strip()
        identifiant = self.identifiant_var.get().strip()
        password = self.password_var.get().strip()
        role = self.role_var.get().strip()

        if not name or not identifiant or not role:
            messagebox.showwarning("Utilisateurs", "Veuillez remplir tous les champs.")
            return
        if not self.edit_mode and not password:
            messagebox.showwarning("Utilisateurs", "Veuillez saisir un mot de passe.")
            return

        try:
            if self.edit_mode:
                updated = DatabaseHelper.update_user(self.original_identifiant, name, password, role)
                message = "Utilisateur modifié avec succès." if updated else "Aucune modification effectuée."
            else:
                DatabaseHelper.add_user(name, identifiant, password, role)
                message = "Utilisateur ajouté avec succès."
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
        self.name_var.set(str(row["NomComplet"]))
        self.identifiant_var.set(str(row["Identifiant"]))
        self.password_var.set("")
        self.show_password_var.set(False)
        self.toggle_password_visibility()
        self.role_var.set(str(row["Role"]))
        self.original_identifiant = str(row["Identifiant"])
        self.edit_mode = True
        self.identifiant_entry.state(["disabled"])
        self.message_var.set(
            "Le mot de passe actuel ne peut pas etre affiche. "
            "Laissez ce champ vide pour le conserver, ou saisissez-en un nouveau pour le reinitialiser."
        )

    def delete_user(self) -> None:
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
        self.password_var.set("")
        self.show_password_var.set(False)
        self.toggle_password_visibility()
        self.role_var.set(ROLES[0])
        self.edit_mode = False
        self.original_identifiant = ""
        self.identifiant_entry.state(["!disabled"])
        self.name_entry.focus()


class StockWindow(BaseModuleWindow):
    def __init__(self, parent: DashboardWindow) -> None:
        super().__init__(parent, "Gestion du stock", "1160x780")
        self.edit_mode = False
        self.selected_exit_id = 0
        self.first_open_of_day = DatabaseHelper.initialize_stock_day(date.today())
        self.closing_message_shown = False
        self.build_ui()
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
        ttk.Button(button_bar, text="Enregistrer", command=self.save_exit).grid(row=0, column=0, padx=4, pady=4)
        ttk.Button(button_bar, text="Modifier", command=self.load_selected_exit).grid(row=0, column=1, padx=4, pady=4)
        ttk.Button(button_bar, text="Supprimer", command=self.delete_exit).grid(row=0, column=2, padx=4, pady=4)
        ttk.Button(button_bar, text="Paramètres", command=self.edit_stock_parameters).grid(
            row=1, column=0, padx=4, pady=4
        )
        ttk.Button(button_bar, text="Fermer", command=self.close_window).grid(row=1, column=1, padx=4, pady=4)

        form.columnconfigure(1, weight=1)

        table_frame = ttk.LabelFrame(content, text="Historique des sorties", style="Card.TLabelframe")
        table_frame.pack(side="left", fill="both", expand=True)
        self.table = DataTable(table_frame, height=18)
        self.table.pack(fill="both", expand=True)

    def _make_entry(self, parent: ttk.LabelFrame, label: str, variable: tk.StringVar, row: int) -> None:
        ttk.Label(parent, text=label).grid(row=row, column=0, sticky="w", pady=6)
        ttk.Entry(parent, textvariable=variable, width=20).grid(row=row, column=1, sticky="ew", pady=6)

    def refresh_live_view(self) -> None:
        self.refresh_data()

    def refresh_data(self) -> None:
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
                    messagebox.showinfo("Stock", "La sortie de stock a été modifiée avec succès.")
                else:
                    messagebox.showwarning("Stock", "Aucune modification n'a été enregistrée.")
            else:
                DatabaseHelper.add_stock_exit(target_date, sacs, paquets, sel, huile)
                messagebox.showinfo("Stock", "La sortie de stock a été enregistrée avec succès.")
            self.reset_form()
            self.refresh_data()
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
        messagebox.showinfo("Stock", "La sortie a été chargée. Modifiez-la puis enregistrez.")

    def delete_exit(self) -> None:
        row = self.table.selected_row()
        if row is None:
            messagebox.showwarning("Stock", "Veuillez sélectionner une sortie dans la grille.")
            return
        if not messagebox.askyesno("Confirmation", "Voulez-vous vraiment supprimer cette sortie ?"):
            return
        try:
            deleted = DatabaseHelper.delete_stock_exit(int(row["Id"]))
            if deleted:
                messagebox.showinfo("Stock", "La sortie de stock a été supprimée avec succès.")
                self.reset_form()
                self.refresh_data()
            else:
                messagebox.showwarning("Stock", "Aucune sortie n'a été supprimée.")
        except Exception as exc:
            messagebox.showerror("Stock", str(exc))

    def edit_stock_parameters(self) -> None:
        current = DatabaseHelper.get_stock_configuration()
        if not current:
            messagebox.showwarning("Stock", "Impossible de charger la configuration du stock.")
            return

        dialog = tk.Toplevel(self)
        dialog.geometry("460x300")
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

        for index, (label, variable) in enumerate(variables.items()):
            row_index = index + 1
            ttk.Label(frame, text=f"{label} initial").grid(row=row_index, column=0, sticky="w", pady=6)
            ttk.Entry(frame, textvariable=variable, width=20).grid(row=row_index, column=1, sticky="ew", pady=6)

        def save() -> None:
            try:
                farine = parse_float(variables["Farine"].get(), "Farine initiale")
                levure = parse_float(variables["Levure"].get(), "Levure initiale")
                sel = parse_float(variables["Sel"].get(), "Sel initial")
                huile = parse_float(variables["Huile"].get(), "Huile initiale")
                if min(farine, levure, sel, huile) < 0:
                    raise ValueError("Les valeurs initiales ne peuvent pas être négatives.")
                DatabaseHelper.update_stock_configuration(farine, levure, sel, huile)
                dialog.destroy()
                self.refresh_data()
                messagebox.showinfo("Stock", "Le stock initial a été mis à jour avec succès.")
            except Exception as exc:
                messagebox.showwarning("Stock", str(exc))

        actions = ttk.Frame(frame)
        actions.grid(row=5, column=0, columnspan=2, pady=(12, 0))
        ttk.Button(actions, text="Enregistrer", command=save).grid(row=0, column=0, padx=6)
        ttk.Button(actions, text="Annuler", command=dialog.destroy).grid(row=0, column=1, padx=6)
        frame.columnconfigure(1, weight=1)
        maximize_window(dialog, 460, 300)

    def reset_form(self) -> None:
        self.date_field.set_date(today_iso())
        self.sacs_var.set("")
        self.paquets_var.set("")
        self.sel_var.set("")
        self.huile_var.set("")
        self.edit_mode = False
        self.selected_exit_id = 0

    def close_window(self) -> None:
        if not self.closing_message_shown:
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


class OrdersWindow(BaseModuleWindow):
    def __init__(self, parent: DashboardWindow) -> None:
        super().__init__(parent, "Gestion des commandes", "1240x840")
        self.edit_mode = False
        self.selected_order_id = 0
        self.show_all_dates = False
        self.loaded_amount_due_rate: float | None = None
        self.build_ui()
        self.reset_form()
        self.refresh_orders()

    def build_ui(self) -> None:
        container = self.body

        content = ttk.Frame(container)
        content.pack(fill="both", expand=True)

        form = ttk.LabelFrame(content, text="Commande", style="Card.TLabelframe")
        form.pack(side="left", fill="y", padx=(0, 12))

        ttk.Label(form, text="Date").grid(row=0, column=0, sticky="w", pady=6)
        self.date_field = DateField(form)
        self.date_field.grid(row=0, column=1, sticky="ew", pady=6)
        self.date_field.bind_change(self._on_date_change)

        ttk.Label(form, text="Client").grid(row=1, column=0, sticky="w", pady=6)
        self.client_var = tk.StringVar()
        ttk.Entry(form, textvariable=self.client_var, width=28).grid(row=1, column=1, sticky="ew", pady=6)

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

        ttk.Label(form, text="Dette").grid(row=6, column=0, sticky="w", pady=6)
        self.debt_var = tk.StringVar(value=format_fc(0))
        self.debt_label = ttk.Label(form, textvariable=self.debt_var, foreground="#006400")
        self.debt_label.grid(row=6, column=1, sticky="w", pady=6)

        actions = ttk.Frame(form)
        actions.grid(row=7, column=0, columnspan=2, pady=(14, 0))
        ttk.Button(actions, text="Enregistrer", command=self.save_order).grid(row=0, column=0, padx=4, pady=4)
        ttk.Button(actions, text="Modifier", command=self.load_order_for_edit).grid(row=0, column=1, padx=4, pady=4)
        ttk.Button(actions, text="Supprimer", command=self.delete_order).grid(row=0, column=2, padx=4, pady=4)
        ttk.Button(actions, text="Tout afficher", command=self.show_all).grid(row=1, column=0, padx=4, pady=4)
        ttk.Button(actions, text="Fermer", command=self.close_window).grid(row=1, column=1, padx=4, pady=4)

        self.summary_var = tk.StringVar()
        ttk.Label(form, textvariable=self.summary_var, wraplength=360, justify="left").grid(
            row=8, column=0, columnspan=2, sticky="ew", pady=(14, 0)
        )

        table_frame = ttk.LabelFrame(content, text="Historique des commandes", style="Card.TLabelframe")
        table_frame.pack(side="left", fill="both", expand=True)
        self.table = DataTable(table_frame, height=20)
        self.table.pack(fill="both", expand=True)

        self.status_combo.bind("<<ComboboxSelected>>", self._on_status_change)
        self.amount_received_var.trace_add("write", lambda *_args: self.recalculate_amounts())
        self.trays_var.trace_add("write", lambda *_args: self.recalculate_amounts())
        form.columnconfigure(1, weight=1)

    def _on_date_change(self) -> None:
        self.show_all_dates = False
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
        debt = amount_due - amount_received
        self.amount_due_var.set(format_fc(amount_due))
        self.debt_var.set(format_fc(debt))
        self.debt_label.configure(foreground="#8b0000" if debt > 0 else "#006400")

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
        debt = amount_due - amount_received
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
            messagebox.showinfo("Commandes", "La commande existante a été modifiée avec succès.")
            self.reset_form()
            self.refresh_orders()
        else:
            messagebox.showwarning("Commandes", "La commande existante n'a pas pu être modifiée.")
        return False

    def save_order(self) -> None:
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
                messagebox.showinfo("Commandes", "La commande a été enregistrée avec succès.")
            self.reset_form()
            self.refresh_orders()
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
                "Dette",
            ],
            headings={
                "DateCommande": "Date",
                "NombreBacs": "Bacs",
                "MontantAPercevoir": "À percevoir",
                "MontantRecu": "Reçu",
                "Dette": "Dette",
            },
            hidden_columns=["Id"],
            formatters={
                "Statut": normalize_status_label,
                "NombreBacs": lambda value: f"{int(value)}",
                "MontantAPercevoir": lambda value: format_fc(float(value)),
                "MontantRecu": lambda value: format_fc(float(value)),
                "Dette": lambda value: format_fc(float(value)),
            },
        )
        self.update_summary(rows)

    def update_summary(self, rows: list[dict[str, Any]]) -> None:
        if self.show_all_dates:
            summary = DatabaseHelper.get_global_orders_summary()
            text = (
                "Affichage : toutes les dates\n"
                f"Nombre de commandes : {len(rows)} | Commandes avec dette : {int(summary.get('NombreAvecDette', 0))}\n"
                f"Total bacs : {int(summary.get('TotalBacs', 0))}\n"
                f"Montant attendu : {format_fc(float(summary.get('MontantAttendu', 0)))} | "
                f"Montant reçu : {format_fc(float(summary.get('MontantRecu', 0)))} | "
                f"Dettes : {format_fc(float(summary.get('TotalDettes', 0)))}"
            )
        else:
            try:
                target_date = self.date_field.get_date()
            except ValueError:
                target_date = date.today()
            total_bacs = sum(int(row["NombreBacs"]) for row in rows)
            total_due = sum(float(row["MontantAPercevoir"]) for row in rows)
            total_received = sum(float(row["MontantRecu"]) for row in rows)
            total_debt = sum(float(row["Dette"]) for row in rows)
            with_debt = sum(1 for row in rows if float(row["Dette"]) > 0)
            text = (
                f"Date : {target_date.strftime('%d/%m/%Y')}\n"
                f"Nombre de commandes : {len(rows)} | Commandes avec dette : {with_debt}\n"
                f"Total bacs : {total_bacs}\n"
                f"Montant attendu : {format_fc(total_due)} | "
                f"Montant reçu : {format_fc(total_received)} | "
                f"Dettes : {format_fc(total_debt)}"
            )
        self.summary_var.set(text)

    def load_order_for_edit(self) -> None:
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
        messagebox.showinfo("Commandes", "La commande a été chargée. Modifiez-la puis enregistrez.")

    def delete_order(self) -> None:
        row = self.table.selected_row()
        if row is None:
            messagebox.showwarning("Commandes", "Veuillez sélectionner une commande dans la grille.")
            return
        if not messagebox.askyesno("Confirmation", "Voulez-vous vraiment supprimer cette commande ?"):
            return
        try:
            deleted = DatabaseHelper.delete_order(int(row["Id"]))
            if deleted:
                messagebox.showinfo("Commandes", "La commande a été supprimée avec succès.")
                self.reset_form()
                self.refresh_orders()
            else:
                messagebox.showwarning("Commandes", "Aucune commande n'a été supprimée.")
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
        self.recalculate_amounts()


class CashWindow(BaseModuleWindow):
    def __init__(self, parent: DashboardWindow) -> None:
        super().__init__(parent, "Gestion de la caisse", "1280x900")
        self.show_all_dates = False
        self.selected_cash_id = 0
        self.trays_today = 0.0
        self.expected_today = 0.0
        self.received_today = 0.0
        self.debts_today = 0.0
        self.total_entries_today = 0.0
        self.build_ui()
        self.reset_form()
        self.refresh_data()

    def build_ui(self) -> None:
        container = self.body

        content = ttk.Frame(container)
        content.pack(fill="both", expand=True)

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
        self.paid_debts_var = tk.StringVar(value="0")
        self.total_entries_var = tk.StringVar()
        self.balance_var = tk.StringVar()

        self._make_label_value(form, "Nombre total de bacs", self.total_trays_var, 1)
        self._make_label_value(form, "Montant attendu", self.expected_var, 2, "#7a0000")
        self._make_label_value(form, "Montant reçu", self.received_var, 3, "#006400")
        self._make_label_value(form, "Dettes", self.debts_var, 4, "#8b0000")

        ttk.Label(form, text="Dettes payées aujourd'hui").grid(row=5, column=0, sticky="w", pady=6)
        ttk.Entry(form, textvariable=self.paid_debts_var, width=28).grid(row=5, column=1, sticky="ew", pady=6)

        ttk.Label(form, text="Ceux qui ont payé leurs dettes").grid(row=6, column=0, sticky="nw", pady=6)
        self.paid_debts_details_text = ScrolledText(form, width=28, height=6)
        self.paid_debts_details_text.configure(font=UI_FONT)
        self.paid_debts_details_text.grid(row=6, column=1, sticky="ew", pady=6)

        self._make_label_value(form, "Total des entrées", self.total_entries_var, 7, "#1f4e79")

        ttk.Label(form, text="Montant total des dépenses").grid(row=8, column=0, sticky="w", pady=6)
        self.expenses_var = tk.StringVar(value="0")
        ttk.Entry(form, textvariable=self.expenses_var, width=28).grid(row=8, column=1, sticky="ew", pady=6)

        ttk.Label(form, text="Dépenses effectuées").grid(row=9, column=0, sticky="nw", pady=6)
        self.expenses_text = ScrolledText(form, width=28, height=7)
        self.expenses_text.configure(font=UI_FONT)
        self.expenses_text.grid(row=9, column=1, sticky="ew", pady=6)

        self._make_label_value(form, "Solde", self.balance_var, 10, "#1b2d5d")

        actions = ttk.Frame(form)
        actions.grid(row=11, column=0, columnspan=2, pady=(14, 0))
        ttk.Button(actions, text="Enregistrer", command=self.save_cash).grid(row=0, column=0, padx=4, pady=4)
        ttk.Button(actions, text="Modifier", command=self.load_cash_for_edit).grid(row=0, column=1, padx=4, pady=4)
        ttk.Button(actions, text="Supprimer", command=self.delete_cash).grid(row=0, column=2, padx=4, pady=4)
        ttk.Button(actions, text="Tout afficher", command=self.show_all).grid(row=1, column=0, padx=4, pady=4)
        ttk.Button(actions, text="Fermer", command=self.close_window).grid(row=1, column=1, padx=4, pady=4)

        self.summary_var = tk.StringVar()
        ttk.Label(form, textvariable=self.summary_var, wraplength=420, justify="left").grid(
            row=12, column=0, columnspan=2, sticky="ew", pady=(14, 0)
        )

        table_frame = ttk.LabelFrame(content, text="Historique de caisse", style="Card.TLabelframe")
        table_frame.pack(side="left", fill="both", expand=True)
        self.table = DataTable(table_frame, height=22)
        self.table.pack(fill="both", expand=True)

        self.paid_debts_var.trace_add("write", lambda *_args: self.calculate_balance())
        self.expenses_var.trace_add("write", lambda *_args: self.calculate_balance())
        form.columnconfigure(1, weight=1)

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

        self.total_trays_var.set(f"{int(self.trays_today)}")
        self.expected_var.set(format_fc(self.expected_today))
        self.received_var.set(format_fc(self.received_today))
        self.debts_var.set(format_fc(self.debts_today))

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
        self.total_entries_today = self.received_today + paid_debts
        balance = self.total_entries_today - expenses
        self.total_entries_var.set(format_fc(self.total_entries_today))
        self.balance_var.set(format_fc(balance))
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
            text = (
                "Affichage : toutes les dates\n"
                f"Fiches caisse : {row_count}\n"
                f"Total bacs : {int(summary.get('TotalBacs', 0))} | "
                f"Attendu : {format_fc(float(summary.get('MontantAttendu', 0)))} | "
                f"Reçu : {format_fc(float(summary.get('MontantRecu', 0)))}\n"
                f"Dettes payées : {format_fc(paid_debts_total)} | Entrées : {format_fc(entries_total)}\n"
                f"Dettes : {format_fc(float(summary.get('TotalDettes', 0)))} | "
                f"Solde global : {format_fc(total_global)}"
            )
        else:
            text = (
                f"Jour : {target_date.strftime('%d/%m/%Y')} | Bacs : {int(self.trays_today)}\n"
                f"Fiches caisse : {row_count} | Reçu : {format_fc(self.received_today)} | "
                f"Dettes payées : {format_fc(paid_debts)}\n"
                f"Entrées : {format_fc(entries_today)} | "
                f"Solde du jour : {format_fc(balance)}\n"
                f"Dettes : {format_fc(self.debts_today)} | Total global : {format_fc(total_global)}"
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
                "DettesPayeesAujourdHui",
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
                "TotalDettes": "Dettes",
                "DettesPayeesAujourdHui": "Dettes payées",
                "TotalEntrees": "Entrées",
                "MontantTotalDepenses": "Dépenses",
                "DepensesEffectuees": "Détails des dépenses",
                "DettesPayeesDetails": "Ceux qui ont payé",
            },
            hidden_columns=["Id", "DettesPayeesDetails"],
            formatters={
                "NombreTotalBacs": lambda value: f"{int(value)}",
                "MontantAttendu": lambda value: format_fc(float(value)),
                "MontantRecu": lambda value: format_fc(float(value)),
                "TotalDettes": lambda value: format_fc(float(value)),
                "DettesPayeesAujourdHui": lambda value: format_fc(float(value)),
                "TotalEntrees": lambda value: format_fc(float(value)),
                "MontantTotalDepenses": lambda value: format_fc(float(value)),
                "Solde": lambda value: format_fc(float(value)),
            },
        )
        self.update_summary(len(rows))

    def refresh_live_view(self) -> None:
        self.refresh_data()

    def show_all(self) -> None:
        self.show_all_dates = True
        self.refresh_data()

    def save_cash(self) -> None:
        try:
            target_date = self.date_field.get_date()
            paid_debts = parse_optional_float(self.paid_debts_var.get())
            expenses = parse_optional_float(self.expenses_var.get())
        except Exception as exc:
            messagebox.showwarning("Caisse", str(exc))
            return

        details = self.expenses_text.get("1.0", "end").strip()
        paid_debts_details = self.paid_debts_details_text.get("1.0", "end").strip()
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

        try:
            DatabaseHelper.save_cash_day(target_date, expenses, details, paid_debts, paid_debts_details)
            messagebox.showinfo("Caisse", "La fiche de caisse a été enregistrée avec succès.")
            self.refresh_data()
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
        messagebox.showinfo("Caisse", "La fiche de caisse a été chargée.")

    def delete_cash(self) -> None:
        row = self.table.selected_row()
        if row is None:
            messagebox.showwarning("Caisse", "Veuillez sélectionner une fiche dans la grille.")
            return
        if not messagebox.askyesno("Confirmation", "Voulez-vous vraiment supprimer cette fiche de caisse ?"):
            return
        try:
            deleted = DatabaseHelper.delete_cash_day(int(row["Id"]))
            if deleted:
                messagebox.showinfo("Caisse", "La fiche de caisse a été supprimée avec succès.")
                self.reset_form()
                self.refresh_data()
            else:
                messagebox.showwarning("Caisse", "Aucune fiche de caisse n'a été supprimée.")
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
        self.reset_form()
        self.refresh_commissions()

    def build_ui(self) -> None:
        container = self.body

        content = ttk.Frame(container)
        content.pack(fill="both", expand=True)

        form = ttk.LabelFrame(content, text="Commission", style="Card.TLabelframe")
        form.pack(side="left", fill="y", padx=(0, 12))

        ttk.Label(form, text="Date").grid(row=0, column=0, sticky="w", pady=6)
        self.date_field = DateField(form)
        self.date_field.grid(row=0, column=1, sticky="ew", pady=6)
        self.date_field.bind_change(self._on_date_change)

        ttk.Label(form, text="Nom").grid(row=1, column=0, sticky="w", pady=6)
        self.name_var = tk.StringVar()
        self.name_combo = ttk.Combobox(form, textvariable=self.name_var, state="readonly", width=28)
        self.name_combo.grid(row=1, column=1, sticky="ew", pady=6)
        self.name_combo.bind("<<ComboboxSelected>>", lambda _event: self.load_synthesis())

        self.status_value = tk.StringVar()
        self.trays_value = tk.StringVar(value="0")
        self.amount_paid_value = tk.StringVar(value=format_fc(0))
        self.commissions_value = tk.StringVar(value=format_fc(0))
        self.debts_value = tk.StringVar(value=format_fc(0))
        self.net_value = tk.StringVar(value=format_fc(0))

        self._make_label_value(form, "Statut", self.status_value, 2, "#7a0000")
        self._make_label_value(form, "Nombre de bacs", self.trays_value, 3, "#1b2d5d")
        self._make_label_value(form, "Montant payé", self.amount_paid_value, 4, "#006400")
        self._make_label_value(form, "Commissions", self.commissions_value, 5, "#7a0000")
        self._make_label_value(form, "Dettes", self.debts_value, 6, "#8b0000")
        self.net_label = ttk.Label(form, textvariable=self.net_value, foreground="#1b2d5d")
        ttk.Label(form, text="Net à payer").grid(row=7, column=0, sticky="w", pady=6)
        self.net_label.grid(row=7, column=1, sticky="w", pady=6)

        ttk.Label(form, text="Filtre de statut").grid(row=8, column=0, sticky="w", pady=6)
        self.filter_var = tk.StringVar(value=COMMISSION_FILTERS[0])
        self.filter_combo = ttk.Combobox(
            form,
            textvariable=self.filter_var,
            values=COMMISSION_FILTERS,
            state="readonly",
            width=28,
        )
        self.filter_combo.grid(row=8, column=1, sticky="ew", pady=6)
        self.filter_combo.bind("<<ComboboxSelected>>", lambda _event: self.apply_filter())

        actions = ttk.Frame(form)
        actions.grid(row=9, column=0, columnspan=2, pady=(14, 0))
        ttk.Button(actions, text="Enregistrer", command=self.save_commission).grid(row=0, column=0, padx=4, pady=4)
        ttk.Button(actions, text="Modifier", command=self.load_commission_for_edit).grid(
            row=0, column=1, padx=4, pady=4
        )
        ttk.Button(actions, text="Supprimer", command=self.delete_commission).grid(row=0, column=2, padx=4, pady=4)
        ttk.Button(actions, text="Tout afficher", command=self.show_all).grid(row=1, column=0, padx=4, pady=4)
        ttk.Button(actions, text="Fermer", command=self.close_window).grid(row=1, column=1, padx=4, pady=4)

        self.summary_var = tk.StringVar()
        ttk.Label(form, textvariable=self.summary_var, wraplength=400, justify="left").grid(
            row=10, column=0, columnspan=2, sticky="ew", pady=(14, 0)
        )

        table_frame = ttk.LabelFrame(content, text="Historique des commissions", style="Card.TLabelframe")
        table_frame.pack(side="left", fill="both", expand=True)
        self.table = DataTable(table_frame, height=22)
        self.table.pack(fill="both", expand=True)

        form.columnconfigure(1, weight=1)

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
        self.net_label.configure(foreground="#1b2d5d")

    def reset_form(self) -> None:
        self.selected_commission_id = 0
        self.edit_mode = False
        self.show_all_dates = False
        self.date_field.set_date(today_iso())
        self.filter_var.set(COMMISSION_FILTERS[0])
        self.reset_synthesis()
        self.load_names()

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
        self.net_label.configure(foreground="#8b0000" if self.current_net < 0 else "#1b2d5d")

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
            messagebox.showinfo("Commissions", "La commission existante a été modifiée avec succès.")
            self.reset_form()
            self.refresh_commissions()
        else:
            messagebox.showwarning("Commissions", "La commission existante n'a pas pu être modifiée.")
        return False

    def save_commission(self) -> None:
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
                messagebox.showinfo("Commissions", "La commission a été enregistrée avec succès.")
            self.reset_form()
            self.refresh_commissions()
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
        self.net_label.configure(foreground="#8b0000" if self.current_net < 0 else "#1b2d5d")
        messagebox.showinfo("Commissions", "La commission a été chargée. Modifiez-la puis enregistrez.")

    def delete_commission(self) -> None:
        row = self.table.selected_row()
        if row is None:
            messagebox.showwarning("Commissions", "Veuillez sélectionner une commission dans la grille.")
            return
        if not messagebox.askyesno("Confirmation", "Voulez-vous vraiment supprimer cette commission ?"):
            return
        try:
            deleted = DatabaseHelper.delete_commission(int(row["Id"]))
            if deleted:
                messagebox.showinfo("Commissions", "La commission a été supprimée avec succès.")
                self.reset_form()
                self.refresh_commissions()
            else:
                messagebox.showwarning("Commissions", "Aucune commission n'a été supprimée.")
        except Exception as exc:
            messagebox.showerror("Commissions", str(exc))
