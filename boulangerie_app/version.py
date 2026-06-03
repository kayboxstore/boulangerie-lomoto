import os


APP_NAME = os.environ.get("BOULANGERIE_APP_NAME", "Boulangerie Lomoto")
APP_VERSION = os.environ.get("BOULANGERIE_APP_VERSION", "1.3.18")
APP_PUBLISHER = "Kay Box Store"
APP_EDITION = os.environ.get("BOULANGERIE_APP_EDITION", "standard")
APP_DEMO = APP_EDITION.strip().lower() == "demo"

# Hypothèse retenue pour GitHub :
# - dépôt application : kayboxstore/boulangerie-lomoto
# - dépôt manifeste : kayboxstore/boulangerie-lomoto-updates
DEFAULT_UPDATE_MANIFEST_URL = "https://raw.githubusercontent.com/kayboxstore/boulangerie-lomoto-updates/main/update.json"

UPDATE_CHECK_INTERVAL_DAYS = 7
UPDATE_MANDATORY_AFTER_DAYS = 10
