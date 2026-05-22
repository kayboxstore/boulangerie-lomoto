from __future__ import annotations

import base64
import functools
import hashlib
import hmac
import os
import secrets
import shutil
import sqlite3
import threading
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Any, Iterator

from .connected_mode import (
    REMOTE_DATABASE_METHODS,
    ConnectionSettings,
    RemoteDatabaseClient,
    load_connection_settings,
    save_connection_settings,
)
from .status_labels import DEPOSITARY_STATUS, LEGACY_DEPOSITARY_6000_STATUS


DB_DATE_FORMAT = "%Y-%m-%d"
PASSWORD_PREFIX = "PBKDF2$"
PASSWORD_ITERATIONS = 100_000
DEFAULT_ADMIN_PASSWORD = "010203"
OUTSTANDING_DEBT_SQL = (
    "CASE WHEN IFNULL(Dette, 0) - IFNULL(DettePayee, 0) > 0 "
    "THEN IFNULL(Dette, 0) - IFNULL(DettePayee, 0) ELSE 0 END"
)
DEBT_STATUS_SQL = (
    "CASE "
    "WHEN IFNULL(Dette, 0) <= 0 THEN 'Sans dette' "
    "WHEN IFNULL(DettePayee, 0) >= IFNULL(Dette, 0) THEN 'Payée' "
    "WHEN IFNULL(DettePayee, 0) > 0 THEN 'Partiellement payée' "
    "ELSE 'En attente' END"
)


@dataclass
class AuthenticatedUser:
    identifiant: str
    role: str
    full_name: str = ""

    @property
    def display_name(self) -> str:
        value = self.full_name.strip()
        return value if value else self.identifiant


class DatabaseHelper:
    app_data_dir = Path(
        os.environ.get(
            "BOULANGERIE_APPDATA_DIR",
            str(
                Path(
                    os.environ.get(
                        "LOCALAPPDATA",
                        str(Path.home() / "AppData" / "Local"),
                    )
                )
                / "BoulangerieLomoto"
            ),
        )
    )
    db_path = app_data_dir / "boulangerie.db"
    backups_dir = app_data_dir / "sauvegardes"
    reports_dir = app_data_dir / "rapports"
    legacy_db_path = Path(__file__).resolve().parent.parent / "boulangerie.db"
    _connection_settings = ConnectionSettings()
    _connection_settings_loaded = False
    _remote_client: RemoteDatabaseClient | None = None
    _execution_context = threading.local()

    @classmethod
    def set_storage_root(cls, base_dir: Path) -> None:
        cls.app_data_dir = Path(base_dir)
        cls.db_path = cls.app_data_dir / "boulangerie.db"
        cls.backups_dir = cls.app_data_dir / "sauvegardes"
        cls.reports_dir = cls.app_data_dir / "rapports"
        cls.reload_connection_settings()

    @classmethod
    def apply_connection_settings(cls, settings: ConnectionSettings, persist: bool = False) -> None:
        normalized_settings = ConnectionSettings(
            mode=settings.normalized_mode(),
            server_url=settings.normalized_url(),
            api_token=settings.api_token.strip(),
        )
        if persist:
            save_connection_settings(cls.app_data_dir, normalized_settings)
        cls._connection_settings = normalized_settings
        cls._connection_settings_loaded = True
        cls._remote_client = (
            RemoteDatabaseClient(
                normalized_settings.normalized_url(),
                api_token=normalized_settings.api_token,
            )
            if normalized_settings.is_remote()
            else None
        )

    @classmethod
    def reload_connection_settings(cls) -> ConnectionSettings:
        cls._connection_settings_loaded = False
        cls._remote_client = None
        return cls.get_connection_settings()

    @classmethod
    def get_connection_settings(cls) -> ConnectionSettings:
        if not cls._connection_settings_loaded:
            settings = load_connection_settings(cls.app_data_dir)
            cls.apply_connection_settings(settings, persist=False)
        return ConnectionSettings(
            mode=cls._connection_settings.mode,
            server_url=cls._connection_settings.server_url,
            api_token=cls._connection_settings.api_token,
        )

    @classmethod
    def save_connection_settings(cls, settings: ConnectionSettings) -> Path:
        cls.apply_connection_settings(settings, persist=True)
        return cls.app_data_dir / "connection_settings.json"

    @classmethod
    def is_remote_mode(cls) -> bool:
        return cls._should_use_remote()

    @classmethod
    def get_connection_status_text(cls) -> str:
        settings = cls.get_connection_settings()
        if settings.is_remote():
            return f"Mode connecté - Serveur central : {settings.normalized_url()}"
        return "Mode local - données stockées sur ce poste"

    @classmethod
    @contextmanager
    def local_calls_only(cls) -> Iterator[None]:
        previous = bool(getattr(cls._execution_context, "force_local", False))
        cls._execution_context.force_local = True
        try:
            yield
        finally:
            cls._execution_context.force_local = previous

    @classmethod
    def invoke_local_method(cls, method_name: str, *args: Any, **kwargs: Any) -> Any:
        with cls.local_calls_only():
            return getattr(cls, method_name)(*args, **kwargs)

    @classmethod
    def _should_use_remote(cls) -> bool:
        if bool(getattr(cls._execution_context, "force_local", False)):
            return False
        settings = cls.get_connection_settings()
        return settings.is_remote() and cls._remote_client is not None

    @classmethod
    def _remote_call(cls, method_name: str, *args: Any, **kwargs: Any) -> Any:
        if cls._remote_client is None:
            raise RuntimeError("Le client distant n'est pas initialis?.")

        result = cls._remote_client.call(method_name, *args, **kwargs)
        if method_name == "find_user_for_login" and result:
            if not isinstance(result, dict):
                raise RuntimeError("La réponse du serveur central pour la connexion est invalide.")
            result.pop("__remote_dataclass__", None)
            return AuthenticatedUser(
                identifiant=str(result.get("identifiant", "")),
                role=str(result.get("role", "")),
                full_name=str(result.get("full_name", "")),
            )
        return result

    @classmethod
    @contextmanager
    def connect(cls) -> Iterator[sqlite3.Connection]:
        connection = sqlite3.connect(cls.db_path, timeout=10)
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA foreign_keys = ON")
        connection.execute("PRAGMA busy_timeout = 10000")
        try:
            yield connection
            connection.commit()
        except Exception:
            connection.rollback()
            raise
        finally:
            connection.close()

    @classmethod
    def initialize_database(cls) -> None:
        if cls._should_use_remote():
            cls.app_data_dir.mkdir(parents=True, exist_ok=True)
            cls.backups_dir.mkdir(parents=True, exist_ok=True)
            cls.reports_dir.mkdir(parents=True, exist_ok=True)
            return

        cls.initialize_local_database()

    @classmethod
    def initialize_local_database(cls) -> None:
        cls.db_path.parent.mkdir(parents=True, exist_ok=True)
        cls.backups_dir.mkdir(parents=True, exist_ok=True)
        cls.reports_dir.mkdir(parents=True, exist_ok=True)
        if (
            not cls.db_path.exists()
            and cls.legacy_db_path.exists()
            and cls.legacy_db_path.resolve() != cls.db_path.resolve()
        ):
            shutil.copy2(cls.legacy_db_path, cls.db_path)
        with cls.connect() as connection:
            cls._create_tables(connection)
            cls._migrate_stock_configuration_table(connection)
            cls._migrate_cash_table(connection)
            cls._migrate_orders_table(connection)
            cls._migrate_order_debt_payment_columns(connection)
            cls._migrate_commissions_table(connection)
            cls._normalize_status_values(connection)
            cls._recalculate_debt_payments(connection)
            cls._sync_all_commissions(connection)
            cls._insert_default_admin(connection)
            cls._insert_default_stock_config(connection)
        pragma_connection: sqlite3.Connection | None = None
        try:
            pragma_connection = sqlite3.connect(cls.db_path, timeout=10)
            pragma_connection.execute("PRAGMA journal_mode = WAL")
        finally:
            if pragma_connection is not None:
                pragma_connection.close()

    @classmethod
    def _timestamp_for_filename(cls) -> str:
        return datetime.now().strftime("%Y%m%d-%H%M%S")

    @staticmethod
    def _coerce_date(value: date | str) -> date:
        if isinstance(value, date):
            return value
        return datetime.strptime(str(value).strip(), DB_DATE_FORMAT).date()

    @classmethod
    def build_backup_path(cls, prefix: str = "boulangerie-lomoto-backup") -> Path:
        cls.backups_dir.mkdir(parents=True, exist_ok=True)
        return cls.backups_dir / f"{prefix}-{cls._timestamp_for_filename()}.db"

    @classmethod
    def get_backups_directory(cls) -> Path:
        cls.backups_dir.mkdir(parents=True, exist_ok=True)
        return cls.backups_dir

    @classmethod
    def list_backup_files(cls, limit: int = 200) -> list[dict[str, Any]]:
        backup_dir = cls.get_backups_directory()
        max_items = max(int(limit), 0)
        if max_items == 0:
            return []

        rows: list[dict[str, Any]] = []
        try:
            candidates = sorted(
                backup_dir.iterdir(),
                key=lambda path: path.stat().st_mtime,
                reverse=True,
            )
        except OSError:
            return rows

        for backup_path in candidates:
            if not backup_path.is_file():
                continue
            try:
                stat = backup_path.stat()
            except OSError:
                continue
            rows.append(
                {
                    "NomFichier": backup_path.name,
                    "CheminComplet": backup_path,
                    "TailleOctets": int(stat.st_size),
                    "DateModification": datetime.fromtimestamp(stat.st_mtime),
                }
            )
            if len(rows) >= max_items:
                break
        return rows

    @classmethod
    def build_report_path(cls, prefix: str = "rapport-journalier") -> Path:
        cls.reports_dir.mkdir(parents=True, exist_ok=True)
        return cls.reports_dir / f"{prefix}-{cls._timestamp_for_filename()}.pdf"

    @staticmethod
    def _safe_folder_name(value: str) -> str:
        sanitized = "".join(
            character if character.isalnum() or character in {"-", "_"} else "_"
            for character in value.strip()
        )
        return sanitized or "utilisateur"

    @classmethod
    def get_reports_dir_for_user(cls, identifiant: str) -> Path:
        target_dir = cls.reports_dir / cls._safe_folder_name(identifiant)
        target_dir.mkdir(parents=True, exist_ok=True)
        return target_dir

    @classmethod
    def _validate_sqlite_database(cls, database_path: Path) -> None:
        connection: sqlite3.Connection | None = None
        try:
            connection = sqlite3.connect(database_path)
            connection.execute("SELECT name FROM sqlite_master LIMIT 1").fetchone()
        except sqlite3.DatabaseError as exc:
            raise ValueError("Le fichier sélectionné n'est pas une base SQLite valide.") from exc
        finally:
            if connection is not None:
                connection.close()

    @classmethod
    def backup_database(cls, destination: Path | None = None) -> Path:
        if cls._should_use_remote():
            raise RuntimeError(
                "Les sauvegardes locales sont désactivées en mode connecté. Utilisez le poste serveur central."
            )
        cls.initialize_database()
        target_path = Path(destination) if destination is not None else cls.build_backup_path()
        target_path.parent.mkdir(parents=True, exist_ok=True)

        if target_path.resolve() == cls.db_path.resolve():
            raise ValueError("Le fichier de sauvegarde doit être différent de la base active.")

        if target_path.exists():
            target_path.unlink()

        source_connection: sqlite3.Connection | None = None
        target_connection: sqlite3.Connection | None = None
        try:
            source_connection = sqlite3.connect(cls.db_path, timeout=10)
            target_connection = sqlite3.connect(target_path, timeout=10)
            source_connection.backup(target_connection)
        finally:
            if target_connection is not None:
                target_connection.close()
            if source_connection is not None:
                source_connection.close()

        return target_path

    @classmethod
    def restore_database(cls, source_path: str | Path) -> tuple[Path | None, Path]:
        if cls._should_use_remote():
            raise RuntimeError(
                "La restauration locale est désactivée en mode connecté. Utilisez le poste serveur central."
            )
        cls.backups_dir.mkdir(parents=True, exist_ok=True)
        source = Path(source_path)
        if not source.exists():
            raise FileNotFoundError("Le fichier de sauvegarde est introuvable.")
        if source.resolve() == cls.db_path.resolve():
            raise ValueError("Impossible de restaurer directement la base active.")

        cls._validate_sqlite_database(source)

        safety_backup: Path | None = None
        if cls.db_path.exists():
            safety_backup = cls.backup_database(cls.build_backup_path("avant-restauration"))

        source_connection: sqlite3.Connection | None = None
        target_connection: sqlite3.Connection | None = None
        try:
            source_connection = sqlite3.connect(source, timeout=10)
            target_connection = sqlite3.connect(cls.db_path, timeout=10)
            source_connection.backup(target_connection)
        finally:
            if target_connection is not None:
                target_connection.close()
            if source_connection is not None:
                source_connection.close()

        with cls.connect() as connection:
            cls._create_tables(connection)
            cls._migrate_stock_configuration_table(connection)
            cls._migrate_cash_table(connection)
            cls._migrate_orders_table(connection)
            cls._migrate_commissions_table(connection)
            cls._normalize_status_values(connection)
            cls._insert_default_admin(connection)
            cls._insert_default_stock_config(connection)

        return safety_backup, cls.db_path

    @classmethod
    def _create_tables(cls, connection: sqlite3.Connection) -> None:
        connection.executescript(
            """
            CREATE TABLE IF NOT EXISTS Utilisateurs (
                Id INTEGER PRIMARY KEY AUTOINCREMENT,
                NomComplet TEXT NOT NULL,
                Identifiant TEXT NOT NULL UNIQUE,
                MotDePasse TEXT NOT NULL,
                Role TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS ConfigurationStock (
                Id INTEGER PRIMARY KEY CHECK (Id = 1),
                FarineInitial REAL NOT NULL,
                LevureInitial REAL NOT NULL,
                SelInitial REAL NOT NULL,
                HuileInitial REAL NOT NULL,
                FarineAlerteMin REAL NOT NULL DEFAULT 20,
                LevureAlerteMin REAL NOT NULL DEFAULT 16,
                SelAlerteMin REAL NOT NULL DEFAULT 10,
                HuileAlerteMin REAL NOT NULL DEFAULT 12
            );

            CREATE TABLE IF NOT EXISTS StockSorties (
                Id INTEGER PRIMARY KEY AUTOINCREMENT,
                DateSortie TEXT NOT NULL,
                SacsUtilises REAL NOT NULL,
                PaquetsUtilises REAL NOT NULL,
                KgSelUtilises REAL NOT NULL,
                LitresHuileUtilises REAL NOT NULL
            );

            CREATE TABLE IF NOT EXISTS StockJournalier (
                Id INTEGER PRIMARY KEY AUTOINCREMENT,
                DateJour TEXT NOT NULL UNIQUE,
                FarineOuverture REAL NOT NULL,
                LevureOuverture REAL NOT NULL,
                SelOuverture REAL NOT NULL,
                HuileOuverture REAL NOT NULL,
                FarineCloture REAL NOT NULL,
                LevureCloture REAL NOT NULL,
                SelCloture REAL NOT NULL,
                HuileCloture REAL NOT NULL
            );

            CREATE TABLE IF NOT EXISTS CaisseVentes (
                Id INTEGER PRIMARY KEY AUTOINCREMENT,
                DateVente TEXT NOT NULL,
                Produit TEXT NOT NULL,
                Quantite INTEGER NOT NULL,
                PrixUnitaire REAL NOT NULL,
                Total REAL NOT NULL
            );

            CREATE TABLE IF NOT EXISTS CaisseJournaliere (
                Id INTEGER PRIMARY KEY AUTOINCREMENT,
                DateCaisse TEXT NOT NULL UNIQUE,
                MontantTotalDepenses REAL NOT NULL,
                DepensesEffectuees TEXT NOT NULL,
                DettesPayeesAujourdHui REAL NOT NULL DEFAULT 0,
                DettesPayeesDetails TEXT NOT NULL DEFAULT ''
            );

            CREATE TABLE IF NOT EXISTS Commandes (
                Id INTEGER PRIMARY KEY AUTOINCREMENT,
                DateCommande TEXT NOT NULL,
                Client TEXT NOT NULL,
                Statut TEXT NOT NULL,
                NombreBacs INTEGER NOT NULL,
                MontantAPercevoir REAL NOT NULL,
                MontantRecu REAL NOT NULL,
                Dette REAL NOT NULL,
                DettePayee REAL NOT NULL DEFAULT 0,
                DetteSoldee INTEGER NOT NULL DEFAULT 0
            );

            CREATE TABLE IF NOT EXISTS Commissions (
                Id INTEGER PRIMARY KEY AUTOINCREMENT,
                DateCommission TEXT NOT NULL,
                Nom TEXT NOT NULL,
                Statut TEXT NOT NULL,
                NombreBacs INTEGER NOT NULL,
                MontantPaye REAL NOT NULL,
                Commissions REAL NOT NULL,
                Dettes REAL NOT NULL,
                NetAPayer REAL NOT NULL
            );

            CREATE TABLE IF NOT EXISTS CloturesJournalieres (
                Id INTEGER PRIMARY KEY AUTOINCREMENT,
                DateJour TEXT NOT NULL UNIQUE,
                DateCloture TEXT NOT NULL,
                Identifiant TEXT NOT NULL,
                NomComplet TEXT NOT NULL,
                Role TEXT NOT NULL,
                CheminRapport TEXT NOT NULL DEFAULT '',
                CheminSauvegarde TEXT NOT NULL DEFAULT '',
                EstReouverte INTEGER NOT NULL DEFAULT 0,
                DateReouverture TEXT NOT NULL DEFAULT '',
                ReouvertParIdentifiant TEXT NOT NULL DEFAULT '',
                ReouvertParNomComplet TEXT NOT NULL DEFAULT '',
                ReouvertParRole TEXT NOT NULL DEFAULT '',
                MotifReouverture TEXT NOT NULL DEFAULT ''
            );

            CREATE TABLE IF NOT EXISTS HistoriqueActions (
                Id INTEGER PRIMARY KEY AUTOINCREMENT,
                DateAction TEXT NOT NULL,
                Identifiant TEXT NOT NULL,
                NomComplet TEXT NOT NULL,
                Role TEXT NOT NULL,
                Module TEXT NOT NULL,
                Action TEXT NOT NULL,
                Details TEXT NOT NULL DEFAULT ''
            );
            """
        )

    @classmethod
    def _normalize_status_values(cls, connection: sqlite3.Connection) -> None:
        for table_name in ("Commandes", "Commissions"):
            connection.execute(
                f"""
                UPDATE {table_name}
                SET Statut = CASE
                    WHEN Statut IN ('Depositaire', 'Dépositaire', 'Depositaire 4.100Fc', 'Dépositaire 4.100Fc')
                        THEN ?
                    WHEN Statut IN ('Depositaire 6.000Fc', 'Dépositaire 6.000Fc')
                        THEN ?
                    ELSE Statut
                END
                WHERE Statut IN (
                    'Depositaire',
                    'Dépositaire',
                    'Depositaire 4.100Fc',
                    'Dépositaire 4.100Fc',
                    'Depositaire 6.000Fc',
                    'Dépositaire 6.000Fc'
                )
                """,
                (DEPOSITARY_STATUS, LEGACY_DEPOSITARY_6000_STATUS),
            )

    @classmethod
    def _migrate_stock_configuration_table(cls, connection: sqlite3.Connection) -> None:
        columns = cls._table_columns(connection, "ConfigurationStock")
        if not columns:
            return

        default_thresholds = {
            "FarineAlerteMin": 20,
            "LevureAlerteMin": 16,
            "SelAlerteMin": 10,
            "HuileAlerteMin": 12,
        }
        for column_name, default_value in default_thresholds.items():
            if column_name in columns:
                continue
            connection.execute(
                f"""
                ALTER TABLE ConfigurationStock
                ADD COLUMN {column_name} REAL NOT NULL DEFAULT {default_value}
                """
            )

    @classmethod
    def _migrate_cash_table(cls, connection: sqlite3.Connection) -> None:
        columns = cls._table_columns(connection, "CaisseJournaliere")
        if not columns:
            return
        if "DettesPayeesAujourdHui" not in columns:
            connection.execute(
                """
                ALTER TABLE CaisseJournaliere
                ADD COLUMN DettesPayeesAujourdHui REAL NOT NULL DEFAULT 0
                """
            )
        if "DettesPayeesDetails" not in columns:
            connection.execute(
                """
                ALTER TABLE CaisseJournaliere
                ADD COLUMN DettesPayeesDetails TEXT NOT NULL DEFAULT ''
                """
            )

    @classmethod
    def _migrate_orders_table(cls, connection: sqlite3.Connection) -> None:
        columns = cls._table_columns(connection, "Commandes")
        if not columns:
            return

        has_new_schema = {
            "DateCommande",
            "Client",
            "Statut",
            "NombreBacs",
            "MontantAPercevoir",
            "MontantRecu",
            "Dette",
        }.issubset(columns) and "Produit" not in columns
        if has_new_schema:
            return

        connection.execute("DROP TABLE IF EXISTS Commandes_Nouvelle")
        connection.execute(
            """
            CREATE TABLE Commandes_Nouvelle (
                Id INTEGER PRIMARY KEY AUTOINCREMENT,
                DateCommande TEXT NOT NULL,
                Client TEXT NOT NULL,
                Statut TEXT NOT NULL,
                NombreBacs INTEGER NOT NULL,
                MontantAPercevoir REAL NOT NULL,
                MontantRecu REAL NOT NULL,
                Dette REAL NOT NULL,
                DettePayee REAL NOT NULL DEFAULT 0,
                DetteSoldee INTEGER NOT NULL DEFAULT 0
            )
            """
        )

        if "Produit" in columns:
            connection.execute(
                """
                INSERT INTO Commandes_Nouvelle
                    (Id, DateCommande, Client, Statut, NombreBacs, MontantAPercevoir, MontantRecu, Dette)
                SELECT
                    Id,
                    DateCommande,
                    Client,
                    Statut,
                    Quantite,
                    Montant,
                    Montant,
                    0
                FROM Commandes
                """
            )
        else:
            try:
                connection.execute(
                    """
                    INSERT INTO Commandes_Nouvelle
                        (Id, DateCommande, Client, Statut, NombreBacs, MontantAPercevoir, MontantRecu, Dette, DettePayee, DetteSoldee)
                    SELECT
                        Id,
                        DateCommande,
                        Client,
                        IFNULL(Statut, ''),
                        IFNULL(NombreBacs, 0),
                        IFNULL(MontantAPercevoir, 0),
                        IFNULL(MontantRecu, 0),
                        IFNULL(Dette, 0),
                        IFNULL(DettePayee, 0),
                        IFNULL(DetteSoldee, 0)
                    FROM Commandes
                    """
                )
            except sqlite3.DatabaseError:
                pass

        connection.execute("DROP TABLE Commandes")
        connection.execute("ALTER TABLE Commandes_Nouvelle RENAME TO Commandes")

    @classmethod
    def _migrate_order_debt_payment_columns(cls, connection: sqlite3.Connection) -> None:
        columns = cls._table_columns(connection, "Commandes")
        if not columns:
            return
        if "DettePayee" not in columns:
            connection.execute(
                """
                ALTER TABLE Commandes
                ADD COLUMN DettePayee REAL NOT NULL DEFAULT 0
                """
            )
        if "DetteSoldee" not in columns:
            connection.execute(
                """
                ALTER TABLE Commandes
                ADD COLUMN DetteSoldee INTEGER NOT NULL DEFAULT 0
                """
            )

    @classmethod
    def _migrate_commissions_table(cls, connection: sqlite3.Connection) -> None:
        columns = cls._table_columns(connection, "Commissions")
        if not columns:
            return

        has_new_schema = {
            "DateCommission",
            "Nom",
            "Statut",
            "NombreBacs",
            "MontantPaye",
            "Commissions",
            "Dettes",
            "NetAPayer",
        }.issubset(columns)
        if has_new_schema:
            return

        connection.execute("DROP TABLE IF EXISTS Commissions_Nouvelle")
        connection.execute(
            """
            CREATE TABLE Commissions_Nouvelle (
                Id INTEGER PRIMARY KEY AUTOINCREMENT,
                DateCommission TEXT NOT NULL,
                Nom TEXT NOT NULL,
                Statut TEXT NOT NULL,
                NombreBacs INTEGER NOT NULL,
                MontantPaye REAL NOT NULL,
                Commissions REAL NOT NULL,
                Dettes REAL NOT NULL,
                NetAPayer REAL NOT NULL
            )
            """
        )

        if "Beneficiaire" in columns:
            connection.execute(
                """
                INSERT INTO Commissions_Nouvelle
                    (Id, DateCommission, Nom, Statut, NombreBacs, MontantPaye, Commissions, Dettes, NetAPayer)
                SELECT Id, DateCommission, Beneficiaire, '', 0, 0, Montant, 0, Montant
                FROM Commissions
                """
            )
        else:
            try:
                connection.execute(
                    """
                    INSERT INTO Commissions_Nouvelle
                        (Id, DateCommission, Nom, Statut, NombreBacs, MontantPaye, Commissions, Dettes, NetAPayer)
                    SELECT
                        Id,
                        DateCommission,
                        IFNULL(Nom, ''),
                        IFNULL(Statut, ''),
                        IFNULL(NombreBacs, 0),
                        IFNULL(MontantPaye, 0),
                        IFNULL(Commissions, 0),
                        IFNULL(Dettes, 0),
                        IFNULL(NetAPayer, 0)
                    FROM Commissions
                    """
                )
            except sqlite3.DatabaseError:
                pass

        connection.execute("DROP TABLE Commissions")
        connection.execute("ALTER TABLE Commissions_Nouvelle RENAME TO Commissions")

    @staticmethod
    def _table_columns(connection: sqlite3.Connection, table_name: str) -> set[str]:
        rows = connection.execute(f"PRAGMA table_info({table_name})").fetchall()
        return {row["name"] for row in rows}

    @classmethod
    def _insert_default_admin(cls, connection: sqlite3.Connection) -> None:
        count = connection.execute(
            "SELECT COUNT(*) FROM Utilisateurs WHERE Role = 'Admin'"
        ).fetchone()[0]
        if count:
            return

        connection.execute(
            """
            INSERT INTO Utilisateurs (NomComplet, Identifiant, MotDePasse, Role)
            VALUES (?, ?, ?, ?)
            """,
            ("Administrateur", "admin", cls.hash_password(DEFAULT_ADMIN_PASSWORD), "Admin"),
        )

    @classmethod
    def _insert_default_stock_config(cls, connection: sqlite3.Connection) -> None:
        count = connection.execute(
            "SELECT COUNT(*) FROM ConfigurationStock WHERE Id = 1"
        ).fetchone()[0]
        if count:
            return

        connection.execute(
            """
            INSERT INTO ConfigurationStock
                (
                    Id,
                    FarineInitial,
                    LevureInitial,
                    SelInitial,
                    HuileInitial,
                    FarineAlerteMin,
                    LevureAlerteMin,
                    SelAlerteMin,
                    HuileAlerteMin
                )
            VALUES (1, 100, 80, 50, 60, 20, 16, 10, 12)
            """
        )

    @staticmethod
    def hash_password(plain_password: str) -> str:
        salt = secrets.token_bytes(16)
        digest = hashlib.pbkdf2_hmac(
            "sha256",
            plain_password.encode("utf-8"),
            salt,
            PASSWORD_ITERATIONS,
            dklen=32,
        )
        salt_b64 = base64.b64encode(salt).decode("ascii")
        digest_b64 = base64.b64encode(digest).decode("ascii")
        return f"{PASSWORD_PREFIX}{PASSWORD_ITERATIONS}${salt_b64}${digest_b64}"

    @staticmethod
    def is_hashed_password(stored_password: str) -> bool:
        return stored_password.startswith(PASSWORD_PREFIX)

    @classmethod
    def verify_password(cls, candidate: str, stored_password: str) -> bool:
        if not cls.is_hashed_password(stored_password):
            return hmac.compare_digest(candidate, stored_password)

        parts = stored_password.split("$")
        if len(parts) != 4:
            return False

        try:
            iterations = int(parts[1])
            salt = base64.b64decode(parts[2])
            expected = base64.b64decode(parts[3])
        except (ValueError, TypeError):
            return False

        digest = hashlib.pbkdf2_hmac(
            "sha256",
            candidate.encode("utf-8"),
            salt,
            iterations,
            dklen=len(expected),
        )
        return hmac.compare_digest(expected, digest)

    @classmethod
    def add_user(cls, full_name: str, identifiant: str, password: str, role: str) -> None:
        with cls.connect() as connection:
            connection.execute(
                """
                INSERT INTO Utilisateurs (NomComplet, Identifiant, MotDePasse, Role)
                VALUES (?, ?, ?, ?)
                """,
                (full_name, identifiant, cls.hash_password(password), role),
            )

    @classmethod
    def update_user(
        cls,
        original_identifiant: str,
        full_name: str,
        password: str,
        role: str,
    ) -> int:
        with cls.connect() as connection:
            if password.strip():
                cursor = connection.execute(
                    """
                    UPDATE Utilisateurs
                    SET NomComplet = ?, MotDePasse = ?, Role = ?
                    WHERE Identifiant = ?
                    """,
                    (full_name, cls.hash_password(password), role, original_identifiant),
                )
            else:
                cursor = connection.execute(
                    """
                    UPDATE Utilisateurs
                    SET NomComplet = ?, Role = ?
                    WHERE Identifiant = ?
                    """,
                    (full_name, role, original_identifiant),
                )
            return cursor.rowcount

    @classmethod
    def find_user_for_login(cls, identifiant: str, password: str) -> AuthenticatedUser | None:
        with cls.connect() as connection:
            row = connection.execute(
                """
                SELECT NomComplet, Identifiant, MotDePasse, Role
                FROM Utilisateurs
                WHERE Identifiant = ?
                """,
                (identifiant,),
            ).fetchone()
            if row is None:
                return None

            stored_password = row["MotDePasse"]
            if not cls.verify_password(password, stored_password):
                return None

            if not cls.is_hashed_password(stored_password):
                connection.execute(
                    "UPDATE Utilisateurs SET MotDePasse = ? WHERE Identifiant = ?",
                    (cls.hash_password(password), row["Identifiant"]),
                )

            return AuthenticatedUser(
                identifiant=row["Identifiant"],
                role=row["Role"],
                full_name=row["NomComplet"] or "",
            )

    @classmethod
    def is_using_default_password(cls, identifiant: str) -> bool:
        stored_password = cls._fetch_value(
            "SELECT MotDePasse FROM Utilisateurs WHERE Identifiant = ?",
            (identifiant,),
        )
        if stored_password is None:
            return False
        return cls.verify_password(DEFAULT_ADMIN_PASSWORD, str(stored_password))

    @classmethod
    def change_user_password(
        cls,
        identifiant: str,
        current_password: str,
        new_password: str,
    ) -> None:
        normalized_identifiant = identifiant.strip()
        if not normalized_identifiant:
            raise ValueError("Utilisateur introuvable.")

        if not current_password.strip():
            raise ValueError("Veuillez saisir le mot de passe actuel.")
        if not new_password.strip():
            raise ValueError("Veuillez saisir le nouveau mot de passe.")
        if len(new_password.strip()) < 6:
            raise ValueError("Le nouveau mot de passe doit contenir au moins 6 caracteres.")

        with cls.connect() as connection:
            row = connection.execute(
                """
                SELECT MotDePasse
                FROM Utilisateurs
                WHERE Identifiant = ?
                """,
                (normalized_identifiant,),
            ).fetchone()
            if row is None:
                raise ValueError("Utilisateur introuvable.")

            stored_password = str(row["MotDePasse"])
            if not cls.verify_password(current_password, stored_password):
                raise ValueError("Le mot de passe actuel est incorrect.")
            if cls.verify_password(new_password, stored_password):
                raise ValueError("Le nouveau mot de passe doit etre different de l'ancien.")

            connection.execute(
                "UPDATE Utilisateurs SET MotDePasse = ? WHERE Identifiant = ?",
                (cls.hash_password(new_password), normalized_identifiant),
            )

    @classmethod
    def search_users_by_identifiant(cls, identifiant: str) -> list[dict[str, Any]]:
        return cls._fetch_all(
            """
            SELECT Id, NomComplet, Identifiant, '********' AS MotDePasse, Role
            FROM Utilisateurs
            WHERE Identifiant LIKE ?
            ORDER BY Identifiant
            """,
            (f"%{identifiant}%",),
        )

    @classmethod
    def delete_user(cls, identifiant: str) -> int:
        return cls._execute(
            "DELETE FROM Utilisateurs WHERE Identifiant = ?",
            (identifiant,),
        )

    @classmethod
    def list_users(cls) -> list[dict[str, Any]]:
        return cls._fetch_all(
            """
            SELECT Id, NomComplet, Identifiant, '********' AS MotDePasse, Role
            FROM Utilisateurs
            ORDER BY Id
            """
        )

    @classmethod
    def count_admins(cls) -> int:
        return int(
            cls._fetch_value("SELECT COUNT(*) FROM Utilisateurs WHERE Role = 'Admin'")
        )

    @classmethod
    def get_user_role(cls, identifiant: str) -> str:
        value = cls._fetch_value(
            "SELECT Role FROM Utilisateurs WHERE Identifiant = ?",
            (identifiant,),
        )
        return "" if value is None else str(value)

    @classmethod
    def count_users(cls) -> int:
        return int(cls._fetch_value("SELECT COUNT(*) FROM Utilisateurs"))

    @classmethod
    def get_stock_configuration(cls) -> dict[str, Any]:
        row = cls._fetch_one(
            """
            SELECT
                Id,
                FarineInitial,
                LevureInitial,
                SelInitial,
                HuileInitial,
                IFNULL(FarineAlerteMin, 20) AS FarineAlerteMin,
                IFNULL(LevureAlerteMin, 16) AS LevureAlerteMin,
                IFNULL(SelAlerteMin, 10) AS SelAlerteMin,
                IFNULL(HuileAlerteMin, 12) AS HuileAlerteMin
            FROM ConfigurationStock
            WHERE Id = 1
            """
        )
        return row or {}

    @classmethod
    def update_stock_configuration(
        cls,
        farine: float,
        levure: float,
        sel: float,
        huile: float,
        farine_alert: float | None = None,
        levure_alert: float | None = None,
        sel_alert: float | None = None,
        huile_alert: float | None = None,
    ) -> None:
        farine_alert = float(farine * 0.2 if farine_alert is None else farine_alert)
        levure_alert = float(levure * 0.2 if levure_alert is None else levure_alert)
        sel_alert = float(sel * 0.2 if sel_alert is None else sel_alert)
        huile_alert = float(huile * 0.2 if huile_alert is None else huile_alert)
        cls._execute(
            """
            UPDATE ConfigurationStock
            SET
                FarineInitial = ?,
                LevureInitial = ?,
                SelInitial = ?,
                HuileInitial = ?,
                FarineAlerteMin = ?,
                LevureAlerteMin = ?,
                SelAlerteMin = ?,
                HuileAlerteMin = ?
            WHERE Id = 1
            """,
            (
                farine,
                levure,
                sel,
                huile,
                farine_alert,
                levure_alert,
                sel_alert,
                huile_alert,
            ),
        )

    @classmethod
    def get_low_stock_alerts(cls) -> list[dict[str, Any]]:
        configuration = cls.get_stock_configuration()
        summary = cls.get_stock_summary()
        if not configuration or not summary:
            return []

        definitions = [
            ("Farine", "sacs", "FarineInitial", "FarineAlerteMin", "FarineRestante"),
            ("Levure", "paquets", "LevureInitial", "LevureAlerteMin", "LevureRestante"),
            ("Sel", "kg", "SelInitial", "SelAlerteMin", "SelRestant"),
            ("Huile", "litres", "HuileInitial", "HuileAlerteMin", "HuileRestante"),
        ]
        alerts: list[dict[str, Any]] = []
        for article, unite, initial_key, threshold_key, remaining_key in definitions:
            initial_value = float(configuration.get(initial_key, 0) or 0)
            threshold_value = float(configuration.get(threshold_key, 0) or 0)
            remaining_value = float(summary.get(remaining_key, 0) or 0)
            if remaining_value > threshold_value:
                continue
            alerts.append(
                {
                    "Article": article,
                    "Unite": unite,
                    "StockInitial": initial_value,
                    "SeuilAlerte": threshold_value,
                    "StockRestant": remaining_value,
                    "Niveau": "critique" if remaining_value <= max(threshold_value * 0.5, 0) else "attention",
                }
            )
        return alerts

    @classmethod
    def get_stock_summary(cls, exclude_exit_id: int = 0) -> dict[str, Any]:
        sql = """
            SELECT
                p.FarineInitial - IFNULL(SUM(s.SacsUtilises), 0) AS FarineRestante,
                p.LevureInitial - IFNULL(SUM(s.PaquetsUtilises), 0) AS LevureRestante,
                p.SelInitial - IFNULL(SUM(s.KgSelUtilises), 0) AS SelRestant,
                p.HuileInitial - IFNULL(SUM(s.LitresHuileUtilises), 0) AS HuileRestante
            FROM ConfigurationStock p
            LEFT JOIN StockSorties s ON 1 = 1
        """
        params: list[Any] = []
        if exclude_exit_id > 0:
            sql += " AND s.Id <> ?"
            params.append(exclude_exit_id)

        sql += """
            WHERE p.Id = 1
            GROUP BY p.FarineInitial, p.LevureInitial, p.SelInitial, p.HuileInitial
        """
        return cls._fetch_one(sql, tuple(params)) or {}

    @classmethod
    def initialize_stock_day(cls, target_date: date) -> bool:
        date_text = target_date.strftime(DB_DATE_FORMAT)
        if int(
            cls._fetch_value(
                "SELECT COUNT(*) FROM StockJournalier WHERE DateJour = ?",
                (date_text,),
            )
        ):
            return False

        summary = cls.get_stock_summary()
        if not summary:
            return False

        cls._execute(
            """
            INSERT INTO StockJournalier (
                DateJour,
                FarineOuverture,
                LevureOuverture,
                SelOuverture,
                HuileOuverture,
                FarineCloture,
                LevureCloture,
                SelCloture,
                HuileCloture
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                date_text,
                summary["FarineRestante"],
                summary["LevureRestante"],
                summary["SelRestant"],
                summary["HuileRestante"],
                summary["FarineRestante"],
                summary["LevureRestante"],
                summary["SelRestant"],
                summary["HuileRestante"],
            ),
        )
        return True

    @classmethod
    def get_stock_journal(cls, target_date: date) -> dict[str, Any]:
        row = cls._fetch_one(
            """
            SELECT
                Id,
                DateJour,
                FarineOuverture,
                LevureOuverture,
                SelOuverture,
                HuileOuverture,
                FarineCloture,
                LevureCloture,
                SelCloture,
                HuileCloture
            FROM StockJournalier
            WHERE DateJour = ?
            """,
            (target_date.strftime(DB_DATE_FORMAT),),
        )
        return row or {}

    @classmethod
    def update_stock_closing(cls, target_date: date) -> None:
        if cls.is_day_closed(target_date):
            return
        summary = cls.get_stock_summary()
        if not summary:
            return

        cls._execute(
            """
            UPDATE StockJournalier
            SET
                FarineCloture = ?,
                LevureCloture = ?,
                SelCloture = ?,
                HuileCloture = ?
            WHERE DateJour = ?
            """,
            (
                summary["FarineRestante"],
                summary["LevureRestante"],
                summary["SelRestant"],
                summary["HuileRestante"],
                target_date.strftime(DB_DATE_FORMAT),
            ),
        )

    @classmethod
    def count_stock_exits(cls) -> int:
        return int(cls._fetch_value("SELECT COUNT(*) FROM StockSorties"))

    @classmethod
    def list_stock_exits(cls) -> list[dict[str, Any]]:
        return cls._fetch_all(
            """
            SELECT Id, DateSortie, SacsUtilises, PaquetsUtilises, KgSelUtilises, LitresHuileUtilises
            FROM StockSorties
            ORDER BY DateSortie DESC, Id DESC
            """
        )

    @classmethod
    def list_stock_exits_by_date(cls, target_date: date) -> list[dict[str, Any]]:
        return cls._fetch_all(
            """
            SELECT Id, DateSortie, SacsUtilises, PaquetsUtilises, KgSelUtilises, LitresHuileUtilises
            FROM StockSorties
            WHERE DateSortie = ?
            ORDER BY Id DESC
            """,
            (target_date.strftime(DB_DATE_FORMAT),),
        )

    @classmethod
    def add_stock_exit(
        cls,
        target_date: date,
        sacs: float,
        paquets: float,
        kg_sel: float,
        litres_huile: float,
    ) -> None:
        cls.ensure_day_open_for_write(target_date, "le stock")
        cls._execute(
            """
            INSERT INTO StockSorties (
                DateSortie, SacsUtilises, PaquetsUtilises, KgSelUtilises, LitresHuileUtilises
            )
            VALUES (?, ?, ?, ?, ?)
            """,
            (
                target_date.strftime(DB_DATE_FORMAT),
                sacs,
                paquets,
                kg_sel,
                litres_huile,
            ),
        )

    @classmethod
    def update_stock_exit(
        cls,
        exit_id: int,
        target_date: date,
        sacs: float,
        paquets: float,
        kg_sel: float,
        litres_huile: float,
    ) -> int:
        original_date_text = cls._get_record_date_text("StockSorties", "DateSortie", exit_id)
        cls._ensure_update_dates_open("le stock", original_date_text, target_date)
        return cls._execute(
            """
            UPDATE StockSorties
            SET
                DateSortie = ?,
                SacsUtilises = ?,
                PaquetsUtilises = ?,
                KgSelUtilises = ?,
                LitresHuileUtilises = ?
            WHERE Id = ?
            """,
            (
                target_date.strftime(DB_DATE_FORMAT),
                sacs,
                paquets,
                kg_sel,
                litres_huile,
                exit_id,
            ),
        )

    @classmethod
    def delete_stock_exit(cls, exit_id: int) -> int:
        original_date_text = cls._get_record_date_text("StockSorties", "DateSortie", exit_id)
        if original_date_text:
            cls.ensure_day_open_for_write(original_date_text, "le stock")
        return cls._execute("DELETE FROM StockSorties WHERE Id = ?", (exit_id,))

    @classmethod
    def get_orders_summary_for_date(cls, target_date: date) -> dict[str, Any]:
        row = cls._fetch_one(
            f"""
            SELECT
                IFNULL(SUM(NombreBacs), 0) AS NombreTotalBacs,
                IFNULL(SUM(MontantAPercevoir), 0) AS MontantAttendu,
                IFNULL(SUM(MontantRecu), 0) AS MontantRecu,
                IFNULL(SUM({OUTSTANDING_DEBT_SQL}), 0) AS TotalDettes
            FROM Commandes
            WHERE DateCommande = ?
            """,
            (target_date.strftime(DB_DATE_FORMAT),),
        )
        return row or {}

    @classmethod
    def get_global_orders_summary(cls) -> dict[str, Any]:
        row = cls._fetch_one(
            f"""
            SELECT
                COUNT(*) AS NombreCommandes,
                IFNULL(SUM(NombreBacs), 0) AS TotalBacs,
                IFNULL(SUM(MontantAPercevoir), 0) AS MontantAttendu,
                IFNULL(SUM(MontantRecu), 0) AS MontantRecu,
                IFNULL(SUM({OUTSTANDING_DEBT_SQL}), 0) AS TotalDettes,
                IFNULL(SUM(CASE WHEN {OUTSTANDING_DEBT_SQL} > 0 THEN 1 ELSE 0 END), 0) AS NombreAvecDette
            FROM Commandes
            """
        )
        return row or {}

    @classmethod
    def get_cash_for_date(cls, target_date: date) -> dict[str, Any]:
        row = cls._fetch_one(
            """
            SELECT
                Id,
                DateCaisse,
                MontantTotalDepenses,
                DepensesEffectuees,
                IFNULL(DettesPayeesAujourdHui, 0) AS DettesPayeesAujourdHui,
                IFNULL(DettesPayeesDetails, '') AS DettesPayeesDetails
            FROM CaisseJournaliere
            WHERE DateCaisse = ?
            """,
            (target_date.strftime(DB_DATE_FORMAT),),
        )
        return row or {}

    @classmethod
    def get_accumulated_debt_totals_for_date(cls, target_date: date) -> dict[str, Any]:
        date_text = target_date.strftime(DB_DATE_FORMAT)
        total_previous_debts = float(
            cls._fetch_value(
                "SELECT IFNULL(SUM(Dette), 0) FROM Commandes WHERE DateCommande < ?",
                (date_text,),
            )
            or 0
        )
        paid_before_date = float(
            cls._fetch_value(
                """
                SELECT IFNULL(SUM(DettesPayeesAujourdHui), 0)
                FROM CaisseJournaliere
                WHERE DateCaisse < ?
                """,
                (date_text,),
            )
            or 0
        )
        paid_on_date = float(
            cls._fetch_value(
                """
                SELECT IFNULL(SUM(DettesPayeesAujourdHui), 0)
                FROM CaisseJournaliere
                WHERE DateCaisse = ?
                """,
                (date_text,),
            )
            or 0
        )
        accumulated_before_payment = max(total_previous_debts - paid_before_date, 0.0)
        remaining_after_saved_payment = max(accumulated_before_payment - paid_on_date, 0.0)
        return {
            "TotalDettesJoursPrecedents": total_previous_debts,
            "DettesPayeesAvantDate": paid_before_date,
            "DettesPayeesDate": paid_on_date,
            "DettesAccumuleesAvantPaiement": accumulated_before_payment,
            "DettesAccumuleesRestantes": remaining_after_saved_payment,
            "StatutDettesAccumulees": (
                "Aucune dette accumulée"
                if accumulated_before_payment <= 0
                else "Payées"
                if remaining_after_saved_payment <= 0
                else "Partiellement payées"
                if paid_on_date > 0
                else "En attente"
            ),
        }

    @classmethod
    def _recalculate_debt_payments(cls, connection: sqlite3.Connection) -> None:
        connection.execute(
            """
            UPDATE Commandes
            SET DettePayee = 0,
                DetteSoldee = CASE WHEN IFNULL(Dette, 0) <= 0 THEN 1 ELSE 0 END
            """
        )

        cash_rows = connection.execute(
            """
            SELECT DateCaisse, IFNULL(DettesPayeesAujourdHui, 0) AS Montant
            FROM CaisseJournaliere
            WHERE IFNULL(DettesPayeesAujourdHui, 0) > 0
            ORDER BY DateCaisse ASC, Id ASC
            """
        ).fetchall()

        for cash_row in cash_rows:
            remaining_payment = max(float(cash_row["Montant"] or 0), 0.0)
            if remaining_payment <= 0:
                continue
            order_rows = connection.execute(
                f"""
                SELECT Id, IFNULL(Dette, 0) AS Dette, IFNULL(DettePayee, 0) AS DettePayee
                FROM Commandes
                WHERE DateCommande < ?
                  AND {OUTSTANDING_DEBT_SQL} > 0
                ORDER BY DateCommande ASC, Id ASC
                """,
                (cash_row["DateCaisse"],),
            ).fetchall()
            for order_row in order_rows:
                outstanding = max(float(order_row["Dette"] or 0) - float(order_row["DettePayee"] or 0), 0.0)
                if outstanding <= 0:
                    continue
                amount_to_apply = min(outstanding, remaining_payment)
                connection.execute(
                    """
                    UPDATE Commandes
                    SET DettePayee = IFNULL(DettePayee, 0) + ?,
                        DetteSoldee = CASE
                            WHEN IFNULL(DettePayee, 0) + ? >= IFNULL(Dette, 0) THEN 1
                            ELSE 0
                        END
                    WHERE Id = ?
                    """,
                    (amount_to_apply, amount_to_apply, order_row["Id"]),
                )
                remaining_payment -= amount_to_apply
                if remaining_payment <= 0:
                    break

        connection.execute(
            """
            UPDATE Commandes
            SET DetteSoldee = CASE
                WHEN IFNULL(Dette, 0) <= 0 THEN 1
                WHEN IFNULL(DettePayee, 0) >= IFNULL(Dette, 0) THEN 1
                ELSE 0
            END
            """
        )

    @classmethod
    def recalculate_debt_payments(cls) -> None:
        with cls.connect() as connection:
            cls._recalculate_debt_payments(connection)
            cls._sync_all_commissions(connection)

    @classmethod
    def save_cash_day(
        cls,
        target_date: date,
        total_expenses: float,
        expense_details: str,
        paid_debts_today: float = 0.0,
        paid_debts_details: str = "",
    ) -> None:
        cls.ensure_day_open_for_write(target_date, "la caisse")
        if total_expenses < 0:
            raise ValueError("Le montant total des dépenses ne peut pas être négatif.")
        if paid_debts_today < 0:
            raise ValueError("Le montant des dettes payées aujourd'hui ne peut pas être négatif.")
        accumulated = cls.get_accumulated_debt_totals_for_date(target_date)
        available_debts = float(accumulated.get("DettesAccumuleesAvantPaiement", 0) or 0)
        if paid_debts_today > available_debts + 0.01:
            raise ValueError(
                "Le montant des dettes payées aujourd'hui dépasse les dettes accumulées des jours précédents."
            )
        date_text = target_date.strftime(DB_DATE_FORMAT)
        exists = int(
            cls._fetch_value(
                "SELECT COUNT(*) FROM CaisseJournaliere WHERE DateCaisse = ?",
                (date_text,),
            )
        )
        if exists:
            cls._execute(
                """
                UPDATE CaisseJournaliere
                SET MontantTotalDepenses = ?, DepensesEffectuees = ?, DettesPayeesAujourdHui = ?, DettesPayeesDetails = ?
                WHERE DateCaisse = ?
                """,
                (total_expenses, expense_details, paid_debts_today, paid_debts_details, date_text),
            )
        else:
            cls._execute(
                """
                INSERT INTO CaisseJournaliere
                    (DateCaisse, MontantTotalDepenses, DepensesEffectuees, DettesPayeesAujourdHui, DettesPayeesDetails)
                VALUES (?, ?, ?, ?, ?)
                """,
                (date_text, total_expenses, expense_details, paid_debts_today, paid_debts_details),
            )
        cls.recalculate_debt_payments()

    @classmethod
    def list_cash_days(cls) -> list[dict[str, Any]]:
        return cls._fetch_all(
            f"""
            SELECT
                c.Id,
                c.DateCaisse,
                IFNULL(cmd.NombreTotalBacs, 0) AS NombreTotalBacs,
                IFNULL(cmd.MontantAttendu, 0) AS MontantAttendu,
                IFNULL(cmd.MontantRecu, 0) AS MontantRecu,
                IFNULL(cmd.TotalDettes, 0) AS TotalDettes,
                CASE
                    WHEN IFNULL(prev.TotalDettesPrecedentes, 0) - IFNULL(prev_pay.DettesPayeesAvantDate, 0) > 0
                    THEN IFNULL(prev.TotalDettesPrecedentes, 0) - IFNULL(prev_pay.DettesPayeesAvantDate, 0)
                    ELSE 0
                END AS TotalDettesAccumulees,
                IFNULL(c.DettesPayeesAujourdHui, 0) AS DettesPayeesAujourdHui,
                CASE
                    WHEN IFNULL(prev.TotalDettesPrecedentes, 0) - IFNULL(prev_pay.DettesPayeesAvantDate, 0) - IFNULL(c.DettesPayeesAujourdHui, 0) > 0
                    THEN IFNULL(prev.TotalDettesPrecedentes, 0) - IFNULL(prev_pay.DettesPayeesAvantDate, 0) - IFNULL(c.DettesPayeesAujourdHui, 0)
                    ELSE 0
                END AS DettesAccumuleesRestantes,
                CASE
                    WHEN IFNULL(prev.TotalDettesPrecedentes, 0) - IFNULL(prev_pay.DettesPayeesAvantDate, 0) <= 0 THEN 'Aucune dette accumulée'
                    WHEN IFNULL(prev.TotalDettesPrecedentes, 0) - IFNULL(prev_pay.DettesPayeesAvantDate, 0) - IFNULL(c.DettesPayeesAujourdHui, 0) <= 0 THEN 'Payées'
                    WHEN IFNULL(c.DettesPayeesAujourdHui, 0) > 0 THEN 'Partiellement payées'
                    ELSE 'En attente'
                END AS StatutDettesAccumulees,
                (IFNULL(cmd.MontantRecu, 0) + IFNULL(c.DettesPayeesAujourdHui, 0)) AS TotalEntrees,
                c.MontantTotalDepenses,
                ((IFNULL(cmd.MontantRecu, 0) + IFNULL(c.DettesPayeesAujourdHui, 0)) - c.MontantTotalDepenses) AS Solde,
                c.DepensesEffectuees,
                IFNULL(c.DettesPayeesDetails, '') AS DettesPayeesDetails
            FROM CaisseJournaliere c
            LEFT JOIN (
                SELECT
                    DateCommande,
                    SUM(NombreBacs) AS NombreTotalBacs,
                    SUM(MontantAPercevoir) AS MontantAttendu,
                    SUM(MontantRecu) AS MontantRecu,
                    SUM({OUTSTANDING_DEBT_SQL}) AS TotalDettes
                FROM Commandes
                GROUP BY DateCommande
            ) cmd ON cmd.DateCommande = c.DateCaisse
            LEFT JOIN (
                SELECT
                    base.DateCaisse,
                    IFNULL(SUM(o.Dette), 0) AS TotalDettesPrecedentes
                FROM CaisseJournaliere base
                LEFT JOIN Commandes o ON o.DateCommande < base.DateCaisse
                GROUP BY base.DateCaisse
            ) prev ON prev.DateCaisse = c.DateCaisse
            LEFT JOIN (
                SELECT
                    base.DateCaisse,
                    IFNULL(SUM(previous_cash.DettesPayeesAujourdHui), 0) AS DettesPayeesAvantDate
                FROM CaisseJournaliere base
                LEFT JOIN CaisseJournaliere previous_cash ON previous_cash.DateCaisse < base.DateCaisse
                GROUP BY base.DateCaisse
            ) prev_pay ON prev_pay.DateCaisse = c.DateCaisse
            ORDER BY c.DateCaisse DESC
            """
        )

    @classmethod
    def list_cash_days_by_date(cls, target_date: date) -> list[dict[str, Any]]:
        return cls._fetch_all(
            f"""
            SELECT
                c.Id,
                c.DateCaisse,
                IFNULL(cmd.NombreTotalBacs, 0) AS NombreTotalBacs,
                IFNULL(cmd.MontantAttendu, 0) AS MontantAttendu,
                IFNULL(cmd.MontantRecu, 0) AS MontantRecu,
                IFNULL(cmd.TotalDettes, 0) AS TotalDettes,
                CASE
                    WHEN IFNULL(prev.TotalDettesPrecedentes, 0) - IFNULL(prev_pay.DettesPayeesAvantDate, 0) > 0
                    THEN IFNULL(prev.TotalDettesPrecedentes, 0) - IFNULL(prev_pay.DettesPayeesAvantDate, 0)
                    ELSE 0
                END AS TotalDettesAccumulees,
                IFNULL(c.DettesPayeesAujourdHui, 0) AS DettesPayeesAujourdHui,
                CASE
                    WHEN IFNULL(prev.TotalDettesPrecedentes, 0) - IFNULL(prev_pay.DettesPayeesAvantDate, 0) - IFNULL(c.DettesPayeesAujourdHui, 0) > 0
                    THEN IFNULL(prev.TotalDettesPrecedentes, 0) - IFNULL(prev_pay.DettesPayeesAvantDate, 0) - IFNULL(c.DettesPayeesAujourdHui, 0)
                    ELSE 0
                END AS DettesAccumuleesRestantes,
                CASE
                    WHEN IFNULL(prev.TotalDettesPrecedentes, 0) - IFNULL(prev_pay.DettesPayeesAvantDate, 0) <= 0 THEN 'Aucune dette accumulée'
                    WHEN IFNULL(prev.TotalDettesPrecedentes, 0) - IFNULL(prev_pay.DettesPayeesAvantDate, 0) - IFNULL(c.DettesPayeesAujourdHui, 0) <= 0 THEN 'Payées'
                    WHEN IFNULL(c.DettesPayeesAujourdHui, 0) > 0 THEN 'Partiellement payées'
                    ELSE 'En attente'
                END AS StatutDettesAccumulees,
                (IFNULL(cmd.MontantRecu, 0) + IFNULL(c.DettesPayeesAujourdHui, 0)) AS TotalEntrees,
                c.MontantTotalDepenses,
                ((IFNULL(cmd.MontantRecu, 0) + IFNULL(c.DettesPayeesAujourdHui, 0)) - c.MontantTotalDepenses) AS Solde,
                c.DepensesEffectuees,
                IFNULL(c.DettesPayeesDetails, '') AS DettesPayeesDetails
            FROM CaisseJournaliere c
            LEFT JOIN (
                SELECT
                    DateCommande,
                    SUM(NombreBacs) AS NombreTotalBacs,
                    SUM(MontantAPercevoir) AS MontantAttendu,
                    SUM(MontantRecu) AS MontantRecu,
                    SUM({OUTSTANDING_DEBT_SQL}) AS TotalDettes
                FROM Commandes
                GROUP BY DateCommande
            ) cmd ON cmd.DateCommande = c.DateCaisse
            LEFT JOIN (
                SELECT
                    base.DateCaisse,
                    IFNULL(SUM(o.Dette), 0) AS TotalDettesPrecedentes
                FROM CaisseJournaliere base
                LEFT JOIN Commandes o ON o.DateCommande < base.DateCaisse
                GROUP BY base.DateCaisse
            ) prev ON prev.DateCaisse = c.DateCaisse
            LEFT JOIN (
                SELECT
                    base.DateCaisse,
                    IFNULL(SUM(previous_cash.DettesPayeesAujourdHui), 0) AS DettesPayeesAvantDate
                FROM CaisseJournaliere base
                LEFT JOIN CaisseJournaliere previous_cash ON previous_cash.DateCaisse < base.DateCaisse
                GROUP BY base.DateCaisse
            ) prev_pay ON prev_pay.DateCaisse = c.DateCaisse
            WHERE c.DateCaisse = ?
            ORDER BY c.Id DESC
            """,
            (target_date.strftime(DB_DATE_FORMAT),),
        )

    @classmethod
    def list_cash_balance_by_period(cls, start_date: date, end_date: date) -> list[dict[str, Any]]:
        if end_date < start_date:
            raise ValueError("La date de fin doit être supérieure ou égale à la date de début.")

        order_rows = cls._fetch_all(
            f"""
            SELECT
                DateCommande,
                IFNULL(SUM(NombreBacs), 0) AS NombreTotalBacs,
                IFNULL(SUM(MontantAPercevoir), 0) AS MontantAttendu,
                IFNULL(SUM(MontantRecu), 0) AS MontantRecu,
                IFNULL(SUM({OUTSTANDING_DEBT_SQL}), 0) AS TotalDettes
            FROM Commandes
            WHERE DateCommande BETWEEN ? AND ?
            GROUP BY DateCommande
            """,
            (start_date.strftime(DB_DATE_FORMAT), end_date.strftime(DB_DATE_FORMAT)),
        )
        cash_rows = cls._fetch_all(
            """
            SELECT
                DateCaisse,
                IFNULL(DettesPayeesAujourdHui, 0) AS DettesPayeesAujourdHui,
                IFNULL(MontantTotalDepenses, 0) AS MontantTotalDepenses,
                IFNULL(DepensesEffectuees, '') AS DepensesEffectuees,
                IFNULL(DettesPayeesDetails, '') AS DettesPayeesDetails
            FROM CaisseJournaliere
            WHERE DateCaisse BETWEEN ? AND ?
            """,
            (start_date.strftime(DB_DATE_FORMAT), end_date.strftime(DB_DATE_FORMAT)),
        )
        orders_by_date = {str(row["DateCommande"]): row for row in order_rows}
        cash_by_date = {str(row["DateCaisse"]): row for row in cash_rows}

        rows: list[dict[str, Any]] = []
        running_balance = 0.0
        current_date = start_date
        while current_date <= end_date:
            date_text = current_date.strftime(DB_DATE_FORMAT)
            order_row = orders_by_date.get(date_text, {})
            cash_row = cash_by_date.get(date_text, {})
            received = float(order_row.get("MontantRecu", 0) or 0)
            paid_debts = float(cash_row.get("DettesPayeesAujourdHui", 0) or 0)
            expenses = float(cash_row.get("MontantTotalDepenses", 0) or 0)
            entries = received + paid_debts
            balance = entries - expenses
            running_balance += balance
            accumulated = cls.get_accumulated_debt_totals_for_date(current_date)
            rows.append(
                {
                    "DateCaisse": date_text,
                    "NombreTotalBacs": int(float(order_row.get("NombreTotalBacs", 0) or 0)),
                    "MontantAttendu": float(order_row.get("MontantAttendu", 0) or 0),
                    "MontantRecu": received,
                    "TotalDettes": float(order_row.get("TotalDettes", 0) or 0),
                    "TotalDettesAccumulees": float(accumulated.get("DettesAccumuleesAvantPaiement", 0) or 0),
                    "DettesPayeesAujourdHui": paid_debts,
                    "DettesAccumuleesRestantes": max(
                        float(accumulated.get("DettesAccumuleesAvantPaiement", 0) or 0) - paid_debts,
                        0.0,
                    ),
                    "TotalEntrees": entries,
                    "MontantTotalDepenses": expenses,
                    "Solde": balance,
                    "SoldeCumule": running_balance,
                    "DepensesEffectuees": str(cash_row.get("DepensesEffectuees", "") or ""),
                    "DettesPayeesDetails": str(cash_row.get("DettesPayeesDetails", "") or ""),
                }
            )
            current_date += timedelta(days=1)
        return rows

    @classmethod
    def delete_cash_day(cls, cash_id: int) -> int:
        original_date_text = cls._get_record_date_text("CaisseJournaliere", "DateCaisse", cash_id)
        if original_date_text:
            cls.ensure_day_open_for_write(original_date_text, "la caisse")
        deleted = cls._execute("DELETE FROM CaisseJournaliere WHERE Id = ?", (cash_id,))
        if deleted:
            cls.recalculate_debt_payments()
        return deleted

    @classmethod
    def get_total_cash(cls) -> float:
        value = cls._fetch_value(
            """
            SELECT IFNULL(SUM(
                IFNULL(cmd.MontantRecu, 0)
                + IFNULL(c.DettesPayeesAujourdHui, 0)
                - IFNULL(c.MontantTotalDepenses, 0)
            ), 0)
            FROM CaisseJournaliere c
            LEFT JOIN (
                SELECT DateCommande, SUM(MontantRecu) AS MontantRecu
                FROM Commandes
                GROUP BY DateCommande
            ) cmd
            ON c.DateCaisse = cmd.DateCommande
            """
        )
        return float(value or 0)

    @classmethod
    def list_orders(cls) -> list[dict[str, Any]]:
        return cls._fetch_all(
            f"""
            SELECT
                Id,
                DateCommande,
                Client,
                Statut,
                NombreBacs,
                MontantAPercevoir,
                MontantRecu,
                Dette AS DetteInitiale,
                IFNULL(DettePayee, 0) AS DettePayee,
                {OUTSTANDING_DEBT_SQL} AS Dette,
                {DEBT_STATUS_SQL} AS StatutDette
            FROM Commandes
            ORDER BY DateCommande DESC, Id DESC
            """
        )

    @classmethod
    def list_orders_by_date(cls, target_date: date) -> list[dict[str, Any]]:
        return cls._fetch_all(
            f"""
            SELECT
                Id,
                DateCommande,
                Client,
                Statut,
                NombreBacs,
                MontantAPercevoir,
                MontantRecu,
                Dette AS DetteInitiale,
                IFNULL(DettePayee, 0) AS DettePayee,
                {OUTSTANDING_DEBT_SQL} AS Dette,
                {DEBT_STATUS_SQL} AS StatutDette
            FROM Commandes
            WHERE DateCommande = ?
            ORDER BY Id DESC
            """,
            (target_date.strftime(DB_DATE_FORMAT),),
        )

    @classmethod
    def add_order(
        cls,
        target_date: date,
        client: str,
        status: str,
        number_of_trays: int,
        amount_due: float,
        amount_received: float,
        debt: float,
    ) -> None:
        cls.ensure_day_open_for_write(target_date, "les commandes")
        cls._execute(
            """
            INSERT INTO Commandes
                (DateCommande, Client, Statut, NombreBacs, MontantAPercevoir, MontantRecu, Dette)
            VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (
                target_date.strftime(DB_DATE_FORMAT),
                client,
                status,
                number_of_trays,
                amount_due,
                amount_received,
                debt,
            ),
        )
        cls.recalculate_debt_payments()

    @classmethod
    def count_orders_with_debt(cls) -> int:
        return int(cls._fetch_value(f"SELECT COUNT(*) FROM Commandes WHERE {OUTSTANDING_DEBT_SQL} > 0"))

    @classmethod
    def get_debt_alerts(cls, limit: int = 10) -> list[dict[str, Any]]:
        row_limit = max(int(limit), 1)
        return cls._fetch_all(
            f"""
            SELECT
                TRIM(Client) AS Client,
                COUNT(*) AS NombreCommandes,
                IFNULL(SUM(NombreBacs), 0) AS TotalBacs,
                IFNULL(SUM({OUTSTANDING_DEBT_SQL}), 0) AS DetteTotale,
                MAX(DateCommande) AS DerniereCommande
            FROM Commandes
            WHERE {OUTSTANDING_DEBT_SQL} > 0
            GROUP BY UPPER(TRIM(Client))
            ORDER BY DetteTotale DESC, DerniereCommande DESC, Client ASC
            LIMIT {row_limit}
            """
        )

    @classmethod
    def update_order(
        cls,
        order_id: int,
        target_date: date,
        client: str,
        status: str,
        number_of_trays: int,
        amount_due: float,
        amount_received: float,
        debt: float,
    ) -> int:
        original_date_text = cls._get_record_date_text("Commandes", "DateCommande", order_id)
        cls._ensure_update_dates_open("les commandes", original_date_text, target_date)
        updated = cls._execute(
            """
            UPDATE Commandes
            SET
                DateCommande = ?,
                Client = ?,
                Statut = ?,
                NombreBacs = ?,
                MontantAPercevoir = ?,
                MontantRecu = ?,
                Dette = ?
            WHERE Id = ?
            """,
            (
                target_date.strftime(DB_DATE_FORMAT),
                client,
                status,
                number_of_trays,
                amount_due,
                amount_received,
                debt,
                order_id,
            ),
        )
        if updated:
            cls.recalculate_debt_payments()
        return updated

    @classmethod
    def delete_order(cls, order_id: int) -> int:
        original_date_text = cls._get_record_date_text("Commandes", "DateCommande", order_id)
        if original_date_text:
            cls.ensure_day_open_for_write(original_date_text, "les commandes")
        deleted = cls._execute("DELETE FROM Commandes WHERE Id = ?", (order_id,))
        if deleted:
            cls.recalculate_debt_payments()
        return deleted

    @classmethod
    def find_existing_order(
        cls,
        target_date: date,
        client: str,
        exclude_id: int = 0,
    ) -> int:
        sql = """
            SELECT Id
            FROM Commandes
            WHERE DateCommande = ?
              AND UPPER(TRIM(Client)) = UPPER(TRIM(?))
        """
        params: list[Any] = [target_date.strftime(DB_DATE_FORMAT), client.strip()]
        if exclude_id > 0:
            sql += " AND Id <> ?"
            params.append(exclude_id)
        sql += " ORDER BY Id DESC LIMIT 1"
        value = cls._fetch_value(sql, tuple(params))
        return int(value or 0)

    @classmethod
    def list_commissions(cls) -> list[dict[str, Any]]:
        return cls._fetch_all(
            """
            SELECT Id, DateCommission, Nom, Statut, NombreBacs, MontantPaye, Commissions, Dettes, NetAPayer
            FROM Commissions
            ORDER BY DateCommission DESC, Id DESC
            """
        )

    @classmethod
    def list_commissions_by_date(cls, target_date: date) -> list[dict[str, Any]]:
        return cls._fetch_all(
            """
            SELECT Id, DateCommission, Nom, Statut, NombreBacs, MontantPaye, Commissions, Dettes, NetAPayer
            FROM Commissions
            WHERE DateCommission = ?
            ORDER BY Id DESC
            """,
            (target_date.strftime(DB_DATE_FORMAT),),
        )

    @classmethod
    def list_clients_from_orders_by_date(cls, target_date: date) -> list[str]:
        rows = cls._fetch_all(
            """
            SELECT DISTINCT Client
            FROM Commandes
            WHERE DateCommande = ?
            ORDER BY Client
            """,
            (target_date.strftime(DB_DATE_FORMAT),),
        )
        return [row["Client"] for row in rows]

    @classmethod
    def _sync_commissions_for_date(cls, connection: sqlite3.Connection, date_text: str) -> None:
        connection.execute("DELETE FROM Commissions WHERE DateCommission = ?", (date_text,))
        connection.execute(
            f"""
            INSERT INTO Commissions
                (DateCommission, Nom, Statut, NombreBacs, MontantPaye, Commissions, Dettes, NetAPayer)
            SELECT
                DateCommande,
                TRIM(Client) AS Nom,
                CASE
                    WHEN COUNT(DISTINCT Statut) = 1 THEN MAX(Statut)
                    ELSE 'Mixte'
                END AS Statut,
                IFNULL(SUM(NombreBacs), 0) AS NombreBacs,
                IFNULL(SUM(MontantRecu), 0) AS MontantPaye,
                IFNULL(SUM(
                    CASE
                        WHEN Statut = 'Maman' THEN NombreBacs * 1650
                        ELSE 0
                    END
                ), 0) AS Commissions,
                IFNULL(SUM({OUTSTANDING_DEBT_SQL}), 0) AS Dettes,
                (
                    IFNULL(SUM(
                        CASE
                            WHEN Statut = 'Maman' THEN NombreBacs * 1650
                            ELSE 0
                        END
                    ), 0) - IFNULL(SUM({OUTSTANDING_DEBT_SQL}), 0)
                ) AS NetAPayer
            FROM Commandes
            WHERE DateCommande = ?
            GROUP BY DateCommande, UPPER(TRIM(Client))
            HAVING Commissions > 0
            ORDER BY Nom
            """,
            (date_text,),
        )

    @classmethod
    def _sync_all_commissions(cls, connection: sqlite3.Connection) -> None:
        date_rows = connection.execute(
            "SELECT DISTINCT DateCommande FROM Commandes ORDER BY DateCommande"
        ).fetchall()
        connection.execute("DELETE FROM Commissions")
        for row in date_rows:
            cls._sync_commissions_for_date(connection, str(row["DateCommande"]))

    @classmethod
    def sync_all_commissions(cls) -> None:
        with cls.connect() as connection:
            cls._sync_all_commissions(connection)

    @classmethod
    def get_commission_synthesis_from_orders(
        cls,
        target_date: date,
        client: str,
    ) -> dict[str, Any]:
        row = cls._fetch_one(
            f"""
            SELECT
                CASE
                    WHEN COUNT(DISTINCT Statut) = 1 THEN MAX(Statut)
                    ELSE 'Mixte'
                END AS Statut,
                IFNULL(SUM(NombreBacs), 0) AS NombreBacs,
                IFNULL(SUM(MontantRecu), 0) AS MontantPaye,
                IFNULL(SUM(
                    CASE
                        WHEN Statut = 'Maman' THEN NombreBacs * 1650
                        WHEN Statut = 'Vente cash' THEN 0
                        WHEN Statut = 'VC' THEN 0
                        WHEN Statut = 'Depositaire 6.000Fc' THEN 0
                        WHEN Statut = 'Dépositaire 6.000Fc' THEN 0
                        WHEN Statut = 'Depositaire' THEN 0
                        WHEN Statut = 'Dépositaire' THEN 0
                        WHEN Statut = 'Depositaire 4.100Fc' THEN 0
                        WHEN Statut = 'Dépositaire 4.100Fc' THEN 0
                        ELSE 0
                    END
                ), 0) AS Commissions,
                IFNULL(SUM({OUTSTANDING_DEBT_SQL}), 0) AS Dettes,
                (
                    IFNULL(SUM(
                        CASE
                            WHEN Statut = 'Maman' THEN NombreBacs * 1650
                            WHEN Statut = 'Vente cash' THEN 0
                            WHEN Statut = 'VC' THEN 0
                            WHEN Statut = 'Depositaire 6.000Fc' THEN 0
                            WHEN Statut = 'Dépositaire 6.000Fc' THEN 0
                            WHEN Statut = 'Depositaire' THEN 0
                            WHEN Statut = 'Dépositaire' THEN 0
                            WHEN Statut = 'Depositaire 4.100Fc' THEN 0
                            WHEN Statut = 'Dépositaire 4.100Fc' THEN 0
                            ELSE 0
                        END
                    ), 0) - IFNULL(SUM({OUTSTANDING_DEBT_SQL}), 0)
                ) AS NetAPayer
            FROM Commandes
            WHERE DateCommande = ? AND Client = ?
            """,
            (target_date.strftime(DB_DATE_FORMAT), client),
        )
        return row or {}

    @classmethod
    def find_existing_commission(
        cls,
        target_date: date,
        name: str,
        exclude_id: int = 0,
    ) -> int:
        sql = """
            SELECT Id
            FROM Commissions
            WHERE DateCommission = ?
              AND UPPER(TRIM(Nom)) = UPPER(TRIM(?))
        """
        params: list[Any] = [target_date.strftime(DB_DATE_FORMAT), name.strip()]
        if exclude_id > 0:
            sql += " AND Id <> ?"
            params.append(exclude_id)
        sql += " ORDER BY Id DESC LIMIT 1"
        value = cls._fetch_value(sql, tuple(params))
        return int(value or 0)

    @classmethod
    def add_commission(
        cls,
        target_date: date,
        name: str,
        status: str,
        number_of_trays: int,
        amount_paid: float,
        commissions: float,
        debts: float,
        net_to_pay: float,
    ) -> None:
        raise ValueError(
            "Les commissions sont calculées automatiquement à partir des commandes. "
            "Modifiez la commande correspondante pour corriger une commission."
        )

    @classmethod
    def update_commission(
        cls,
        commission_id: int,
        target_date: date,
        name: str,
        status: str,
        number_of_trays: int,
        amount_paid: float,
        commissions: float,
        debts: float,
        net_to_pay: float,
    ) -> int:
        raise ValueError(
            "Les commissions sont calculées automatiquement à partir des commandes. "
            "Modifiez la commande correspondante pour corriger une commission."
        )

    @classmethod
    def delete_commission(cls, commission_id: int) -> int:
        raise ValueError(
            "Les commissions sont calculées automatiquement à partir des commandes. "
            "Supprimez ou modifiez la commande correspondante pour corriger une commission."
        )

    @classmethod
    def get_total_commissions(cls) -> float:
        value = cls._fetch_value("SELECT IFNULL(SUM(Commissions), 0) FROM Commissions")
        return float(value or 0)

    @classmethod
    def _decorate_day_closure_row(cls, row: dict[str, Any] | None) -> dict[str, Any]:
        if not row:
            return {}
        decorated = dict(row)
        decorated["EstReouverte"] = bool(int(decorated.get("EstReouverte", 0) or 0))
        decorated["StatutAffichage"] = "Réouverte" if decorated["EstReouverte"] else "Clôturée"
        return decorated

    @classmethod
    def get_day_closure(cls, target_date: date | str) -> dict[str, Any]:
        normalized_date = cls._coerce_date(target_date)
        row = cls._fetch_one(
            """
            SELECT
                Id,
                DateJour,
                DateCloture,
                Identifiant,
                NomComplet,
                Role,
                CheminRapport,
                CheminSauvegarde,
                EstReouverte,
                DateReouverture,
                ReouvertParIdentifiant,
                ReouvertParNomComplet,
                ReouvertParRole,
                MotifReouverture
            FROM CloturesJournalieres
            WHERE DateJour = ?
            """,
            (normalized_date.strftime(DB_DATE_FORMAT),),
        )
        return cls._decorate_day_closure_row(row)

    @classmethod
    def is_day_closed(cls, target_date: date | str) -> bool:
        closure = cls.get_day_closure(target_date)
        return bool(closure) and not bool(closure.get("EstReouverte", False))

    @classmethod
    def list_day_closures(cls, limit: int = 120) -> list[dict[str, Any]]:
        row_limit = max(int(limit), 1)
        rows = cls._fetch_all(
            f"""
            SELECT
                Id,
                DateJour,
                DateCloture,
                Identifiant,
                NomComplet,
                Role,
                CheminRapport,
                CheminSauvegarde,
                EstReouverte,
                DateReouverture,
                ReouvertParIdentifiant,
                ReouvertParNomComplet,
                ReouvertParRole,
                MotifReouverture
            FROM CloturesJournalieres
            ORDER BY DateJour DESC, Id DESC
            LIMIT {row_limit}
            """
        )
        return [cls._decorate_day_closure_row(row) for row in rows]

    @classmethod
    def ensure_day_open_for_write(cls, target_date: date | str, module_name: str) -> None:
        normalized_date = cls._coerce_date(target_date)
        closure = cls.get_day_closure(normalized_date)
        if not closure or bool(closure.get("EstReouverte", False)):
            return

        closed_by = str(closure.get("NomComplet", "") or closure.get("Identifiant", "")).strip()
        closed_date = normalized_date.strftime("%d/%m/%Y")
        module_label = module_name.strip() or "ce module"
        message = f"La journée du {closed_date} est déjà clôturée pour {module_label}."
        if closed_by:
            message += f" Clôturée par {closed_by}."
        message += " Réouvrez-la d'abord depuis le tableau de bord administrateur."
        raise ValueError(message)

    @classmethod
    def _get_record_date_text(
        cls,
        table_name: str,
        date_column: str,
        record_id: int,
    ) -> str:
        value = cls._fetch_value(
            f"SELECT {date_column} FROM {table_name} WHERE Id = ?",
            (record_id,),
        )
        return "" if value is None else str(value)

    @classmethod
    def _ensure_update_dates_open(
        cls,
        module_name: str,
        original_date_text: str,
        target_date: date,
    ) -> None:
        if original_date_text:
            cls.ensure_day_open_for_write(original_date_text, module_name)
        if not original_date_text or original_date_text != target_date.strftime(DB_DATE_FORMAT):
            cls.ensure_day_open_for_write(target_date, module_name)

    @classmethod
    def close_day(
        cls,
        target_date: date | str,
        identifiant: str,
        full_name: str,
        role: str,
    ) -> dict[str, Any]:
        normalized_date = cls._coerce_date(target_date)
        if normalized_date > date.today():
            raise ValueError("Impossible de clôturer une journée future.")

        existing = cls.get_day_closure(normalized_date)
        if existing and not bool(existing.get("EstReouverte", False)):
            raise ValueError("Cette journée est déjà clôturée.")

        cls.initialize_stock_day(normalized_date)
        cls.update_stock_closing(normalized_date)

        backup_path = cls.backup_database(
            cls.build_backup_path(f"cloture-{normalized_date.strftime('%Y%m%d')}")
        )

        from .reports import create_daily_pdf_report

        report_dir = cls.get_reports_dir_for_user(identifiant.strip() or "admin")
        report_path = create_daily_pdf_report(
            normalized_date,
            destination=report_dir / f"cloture-journaliere-{normalized_date.strftime('%Y%m%d')}.pdf",
            role="Admin",
            generated_by=full_name.strip() or identifiant.strip(),
            generated_role=role.strip() or "Admin",
        )

        timestamp = datetime.now().isoformat(timespec="seconds")
        if existing:
            cls._execute(
                """
                UPDATE CloturesJournalieres
                SET
                    DateCloture = ?,
                    Identifiant = ?,
                    NomComplet = ?,
                    Role = ?,
                    CheminRapport = ?,
                    CheminSauvegarde = ?,
                    EstReouverte = 0,
                    DateReouverture = '',
                    ReouvertParIdentifiant = '',
                    ReouvertParNomComplet = '',
                    ReouvertParRole = '',
                    MotifReouverture = ''
                WHERE DateJour = ?
                """,
                (
                    timestamp,
                    identifiant.strip(),
                    full_name.strip() or identifiant.strip(),
                    role.strip(),
                    str(report_path),
                    str(backup_path),
                    normalized_date.strftime(DB_DATE_FORMAT),
                ),
            )
        else:
            cls._execute(
                """
                INSERT INTO CloturesJournalieres
                    (
                        DateJour,
                        DateCloture,
                        Identifiant,
                        NomComplet,
                        Role,
                        CheminRapport,
                        CheminSauvegarde
                    )
                VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    normalized_date.strftime(DB_DATE_FORMAT),
                    timestamp,
                    identifiant.strip(),
                    full_name.strip() or identifiant.strip(),
                    role.strip(),
                    str(report_path),
                    str(backup_path),
                ),
            )

        cls.log_activity(
            identifiant.strip(),
            full_name.strip() or identifiant.strip(),
            role.strip(),
            "Clôture journalière",
            "Journée clôturée",
            (
                f"{normalized_date.strftime('%d/%m/%Y')} | "
                f"Sauvegarde : {backup_path} | Rapport : {report_path}"
            ),
        )
        return cls.get_day_closure(normalized_date)

    @classmethod
    def reopen_day(
        cls,
        target_date: date | str,
        identifiant: str,
        full_name: str,
        role: str,
        reason: str,
    ) -> dict[str, Any]:
        normalized_date = cls._coerce_date(target_date)
        closure = cls.get_day_closure(normalized_date)
        if not closure:
            raise ValueError("Aucune clôture n'a été trouvée pour cette journée.")
        if bool(closure.get("EstReouverte", False)):
            raise ValueError("Cette journée est déjà réouverte.")

        normalized_reason = reason.strip()
        if not normalized_reason:
            raise ValueError("Veuillez renseigner le motif de réouverture.")

        cls._execute(
            """
            UPDATE CloturesJournalieres
            SET
                EstReouverte = 1,
                DateReouverture = ?,
                ReouvertParIdentifiant = ?,
                ReouvertParNomComplet = ?,
                ReouvertParRole = ?,
                MotifReouverture = ?
            WHERE DateJour = ?
            """,
            (
                datetime.now().isoformat(timespec="seconds"),
                identifiant.strip(),
                full_name.strip() or identifiant.strip(),
                role.strip(),
                normalized_reason,
                normalized_date.strftime(DB_DATE_FORMAT),
            ),
        )

        cls.log_activity(
            identifiant.strip(),
            full_name.strip() or identifiant.strip(),
            role.strip(),
            "Clôture journalière",
            "Journée réouverte",
            f"{normalized_date.strftime('%d/%m/%Y')} | Motif : {normalized_reason}",
        )
        return cls.get_day_closure(normalized_date)

    @classmethod
    def log_activity(
        cls,
        identifiant: str,
        full_name: str,
        role: str,
        module: str,
        action: str,
        details: str = "",
    ) -> None:
        normalized_identifiant = identifiant.strip()
        normalized_module = module.strip()
        normalized_action = action.strip()
        if not normalized_identifiant or not normalized_module or not normalized_action:
            return

        cls._execute(
            """
            INSERT INTO HistoriqueActions
                (DateAction, Identifiant, NomComplet, Role, Module, Action, Details)
            VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (
                datetime.now().isoformat(timespec="seconds"),
                normalized_identifiant,
                full_name.strip() or normalized_identifiant,
                role.strip(),
                normalized_module,
                normalized_action,
                details.strip(),
            ),
        )

    @classmethod
    def list_activity_logs(
        cls,
        limit: int = 300,
        identifiant: str = "",
        role: str = "",
    ) -> list[dict[str, Any]]:
        row_limit = max(int(limit), 1)
        sql = """
            SELECT
                Id,
                DateAction,
                Identifiant,
                NomComplet,
                Role,
                Module,
                Action,
                Details
            FROM HistoriqueActions
            WHERE 1 = 1
        """
        params: list[Any] = []
        normalized_identifiant = identifiant.strip()
        if normalized_identifiant:
            sql += " AND UPPER(Identifiant) LIKE UPPER(?)"
            params.append(f"%{normalized_identifiant}%")
        normalized_role = role.strip()
        if normalized_role:
            sql += " AND Role = ?"
            params.append(normalized_role)
        sql += f" ORDER BY DateAction DESC, Id DESC LIMIT {row_limit}"
        return cls._fetch_all(sql, tuple(params))

    @classmethod
    def get_recent_activity_summary(cls, limit: int = 8) -> list[dict[str, Any]]:
        return cls.list_activity_logs(limit=limit)

    @classmethod
    def _fetch_all(
        cls,
        sql: str,
        params: tuple[Any, ...] = (),
    ) -> list[dict[str, Any]]:
        with cls.connect() as connection:
            rows = connection.execute(sql, params).fetchall()
            return [dict(row) for row in rows]

    @classmethod
    def _fetch_one(
        cls,
        sql: str,
        params: tuple[Any, ...] = (),
    ) -> dict[str, Any] | None:
        with cls.connect() as connection:
            row = connection.execute(sql, params).fetchone()
            return None if row is None else dict(row)

    @classmethod
    def _fetch_value(
        cls,
        sql: str,
        params: tuple[Any, ...] = (),
    ) -> Any:
        with cls.connect() as connection:
            row = connection.execute(sql, params).fetchone()
            return None if row is None else row[0]

    @classmethod
    def _execute(
        cls,
        sql: str,
        params: tuple[Any, ...] = (),
    ) -> int:
        with cls.connect() as connection:
            cursor = connection.execute(sql, params)
            return cursor.rowcount


def _install_remote_database_proxies() -> None:
    for method_name in REMOTE_DATABASE_METHODS:
        descriptor = DatabaseHelper.__dict__.get(method_name)
        if not isinstance(descriptor, classmethod):
            continue

        original_method = descriptor.__func__

        def make_wrapper(
            wrapped_method_name: str,
            wrapped_original_method: Any,
        ) -> classmethod:
            @functools.wraps(wrapped_original_method)
            def wrapper(cls: type[DatabaseHelper], *args: Any, **kwargs: Any) -> Any:
                if cls._should_use_remote():
                    return cls._remote_call(wrapped_method_name, *args, **kwargs)
                return wrapped_original_method(cls, *args, **kwargs)

            return classmethod(wrapper)

        setattr(DatabaseHelper, method_name, make_wrapper(method_name, original_method))


_install_remote_database_proxies()
