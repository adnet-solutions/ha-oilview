"""Konstanten der OilView-Integration."""

from datetime import timedelta

DOMAIN = "oilview"
MANUFACTURER = "TECSON"

API_BASE = "https://www.oilview.de/api"

CONF_TOKEN = "token"
CONF_LINK_ID = "link_id"
CONF_START_DATE = "start_date"
CONF_CONSUMPTION_THRESHOLD = "consumption_threshold"
CONF_REFILL_THRESHOLD = "refill_threshold"

# Rauschfilter: Verbrauch wird erst gezählt, wenn der Stand mindestens so weit
# unter den Referenzstand fällt (dann aber der volle Betrag); ein Anstieg ab
# REFILL gilt als Tankung. Alles dazwischen ist Messrauschen.
DEFAULT_CONSUMPTION_THRESHOLD = 5  # Liter
DEFAULT_REFILL_THRESHOLD = 50  # Liter

UPDATE_INTERVAL = timedelta(minutes=30)
BACKFILL_PAUSE = 0.3  # Sekunden zwischen API-Abrufen beim Nachholen
BACKFILL_HOUR = 0
BACKFILL_MINUTE = 15
DAYS_IN_ATTRIBUTE = 35

STORAGE_VERSION = 1
