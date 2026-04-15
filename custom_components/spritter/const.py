from datetime import timedelta

DOMAIN = "spritter"

ADDON_PRICE_MAP_ENDPOINT = "http://127.0.0.1:8099/prices/"
REQUEST_TIMEOUT_SECONDS = 30

DEFAULT_POLL_INTERVAL = timedelta(minutes=5)