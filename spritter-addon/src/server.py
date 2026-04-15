from __future__ import annotations

import json
import logging
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from fastapi import FastAPI, HTTPException, Query
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

    def _load(self) -> AppConfig:
        if not self._config_path.exists():
            return AppConfig()

        try:
            raw = json.loads(self._config_path.read_text(encoding="utf-8"))
        except Exception as err:  # pragma: no cover
            LOGGER.warning("Could not read config file: %s", err)
            return AppConfig()

        if not isinstance(raw, dict):
            LOGGER.warning("Config file must contain a JSON object")
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
        refresh_interval_seconds = max(10, min(3600, refresh_interval_seconds))

        return AppConfig(
            refresh_interval_seconds=refresh_interval_seconds,
            stations=stations,
        )

    def get(self) -> AppConfig:
        return self._load()


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


def find_station_config(
    config: AppConfig, provider: str, station_id: str
) -> StationConfig | None:
    provider_key = provider.strip().lower()
    station_key = station_id.strip()

    for station in config.stations:
        if (
            station.provider.strip().lower() == provider_key
            and station.station_id.strip() == station_key
        ):
            return station

    return None


def build_station_payload(
    provider: str,
    station_id: str,
    station_config: StationConfig | None,
) -> dict[str, Any]:
    request_obj = FuelStationRequest(
        provider=provider,
        station_id=station_id,
        keys=tuple(station_config.keys) if station_config and station_config.keys else None,
        user_agent=station_config.user_agent if station_config else None,
    )

    price_map = get_fuel_prices(request_obj).to_price_map(
        keys=tuple(station_config.keys) if station_config and station_config.keys else None
    )

    return {
        "provider": provider,
        "station_id": station_id,
        "name": (
            station_config.name
            if station_config and station_config.name
            else f"{provider.upper()} {station_id}"
        ),
        "prices": {fuel_type: float(price) for fuel_type, price in price_map.items()},
    }


app = FastAPI(title="Spritter Add-On")
store = ConfigStore(CONFIG_FILE)


@app.get("/")
def root() -> dict[str, str]:
    return {"status": "ok", "service": "spritter-addon"}


@app.get("/prices/")
def get_prices(
    provider: str = Query(..., min_length=1),
    station_id: str = Query(..., alias="id", min_length=1),
) -> dict[str, Any]:
    config = store.get()
    station_cfg = find_station_config(config, provider=provider, station_id=station_id)

    try:
        station = build_station_payload(
            provider=provider,
            station_id=station_id,
            station_config=station_cfg,
        )
    except Exception as err:
        LOGGER.exception("Failed to build station prices")
        raise HTTPException(status_code=502, detail=str(err))

    return {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "refresh_interval_seconds": config.refresh_interval_seconds,
        "station": station,
    }


if __name__ == "__main__":
    import uvicorn

    uvicorn.run("server:app", host=HOST, port=PORT)
