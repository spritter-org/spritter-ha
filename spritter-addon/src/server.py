from __future__ import annotations

import json
import logging
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from threading import RLock
from typing import Any

from flask import Flask, jsonify, request, send_from_directory
from spritter import FuelStationRequest, get_fuel_prices

LOGGER = logging.getLogger("spritter_addon")
logging.basicConfig(level=logging.INFO)

HOST = "0.0.0.0"
PORT = 8099
DATA_DIR = Path("/data")
CONFIG_FILE = DATA_DIR / "spritter_config.json"


@dataclass(slots=True)
class StationConfig:
    provider: str
    station_id: str
    name: str | None = None
    keys: list[str] | None = None
    user_agent: str | None = None


@dataclass(slots=True)
class AppConfig:
    refresh_interval_seconds: int = 300
    stations: list[StationConfig] = field(default_factory=list)


class ConfigStore:
    def __init__(self, config_path: Path) -> None:
        self._config_path = config_path
        self._lock = RLock()
        self._config = self._load()

    def _load(self) -> AppConfig:
        if not self._config_path.exists():
            return AppConfig()

        try:
            raw = json.loads(self._config_path.read_text(encoding="utf-8"))
        except Exception as err:  # pragma: no cover
            LOGGER.warning("Could not read config file: %s", err)
            return AppConfig()

        stations = [
            StationConfig(
                provider=str(item.get("provider", "")).strip(),
                station_id=str(item.get("station_id", "")).strip(),
                name=(str(item["name"]).strip() if item.get("name") else None),
                keys=[str(k).strip() for k in item.get("keys", []) if str(k).strip()] or None,
                user_agent=(
                    str(item["user_agent"]).strip()
                    if item.get("user_agent")
                    else None
                ),
            )
            for item in raw.get("stations", [])
            if str(item.get("provider", "")).strip() and str(item.get("station_id", "")).strip()
        ]

        refresh_interval_seconds = int(raw.get("refresh_interval_seconds", 300))
        if refresh_interval_seconds < 10:
            refresh_interval_seconds = 10

        return AppConfig(
            refresh_interval_seconds=refresh_interval_seconds,
            stations=stations,
        )

    def _save(self) -> None:
        self._config_path.parent.mkdir(parents=True, exist_ok=True)
        payload = {
            "refresh_interval_seconds": self._config.refresh_interval_seconds,
            "stations": [asdict(station) for station in self._config.stations],
        }
        self._config_path.write_text(
            json.dumps(payload, indent=2, sort_keys=True),
            encoding="utf-8",
        )

    def get(self) -> AppConfig:
        with self._lock:
            return AppConfig(
                refresh_interval_seconds=self._config.refresh_interval_seconds,
                stations=[StationConfig(**asdict(station)) for station in self._config.stations],
            )

    def replace(self, payload: dict[str, Any]) -> AppConfig:
        stations_payload = payload.get("stations", [])
        stations: list[StationConfig] = []
        for entry in stations_payload:
            provider = str(entry.get("provider", "")).strip()
            station_id = str(entry.get("station_id", "")).strip()
            if not provider or not station_id:
                continue
            stations.append(
                StationConfig(
                    provider=provider,
                    station_id=station_id,
                    name=(str(entry["name"]).strip() if entry.get("name") else None),
                    keys=[str(k).strip() for k in entry.get("keys", []) if str(k).strip()] or None,
                    user_agent=(
                        str(entry["user_agent"]).strip()
                        if entry.get("user_agent")
                        else None
                    ),
                )
            )

        refresh_interval_seconds = int(payload.get("refresh_interval_seconds", 300))
        refresh_interval_seconds = max(10, min(3600, refresh_interval_seconds))

        with self._lock:
            self._config = AppConfig(
                refresh_interval_seconds=refresh_interval_seconds,
                stations=stations,
            )
            self._save()
            return self.get()


def build_price_map(config: AppConfig) -> list[dict[str, Any]]:
    stations_payload: list[dict[str, Any]] = []

    for station in config.stations:
        request_obj = FuelStationRequest(
            provider=station.provider,
            station_id=station.station_id,
            keys=tuple(station.keys) if station.keys else None,
            user_agent=station.user_agent,
        )

        price_map = get_fuel_prices(request_obj).to_price_map(
            keys=tuple(station.keys) if station.keys else None
        )

        stations_payload.append(
            {
                "provider": station.provider,
                "station_id": station.station_id,
                "name": station.name or f"{station.provider.upper()} {station.station_id}",
                "prices": {
                    fuel_type: float(price) for fuel_type, price in price_map.items()
                },
            }
        )

    return stations_payload


app = Flask(__name__, static_folder="static")
store = ConfigStore(CONFIG_FILE)


@app.route("/")
def index() -> Any:
    return send_from_directory(app.static_folder, "index.html")


@app.route("/static/<path:path>")
def static_proxy(path: str) -> Any:
    return send_from_directory(app.static_folder, path)


@app.get("/api/v1/config")
def get_config() -> Any:
    config = store.get()
    return jsonify(
        {
            "refresh_interval_seconds": config.refresh_interval_seconds,
            "stations": [asdict(station) for station in config.stations],
        }
    )


@app.put("/api/v1/config")
def put_config() -> Any:
    payload = request.get_json(silent=True) or {}
    config = store.replace(payload)
    return jsonify(
        {
            "refresh_interval_seconds": config.refresh_interval_seconds,
            "stations": [asdict(station) for station in config.stations],
        }
    )


@app.get("/api/v1/price-map")
def get_price_map() -> Any:
    config = store.get()

    try:
        stations = build_price_map(config)
    except Exception as err:
        LOGGER.exception("Failed to build price map")
        return jsonify({"error": str(err)}), 502

    return jsonify(
        {
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "refresh_interval_seconds": config.refresh_interval_seconds,
            "stations": stations,
        }
    )


if __name__ == "__main__":
    app.run(host=HOST, port=PORT)
