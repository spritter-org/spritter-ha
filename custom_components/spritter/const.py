from datetime import timedelta

DOMAIN = "spritter"

CONF_SOURCES = "sources"
CONF_PROVIDER = "provider"
CONF_STATION_ID = "station_id"
CONF_SCAN_INTERVAL_MINUTES = "scan_interval_minutes"

DEFAULT_SCAN_INTERVAL = timedelta(minutes=15)
DEFAULT_SCAN_INTERVAL_MINUTES = 15