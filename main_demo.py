import os
from pathlib import Path


os.environ.setdefault("BOULANGERIE_APP_EDITION", "demo")
os.environ.setdefault("BOULANGERIE_APP_NAME", "Boulangerie Lomoto Démo")
os.environ.setdefault("BOULANGERIE_DEFAULT_ADMIN_FULL_NAME", "Administrateur Démo")
os.environ.setdefault("BOULANGERIE_DEFAULT_ADMIN_USERNAME", "demo.admin")
os.environ.setdefault("BOULANGERIE_DEFAULT_ADMIN_PASSWORD", "demo2026")

if "BOULANGERIE_APPDATA_DIR" not in os.environ:
    local_appdata = Path(os.environ.get("LOCALAPPDATA", str(Path.home() / "AppData" / "Local")))
    os.environ["BOULANGERIE_APPDATA_DIR"] = str(local_appdata / "BoulangerieLomotoDemo")

from boulangerie_app.demo_data import seed_demo_database_if_empty
from boulangerie_app.app import run_app


if __name__ == "__main__":
    seed_demo_database_if_empty()
    run_app()
