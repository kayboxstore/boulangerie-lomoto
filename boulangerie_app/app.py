from __future__ import annotations

from queue import Empty, Queue
import tkinter as tk
import webbrowser
from datetime import date, datetime
from tkinter import messagebox, ttk
from tkinter.scrolledtext import ScrolledText
from typing import Any, Callable

from .database import AuthenticatedUser, DatabaseHelper
from .updater import SessionNotice, UpdateCheckResult, UpdateChecker, UpdateInfo
from .version import APP_NAME, APP_VERSION


ROLES = [
    "Admin",
    "Caissier",
    "Gestionnaire de stock",
    "Gestionnaire des commandes",
]

ORDER_STATUSES = [
    "Maman",
    "Vente cash",
    "Depositaire 6.000Fc",
    "Depositaire 4.100Fc",
]

COMMISSION_FILTERS = [
    "Tous",
    "Maman",
    "Depositaire",
    "Vente cash",
    "Depositaire 6.000Fc",
    "Depositaire 4.100Fc",
]


def run_app() -> None:
    DatabaseHelper.initialize_database()
    post_update_notice = UpdateChecker.consume_post_update_notice()
    root = tk.Tk()
    root.title(f"{APP_NAME} - Connexion - v{APP_VERSION}")
    root.geometry("580x380")
    root.minsize(580, 380)
    root.configure(bg="#dfeaf4")
    configure_styles()
    LoginWindow(root, post_update_notice)
    center_window(root)
    root.mainloop()


def configure_styles() -> None:
    style = ttk.Style()
    try:
        style.theme_use("clam")
    except tk.TclError:
        pass
    style.configure("TLabel", font=("Segoe UI", 10))
    style.configure("Header.TLabel", font=("Segoe UI Semibold", 18))
    style.configure("Card.TLabelframe", padding=12)
    style.configure("Card.TLabelframe.Label", font=("Segoe UI Semibold", 11))
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


def center_window(window: tk.Misc) -> None:
    window.update_idletasks()
    width = window.winfo_width()
    height = window.winfo_height()

    if width <= 1 or height <= 1:
        geometry = str(window.winfo_geometry()).split("+")[0]
        if "x" in geometry:
            width_text, height_text = geometry.split("x", 1)
            try:
                width = int(width_text)
                height = int(height_text)
            except ValueError:
                width = window.winfo_reqwidth()
                height = window.winfo_reqheight()
        else:
            width = window.winfo_reqwidth()
            height = window.winfo_reqheight()

    x = max((window.winfo_screenwidth() - width) // 2, 0)
    y = max((window.winfo_screenheight() - height) // 2, 0)
    window.geometry(f"{width}x{height}+{x}+{y}")


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
            self.tree.heading(column, text=headings.get(column, column))
            self.tree.column(column, anchor="center", width=110, stretch=True)

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


class LoginWindow(ttk.Frame):
    def __init__(self, root: tk.Tk, post_update_notice: SessionNotice | None = None) -> None:
        super().__init__(root, padding=24)
        self.root = root
        self.post_update_notice = post_update_notice
        self.notice_label: ttk.Label | None = None
        self.pack(fill="both", expand=True)
        self.root.protocol("WM_DELETE_WINDOW", self.on_quit)
        self.build_ui()

    def build_ui(self) -> None:
        card = ttk.LabelFrame(self, text="Connexion", style="Card.TLabelframe", padding=18)
        card.pack(expand=True)

        ttk.Label(card, text=APP_NAME, style="Header.TLabel").grid(
            row=0, column=0, columnspan=2, pady=(0, 18)
        )

        ttk.Label(card, text=f"Version {APP_VERSION}", foreground="#5a6570").grid(
            row=1, column=0, columnspan=2, pady=(0, 12)
        )

        row_index = 2
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
        row_index += 1

        hint = ttk.Label(
            card,
            text="Compte par défaut disponible : identifiant admin",
            foreground="#444444",
        )
        hint.grid(row=row_index, column=0, columnspan=2, pady=(14, 0))

        card.columnconfigure(1, weight=1)
        user_entry.focus()
        user_entry.bind("<Return>", lambda _event: self.password_entry.focus())
        self.password_entry.bind("<Return>", lambda _event: self.login())

    def login(self) -> None:
        identifiant = self.user_var.get().strip()
        mot_de_passe = self.password_var.get().strip()
        if not identifiant:
            messagebox.showwarning("Connexion", "Veuillez entrer un identifiant.")
            return
        if not mot_de_passe:
            messagebox.showwarning("Connexion", "Veuillez entrer un mot de passe.")
            return

        user = DatabaseHelper.find_user_for_login(identifiant, mot_de_passe)
        if user is None:
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
        self.title(f"{APP_NAME} - Tableau de bord - v{APP_VERSION}")
        self.geometry("900x560")
        self.minsize(860, 520)
        self.configure(bg="#dfeaf4")
        self.protocol("WM_DELETE_WINDOW", self.on_close_app)
        self.build_ui()
        self.refresh_summary()
        center_window(self)
        self.bind("<FocusIn>", lambda _event: self.refresh_summary())
        self.after(1000, self.start_weekly_update_check)

    def build_ui(self) -> None:
        container = ttk.Frame(self, padding=20)
        container.pack(fill="both", expand=True)

        ttk.Label(
            container,
            text=f"Bienvenue, {self.user.identifiant} ({self.user.role})",
            style="Header.TLabel",
        ).pack(anchor="center", pady=(0, 18))

        ttk.Label(
            container,
            text=f"Version installee : {APP_VERSION}",
            foreground="#5a6570",
        ).pack(anchor="center", pady=(0, 12))

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

        actions = ttk.Frame(container)
        actions.pack(anchor="center", pady=(8, 0))
        ttk.Button(actions, text="Déconnexion", command=self.logout).grid(row=0, column=0, padx=8)
        ttk.Button(actions, text="Quitter", command=self.on_close_app).grid(row=0, column=1, padx=8)

        self.apply_permissions()

    def hide_notice(self) -> None:
        if self.notice_label is None:
            return
        self.notice_label.destroy()
        self.notice_label = None

    def apply_permissions(self) -> None:
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

    def refresh_summary(self) -> None:
        try:
            summary = (
                f"Utilisateurs : {DatabaseHelper.count_users()} | "
                f"Sorties stock : {DatabaseHelper.count_stock_exits()} | "
                f"Commandes avec dette : {DatabaseHelper.count_orders_with_debt()}\n"
                f"Total caisse : {format_fc(DatabaseHelper.get_total_cash())} | "
                f"Total commissions : {format_fc(DatabaseHelper.get_total_commissions())}"
            )
        except Exception:
            summary = "Statistiques indisponibles pour le moment."
        self.summary_var.set(summary)

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

        message += "\n\nVoulez-vous ouvrir le lien de telechargement ?"

        if messagebox.askyesno("Mise a jour disponible", message):
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

    def on_close_app(self) -> None:
        if not messagebox.askyesno("Confirmation", "Voulez-vous vraiment quitter l'application ?"):
            return
        self.root.destroy()


class BaseModuleWindow(tk.Toplevel):
    def __init__(self, parent: DashboardWindow, title: str, geometry: str) -> None:
        super().__init__(parent)
        self.parent = parent
        self.title(title)
        self.geometry(geometry)
        self.configure(bg="#eef3f8")
        self.transient(parent)
        self.grab_set()
        self.protocol("WM_DELETE_WINDOW", self.close_window)
        self.after(0, lambda: center_window(self))

    def close_window(self) -> None:
        self.destroy()


class UsersWindow(BaseModuleWindow):
    def __init__(self, parent: DashboardWindow) -> None:
        super().__init__(parent, "Gestion des utilisateurs", "1060x700")
        self.edit_mode = False
        self.original_identifiant = ""
        self.build_ui()
        self.refresh_users()

    def build_ui(self) -> None:
        container = ttk.Frame(self, padding=16)
        container.pack(fill="both", expand=True)

        ttk.Label(container, text="Gestion des utilisateurs", style="Header.TLabel").pack(pady=(0, 14))

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
        ttk.Entry(form, textvariable=self.password_var, show="*", width=34).grid(
            row=2, column=1, sticky="ew", pady=6
        )

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
        self.role_var.set(str(row["Role"]))
        self.original_identifiant = str(row["Identifiant"])
        self.edit_mode = True
        self.identifiant_entry.state(["disabled"])
        self.message_var.set("Le mot de passe peut rester vide pour être conservé.")

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
        container = ttk.Frame(self, padding=16)
        container.pack(fill="both", expand=True)
        ttk.Label(container, text="Gestion du stock", style="Header.TLabel").pack(pady=(0, 12))

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
        dialog.transient(self)
        dialog.grab_set()
        dialog.configure(bg="#eef3f8")
        frame = ttk.Frame(dialog, padding=16)
        frame.pack(fill="both", expand=True)

        variables = {
            "Farine": tk.StringVar(value=format_number(float(current["FarineInitial"]))),
            "Levure": tk.StringVar(value=format_number(float(current["LevureInitial"]))),
            "Sel": tk.StringVar(value=format_number(float(current["SelInitial"]))),
            "Huile": tk.StringVar(value=format_number(float(current["HuileInitial"]))),
        }

        for index, (label, variable) in enumerate(variables.items()):
            ttk.Label(frame, text=f"{label} initial").grid(row=index, column=0, sticky="w", pady=6)
            ttk.Entry(frame, textvariable=variable, width=20).grid(row=index, column=1, sticky="ew", pady=6)

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
        actions.grid(row=4, column=0, columnspan=2, pady=(12, 0))
        ttk.Button(actions, text="Enregistrer", command=save).grid(row=0, column=0, padx=6)
        ttk.Button(actions, text="Annuler", command=dialog.destroy).grid(row=0, column=1, padx=6)
        frame.columnconfigure(1, weight=1)
        center_window(dialog)

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
        self.build_ui()
        self.reset_form()
        self.refresh_orders()

    def build_ui(self) -> None:
        container = ttk.Frame(self, padding=16)
        container.pack(fill="both", expand=True)
        ttk.Label(container, text="Gestion des commandes", style="Header.TLabel").pack(pady=(0, 12))

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

        self.status_combo.bind("<<ComboboxSelected>>", lambda _event: self.recalculate_amounts())
        self.amount_received_var.trace_add("write", lambda *_args: self.recalculate_amounts())
        self.trays_var.trace_add("write", lambda *_args: self.recalculate_amounts())
        form.columnconfigure(1, weight=1)

    def _on_date_change(self) -> None:
        self.show_all_dates = False
        self.refresh_orders()

    def get_status_rate(self, status: str) -> float:
        rates = {
            "Maman": 6000,
            "Vente cash": 4350,
            "Depositaire 6.000Fc": 6000,
            "Depositaire 4.100Fc": 4100,
        }
        return float(rates.get(status, 0))

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
        status = self.status_var.get().strip()
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
        self.status_var.set(str(row["Statut"]))
        self.trays_var.set(str(int(row["NombreBacs"])))
        self.amount_received_var.set(format_number(float(row["MontantRecu"])))
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
        self.build_ui()
        self.reset_form()
        self.refresh_data()

    def build_ui(self) -> None:
        container = ttk.Frame(self, padding=16)
        container.pack(fill="both", expand=True)
        ttk.Label(container, text="Gestion de la caisse", style="Header.TLabel").pack(pady=(0, 12))

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
        self.balance_var = tk.StringVar()

        self._make_label_value(form, "Nombre total de bacs", self.total_trays_var, 1)
        self._make_label_value(form, "Montant attendu", self.expected_var, 2, "#7a0000")
        self._make_label_value(form, "Montant reçu", self.received_var, 3, "#006400")
        self._make_label_value(form, "Dettes", self.debts_var, 4, "#8b0000")

        ttk.Label(form, text="Montant total des dépenses").grid(row=5, column=0, sticky="w", pady=6)
        self.expenses_var = tk.StringVar(value="0")
        ttk.Entry(form, textvariable=self.expenses_var, width=28).grid(row=5, column=1, sticky="ew", pady=6)

        ttk.Label(form, text="Dépenses effectuées").grid(row=6, column=0, sticky="nw", pady=6)
        self.expenses_text = ScrolledText(form, width=28, height=7)
        self.expenses_text.grid(row=6, column=1, sticky="ew", pady=6)

        self._make_label_value(form, "Solde", self.balance_var, 7, "#1b2d5d")

        actions = ttk.Frame(form)
        actions.grid(row=8, column=0, columnspan=2, pady=(14, 0))
        ttk.Button(actions, text="Enregistrer", command=self.save_cash).grid(row=0, column=0, padx=4, pady=4)
        ttk.Button(actions, text="Modifier", command=self.load_cash_for_edit).grid(row=0, column=1, padx=4, pady=4)
        ttk.Button(actions, text="Supprimer", command=self.delete_cash).grid(row=0, column=2, padx=4, pady=4)
        ttk.Button(actions, text="Tout afficher", command=self.show_all).grid(row=1, column=0, padx=4, pady=4)
        ttk.Button(actions, text="Fermer", command=self.close_window).grid(row=1, column=1, padx=4, pady=4)

        self.summary_var = tk.StringVar()
        ttk.Label(form, textvariable=self.summary_var, wraplength=420, justify="left").grid(
            row=9, column=0, columnspan=2, sticky="ew", pady=(14, 0)
        )

        table_frame = ttk.LabelFrame(content, text="Historique de caisse", style="Card.TLabelframe")
        table_frame.pack(side="left", fill="both", expand=True)
        self.table = DataTable(table_frame, height=22)
        self.table.pack(fill="both", expand=True)

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
            self.expenses_var.set(format_number(float(cash["MontantTotalDepenses"])))
            self.expenses_text.delete("1.0", "end")
            self.expenses_text.insert("1.0", str(cash["DepensesEffectuees"]))
        else:
            self.selected_cash_id = 0
            self.expenses_var.set("0")
            self.expenses_text.delete("1.0", "end")

        self.calculate_balance()

    def calculate_balance(self) -> None:
        try:
            expenses = parse_optional_float(self.expenses_var.get())
        except ValueError:
            expenses = 0
        balance = self.expected_today - expenses
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
        expenses = parse_optional_float(self.expenses_var.get())
        balance = self.expected_today - expenses

        if self.show_all_dates:
            summary = DatabaseHelper.get_global_orders_summary()
            text = (
                "Affichage : toutes les dates\n"
                f"Fiches caisse : {row_count}\n"
                f"Total bacs : {int(summary.get('TotalBacs', 0))} | "
                f"Attendu : {format_fc(float(summary.get('MontantAttendu', 0)))} | "
                f"Reçu : {format_fc(float(summary.get('MontantRecu', 0)))}\n"
                f"Dettes : {format_fc(float(summary.get('TotalDettes', 0)))} | "
                f"Solde global : {format_fc(total_global)}"
            )
        else:
            text = (
                f"Jour : {target_date.strftime('%d/%m/%Y')} | Bacs : {int(self.trays_today)}\n"
                f"Fiches caisse : {row_count} | Reçu : {format_fc(self.received_today)} | "
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
                "MontantTotalDepenses",
                "Solde",
                "DepensesEffectuees",
            ],
            headings={
                "DateCaisse": "Date",
                "NombreTotalBacs": "Bacs",
                "MontantAttendu": "Attendu",
                "MontantRecu": "Reçu",
                "TotalDettes": "Dettes",
                "MontantTotalDepenses": "Dépenses",
                "DepensesEffectuees": "Détails des dépenses",
            },
            hidden_columns=["Id"],
            formatters={
                "NombreTotalBacs": lambda value: f"{int(value)}",
                "MontantAttendu": lambda value: format_fc(float(value)),
                "MontantRecu": lambda value: format_fc(float(value)),
                "TotalDettes": lambda value: format_fc(float(value)),
                "MontantTotalDepenses": lambda value: format_fc(float(value)),
                "Solde": lambda value: format_fc(float(value)),
            },
        )
        self.update_summary(len(rows))

    def show_all(self) -> None:
        self.show_all_dates = True
        self.refresh_data()

    def save_cash(self) -> None:
        try:
            target_date = self.date_field.get_date()
            expenses = parse_optional_float(self.expenses_var.get())
        except Exception as exc:
            messagebox.showwarning("Caisse", str(exc))
            return

        details = self.expenses_text.get("1.0", "end").strip()
        if expenses > 0 and not details:
            messagebox.showwarning(
                "Caisse",
                "Veuillez décrire les dépenses effectuées avant d'enregistrer la caisse.",
            )
            return

        try:
            DatabaseHelper.save_cash_day(target_date, expenses, details)
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
        self.expenses_text.delete("1.0", "end")
        self.expenses_text.insert("1.0", str(row["DepensesEffectuees"]))
        self.load_day_summary()
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
        container = ttk.Frame(self, padding=16)
        container.pack(fill="both", expand=True)
        ttk.Label(container, text="Gestion des commissions", style="Header.TLabel").pack(pady=(0, 12))

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

        ttk.Label(form, text="Filtre statut").grid(row=8, column=0, sticky="w", pady=6)
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

        self.current_status = str(summary.get("Statut", ""))
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

    def apply_filter(self) -> None:
        filter_value = self.filter_var.get()
        rows = self.all_rows
        if filter_value == "Maman":
            rows = [row for row in rows if str(row["Statut"]) == "Maman"]
        elif filter_value == "Depositaire":
            rows = [row for row in rows if "Depositaire" in str(row["Statut"]) or "Dépositaire" in str(row["Statut"])]
        elif filter_value == "Vente cash":
            rows = [row for row in rows if str(row["Statut"]) in {"Vente cash", "VC"}]
        elif filter_value == "Depositaire 6.000Fc":
            rows = [
                row
                for row in rows
                if str(row["Statut"]) in {"Depositaire 6.000Fc", "Dépositaire 6.000Fc"}
            ]
        elif filter_value == "Depositaire 4.100Fc":
            rows = [
                row
                for row in rows
                if str(row["Statut"]) in {"Depositaire 4.100Fc", "Dépositaire 4.100Fc"}
            ]

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
        self.current_status = str(row["Statut"])
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
