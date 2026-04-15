from __future__ import annotations

import asyncio
import json
import logging
import os
import signal
import threading
from contextlib import suppress
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import paho.mqtt.client as mqtt
from spritter import FuelStationRequest, get_fuel_prices

LOGGER = logging.getLogger("spritter_addon")
logging.basicConfig(level=logging.INFO)

DATA_DIR = Path("/data")
CONFIG_FILE = DATA_DIR / "options.json"
DEFAULT_MAX_PARALLELISM = 6


@dataclass(slots=True)
class StationConfig:
    provider: str
    station_id: str
    name: str | None = None
    keys: list[str] | None = None


@dataclass(slots=True)
class MqttConfig:
    host: str
    port: int = 1883
    username: str | None = None
    password: str | None = None
    topic_prefix: str = "spritter/stations"
    client_id: str = "spritter-addon"
    qos: int = 0
    retain: bool = False


@dataclass(slots=True)
class AppConfig:
    refresh_interval_minutes: int = 5
    max_parallelism: int = DEFAULT_MAX_PARALLELISM
    mqtt: MqttConfig = field(default_factory=lambda: MqttConfig(host="core-mosquitto"))
    stations: list[StationConfig] = field(default_factory=list)


def _clamp(value: int, lower: int, upper: int) -> int:
    return max(lower, min(upper, value))


def _to_int(value: Any, default: int) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


class ConfigStore:
    def __init__(self, config_path: Path) -> None:
        self._config_path = config_path

    def _build_mqtt_config(self) -> MqttConfig:
        host = str(os.getenv("MQTT_HOST") or "core-mosquitto").strip()
        port = _clamp(
            _to_int(os.getenv("MQTT_PORT", 1883), 1883),
            1,
            65535,
        )
        username = str(os.getenv("MQTT_USERNAME") or os.getenv("MQTT_USER") or "").strip() or None
        password = os.getenv("MQTT_PASSWORD") or None

        return MqttConfig(
            host=host,
            port=port,
            username=username,
            password=password,
        )

    def _load(self) -> AppConfig:
        if not self._config_path.exists():
            LOGGER.warning("Config file %s does not exist", self._config_path)
            return AppConfig(mqtt=self._build_mqtt_config())

        try:
            raw = json.loads(self._config_path.read_text(encoding="utf-8"))
        except Exception as err:  # pragma: no cover
            LOGGER.warning("Could not read config file: %s", err)
            return AppConfig(mqtt=self._build_mqtt_config())

        if not isinstance(raw, dict):
            LOGGER.warning("Config file must contain a JSON object")
            return AppConfig(mqtt=self._build_mqtt_config())

        stations = [
            StationConfig(
                provider=str(item.get("provider", "")).strip(),
                station_id=str(item.get("station_id", "")).strip(),
                name=(str(item["name"]).strip() if item.get("name") else None),
                keys=[str(k).strip() for k in item.get("keys", []) if str(k).strip()] or None,
            )
            for item in raw.get("stations", [])
            if str(item.get("provider", "")).strip() and str(item.get("station_id", "")).strip()
        ]

        refresh_interval_minutes = _clamp(_to_int(raw.get("refresh_interval_minutes"), 5), 1, 10080)
        max_parallelism = _clamp(_to_int(raw.get("max_parallelism"), DEFAULT_MAX_PARALLELISM), 1, 32)

        return AppConfig(
            refresh_interval_minutes=refresh_interval_minutes,
            max_parallelism=max_parallelism,
            mqtt=self._build_mqtt_config(),
            stations=stations,
        )

    def get(self) -> AppConfig:
        return self._load()


def build_station_payload(station: StationConfig) -> dict[str, Any]:
    request_obj = FuelStationRequest(
        provider=station.provider,
        station_id=station.station_id,
        keys=tuple(station.keys) if station.keys else None,
    )

    price_map = get_fuel_prices(request_obj).to_price_map(
        keys=tuple(station.keys) if station.keys else None
    )

    return {
        "provider": station.provider,
        "station_id": station.station_id,
        "name": station.name or f"{station.provider.upper()} {station.station_id}",
        "prices": {fuel_type: float(price) for fuel_type, price in price_map.items()},
    }


async def fetch_station_payload(station: StationConfig, semaphore: asyncio.Semaphore) -> dict[str, Any]:
    async with semaphore:
        return await asyncio.to_thread(build_station_payload, station)


async def collect_station_payloads(config: AppConfig) -> list[dict[str, Any]]:
    semaphore = asyncio.Semaphore(config.max_parallelism)
    tasks = [asyncio.create_task(fetch_station_payload(station, semaphore)) for station in config.stations]
    results = await asyncio.gather(*tasks, return_exceptions=True)

    payloads: list[dict[str, Any]] = []
    for station, result in zip(config.stations, results, strict=True):
        if isinstance(result, Exception):
            LOGGER.exception(
                "Failed fetching station %s/%s",
                station.provider,
                station.station_id,
                exc_info=result,
            )
            continue
        payloads.append(result)

    return payloads


def publish_station_payloads(
    mqtt_config: MqttConfig,
    generated_at: str,
    refresh_interval_minutes: int,
    stations: list[dict[str, Any]],
) -> None:
    client = mqtt.Client(
        callback_api_version=mqtt.CallbackAPIVersion.VERSION2,
        client_id=mqtt_config.client_id,
    )
    if mqtt_config.username:
        client.username_pw_set(mqtt_config.username, mqtt_config.password)

    connected = threading.Event()
    connect_error: list[str | None] = [None]

    def on_connect(client: mqtt.Client, userdata: Any, flags: Any, reason_code: Any, properties: Any) -> None:
        if getattr(reason_code, "is_failure", False):
            connect_error[0] = f"{reason_code}"
        connected.set()

    client.on_connect = on_connect

    client.connect(mqtt_config.host, mqtt_config.port, keepalive=60)
    client.loop_start()
    try:
        if not connected.wait(timeout=10):
            raise TimeoutError(f"Timed out waiting for MQTT connection to {mqtt_config.host}:{mqtt_config.port}")

        if connect_error[0]:
            raise RuntimeError(f"MQTT connection failed: {connect_error[0]}")

        for station in stations:
            provider = station["provider"]
            station_id = station["station_id"]
            topic = f"{mqtt_config.topic_prefix}/{provider}/{station_id}"

            # Publish Auto-Discovery configs so Home Assistant can create entities per fuel type.
            for fuel_type in station["prices"].keys():
                safe_id = station_id.replace(".", "_").replace("-", "_")
                node_id = f"spritter_{provider}_{safe_id}"
                
                # Create a safe string without spaces for IDs and Topics
                safe_fuel = fuel_type.replace(" ", "_")

                config_topic = f"homeassistant/sensor/{node_id}/{safe_fuel}/config"
                config_payload = {
                    "name": fuel_type.capitalize(),
                    "object_id": f"{node_id}_{safe_fuel}",
                    "unique_id": f"{node_id}_{safe_fuel}",
                    "state_topic": topic,
                    # Fix Jinja2 template to use bracket notation
                    "value_template": f"{{{{ value_json.station.prices['{fuel_type}'] }}}}",
                    "unit_of_measurement": "€",
                    "device_class": "monetary",
                    "state_class": "measurement",
                    "icon": "mdi:gas-station",
                    "device": {
                        "identifiers": [node_id],
                        "name": station["name"],
                        "manufacturer": "Spritter",
                        "model": f"{provider} ({station_id})",
                    },
                }
                client.publish(config_topic, json.dumps(config_payload), qos=1, retain=True)

            payload = {
                "generated_at": generated_at,
                "refresh_interval_minutes": refresh_interval_minutes,
                "station": station,
            }
            LOGGER.info(
                "Publishing station %s/%s to %s with payload %s",
                provider,
                station_id,
                topic,
                json.dumps(payload, separators=(",", ":")),
            )
            message = json.dumps(payload, separators=(",", ":"))
            publish_result = client.publish(topic, message, qos=mqtt_config.qos, retain=mqtt_config.retain)
            publish_result.wait_for_publish()

        summary_topic = f"{mqtt_config.topic_prefix}/_summary"
        summary_payload = {
            "generated_at": generated_at,
            "refresh_interval_minutes": refresh_interval_minutes,
            "published_stations": len(stations),
        }
        summary_message = json.dumps(summary_payload, separators=(",", ":"))
        client.publish(summary_topic, summary_message, qos=mqtt_config.qos, retain=mqtt_config.retain).wait_for_publish()
    finally:
        client.disconnect()
        client.loop_stop()


async def run() -> None:
    store = ConfigStore(CONFIG_FILE)

    while True:
        config = store.get()
        generated_at = datetime.now(timezone.utc).isoformat()

        if not config.stations:
            LOGGER.warning("No stations configured, waiting for next cycle")
        else:
            station_payloads = await collect_station_payloads(config)
            if station_payloads:
                try:
                    await asyncio.to_thread(
                        publish_station_payloads,
                        config.mqtt,
                        generated_at,
                        config.refresh_interval_minutes,
                        station_payloads,
                    )
                    LOGGER.info("Published %s station payloads", len(station_payloads))
                except Exception:
                    LOGGER.exception("Failed to publish payloads to MQTT")
            else:
                LOGGER.warning("No station payloads fetched successfully in this cycle")

        await asyncio.sleep(config.refresh_interval_minutes * 60)


async def main() -> None:
    loop = asyncio.get_running_loop()
    stop_event = asyncio.Event()

    for sig in (signal.SIGINT, signal.SIGTERM):
        loop.add_signal_handler(sig, stop_event.set)

    task = asyncio.create_task(run())

    await stop_event.wait()
    LOGGER.info("Received stop signal, shutting down cleanly...")

    task.cancel()
    with suppress(asyncio.CancelledError):
        await task


if __name__ == "__main__":
    asyncio.run(main())
