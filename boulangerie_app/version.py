import os

from .client_config import get_app_name, get_publisher

APP_NAME = get_app_name()
APP_VERSION = os.environ.get("BOULANGERIE_APP_VERSION", "1.5.4")
APP_PUBLISHER = get_publisher()
APP_EDITION = os.environ.get("BOULANGERIE_APP_EDITION", "standard")
APP_DEMO = APP_EDITION.strip().lower() == "demo"

# Hypothèse retenue pour GitHub :
# - dépôt application : kayboxstore/boulangerie-lomoto
# - dépôt manifeste : kayboxstore/boulangerie-lomoto-updates
DEFAULT_UPDATE_MANIFEST_URL = "https://raw.githubusercontent.com/kayboxstore/boulangerie-lomoto-updates/main/update.json"

UPDATE_CHECK_INTERVAL_DAYS = 7
UPDATE_MANDATORY_AFTER_DAYS = 10
